"""Read-only aggregation service for the order analysis workbench."""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import SessionLocal
from domain.bet_types import (
    BET_TYPE_LIANXIAO,
    BET_TYPE_NUMBER,
    BET_TYPE_PINGTE_ZODIAC,
    BET_TYPE_SPECIAL,
    REGION_HONG_KONG,
    REGION_MACAU,
)
from domain.zodiac_rules import get_zodiac
from models import Order, SettlementRecord
from repositories.order_repository import OrderRepository
from schemas.order_analysis_schema import (
    NumberAnalysisRow,
    OrderAnalysisWorkbench,
    ZodiacAmountRow,
    ZodiacFrequencyRow,
)

_EXCLUDED_FROM_EFFECTIVE_STATS = ("voided",)
_NUMBER_BET_TYPES = frozenset({BET_TYPE_SPECIAL, BET_TYPE_NUMBER, "平码"})
_ZODIAC_AMOUNT_BET_TYPES = frozenset({BET_TYPE_PINGTE_ZODIAC, "六肖中特"})
_SELECTION_SPLIT = re.compile(r"[,，、\s]+")
_ZODIAC_ORDER = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")
_ZODIAC_SET = frozenset(_ZODIAC_ORDER)


class OrderAnalysisService:
    """Build read-only analysis snapshots from saved orders and order items."""

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory

    def get_workbench(self, *, region: str | None = None) -> OrderAnalysisWorkbench:
        filter_key = self._filter_key(region)
        number_amounts = {number: Decimal("0") for number in range(1, 50)}
        lianxiao_counts = {zodiac: 0 for zodiac in _ZODIAC_ORDER}
        pingte_amounts = {zodiac: Decimal("0") for zodiac in _ZODIAC_ORDER}

        with self._session_factory() as session:
            orders = [
                order
                for order in OrderRepository(session).list_for_analysis(
                    exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS
                )
                if self._region_matches(order.region, filter_key)
            ]

            for order in orders:
                for item in order.items:
                    for number in self._number_selection(item.bet_type, item.selection):
                        number_amounts[number] += Decimal(item.amount or 0)

                    for zodiac in self._lianxiao_selection(item.bet_type, item.selection):
                        lianxiao_counts[zodiac] += 1

                    for zodiac in self._zodiac_amount_selection(item.bet_type, item.selection):
                        pingte_amounts[zodiac] += Decimal(item.amount or 0)

            number_rows = tuple(
                NumberAnalysisRow(
                    row_id=number,
                    number=number,
                    zodiac=get_zodiac(number),
                    display=f"{get_zodiac(number)}{number:02d}",
                    bet_amount=number_amounts[number],
                    profit_loss=None,
                )
                for number in range(1, 50)
            )
            lianxiao_frequency = tuple(
                ZodiacFrequencyRow(zodiac=zodiac, count=lianxiao_counts[zodiac])
                for zodiac in _ZODIAC_ORDER
            )
            pingte_zodiac_amounts = tuple(
                ZodiacAmountRow(zodiac=zodiac, amount=pingte_amounts[zodiac])
                for zodiac in _ZODIAC_ORDER
            )
            order_count = len(orders)
            item_count = sum(len(order.items) for order in orders)
            total_amount = sum((Decimal(order.total_amount or 0) for order in orders), Decimal("0"))
            settled_payout_amount, old_snapshot_count = self._settled_payout_summary(session, filter_key)

        filter_label = self._filter_label(filter_key)
        report_text = self._build_report(
            filter_label=filter_label,
            order_count=order_count,
            item_count=item_count,
            total_amount=total_amount,
            settled_payout_amount=settled_payout_amount,
            old_snapshot_count=old_snapshot_count,
            number_rows=number_rows,
            lianxiao_frequency=lianxiao_frequency,
            pingte_zodiac_amounts=pingte_zodiac_amounts,
        )
        return OrderAnalysisWorkbench(
            filter_key=filter_key,
            filter_label=filter_label,
            order_count=order_count,
            item_count=item_count,
            total_amount=total_amount,
            number_rows=number_rows,
            lianxiao_frequency=lianxiao_frequency,
            pingte_zodiac_amounts=pingte_zodiac_amounts,
            report_text=report_text,
        )

    def _filter_key(self, region: str | None) -> str:
        text = (region or "all").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
        if text in {"all", "全部", "全部订单"}:
            return "all"
        if text in {"澳门", "澳門", "澳", "macau", "macao"}:
            return "macau"
        if text in {"香港", "港", "hongkong", "hk"}:
            return "hongkong"
        return "all"

    def _filter_label(self, filter_key: str) -> str:
        if filter_key == "macau":
            return REGION_MACAU
        if filter_key == "hongkong":
            return REGION_HONG_KONG
        return "全部"

    def _region_matches(self, order_region: str, filter_key: str) -> bool:
        if filter_key == "all":
            return True
        text = (order_region or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
        if filter_key == "macau":
            return text in {"澳门", "澳門", "澳", "macau", "macao"}
        if filter_key == "hongkong":
            return text in {"香港", "港", "hongkong", "hk"}
        return True

    def _number_selection(self, bet_type: str, selection: str) -> tuple[int, ...]:
        if bet_type not in _NUMBER_BET_TYPES:
            return ()
        tokens = self._split_selection(selection)
        if not tokens or not all(token.isdigit() for token in tokens):
            return ()
        numbers: list[int] = []
        for token in tokens:
            number = int(token)
            if number < 1 or number > 49:
                return ()
            numbers.append(number)
        return tuple(dict.fromkeys(numbers))

    def _lianxiao_selection(self, bet_type: str, selection: str) -> tuple[str, ...]:
        zodiacs = self._parse_zodiac_selection(selection)
        if not zodiacs:
            return ()
        if bet_type == BET_TYPE_LIANXIAO:
            return zodiacs
        if len(zodiacs) >= 2 and "肖" in bet_type:
            return zodiacs
        return ()

    def _zodiac_amount_selection(self, bet_type: str, selection: str) -> tuple[str, ...]:
        is_clear_zodiac_bet = bet_type.endswith("肖") and bet_type != BET_TYPE_LIANXIAO
        if bet_type not in _ZODIAC_AMOUNT_BET_TYPES and not is_clear_zodiac_bet:
            return ()
        return self._parse_zodiac_selection(selection)

    def _parse_zodiac_selection(self, selection: str) -> tuple[str, ...]:
        text = (selection or "").strip()
        if not text:
            return ()
        if _SELECTION_SPLIT.search(text):
            tokens = self._split_selection(text)
            if tokens and all(token in _ZODIAC_SET for token in tokens):
                return tuple(dict.fromkeys(tokens))
            return ()
        if all(char in _ZODIAC_SET for char in text):
            return tuple(dict.fromkeys(text))
        return ()

    def _split_selection(self, selection: str) -> list[str]:
        return [part.strip() for part in _SELECTION_SPLIT.split(selection.strip()) if part.strip()]

    def _settled_payout_summary(self, session: Session, filter_key: str) -> tuple[Decimal, int]:
        stmt = (
            select(SettlementRecord.result_snapshot, Order.region, Order.status)
            .join(Order, Order.id == SettlementRecord.order_id)
            .where(Order.status != "voided")
        )
        total = Decimal("0")
        old_snapshot_count = 0
        for snapshot, region, _status in session.execute(stmt):
            if not self._region_matches(region, filter_key):
                continue
            payout, has_payout = self._snapshot_payout_amount(snapshot)
            if has_payout:
                total += payout
            else:
                old_snapshot_count += 1
        return total.quantize(Decimal("0.01")), old_snapshot_count

    def _snapshot_payout_amount(self, snapshot: object) -> tuple[Decimal, bool]:
        if not isinstance(snapshot, dict):
            return Decimal("0"), False
        settlement = snapshot.get("settlement")
        if isinstance(settlement, dict) and settlement.get("total_payout_amount") not in (None, ""):
            return self._to_decimal_money(settlement.get("total_payout_amount")), True
        items = snapshot.get("items")
        if not isinstance(items, list):
            return Decimal("0"), False
        total = Decimal("0")
        has_item_payout = False
        for item in items:
            if isinstance(item, dict) and item.get("payout_amount") not in (None, ""):
                total += self._to_decimal_money(item.get("payout_amount"))
                has_item_payout = True
        return total, has_item_payout

    def _to_decimal_money(self, value: object) -> Decimal:
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except Exception:
            return Decimal("0.00")

    def _build_report(
        self,
        *,
        filter_label: str,
        order_count: int,
        item_count: int,
        total_amount: Decimal,
        settled_payout_amount: Decimal,
        old_snapshot_count: int,
        number_rows: tuple[NumberAnalysisRow, ...],
        lianxiao_frequency: tuple[ZodiacFrequencyRow, ...],
        pingte_zodiac_amounts: tuple[ZodiacAmountRow, ...],
    ) -> str:
        number_top = sorted(number_rows, key=lambda row: (-row.bet_amount, row.number))[:5]
        lianxiao_top = sorted(lianxiao_frequency, key=lambda row: (-row.count, _ZODIAC_ORDER.index(row.zodiac)))[:5]
        pingte_top = sorted(
            pingte_zodiac_amounts,
            key=lambda row: (-row.amount, _ZODIAC_ORDER.index(row.zodiac)),
        )[:5]

        lines = [
            "订单分析报告（仅参考）：",
            f"当前筛选范围：{filter_label}",
            f"订单数量：{order_count}",
            f"明细数量：{item_count}",
            f"总投注金额：{total_amount:.2f}",
            f"已结算中奖金额：{settled_payout_amount:.2f}",
            f"下注最多的号码 Top 5：{self._format_number_top(number_top)}",
            f"连肖出现最多的生肖 Top 5：{self._format_count_top(lianxiao_top)}",
            f"平特一肖投注金额 Top 5：{self._format_amount_top(pingte_top)}",
            "",
            "说明：当前分析基于订单明细和投注金额统计。",
            "说明：已结算中奖金额只读取 SettlementRecord 快照中的第一阶段基础中奖金额。",
            f"说明：旧结算快照无赔付字段的记录数：{old_snapshot_count}。",
            "说明：未结算订单不参与真实盈亏；当前不写余额，不计算返水、佣金。",
            "说明：盈亏字段仍不代表余额或真实净利润，仅作占位/风险参考。",
        ]
        return "\n".join(lines)

    def _format_number_top(self, rows: list[NumberAnalysisRow]) -> str:
        rows = [row for row in rows if row.bet_amount > 0]
        if not rows:
            return "无"
        return "；".join(f"{row.display} {row.bet_amount:.2f}" for row in rows[:5])

    def _format_count_top(self, rows: list[ZodiacFrequencyRow]) -> str:
        rows = [row for row in rows if row.count > 0]
        if not rows:
            return "无"
        return "；".join(f"{row.zodiac} {row.count}" for row in rows[:5])

    def _format_amount_top(self, rows: list[ZodiacAmountRow]) -> str:
        rows = [row for row in rows if row.amount > 0]
        if not rows:
            return "无"
        return "；".join(f"{row.zodiac} {row.amount:.2f}" for row in rows[:5])
