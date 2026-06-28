from __future__ import annotations

from datetime import date

from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_service import OrderService
from services.settlement_service import SettlementService


def create_tail_draw(draw_service: DrawService):
    return draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="TAIL-1",
            draw_date=date(2026, 6, 11),
            regular_numbers=["01", "12", "23", "34", "45", "06"],
            special_number="19",
            source="test",
        )
    )


def create_halfwave_draw(draw_service: DrawService, *, special_number: str = "01"):
    return draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number=f"HALF-{special_number}",
            draw_date=date(2026, 6, 11),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number=special_number,
            source="test",
        )
    )


def create_order(order_service: OrderService, *, items: list[OrderItemCreate]):
    return order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text="tail and halfwave settlement",
            source="test",
            items=items,
        )
    )


def test_linked_tail_hits_when_all_selected_tails_appear(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="连尾", selection="1尾、2尾", amount="10")],
    )
    draw = create_tail_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 1
    assert item.is_winner is True
    assert item.draw_numbers == ("01", "12", "23", "34", "45", "06", "19")
    assert item.draw_tails == ("1", "2", "3", "4", "5", "6", "9")
    assert item.selected_tails == ("1", "2")
    assert item.matched_tails == ("1", "2")


def test_linked_tail_misses_when_any_selected_tail_is_absent(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="连尾", selection="1尾,8尾", amount="10")],
    )
    draw = create_tail_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.losing_items == 1
    assert item.is_winner is False
    assert item.selected_tails == ("1", "8")
    assert item.matched_tails == ("1",)
    assert "未全部出现" in item.reason


def test_linked_tail_invalid_tail_is_unsupported(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="连尾", selection="10尾", amount="10")],
    )
    draw = create_tail_draw(DrawService(session_factory))

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.unsupported_items == 1
    assert preview.results[0].is_supported is False
    assert preview.results[0].unsupported_reason


def test_package_halfwave_hits_when_special_matches_any_combo(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="包半波", selection="蓝双,红小", amount="10")],
    )
    draw = create_halfwave_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 1
    assert item.is_winner is True
    assert item.draw_special_number == "01"
    assert item.draw_special_wave == "红波"
    assert item.draw_special_odd_even == "单"
    assert item.draw_special_big_small == "小"
    assert item.selected_halfwaves == ("蓝双", "红小")
    assert item.matched_halfwave == "红小"


def test_package_halfwave_misses_when_special_matches_no_combo(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="包半波", selection="蓝双,绿大", amount="10")],
    )
    draw = create_halfwave_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.losing_items == 1
    assert item.is_winner is False
    assert item.matched_halfwave is None
    assert "未命中" in item.reason


def test_package_halfwave_invalid_combo_is_unsupported(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="包半波", selection="红中", amount="10")],
    )
    draw = create_halfwave_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.unsupported_items == 1
    assert preview.results[0].is_supported is False
    assert preview.results[0].unsupported_reason


def test_tail_and_halfwave_snapshot_contains_reference_data(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[
            OrderItemCreate(bet_type="连尾", selection="1尾,2尾", amount="10"),
            OrderItemCreate(bet_type="包半波", selection="红单,红小", amount="10"),
        ],
    )
    draw = create_tail_draw(DrawService(session_factory))

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.win_count == 2
    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    snapshot = record.result_snapshot
    tail_item, halfwave_item = snapshot["items"]
    assert tail_item["draw_numbers"] == ["01", "12", "23", "34", "45", "06", "19"]
    assert tail_item["draw_tails"] == ["1", "2", "3", "4", "5", "6", "9"]
    assert tail_item["selected_tails"] == ["1", "2"]
    assert tail_item["matched_tails"] == ["1", "2"]
    assert halfwave_item["draw_special_number"] == "19"
    assert halfwave_item["draw_special_wave"] == "红波"
    assert halfwave_item["draw_special_odd_even"] == "单"
    assert halfwave_item["draw_special_big_small"] == "小"
    assert halfwave_item["selected_halfwaves"] == ["红单", "红小"]
    assert halfwave_item["matched_halfwave"] in {"红单", "红小"}
    assert "payout" not in str(snapshot).lower()
    assert "balance" not in str(snapshot).lower()
    assert "rebate" not in str(snapshot).lower()
