from __future__ import annotations

from datetime import date

import pytest

from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_service import OrderService
from services.settlement_service import SettlementService
from settlement.exceptions import SettlementDataError


def create_draw(draw_service: DrawService, *, special_number: str = "07"):
    regular_numbers = ["01", "02", "03", "04", "05", "06"]
    if special_number in regular_numbers:
        regular_numbers = ["02", "03", "04", "05", "06", "07"]
    return draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number=f"NUM-{special_number}",
            draw_date=date(2026, 6, 11),
            regular_numbers=regular_numbers,
            special_number=special_number,
            source="test",
        )
    )


def create_order(order_service: OrderService, *, items: list[OrderItemCreate]):
    return order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text="complex number settlement",
            source="test",
            items=items,
        )
    )


def test_non_hit_hits_when_all_selected_numbers_are_absent(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="不中", selection="08,09,10", amount="10")],
    )
    draw = create_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_supported is True
    assert item.is_winner is True
    assert item.selected_numbers == ("08", "09", "10")
    assert item.hit_numbers == ()
    assert item.draw_numbers == ("01", "02", "03", "04", "05", "06", "07")


def test_non_hit_misses_when_any_selected_number_appears(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="不中", selection="06,08,09", amount="10")],
    )
    draw = create_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.losing_items == 1
    assert item.is_winner is False
    assert item.hit_numbers == ("06",)
    assert "06" in item.reason


def test_non_hit_invalid_number_is_unsupported(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="不中", selection="08,50", amount="10")],
    )
    draw = create_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.unsupported_items == 1
    assert preview.results[0].is_supported is False
    assert preview.results[0].unsupported_reason


def test_six_special_zodiac_hits_when_special_zodiac_is_selected(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="六肖中特", selection="马,蛇,龙,兔,虎,牛", amount="10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 1
    assert item.is_winner is True
    assert item.draw_special_number == "01"
    assert item.draw_special_zodiac == "马"
    assert item.selected_zodiacs == ("马", "蛇", "龙", "兔", "虎", "牛")
    assert item.matched_zodiac == "马"


def test_six_special_zodiac_misses_when_special_zodiac_is_not_selected(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="六肖中特", selection="蛇,龙,兔,虎,牛,鼠", amount="10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.losing_items == 1
    assert item.is_winner is False
    assert item.matched_zodiac is None


def test_six_special_zodiac_invalid_zodiac_is_unsupported(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="六肖中特", selection="马,蛇,龙,兔,虎,猫", amount="10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.unsupported_items == 1
    assert preview.results[0].is_supported is False
    assert "无法解析六肖中特生肖列表" in preview.results[0].reason


def test_regular_number_hits_only_regular_numbers(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="平码", selection="03", amount="10")],
    )
    draw = create_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 1
    assert item.is_winner is True
    assert item.draw_regular_numbers == ("01", "02", "03", "04", "05", "06")
    assert item.draw_special_number == "07"
    assert item.selected_numbers == ("03",)
    assert item.matched_numbers == ("03",)


def test_regular_number_misses_when_number_only_appears_as_special(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="平码", selection="07", amount="10")],
    )
    draw = create_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.losing_items == 1
    assert item.is_winner is False
    assert item.matched_numbers == ()
    assert "特码 07 不参与" in item.reason


def test_regular_number_invalid_number_is_unsupported(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="平码", selection="00", amount="10")],
    )
    draw = create_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.unsupported_items == 1
    assert preview.results[0].is_supported is False


def test_complex_number_preview_counts_hit_miss_and_unsupported(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[
            OrderItemCreate(bet_type="平码", selection="03", amount="10"),
            OrderItemCreate(bet_type="平码", selection="07", amount="10"),
            OrderItemCreate(bet_type="不中", selection="50", amount="10"),
        ],
    )
    draw = create_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.winning_items == 1
    assert preview.losing_items == 1
    assert preview.unsupported_items == 1


def test_commit_is_blocked_when_complex_number_item_is_unsupported(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(
        order_service,
        items=[
            OrderItemCreate(bet_type="平码", selection="03", amount="10"),
            OrderItemCreate(bet_type="不中", selection="50", amount="10"),
        ],
    )
    draw = create_draw(DrawService(session_factory))

    with pytest.raises(SettlementDataError, match="存在暂不支持玩法"):
        SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    after = order_service.get_order(order.id)
    assert after.raw_text == "complex number settlement"
    assert after.status == "active"
    assert SettlementService(session_factory).count_settlement_records() == 0


def test_commit_is_allowed_without_unsupported_and_does_not_write_payout_fields(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(
        order_service,
        items=[
            OrderItemCreate(bet_type="平码", selection="03", amount="10"),
            OrderItemCreate(bet_type="不中", selection="08,09", amount="10"),
        ],
    )
    draw = create_draw(DrawService(session_factory))

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.win_count == 2
    assert result.lose_count == 0
    assert result.unsupported_items == 0
    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    assert record.hit_count == 2
    assert record.miss_count == 0
    assert record.unsupported_count == 0
    snapshot = record.result_snapshot
    assert snapshot["items"][0]["draw_regular_numbers"] == ["01", "02", "03", "04", "05", "06"]
    assert snapshot["items"][1]["draw_numbers"] == ["01", "02", "03", "04", "05", "06", "07"]
    assert "payout" not in str(snapshot).lower()
    assert "balance" not in str(snapshot).lower()
    assert "rebate" not in str(snapshot).lower()
