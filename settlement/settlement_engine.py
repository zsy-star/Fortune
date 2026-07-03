"""Pure settlement preview engine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.color_rules import get_wave_color
from domain.number_rules import normalize_number, odd_even_label, size_label, tail_number
from domain.zodiac_rules import get_zodiac
from schemas.settlement_schema import ItemSettlementResult, OrderSettlementPreview
from settlement.bet_normalizer import (
    LINKED_TAIL,
    LIANMA_THREE_THREE,
    LIANMA_THREE_TWO,
    LIANMA_TWO_TWO,
    NON_HIT_NUMBER,
    NUMBER_FUXUAN,
    PACKAGE_HALF_WAVE,
    PING_TAIL,
    REGULAR_NUMBER,
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
    SIX_SPECIAL_ZODIAC,
    BetTypeNormalizer,
)
from settlement.exceptions import InvalidDrawError, InvalidSelectionError, SettlementDataError, UnsupportedBetTypeError
from settlement.matchers import (
    match_color,
    match_element,
    match_half_color,
    match_head,
    match_linked_tail,
    match_non_hit_number,
    match_number_fuxuan,
    match_package_half_wave,
    match_parity,
    match_ping_tail,
    match_regular_number,
    match_six_special_zodiac,
    match_size,
    match_special_number,
    match_sum_parity,
    match_sum_size,
    match_tail,
    match_three_in_three,
    match_three_in_two,
    match_two_in_two,
    match_zodiac,
    match_zodiac_group,
    fuxuan_groups,
    format_lianma_group,
    matched_lianma_groups,
    parse_lianma_groups,
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
    SPECIAL_ZODIAC_GROUP: match_zodiac_group,
    LINKED_TAIL: match_linked_tail,
    PING_TAIL: match_ping_tail,
    LIANMA_TWO_TWO: match_two_in_two,
    LIANMA_THREE_THREE: match_three_in_three,
    LIANMA_THREE_TWO: match_three_in_two,
    NUMBER_FUXUAN: match_number_fuxuan,
    NON_HIT_NUMBER: match_non_hit_number,
    SIX_SPECIAL_ZODIAC: match_six_special_zodiac,
    REGULAR_NUMBER: match_regular_number,
    PACKAGE_HALF_WAVE: match_package_half_wave,
}


class SettlementEngine:
    """Evaluate order items against an explicitly supplied lottery draw."""

    def __init__(self, normalizer: BetTypeNormalizer | None = None, *, zodiac_year: int = 2026):
        self._normalizer = normalizer or BetTypeNormalizer()
        self._zodiac_year = zodiac_year

    def evaluate_item(self, order_item: Any, lottery_draw: Any) -> ItemSettlementResult:
        draw = self._validate_draw(lottery_draw)
        amount = self._item_amount(order_item)
        draw_regular_numbers = tuple(draw["regular_numbers"])
        draw_special_number = draw["special_number"]
        draw_special_zodiac = get_zodiac(draw_special_number, year=self._zodiac_year)
        common_draw_fields = self._draw_reference_fields(draw_regular_numbers, draw_special_number)
        try:
            normalized = self._normalizer.normalize(
                order_item.bet_type,
                order_item.selection,
                note=getattr(order_item, "note", None),
            )
        except (UnsupportedBetTypeError, InvalidSelectionError) as exc:
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
                draw_special_number=draw_special_number,
                draw_special_zodiac=draw_special_zodiac,
                unsupported_reason=str(exc),
                **common_draw_fields,
            )

        matcher = MATCHERS[normalized.normalized_bet_type]
        if normalized.normalized_bet_type in {SPECIAL_ZODIAC, SPECIAL_ZODIAC_GROUP, SIX_SPECIAL_ZODIAC}:
            is_winner, matched_number, reason = matcher(
                normalized.selection,
                draw_special_number,
                year=self._zodiac_year,
            )
        elif normalized.normalized_bet_type in {
            LINKED_TAIL,
            PING_TAIL,
            NON_HIT_NUMBER,
            REGULAR_NUMBER,
            LIANMA_TWO_TWO,
            LIANMA_THREE_THREE,
            LIANMA_THREE_TWO,
            NUMBER_FUXUAN,
        }:
            is_winner, matched_number, reason = matcher(
                normalized.selection,
                list(draw_regular_numbers),
                draw_special_number,
            )
        else:
            is_winner, matched_number, reason = matcher(normalized.selection, draw_special_number)

        selected_zodiacs = (
            tuple(token for token in normalized.selection.split(",") if token)
            if normalized.normalized_bet_type in {SPECIAL_ZODIAC_GROUP, SIX_SPECIAL_ZODIAC}
            else ()
        )
        matched_zodiac = (
            draw_special_zodiac
            if normalized.normalized_bet_type in {SPECIAL_ZODIAC_GROUP, SIX_SPECIAL_ZODIAC} and is_winner
            else None
        )
        match_fields = self._match_reference_fields(
            normalized.normalized_bet_type,
            normalized.selection,
            draw_regular_numbers,
            draw_special_number,
        )

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
            draw_special_number=draw_special_number,
            draw_special_zodiac=draw_special_zodiac,
            selected_zodiacs=selected_zodiacs,
            matched_zodiac=matched_zodiac,
            **common_draw_fields,
            **match_fields,
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

    def _draw_reference_fields(
        self,
        regular_numbers: tuple[str, ...],
        special_number: str,
    ) -> dict[str, Any]:
        draw_numbers = (*regular_numbers, special_number)
        return {
            "draw_numbers": draw_numbers,
            "draw_tails": tuple(str(tail_number(number)) for number in draw_numbers),
            "draw_regular_numbers": regular_numbers,
            "draw_special_wave": get_wave_color(special_number),
            "draw_special_odd_even": odd_even_label(special_number),
            "draw_special_big_small": size_label(special_number),
        }

    def _match_reference_fields(
        self,
        normalized_type: str,
        selection: str,
        regular_numbers: tuple[str, ...],
        special_number: str,
    ) -> dict[str, Any]:
        draw_numbers = (*regular_numbers, special_number)
        draw_tails = {str(tail_number(number)) for number in draw_numbers}
        if normalized_type == LINKED_TAIL:
            selected_tails = tuple(token for token in selection.split(",") if token)
            return {
                "selected_tails": selected_tails,
                "matched_tails": tuple(tail for tail in selected_tails if tail in draw_tails),
            }
        if normalized_type == PING_TAIL:
            selected_tails = tuple(token for token in selection.split(",") if token)
            regular_tails = {str(tail_number(number)) for number in regular_numbers}
            return {
                "selected_tails": selected_tails,
                "matched_tails": tuple(tail for tail in selected_tails if tail in regular_tails),
            }
        if normalized_type in {LIANMA_TWO_TWO, LIANMA_THREE_THREE, LIANMA_THREE_TWO}:
            if normalized_type == LIANMA_TWO_TWO:
                group_size, required_hits = 2, 2
            elif normalized_type == LIANMA_THREE_THREE:
                group_size, required_hits = 3, 3
            else:
                group_size, required_hits = 3, 2
            selected_groups = parse_lianma_groups(selection)
            matched_groups = matched_lianma_groups(
                selection,
                list(regular_numbers),
                group_size=group_size,
                required_hits=required_hits,
            )
            return {
                "selected_groups": tuple(format_lianma_group(group) for group in selected_groups),
                "matched_groups": tuple(format_lianma_group(group) for group in matched_groups),
            }
        if normalized_type == NUMBER_FUXUAN:
            groups = fuxuan_groups(selection)
            regular_set = set(regular_numbers)
            matched_groups = tuple(group for group in groups if all(number in regular_set for number in group))
            fuxuan_type = selection.split("|", 1)[0] if "|" in selection else None
            selected_numbers = tuple(selection.split("|", 1)[1].split(",")) if "|" in selection else ()
            return {
                "selected_numbers": selected_numbers,
                "selected_groups": tuple(format_lianma_group(group) for group in groups),
                "matched_groups": tuple(format_lianma_group(group) for group in matched_groups),
                "fuxuan_type": fuxuan_type,
            }
        if normalized_type == NON_HIT_NUMBER:
            selected_numbers = tuple(token for token in selection.split(",") if token)
            draw_set = set(draw_numbers)
            return {
                "selected_numbers": selected_numbers,
                "hit_numbers": tuple(number for number in selected_numbers if number in draw_set),
            }
        if normalized_type == REGULAR_NUMBER:
            selected_numbers = tuple(token for token in selection.split(",") if token)
            regular_set = set(regular_numbers)
            return {
                "selected_numbers": selected_numbers,
                "matched_numbers": tuple(number for number in selected_numbers if number in regular_set),
            }
        if normalized_type == PACKAGE_HALF_WAVE:
            selected_halfwaves = tuple(token for token in selection.split(",") if token)
            color = get_wave_color(special_number).removesuffix("波")
            actual_halfwaves = {
                f"{color}{odd_even_label(special_number)}",
                f"{color}{size_label(special_number)}",
            }
            matched_halfwave = next((token for token in selected_halfwaves if token in actual_halfwaves), None)
            return {
                "selected_halfwaves": selected_halfwaves,
                "matched_halfwave": matched_halfwave,
            }
        return {}
