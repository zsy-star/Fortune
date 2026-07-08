"""Lightweight summaries for special-number and lianxiao adjustment pages."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from itertools import combinations
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from core.database import SessionLocal
from domain.number_rules import normalize_number
from domain.zodiac_config import (
    ZODIAC_SEQUENCE,
    get_default_zodiac_year,
    get_zodiac_number_map,
    validate_zodiac_year,
)
from domain.zodiac_rules import get_zodiac
from models import Order

CENT = Decimal("0.01")
EXCLUDED_ORDER_STATUSES = {"voided", "void"}
SPECIAL_BET_TYPES = {"特码", "号码", "单号投注", "纯数字", "特码号码", "特号"}
LIANXIAO_BET_TYPES = {"连肖", "多生肖", "连肖复选"}
ZODIAC_RANK = {zodiac: index for index, zodiac in enumerate(ZODIAC_SEQUENCE)}


@dataclass(frozen=True, slots=True)
class TemaNumberSummary:
    number: str
    zodiac: str
    original_amount: Decimal
    adjustment_amount: Decimal
    total_amount: Decimal
    profit_loss: Decimal
    row_id: int


@dataclass(frozen=True, slots=True)
class TemaSummary:
    rows: list[TemaNumberSummary]
    original_total: Decimal
    adjustment_total: Decimal
    after_total: Decimal
    max_profit: Decimal
    max_loss: Decimal
    profit_count: int
    loss_count: int


@dataclass(frozen=True, slots=True)
class LianxiaoGroupSummary:
    group: str
    original_amount: Decimal
    adjustment_amount: Decimal
    total_amount: Decimal
    profit_loss: Decimal


@dataclass(frozen=True, slots=True)
class LianxiaoSummary:
    rows: list[LianxiaoGroupSummary]
    original_total: Decimal
    adjustment_total: Decimal
    after_total: Decimal
    max_profit: Decimal
    max_loss: Decimal


class AdjustmentSummaryService:
    """Read-only order summarizer used by adjustment workbench pages."""

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal, *, zodiac_year: int | None = None):
        self._session_factory = session_factory
        self.set_zodiac_year(zodiac_year or get_default_zodiac_year())

    def set_zodiac_year(self, zodiac_year: int) -> None:
        self._zodiac_year = validate_zodiac_year(zodiac_year)
        self._zodiac_map = get_zodiac_number_map(self._zodiac_year)

    def summarize_tema(
        self,
        *,
        region: str | None = None,
        adjustments: dict[str, Decimal] | None = None,
    ) -> TemaSummary:
        adjustments = adjustments or {}
        amounts = {f"{number:02d}": Decimal("0") for number in range(1, 50)}
        with self._session_factory() as session:
            for order in self._iter_orders(session, region=region):
                for item in order.items:
                    if item.bet_type not in SPECIAL_BET_TYPES:
                        continue
                    amount = _money_decimal(item.amount)
                    for number in self.expand_tema_selection(item.selection):
                        amounts[number] += amount

        rows: list[TemaNumberSummary] = []
        profit_losses: list[Decimal] = []
        for index, number in enumerate((f"{value:02d}" for value in range(1, 50)), start=1):
            original = _money_decimal(amounts[number])
            adjustment = _money_decimal(adjustments.get(number, Decimal("0")))
            total = _money_decimal(original + adjustment)
            profit_loss = _money_decimal(-total)
            profit_losses.append(profit_loss)
            rows.append(
                TemaNumberSummary(
                    number=number,
                    zodiac=get_zodiac(number, year=self._zodiac_year),
                    original_amount=original,
                    adjustment_amount=adjustment,
                    total_amount=total,
                    profit_loss=profit_loss,
                    row_id=index,
                )
            )
        return TemaSummary(
            rows=rows,
            original_total=_money_decimal(sum((row.original_amount for row in rows), Decimal("0"))),
            adjustment_total=_money_decimal(sum((row.adjustment_amount for row in rows), Decimal("0"))),
            after_total=_money_decimal(sum((row.total_amount for row in rows), Decimal("0"))),
            max_profit=max([Decimal("0"), *profit_losses]),
            max_loss=min([Decimal("0"), *profit_losses]),
            profit_count=sum(1 for value in profit_losses if value > 0),
            loss_count=sum(1 for value in profit_losses if value < 0),
        )

    def summarize_lianxiao(
        self,
        *,
        region: str | None = None,
        adjustments: dict[str, Decimal] | None = None,
    ) -> LianxiaoSummary:
        adjustments = adjustments or {}
        grouped: dict[str, Decimal] = defaultdict(Decimal)
        with self._session_factory() as session:
            for order in self._iter_orders(session, region=region):
                for item in order.items:
                    if item.bet_type not in LIANXIAO_BET_TYPES:
                        continue
                    for group in self.expand_lianxiao_selection(item.selection, note=item.note, bet_type=item.bet_type):
                        grouped[group] += _money_decimal(item.amount)

        rows: list[LianxiaoGroupSummary] = []
        for group, original_value in sorted(grouped.items(), key=lambda item: (-item[1], _group_sort_key(item[0]))):
            original = _money_decimal(original_value)
            adjustment = _money_decimal(adjustments.get(group, Decimal("0")))
            total = _money_decimal(original + adjustment)
            rows.append(
                LianxiaoGroupSummary(
                    group=group,
                    original_amount=original,
                    adjustment_amount=adjustment,
                    total_amount=total,
                    profit_loss=_money_decimal(-total),
                )
            )
        profit_losses = [row.profit_loss for row in rows]
        return LianxiaoSummary(
            rows=rows,
            original_total=_money_decimal(sum((row.original_amount for row in rows), Decimal("0"))),
            adjustment_total=_money_decimal(sum((row.adjustment_amount for row in rows), Decimal("0"))),
            after_total=_money_decimal(sum((row.total_amount for row in rows), Decimal("0"))),
            max_profit=max([Decimal("0"), *profit_losses]),
            max_loss=min([Decimal("0"), *profit_losses]),
        )

    def expand_tema_selection(self, selection: str) -> list[str]:
        text = _strip_embedded_amount(selection)
        numbers = [normalize_number(match.group(0)) for match in re.finditer(r"(?<!\d)(?:0?[1-9]|[1-4]\d)(?!\d)", text)]
        zodiacs = [char for char in text if char in self._zodiac_map]
        for zodiac in zodiacs:
            numbers.extend(self._zodiac_map[zodiac])
        return sorted(set(numbers))

    def expand_lianxiao_selection(self, selection: str, *, note: str | None = None, bet_type: str = "") -> list[str]:
        text = _strip_embedded_amount(selection)
        fuxuan_count = _extract_fuxuan_count(text, note)
        text = re.sub(r"复\s*\d+", "", text)
        tokens = _extract_zodiacs(text)
        if len(tokens) < 2:
            return []
        unique_tokens = list(dict.fromkeys(tokens))
        if fuxuan_count is None and bet_type == "连肖复选":
            fuxuan_count = len(unique_tokens)
        if fuxuan_count is None:
            return [normalize_lianxiao_group(unique_tokens)]
        if fuxuan_count < 2 or fuxuan_count > len(unique_tokens):
            return []
        return [normalize_lianxiao_group(group) for group in combinations(unique_tokens, fuxuan_count)]

    def parse_tema_adjustments(self, text: str) -> dict[str, Decimal]:
        adjustments: dict[str, Decimal] = {}
        for expression, amount in _split_adjustment_text(text):
            numbers = self.expand_tema_selection(expression)
            if not numbers:
                raise ValueError(f"无法识别特码调整对象：{expression}")
            for number in numbers:
                adjustments[number] = _money_decimal(adjustments.get(number, Decimal("0")) + amount)
        return adjustments

    def parse_lianxiao_adjustments(self, text: str) -> dict[str, Decimal]:
        adjustments: dict[str, Decimal] = {}
        for expression, amount in _split_adjustment_text(text):
            groups = self.expand_lianxiao_selection(expression)
            if len(groups) != 1:
                raise ValueError(f"无法识别连肖调整组：{expression}")
            group = groups[0]
            adjustments[group] = _money_decimal(adjustments.get(group, Decimal("0")) + amount)
        return adjustments

    def suggest_tema_adjustments(self, rows: Iterable[TemaNumberSummary], max_loss: Decimal | str) -> dict[str, Decimal]:
        limit = _positive_or_zero_decimal(max_loss)
        suggestions: dict[str, Decimal] = {}
        for row in rows:
            overflow = row.total_amount - limit
            if overflow > 0:
                suggestions[row.number] = _money_decimal(-overflow)
        return suggestions

    def round_adjustments_to_tens(self, adjustments: dict[str, Decimal]) -> dict[str, Decimal]:
        rounded: dict[str, Decimal] = {}
        for key, value in adjustments.items():
            if value == 0:
                continue
            sign = Decimal("-1") if value < 0 else Decimal("1")
            rounded[key] = sign * ((abs(value) / Decimal("10")).to_integral_value(rounding=ROUND_CEILING) * Decimal("10"))
        return rounded

    def _iter_orders(self, session: Session, *, region: str | None) -> list[Order]:
        stmt = select(Order).options(selectinload(Order.items)).where(Order.status.not_in(EXCLUDED_ORDER_STATUSES))
        if region:
            stmt = stmt.where(Order.region == region)
        try:
            orders = list(session.scalars(stmt))
        except OperationalError as exc:
            if "zodiac_year" not in str(exc):
                raise
            session.rollback()
            return []
        default_year = get_default_zodiac_year()
        return [
            order
            for order in orders
            if validate_zodiac_year(order.zodiac_year or default_year) == self._zodiac_year
        ]


def normalize_lianxiao_group(zodiacs: Iterable[str]) -> str:
    unique = list(dict.fromkeys(zodiacs))
    invalid = [zodiac for zodiac in unique if zodiac not in ZODIAC_RANK]
    if invalid:
        raise ValueError(f"无效生肖：{','.join(invalid)}")
    return "".join(sorted(unique, key=lambda zodiac: ZODIAC_RANK[zodiac]))


def _extract_zodiacs(text: str) -> list[str]:
    compact = re.sub(r"[\s,，、/|+\-=]+", "", text.strip())
    return [char for char in compact if char in ZODIAC_RANK]


def _extract_fuxuan_count(selection: str, note: str | None) -> int | None:
    for text in (selection, note or ""):
        match = re.search(r"复\s*([2-9]\d*)", text)
        if match:
            return int(match.group(1))
    return None


def _strip_embedded_amount(text: str) -> str:
    return re.sub(r"(?:各\s*|\s+)\d+(?:\.\d+)?\s*$", "", str(text or "").strip())


def _split_adjustment_text(text: str) -> list[tuple[str, Decimal]]:
    result: list[tuple[str, Decimal]] = []
    for part in [part.strip() for part in re.split(r"[\n;；,，]+", text or "") if part.strip()]:
        if "=" not in part:
            raise ValueError(f"调整格式必须是 左侧=金额：{part}")
        left, right = part.split("=", 1)
        expression = left.strip()
        if not expression:
            raise ValueError(f"调整对象不能为空：{part}")
        result.append((expression, _decimal(right)))
    return result


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"金额无效：{value}") from None
    if not result.is_finite():
        raise ValueError(f"金额无效：{value}")
    return _money_decimal(result)


def _positive_or_zero_decimal(value: Any) -> Decimal:
    result = _decimal(value)
    if result < 0:
        raise ValueError("最大亏损不能为负数")
    return result


def _money_decimal(value: Any) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def money(value: Decimal) -> str:
    return f"{_money_decimal(value):.2f}"


def _group_sort_key(group: str) -> tuple[int, ...]:
    return tuple(ZODIAC_RANK[zodiac] for zodiac in group if zodiac in ZODIAC_RANK)
