"""Risk summaries and throw/reversal helpers for adjustment pages."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from core.database import SessionLocal
from domain.color_rules import FIVE_ELEMENT_NUMBERS, WAVE_NUMBERS, get_five_element, get_half_wave, get_wave_color
from domain.number_rules import (
    composite_odd_even_label,
    composite_size_label,
    head_number,
    normalize_number,
    odd_even_label,
    size_label,
    tail_number,
)
from domain.zodiac_rules import get_zodiac
from domain.zodiac_config import get_default_zodiac_year, get_zodiac_number_map, validate_zodiac_year
from models import Order
from repositories.settings_repository import SettingsRepository
from settlement.bet_normalizer import (
    SPECIAL_COLOR,
    SPECIAL_ELEMENT,
    SPECIAL_HALF_WAVE,
    SPECIAL_HEAD,
    SPECIAL_NUMBER,
    SPECIAL_PARITY,
    SPECIAL_SIZE,
    SPECIAL_SUM_PARITY,
    SPECIAL_SUM_SIZE,
    SPECIAL_TAIL,
    SPECIAL_ZODIAC,
    SPECIAL_ZODIAC_GROUP,
    BetTypeNormalizer,
)
from services.adjustment_record_service import AdjustmentRecordService

CENT = Decimal("0.01")
SPECIAL_ADJUSTMENT_TYPES = {"special_throw", "special_throw_reversal"}
LIANXIAO_ADJUSTMENT_TYPES = {"lianxiao_throw", "lianxiao_throw_reversal"}
THROW_TYPES = {"special_throw", "lianxiao_throw"}
REVERSAL_TYPES = {"special_throw_reversal", "lianxiao_throw_reversal"}
EXCLUDED_ORDER_STATUSES = {"voided", "void"}
SPECIAL_SCOPE_TYPES = {
    SPECIAL_NUMBER,
    SPECIAL_ZODIAC,
    SPECIAL_COLOR,
    SPECIAL_HALF_WAVE,
    SPECIAL_SIZE,
    SPECIAL_PARITY,
    SPECIAL_TAIL,
    SPECIAL_HEAD,
    SPECIAL_SUM_PARITY,
    SPECIAL_SUM_SIZE,
    SPECIAL_ELEMENT,
    SPECIAL_ZODIAC_GROUP,
}
SPECIAL_ODDS_CANDIDATES: dict[str, tuple[str, ...]] = {
    SPECIAL_NUMBER: ("特码号码", "特码", "号码", "特号", "单号投注", "纯数字"),
    SPECIAL_ZODIAC: ("特码生肖", "生肖", "平特一肖", "一肖"),
    SPECIAL_COLOR: ("波色", "特码波色", "色波"),
    SPECIAL_HALF_WAVE: ("半波", "包半波", "特码半波"),
    SPECIAL_SIZE: ("大小", "特码大小", "特码两面"),
    SPECIAL_PARITY: ("单双", "特码单双", "特码两面"),
    SPECIAL_TAIL: ("尾数", "特码尾数"),
    SPECIAL_HEAD: ("头数", "特码头数"),
    SPECIAL_SUM_PARITY: ("合数", "合数单双", "特码合数单双"),
    SPECIAL_SUM_SIZE: ("合数", "合数大小", "特码合数大小"),
    SPECIAL_ELEMENT: ("五行", "特码五行"),
    SPECIAL_ZODIAC_GROUP: ("连肖", "多生肖", "生肖"),
}
LIANXIAO_ALIASES = {"连肖", "多生肖"}
ZODIAC_ORDER = tuple(get_zodiac_number_map(get_default_zodiac_year()).keys())
ZODIAC_RANK = {zodiac: index for index, zodiac in enumerate(ZODIAC_ORDER)}


@dataclass(frozen=True, slots=True)
class SpecialRiskRow:
    number: str
    zodiac: str
    raw_stake_amount: Decimal
    potential_payout_amount: Decimal
    rebate_amount: Decimal
    risk_amount: Decimal
    thrown_amount: Decimal
    adjusted_risk_amount: Decimal
    note: str = ""


@dataclass(frozen=True, slots=True)
class LianxiaoRiskRow:
    zodiac_group: str
    raw_amount: Decimal
    potential_payout_amount: Decimal
    rebate_amount: Decimal
    risk_amount: Decimal
    thrown_amount: Decimal
    adjusted_risk_amount: Decimal
    order_count: int
    note: str = ""


@dataclass(frozen=True, slots=True)
class ThrowEntry:
    amount: Decimal
    source_expression: str
    number: str | None = None
    zodiac_group: str | None = None


class RiskAdjustmentService:
    """Service used by the adjustment UI; it never mutates orders or balances."""

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal, *, zodiac_year: int | None = None):
        self._session_factory = session_factory
        self.set_zodiac_year(zodiac_year or get_default_zodiac_year())
        self._adjustment_records = AdjustmentRecordService(session_factory)

    def set_zodiac_year(self, zodiac_year: int) -> None:
        self._zodiac_year = validate_zodiac_year(zodiac_year)
        self._zodiac_map = get_zodiac_number_map(self._zodiac_year)
        self._zodiac_order = tuple(self._zodiac_map.keys())
        self._zodiac_rank = {zodiac: index for index, zodiac in enumerate(self._zodiac_order)}
        self._normalizer = BetTypeNormalizer(zodiac_year=self._zodiac_year)

    def build_special_risk_table(self, *, region: str | None = None) -> list[SpecialRiskRow]:
        aggregates = {
            f"{number:02d}": {
                "raw": Decimal("0"),
                "payout": Decimal("0"),
                "rebate": Decimal("0"),
                "notes": set(),
            }
            for number in range(1, 50)
        }
        with self._session_factory() as session:
            for order in self._iter_orders(session, region=region, zodiac_year=self._zodiac_year):
                plan_items = self._plan_items_for_order(session, order)
                for item in order.items:
                    if item.bet_type == "连肖":
                        continue
                    try:
                        normalized = self._normalizer.normalize(item.bet_type, item.selection, note=item.note)
                    except Exception as exc:
                        continue
                    if normalized.normalized_bet_type not in SPECIAL_SCOPE_TYPES:
                        continue
                    try:
                        numbers = self._numbers_for_normalized(normalized.normalized_bet_type, normalized.selection)
                    except Exception as exc:
                        for bucket in aggregates.values():
                            bucket["notes"].add(f"{item.bet_type}/{item.selection} 未纳入：{exc}")
                        continue
                    amount = Decimal(item.amount)
                    odds_item = self._find_odds_item(
                        normalized.normalized_bet_type,
                        item.bet_type,
                        plan_items,
                    )
                    odds = Decimal(odds_item.odds) if odds_item is not None else None
                    rebate_item = self._find_rebate_item(item.bet_type, plan_items, normalized.normalized_bet_type)
                    rebate_rate = (Decimal(rebate_item.rebate) / Decimal("100")) if rebate_item is not None else Decimal("0")
                    if odds is None:
                        note = "未配置赔率"
                    else:
                        note = ""
                    for number in numbers:
                        bucket = aggregates[number]
                        bucket["raw"] += amount
                        if odds is not None:
                            bucket["payout"] += amount * odds
                        bucket["rebate"] += amount * rebate_rate
                        if note:
                            bucket["notes"].add(note)
            thrown = self._active_special_thrown_amounts(session, region=region)

        rows: list[SpecialRiskRow] = []
        for number in range(1, 50):
            key = f"{number:02d}"
            raw = _money_decimal(aggregates[key]["raw"])
            payout = _money_decimal(aggregates[key]["payout"])
            rebate = _money_decimal(aggregates[key]["rebate"])
            risk = _money_decimal(payout + rebate - raw)
            thrown_amount = _money_decimal(thrown.get(key, Decimal("0")))
            rows.append(
                SpecialRiskRow(
                    number=key,
                    zodiac=get_zodiac(key, year=self._zodiac_year),
                    raw_stake_amount=raw,
                    potential_payout_amount=payout,
                    rebate_amount=rebate,
                    risk_amount=risk,
                    thrown_amount=thrown_amount,
                    adjusted_risk_amount=_money_decimal(risk - thrown_amount),
                    note="；".join(sorted(aggregates[key]["notes"])),
                )
            )
        return rows

    def build_lianxiao_risk_table(self, *, region: str | None = None) -> list[LianxiaoRiskRow]:
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "raw": Decimal("0"),
                "payout": Decimal("0"),
                "rebate": Decimal("0"),
                "order_ids": set(),
                "notes": set(),
            }
        )
        with self._session_factory() as session:
            for order in self._iter_orders(session, region=region, zodiac_year=self._zodiac_year):
                plan_items = self._plan_items_for_order(session, order)
                for item in order.items:
                    try:
                        normalized = self._normalizer.normalize(item.bet_type, item.selection, note=item.note)
                    except Exception:
                        continue
                    if normalized.normalized_bet_type != SPECIAL_ZODIAC_GROUP or item.bet_type not in LIANXIAO_ALIASES:
                        continue
                    key = self._stable_zodiac_group(normalized.selection.split(","))
                    bucket = grouped[key]
                    amount = Decimal(item.amount)
                    bucket["raw"] += amount
                    bucket["order_ids"].add(order.id)
                    odds_item = self._find_odds_item(SPECIAL_ZODIAC_GROUP, item.bet_type, plan_items)
                    if odds_item is None:
                        bucket["notes"].add("未配置赔率")
                    else:
                        bucket["payout"] += amount * Decimal(odds_item.odds)
                    rebate_item = self._find_rebate_item(item.bet_type, plan_items, SPECIAL_ZODIAC_GROUP)
                    if rebate_item is not None:
                        bucket["rebate"] += amount * (Decimal(rebate_item.rebate) / Decimal("100"))
            thrown = self._active_lianxiao_thrown_amounts(session, region=region)

        rows: list[LianxiaoRiskRow] = []
        for key, bucket in sorted(grouped.items(), key=lambda item: (-item[1]["raw"], item[0])):
            raw = _money_decimal(bucket["raw"])
            payout = _money_decimal(bucket["payout"])
            rebate = _money_decimal(bucket["rebate"])
            risk = _money_decimal(payout + rebate - raw)
            thrown_amount = _money_decimal(thrown.get(key, Decimal("0")))
            rows.append(
                LianxiaoRiskRow(
                    zodiac_group=key,
                    raw_amount=raw,
                    potential_payout_amount=payout,
                    rebate_amount=rebate,
                    risk_amount=risk,
                    thrown_amount=thrown_amount,
                    adjusted_risk_amount=_money_decimal(risk - thrown_amount),
                    order_count=len(bucket["order_ids"]),
                    note="；".join(sorted(bucket["notes"])),
                )
            )
        return rows

    def generate_special_throw_suggestions(
        self,
        rows: Iterable[SpecialRiskRow],
        max_loss: Decimal | str,
    ) -> str:
        max_loss_value = _positive_or_zero_decimal(max_loss, "最大亏损")
        lines = []
        for row in rows:
            if row.adjusted_risk_amount > max_loss_value:
                lines.append(f"{row.number}={_money(row.adjusted_risk_amount - max_loss_value)}")
        return "\n".join(lines)

    def parse_special_throw_text(self, text: str) -> list[ThrowEntry]:
        grouped: dict[str, dict[str, Any]] = {}
        for expression, amount in self._split_throw_expressions(text):
            numbers = self._expand_special_expression(expression)
            for number in numbers:
                entry = grouped.setdefault(number, {"amount": Decimal("0"), "sources": []})
                entry["amount"] += amount
                entry["sources"].append(expression)
        return [
            ThrowEntry(
                number=number,
                amount=_money_decimal(data["amount"]),
                source_expression=",".join(dict.fromkeys(data["sources"])),
            )
            for number, data in sorted(grouped.items())
        ]

    def parse_lianxiao_throw_text(self, text: str) -> list[ThrowEntry]:
        grouped: dict[str, dict[str, Any]] = {}
        for expression, amount in self._split_throw_expressions(text):
            group = self._parse_lianxiao_group(expression)
            entry = grouped.setdefault(group, {"amount": Decimal("0"), "sources": []})
            entry["amount"] += amount
            entry["sources"].append(expression)
        return [
            ThrowEntry(
                zodiac_group=group,
                amount=_money_decimal(data["amount"]),
                source_expression=",".join(dict.fromkeys(data["sources"])),
            )
            for group, data in sorted(grouped.items(), key=lambda item: self._zodiac_group_sort_key(item[0]))
        ]

    def apply_special_adjustments(
        self,
        adjustments: dict[str, Decimal],
        *,
        region: str,
        reason: str = "特码调单",
        operator: str = "系统操作员",
    ):
        """Validate page adjustments and persist them as reversible special throw records."""

        clean: dict[str, Decimal] = {}
        for number, amount in adjustments.items():
            normalized = normalize_number(str(number))
            clean[normalized] = _money_decimal(clean.get(normalized, Decimal("0")) + _positive_decimal(amount, "调整金额"))
        if not clean:
            raise ValueError("调整内容不能为空")

        rows = {row.number: row for row in self.build_special_risk_table(region=None if region == "全部" else region)}
        entries: list[ThrowEntry] = []
        for number, amount in sorted(clean.items()):
            row = rows.get(number)
            if row is None:
                raise ValueError(f"号码不存在于当前汇总：{number}")
            available = _money_decimal(row.raw_stake_amount - row.thrown_amount)
            if available <= 0:
                raise ValueError(f"{number} 当前没有可调整金额")
            if amount > available:
                raise ValueError(f"{number} 调整金额不能超过当前可调整金额 {available:.2f}")
            entries.append(ThrowEntry(number=number, amount=amount, source_expression=number))
        return self.apply_special_throw(entries, region=region, reason=reason, operator=operator)

    def apply_lianxiao_adjustments(
        self,
        adjustments: dict[str, Decimal],
        *,
        region: str,
        reason: str = "连肖调单",
        operator: str = "系统操作员",
    ):
        """Validate page adjustments and persist them as reversible lianxiao throw records."""

        clean: dict[str, dict[str, Any]] = {}
        for group, amount in adjustments.items():
            stable_group = self._parse_lianxiao_group(str(group))
            entry = clean.setdefault(stable_group, {"amount": Decimal("0"), "sources": []})
            entry["amount"] += _positive_decimal(amount, "调整金额")
            entry["sources"].append(str(group))
        if not clean:
            raise ValueError("调整内容不能为空")

        rows = {row.zodiac_group: row for row in self.build_lianxiao_risk_table(region=None if region == "全部" else region)}
        entries: list[ThrowEntry] = []
        for group, data in sorted(clean.items(), key=lambda item: self._zodiac_group_sort_key(item[0])):
            row = rows.get(group)
            if row is None:
                raise ValueError(f"生肖组合不存在于当前汇总：{group.replace(',', '')}")
            amount = _money_decimal(data["amount"])
            available = _money_decimal(row.raw_amount - row.thrown_amount)
            if available <= 0:
                raise ValueError(f"{group.replace(',', '')} 当前没有可调整金额")
            if amount > available:
                raise ValueError(f"{group.replace(',', '')} 调整金额不能超过当前组合金额 {available:.2f}")
            entries.append(
                ThrowEntry(
                    zodiac_group=group,
                    amount=amount,
                    source_expression=",".join(dict.fromkeys(data["sources"])),
                )
            )
        return self.apply_lianxiao_throw(entries, region=region, reason=reason, operator=operator)

    def apply_special_throw(
        self,
        entries: list[ThrowEntry],
        *,
        region: str,
        reason: str,
        operator: str = "系统操作员",
    ):
        if not entries:
            raise ValueError("没有可保存的特码抛出明细")
        reason = _require_text(reason, "原因")
        before_rows = self.build_special_risk_table(region=None if region == "全部" else region)
        before_by_number = {row.number: row for row in before_rows}
        throw_by_number = {entry.number or "": entry.amount for entry in entries}
        after_snapshot = []
        before_snapshot = []
        for entry in entries:
            if not entry.number:
                raise ValueError("特码抛出明细缺少号码")
            row = before_by_number.get(entry.number)
            if row is None:
                continue
            before_snapshot.append(_special_row_snapshot(row))
            after_snapshot.append(
                {
                    **_special_row_snapshot(row),
                    "new_thrown_amount": _money(row.thrown_amount + entry.amount),
                    "new_adjusted_risk_amount": _money(row.adjusted_risk_amount - entry.amount),
                }
            )
        total = sum((entry.amount for entry in entries), Decimal("0"))
        return self._adjustment_records.create_record_with_action(
            adjustment_type="special_throw",
            region=region,
            source_filter={"region": region, "zodiac_year": self._zodiac_year},
            original_total=_money(sum((row.risk_amount for row in before_rows), Decimal("0"))),
            adjustment_total=_money(total),
            after_total=_money(sum((row.adjusted_risk_amount for row in before_rows), Decimal("0")) - total),
            item_count=len(entries),
            positive_count=len(entries),
            negative_count=0,
            record_snapshot={
                "action": "throw",
                "entries": [_throw_entry_snapshot(entry) for entry in entries],
                "total_throw_amount": _money(total),
                "before_risk_snapshot": before_snapshot,
                "after_risk_snapshot": after_snapshot,
                "reason": reason,
                "operator": operator,
            },
            summary_snapshot={
                "risk_formula": "risk_amount = potential_payout_amount + rebate_amount - raw_stake_amount",
                "adjusted_formula": "adjusted_risk_amount = risk_amount - thrown_amount",
            },
            note=f"特码抛出：{reason}",
            action="adjustment/special_throw",
            operator=operator,
        )

    def apply_lianxiao_throw(
        self,
        entries: list[ThrowEntry],
        *,
        region: str,
        reason: str,
        operator: str = "系统操作员",
    ):
        if not entries:
            raise ValueError("没有可保存的连肖抛出明细")
        reason = _require_text(reason, "原因")
        before_rows = self.build_lianxiao_risk_table(region=None if region == "全部" else region)
        before_by_group = {row.zodiac_group: row for row in before_rows}
        before_snapshot = []
        after_snapshot = []
        for entry in entries:
            if not entry.zodiac_group:
                raise ValueError("连肖抛出明细缺少生肖组合")
            row = before_by_group.get(entry.zodiac_group)
            if row is not None:
                before_snapshot.append(_lianxiao_row_snapshot(row))
                after_snapshot.append(
                    {
                        **_lianxiao_row_snapshot(row),
                        "new_thrown_amount": _money(row.thrown_amount + entry.amount),
                        "new_adjusted_risk_amount": _money(row.adjusted_risk_amount - entry.amount),
                    }
                )
        total = sum((entry.amount for entry in entries), Decimal("0"))
        return self._adjustment_records.create_record_with_action(
            adjustment_type="lianxiao_throw",
            region=region,
            source_filter={"region": region, "zodiac_year": self._zodiac_year},
            original_total=_money(sum((row.risk_amount for row in before_rows), Decimal("0"))),
            adjustment_total=_money(total),
            after_total=_money(sum((row.adjusted_risk_amount for row in before_rows), Decimal("0")) - total),
            item_count=len(entries),
            positive_count=len(entries),
            negative_count=0,
            record_snapshot={
                "action": "throw",
                "entries": [_throw_entry_snapshot(entry) for entry in entries],
                "total_throw_amount": _money(total),
                "before_risk_snapshot": before_snapshot,
                "after_risk_snapshot": after_snapshot,
                "reason": reason,
                "operator": operator,
            },
            summary_snapshot={
                "risk_formula": "risk_amount = potential_payout_amount + rebate_amount - raw_amount",
                "adjusted_formula": "adjusted_risk_amount = risk_amount - thrown_amount",
            },
            note=f"连肖抛出：{reason}",
            action="adjustment/lianxiao_throw",
            operator=operator,
        )

    def reverse_record(
        self,
        record_id: int,
        *,
        reason: str,
        operator: str = "系统操作员",
    ):
        reason = _require_text(reason, "原因")
        record = self._adjustment_records.get_record(record_id)
        if record is None:
            raise ValueError("调整记录不存在")
        if record.adjustment_type not in THROW_TYPES:
            raise ValueError("只能撤销 active 的抛出记录")
        if self._is_record_reversed(record.id):
            raise ValueError("该抛出记录已撤销，不能重复撤销")
        reversal_type = f"{record.adjustment_type}_reversal"
        entries = record.record_snapshot.get("entries", []) if isinstance(record.record_snapshot, dict) else []
        total = _to_decimal(record.adjustment_total)
        return self._adjustment_records.create_record_with_action(
            adjustment_type=reversal_type,
            region=record.region,
            source_filter=record.source_filter,
            original_total=record.after_total,
            adjustment_total=_money(-total),
            after_total=record.original_total,
            item_count=record.item_count,
            positive_count=0,
            negative_count=record.item_count,
            record_snapshot={
                "action": "reversal",
                "reversed_record_id": record.id,
                "entries": entries,
                "total_throw_amount": _money(-total),
                "reason": reason,
                "operator": operator,
            },
            summary_snapshot={
                "reversal_of": record.id,
                "original_adjustment_type": record.adjustment_type,
            },
            note=f"撤销调单记录 {record.id}：{reason}",
            action=f"adjustment/{reversal_type}",
            operator=operator,
        )

    def record_status(self, record_id: int, adjustment_type: str, record_snapshot: dict[str, Any]) -> str:
        if adjustment_type in REVERSAL_TYPES:
            return "reversal"
        if adjustment_type in THROW_TYPES:
            return "reversed" if self._is_record_reversed(record_id) else "active"
        action = record_snapshot.get("action") if isinstance(record_snapshot, dict) else None
        if action == "reversal":
            return "reversal"
        return "legacy"

    def can_reverse(self, record_id: int, adjustment_type: str) -> bool:
        return adjustment_type in THROW_TYPES and not self._is_record_reversed(record_id)

    def _iter_orders(self, session: Session, *, region: str | None = None, zodiac_year: int | None = None) -> list[Order]:
        stmt = select(Order).options(selectinload(Order.items))
        if region:
            stmt = stmt.where(Order.region == region)
        stmt = stmt.where(Order.status.not_in(EXCLUDED_ORDER_STATUSES))
        try:
            orders = list(session.scalars(stmt))
        except OperationalError as exc:
            if "zodiac_year" not in str(exc):
                raise
            session.rollback()
            return []
        if zodiac_year is None:
            return orders
        selected_year = validate_zodiac_year(zodiac_year)
        default_year = get_default_zodiac_year()
        return [
            order
            for order in orders
            if validate_zodiac_year(order.zodiac_year or default_year) == selected_year
        ]

    def _plan_items_for_order(self, session: Session, order: Order) -> list[Any]:
        repo = SettingsRepository(session)
        customer_name = (order.customer_name or "").strip()
        if customer_name:
            declarer = repo.get_declarer_by_name(customer_name)
            if declarer is not None:
                plan = repo.get_plan(declarer.plan_id)
                if plan is not None:
                    return list(plan.items)
        default_plan = next((plan for plan in repo.list_plans() if plan.is_default), None)
        return list(default_plan.items) if default_plan is not None else []

    def _find_odds_item(self, normalized_type: str, bet_type: str, plan_items: list[Any]):
        item_by_name = {str(item.bet_type).strip(): item for item in plan_items}
        exact = item_by_name.get(str(bet_type).strip())
        if exact is not None:
            return exact
        for candidate in SPECIAL_ODDS_CANDIDATES.get(normalized_type, ()):
            if candidate in item_by_name:
                return item_by_name[candidate]
        return None

    def _find_rebate_item(self, bet_type: str, plan_items: list[Any], normalized_type: str):
        item_by_name = {str(item.bet_type).strip(): item for item in plan_items}
        if str(bet_type).strip() in item_by_name:
            return item_by_name[str(bet_type).strip()]
        for generic in ("全部", "统一返水", "默认返水"):
            if generic in item_by_name:
                return item_by_name[generic]
        return self._find_odds_item(normalized_type, bet_type, plan_items)

    def _numbers_for_normalized(self, normalized_type: str, selection: str) -> list[str]:
        if normalized_type == SPECIAL_NUMBER:
            return [normalize_number(token) for token in selection.split(",") if token]
        if normalized_type == SPECIAL_ZODIAC:
            return list(self._zodiac_map[selection])
        if normalized_type == SPECIAL_ZODIAC_GROUP:
            numbers: list[str] = []
            for zodiac in selection.split(","):
                numbers.extend(self._zodiac_map[zodiac])
            return sorted(set(numbers))
        return self._expand_special_expression(selection)

    def _expand_special_expression(self, expression: str) -> list[str]:
        text = expression.strip()
        if not text:
            raise ValueError("表达式不能为空")
        try:
            return [normalize_number(text)]
        except Exception:
            pass
        if text in self._zodiac_map:
            return list(self._zodiac_map[text])
        if text in WAVE_NUMBERS:
            return _format_numbers(WAVE_NUMBERS[text])
        if text in FIVE_ELEMENT_NUMBERS:
            return _format_numbers(FIVE_ELEMENT_NUMBERS[text])
        predicates = []
        wave_match = re.fullmatch(r"([红蓝绿])波?([单双大小])", text)
        if wave_match:
            color, suffix = wave_match.groups()
            predicates.append(lambda number, color=color: get_wave_color(number) == f"{color}波")
            if suffix in {"单", "双"}:
                predicates.append(lambda number, suffix=suffix: odd_even_label(number) == suffix)
            else:
                predicates.append(lambda number, suffix=suffix: size_label(number) == suffix)
        elif text in {"大", "小"}:
            predicates.append(lambda number, text=text: size_label(number) == text)
        elif text in {"单", "双"}:
            predicates.append(lambda number, text=text: odd_even_label(number) == text)
        elif text in {"合大", "合小"}:
            predicates.append(lambda number, text=text: composite_size_label(number) == text)
        elif text in {"合单", "合双"}:
            predicates.append(lambda number, text=text: composite_odd_even_label(number) == text)
        elif re.fullmatch(r"(尾[0-9]|[0-9]尾)", text):
            tail = int(text.replace("尾", ""))
            predicates.append(lambda number, tail=tail: tail_number(number) == tail)
        elif re.fullmatch(r"([0-4]头|头[0-4])", text):
            head = int(text.replace("头", ""))
            predicates.append(lambda number, head=head: head_number(number) == head)
        elif text in {"红单", "红双", "蓝单", "蓝双", "绿单", "绿双"}:
            predicates.append(lambda number, text=text: get_half_wave(number) == text)
        if not predicates:
            raise ValueError(f"无法识别特码抛出表达式：{expression}")
        return [f"{number:02d}" for number in range(1, 50) if all(predicate(f"{number:02d}") for predicate in predicates)]

    def _split_throw_expressions(self, text: str) -> list[tuple[str, Decimal]]:
        if not text.strip():
            raise ValueError("抛出内容不能为空")
        parts: list[str] = []
        for chunk in [part.strip() for part in re.split(r"[\n;；]+", text) if part.strip()]:
            if chunk.count("=") > 1:
                parts.extend(part.strip() for part in re.split(r"[,，]+", chunk) if part.strip())
            else:
                parts.append(chunk)
        result: list[tuple[str, Decimal]] = []
        for part in parts:
            if "=" not in part:
                raise ValueError(f"抛出格式必须为 左侧=金额：{part}")
            left, right = part.split("=", 1)
            expression = left.strip()
            amount = _positive_decimal(right, "抛出金额")
            if not expression:
                raise ValueError(f"抛出表达式不能为空：{part}")
            result.append((expression, amount))
        return result

    def _parse_lianxiao_group(self, expression: str) -> str:
        tokens = [token for token in re.split(r"[\s,，、/\-|+]+", expression.strip()) if token]
        if len(tokens) <= 1:
            tokens = list("".join(tokens) if tokens else expression.strip())
        if len(tokens) < 2:
            raise ValueError("连肖组合至少需要 2 个生肖")
        invalid = [token for token in tokens if token not in self._zodiac_rank]
        if invalid:
            raise ValueError(f"无效生肖：{','.join(invalid)}")
        if len(set(tokens)) != len(tokens):
            raise ValueError("连肖组合不能包含重复生肖")
        return self._stable_zodiac_group(tokens)

    def _stable_zodiac_group(self, zodiacs: Iterable[str]) -> str:
        unique = list(dict.fromkeys(zodiacs))
        return ",".join(sorted(unique, key=lambda zodiac: self._zodiac_rank[zodiac]))

    def _zodiac_group_sort_key(self, group: str) -> tuple[int, ...]:
        return tuple(self._zodiac_rank[zodiac] for zodiac in group.split(",") if zodiac)

    def _active_special_thrown_amounts(self, session: Session, *, region: str | None) -> dict[str, Decimal]:
        amounts: dict[str, Decimal] = defaultdict(Decimal)
        for record in self._throw_records(session, SPECIAL_ADJUSTMENT_TYPES, region=region):
            sign = Decimal("-1") if record.adjustment_type.endswith("_reversal") else Decimal("1")
            for entry in _snapshot_entries(record.record_snapshot):
                number = entry.get("number")
                if not number:
                    continue
                amounts[str(number)] += sign * _to_decimal(entry.get("amount"))
        return amounts

    def _active_lianxiao_thrown_amounts(self, session: Session, *, region: str | None) -> dict[str, Decimal]:
        amounts: dict[str, Decimal] = defaultdict(Decimal)
        for record in self._throw_records(session, LIANXIAO_ADJUSTMENT_TYPES, region=region):
            sign = Decimal("-1") if record.adjustment_type.endswith("_reversal") else Decimal("1")
            for entry in _snapshot_entries(record.record_snapshot):
                group = entry.get("zodiac_group")
                if not group:
                    continue
                amounts[str(group)] += sign * _to_decimal(entry.get("amount"))
        return amounts

    def _throw_records(self, session: Session, types: set[str], *, region: str | None):
        from models import AdjustmentRecord

        stmt = select(AdjustmentRecord).where(AdjustmentRecord.adjustment_type.in_(types))
        if region:
            stmt = stmt.where(AdjustmentRecord.region.in_((region, "全部")))
        return list(session.scalars(stmt.order_by(AdjustmentRecord.id.asc())))

    def _is_record_reversed(self, record_id: int) -> bool:
        records = self._adjustment_records.list_records(limit=500)
        for record in records:
            if record.adjustment_type in REVERSAL_TYPES and isinstance(record.record_snapshot, dict):
                if record.record_snapshot.get("reversed_record_id") == record_id:
                    return True
        return False


def _format_numbers(numbers: Iterable[int]) -> list[str]:
    return [f"{number:02d}" for number in sorted(numbers)]


def _money_decimal(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> str:
    return f"{_money_decimal(value):.2f}"


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _positive_decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label}必须是有效金额") from None
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{label}必须大于 0")
    return _money_decimal(result)


def _positive_or_zero_decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label}必须是有效金额") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label}不能为负数")
    return _money_decimal(result)


def _require_text(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label}不能为空")
    return text


def _snapshot_entries(snapshot: Any) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return []
    entries = snapshot.get("entries")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def _throw_entry_snapshot(entry: ThrowEntry) -> dict[str, str]:
    payload = {
        "amount": _money(entry.amount),
        "source_expression": entry.source_expression,
    }
    if entry.number:
        payload["number"] = entry.number
    if entry.zodiac_group:
        payload["zodiac_group"] = entry.zodiac_group
    return payload


def _special_row_snapshot(row: SpecialRiskRow) -> dict[str, str]:
    return {
        "number": row.number,
        "zodiac": row.zodiac,
        "raw_stake_amount": _money(row.raw_stake_amount),
        "potential_payout_amount": _money(row.potential_payout_amount),
        "rebate_amount": _money(row.rebate_amount),
        "risk_amount": _money(row.risk_amount),
        "thrown_amount": _money(row.thrown_amount),
        "adjusted_risk_amount": _money(row.adjusted_risk_amount),
        "note": row.note,
    }


def _lianxiao_row_snapshot(row: LianxiaoRiskRow) -> dict[str, str]:
    return {
        "zodiac_group": row.zodiac_group,
        "raw_amount": _money(row.raw_amount),
        "potential_payout_amount": _money(row.potential_payout_amount),
        "rebate_amount": _money(row.rebate_amount),
        "risk_amount": _money(row.risk_amount),
        "thrown_amount": _money(row.thrown_amount),
        "adjusted_risk_amount": _money(row.adjusted_risk_amount),
        "order_count": str(row.order_count),
        "note": row.note,
    }
