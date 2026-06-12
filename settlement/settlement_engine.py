"""Pure settlement preview engine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.number_rules import normalize_number
from schemas.settlement_schema import ItemSettlementResult, OrderSettlementPreview
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
    BetTypeNormalizer,
)
from settlement.exceptions import InvalidDrawError, SettlementDataError, UnsupportedBetTypeError
from settlement.matchers import (
    match_color,
    match_element,
    match_half_color,
    match_head,
    match_parity,
    match_size,
    match_special_number,
    match_sum_parity,
    match_sum_size,
    match_tail,
    match_zodiac,
)

Matcher = Any

MATCHERS: dict[str, Matcher] = {
    SPECIAL_NUMBER: match_special_number,
    SPECIAL_ZODIAC: match_zodiac,
    SPECIAL_COLOR: match_color,
    SPECIAL_HALF_WAVE: match_half_color,
    SPECIAL_SIZE: match_size,
    SPECIAL_PARITY: match_parity,
    SPECIAL_TAIL: match_tail,
    SPECIAL_HEAD: match_head,
    SPECIAL_SUM_PARITY: match_sum_parity,
    SPECIAL_SUM_SIZE: match_sum_size,
    SPECIAL_ELEMENT: match_element,
}


class SettlementEngine:
    """Evaluate order items against an explicitly supplied lottery draw."""

    def __init__(self, normalizer: BetTypeNormalizer | None = None, *, zodiac_year: int = 2026):
        self._normalizer = normalizer or BetTypeNormalizer()
        self._zodiac_year = zodiac_year

    def evaluate_item(self, order_item: Any, lottery_draw: Any) -> ItemSettlementResult:
        draw = self._validate_draw(lottery_draw)
        amount = self._item_amount(order_item)
        try:
            normalized = self._normalizer.normalize(order_item.bet_type, order_item.selection)
        except UnsupportedBetTypeError as exc:
            return ItemSettlementResult(
                order_item_id=getattr(order_item, "id", None),
                bet_type=order_item.bet_type,
                normalized_bet_type=None,
                selection=order_item.selection,
                amount=amount,
                is_supported=False,
                is_winner=None,
                matched_number=None,
                reason=str(exc),
            )

        matcher = MATCHERS[normalized.normalized_bet_type]
        if normalized.normalized_bet_type == SPECIAL_ZODIAC:
            is_winner, matched_number, reason = matcher(
                normalized.selection,
                draw["special_number"],
                year=self._zodiac_year,
            )
        else:
            is_winner, matched_number, reason = matcher(normalized.selection, draw["special_number"])

        return ItemSettlementResult(
            order_item_id=getattr(order_item, "id", None),
            bet_type=order_item.bet_type,
            normalized_bet_type=normalized.normalized_bet_type,
            selection=normalized.selection,
            amount=amount,
            is_supported=True,
            is_winner=is_winner,
            matched_number=matched_number,
            reason=reason,
        )

    def evaluate_order(self, order: Any, lottery_draw: Any) -> OrderSettlementPreview:
        draw = self._validate_draw(lottery_draw)
        if order.region != draw["region"]:
            raise SettlementDataError(f"订单地区 {order.region} 与开奖地区 {draw['region']} 不一致")
        items = list(getattr(order, "items", []) or [])
        if not items:
            raise SettlementDataError("订单必须至少包含一条明细")

        results = [self.evaluate_item(item, lottery_draw) for item in items]
        supported = [result for result in results if result.is_supported]
        winning = [result for result in supported if result.is_winner is True]
        losing = [result for result in supported if result.is_winner is False]
        unsupported = [result for result in results if not result.is_supported]
        return OrderSettlementPreview(
            order_id=order.id,
            order_no=order.order_no,
            region=order.region,
            issue_number=draw["issue_number"],
            draw_date=draw["draw_date"],
            regular_numbers=draw["regular_numbers"],
            special_number=draw["special_number"],
            total_items=len(results),
            supported_items=len(supported),
            unsupported_items=len(unsupported),
            winning_items=len(winning),
            losing_items=len(losing),
            results=results,
        )

    def _validate_draw(self, lottery_draw: Any) -> dict[str, Any]:
        region = getattr(lottery_draw, "region", None)
        issue_number = getattr(lottery_draw, "issue_number", None)
        draw_date = getattr(lottery_draw, "draw_date", None)
        regular_numbers = list(getattr(lottery_draw, "regular_numbers", []) or [])
        special_number = getattr(lottery_draw, "special_number", None)
        if not region:
            raise InvalidDrawError("开奖地区不能为空")
        if not issue_number:
            raise InvalidDrawError("开奖期号不能为空")
        if draw_date is None:
            raise InvalidDrawError("开奖日期不能为空")
        if len(regular_numbers) != 6:
            raise InvalidDrawError("普通号码必须为6个")
        normalized_regular = [normalize_number(number) for number in regular_numbers]
        normalized_special = normalize_number(special_number)
        all_numbers = [*normalized_regular, normalized_special]
        if len(set(all_numbers)) != len(all_numbers):
            raise InvalidDrawError("普通号码和特码不能重复")
        return {
            "region": region,
            "issue_number": str(issue_number),
            "draw_date": draw_date,
            "regular_numbers": normalized_regular,
            "special_number": normalized_special,
        }

    def _item_amount(self, order_item: Any) -> Decimal:
        amount = Decimal(str(getattr(order_item, "amount", "")))
        if not amount.is_finite() or amount <= 0:
            raise SettlementDataError(f"订单明细金额非法：{getattr(order_item, 'amount', None)!r}")
        return amount
