from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from models import Order, OrderItem, SettlementRecord
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from services.settlement_service import SettlementService
from settlement.exceptions import SettlementDataError


def create_draw(draw_service: DrawService, *, special_number: str = "01"):
    return draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number=f"ZODIAC-{special_number}",
            draw_date=date(2026, 6, 11),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number=special_number,
            source="test",
        )
    )


def create_lianxiao_order(order_service: OrderService, *, selection: str):
    return order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text=f"连肖{selection}各10",
            source="test",
            items=[OrderItemCreate(bet_type="连肖", selection=selection, amount="10")],
        )
    )


def create_multi_zodiac_order(session_factory, *, selection: str, amount: str = "10"):
    with session_factory() as session:
        now = datetime.now()
        order = Order(
            order_no=f"ORD-MULTI-{now:%H%M%S%f}",
            customer_name="multi-zodiac",
            channel="test",
            region="澳门",
            source="test",
            raw_text=f"多生肖{selection}各{amount}",
            total_amount=Decimal(amount),
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(order)
        session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                bet_type="多生肖",
                selection=selection,
                amount=Decimal(amount),
            )
        )
        session.commit()
        return order.id


def test_multi_zodiac_hits_when_special_zodiac_is_selected(session_factory) -> None:
    order_id = create_multi_zodiac_order(session_factory, selection="马,蛇")
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order_id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 1
    assert preview.losing_items == 0
    assert preview.unsupported_items == 0
    assert item.is_supported is True
    assert item.is_winner is True
    assert item.draw_special_number == "01"
    assert item.draw_special_zodiac == "马"
    assert item.selected_zodiacs == ("蛇", "马")
    assert item.matched_zodiac == "马"
    assert "开奖" not in item.reason or "特码 01" in item.reason
    assert "投注生肖列表：蛇、马" in item.reason
    assert "命中生肖：马" in item.reason


def test_multi_zodiac_misses_when_special_zodiac_is_not_selected(session_factory) -> None:
    order_id = create_multi_zodiac_order(session_factory, selection="牛,蛇")
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order_id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 0
    assert preview.losing_items == 1
    assert preview.unsupported_items == 0
    assert item.is_supported is True
    assert item.is_winner is False
    assert item.draw_special_zodiac == "马"
    assert item.selected_zodiacs == ("牛", "蛇")
    assert item.matched_zodiac is None
    assert "投注生肖列表：牛、蛇" in item.reason


def test_multi_zodiac_invalid_selection_is_unsupported(session_factory) -> None:
    order_id = create_multi_zodiac_order(session_factory, selection="马X")
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order_id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 0
    assert preview.losing_items == 0
    assert preview.unsupported_items == 1
    assert item.is_supported is False
    assert item.is_winner is None
    assert item.unsupported_reason
    assert "无法解析生肖列表" in item.reason


def test_lianxiao_hits_when_special_zodiac_is_selected(session_factory) -> None:
    order = create_lianxiao_order(OrderService(session_factory), selection="马蛇")
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 1
    assert preview.unsupported_items == 0
    assert item.is_winner is True
    assert item.selection == "蛇,马"
    assert item.selected_zodiacs == ("蛇", "马")
    assert item.matched_zodiac == "马"


def test_lianxiao_misses_when_special_zodiac_is_not_selected(session_factory) -> None:
    order = create_lianxiao_order(OrderService(session_factory), selection="牛,蛇")
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert preview.winning_items == 0
    assert preview.losing_items == 1
    assert preview.unsupported_items == 0
    assert item.is_winner is False
    assert item.draw_special_zodiac == "马"


def test_lianxiao_group_amount_flows_to_preview_but_v2_commit_is_blocked(session_factory) -> None:
    intake = OrderIntakeService(session_factory)
    save_result = intake.parse_and_save(
        "连肖 龙羊猴 各30",
        region="澳门",
        source="test",
        customer_name="连肖金额口径",
        channel="微信",
    )
    assert save_result.success
    assert save_result.order is not None
    assert save_result.order.total_amount == Decimal("30.00")
    draw = create_draw(DrawService(session_factory))

    service = SettlementService(session_factory)
    preview = service.preview_order(save_result.order.id, draw.id)
    item = preview.results[0]

    assert item.bet_type == "连肖"
    assert item.selection == "龙,羊,猴"
    assert item.amount == Decimal("30.00")
    assert preview.total_payout_amount == Decimal("0.00")

    with pytest.raises(SettlementDataError, match="V2规则修复尚未完成"):
        service.commit_order_settlement(save_result.order.id, draw.id)
    assert service.get_settlement_record_by_order_id(save_result.order.id) is None


def test_lianxiao_invalid_selection_is_unsupported(session_factory) -> None:
    order = create_lianxiao_order(OrderService(session_factory), selection="马X")
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.supported_items == 0
    assert preview.unsupported_items == 1
    assert preview.results[0].is_supported is False
    assert "无法解析生肖列表" in preview.results[0].reason


def test_legacy_multi_zodiac_alias_cannot_bypass_v2_lianxiao_gate(session_factory) -> None:
    order_id = create_multi_zodiac_order(session_factory, selection="马,蛇", amount="15")
    draw = create_draw(DrawService(session_factory), special_number="01")

    with pytest.raises(SettlementDataError, match="V2规则别名同样受门禁限制"):
        SettlementService(session_factory).commit_order_settlement(order_id, draw.id)

    with session_factory() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.raw_text == "多生肖马,蛇各15"
        assert order.status == "active"
        assert session.query(SettlementRecord).filter_by(order_id=order_id).first() is None


def test_complex_zodiac_commit_is_blocked_when_any_item_is_unsupported(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text="mixed unsupported",
            source="test",
            items=[
                OrderItemCreate(bet_type="特码", selection="01", amount="10"),
                OrderItemCreate(bet_type="连肖", selection="马X", amount="10"),
            ],
        )
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    with pytest.raises(SettlementDataError, match="存在暂不支持玩法"):
        SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert order_service.get_order(order.id).status == "active"
    assert SettlementService(session_factory).count_settlement_records() == 0


def test_complex_zodiac_preview_does_not_modify_order(session_factory) -> None:
    order_id = create_multi_zodiac_order(session_factory, selection="马,蛇", amount="10")
    draw = create_draw(DrawService(session_factory), special_number="01")
    with session_factory() as session:
        before = session.get(Order, order_id)
        assert before is not None
        before_state = (before.status, before.total_amount, before.raw_text)

    SettlementService(session_factory).preview_order(order_id, draw.id)

    with session_factory() as session:
        after = session.get(Order, order_id)
        assert after is not None
        assert (after.status, after.total_amount, after.raw_text) == before_state
        assert session.query(SettlementRecord).count() == 0
