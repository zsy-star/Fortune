from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import AdjustmentRecord, OperationLog, Order, OrderItem
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService
from services.risk_adjustment_service import RiskAdjustmentService
from services.settings_service import SettingsService


def create_order(
    service: OrderService,
    *,
    region: str = "澳门",
    bet_type: str = "特码",
    selection: str = "01",
    amount: str = "10",
):
    return service.create_order(
        OrderCreate(
            customer_name="风控测试",
            channel="pytest",
            region=region,
            raw_text=f"{bet_type} {selection} {amount}",
            source="test",
            items=[OrderItemCreate(bet_type=bet_type, selection=selection, amount=amount)],
        )
    )


def test_special_risk_table_expands_numbers_and_semantic_inputs(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, bet_type="特码", selection="25", amount="100")
    create_order(order_service, bet_type="特码", selection="马", amount="5")
    create_order(order_service, bet_type="特码波色", selection="红波", amount="2")
    service = RiskAdjustmentService(session_factory)

    rows = service.build_special_risk_table()
    by_number = {row.number: row for row in rows}

    assert len(rows) == 49
    assert by_number["25"].raw_stake_amount == Decimal("105.00")
    assert by_number["01"].raw_stake_amount == Decimal("7.00")
    parsed = service.parse_special_throw_text("25=100,37=50\n红波大=3\n合大=2\n尾1=1\n1头=4")
    parsed_by_number = {entry.number: entry.amount for entry in parsed}
    assert parsed_by_number["25"] >= Decimal("100.00")
    assert parsed_by_number["29"] >= Decimal("3.00")
    assert parsed_by_number["19"] >= Decimal("4.00")


def test_special_suggestions_apply_and_reverse_without_modifying_orders(session_factory) -> None:
    order_service = OrderService(session_factory)
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "特码", "2", "0")
    create_order(order_service, bet_type="特码", selection="25", amount="100")
    service = RiskAdjustmentService(session_factory)
    rows = service.build_special_risk_table()
    suggestion = service.generate_special_throw_suggestions(rows, "99")
    entries = service.parse_special_throw_text("25=10")
    with session_factory() as session:
        before_amount = session.scalars(select(OrderItem.amount)).one()

    result = service.apply_special_throw(entries, region="全部", reason="测试抛出")
    after_throw = {row.number: row for row in service.build_special_risk_table()}
    reversal = service.reverse_record(result.record.id, reason="测试撤销")
    after_reverse = {row.number: row for row in service.build_special_risk_table()}

    assert "25=1.00" in suggestion
    assert result.record.adjustment_type == "special_throw"
    assert reversal.record.adjustment_type == "special_throw_reversal"
    assert after_throw["25"].thrown_amount == Decimal("10.00")
    assert after_reverse["25"].thrown_amount == Decimal("0.00")
    with pytest.raises(ValueError, match="已撤销"):
        service.reverse_record(result.record.id, reason="重复撤销")
    with session_factory() as session:
        assert session.scalars(select(OrderItem.amount)).one() == before_amount
        assert session.scalar(select(func.count(Order.id))) == 1
        assert session.scalar(select(func.count(AdjustmentRecord.id))) == 2
        actions = list(session.scalars(select(OperationLog.action).order_by(OperationLog.id)))
        assert "adjustment/special_throw" in actions
        assert "adjustment/special_throw_reversal" in actions


def test_lianxiao_groups_parse_apply_and_reverse(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, bet_type="连肖", selection="龙羊猴", amount="40")
    create_order(order_service, bet_type="连肖", selection="猴,羊,龙", amount="60")
    service = RiskAdjustmentService(session_factory)

    rows = service.build_lianxiao_risk_table()
    entries = service.parse_lianxiao_throw_text("龙,羊,猴=30\n龙-羊-猴=20")
    result = service.apply_lianxiao_throw(entries, region="全部", reason="连肖测试")
    after_throw = {row.zodiac_group: row for row in service.build_lianxiao_risk_table()}
    reversal = service.reverse_record(result.record.id, reason="连肖撤销")
    after_reverse = {row.zodiac_group: row for row in service.build_lianxiao_risk_table()}

    assert len(rows) == 1
    assert rows[0].zodiac_group == "龙,猴,羊"
    assert rows[0].raw_amount == Decimal("100.00")
    assert entries[0].zodiac_group == "龙,猴,羊"
    assert entries[0].amount == Decimal("50.00")
    assert result.record.adjustment_type == "lianxiao_throw"
    assert reversal.record.adjustment_type == "lianxiao_throw_reversal"
    assert after_throw["龙,猴,羊"].thrown_amount == Decimal("50.00")
    assert after_reverse["龙,猴,羊"].thrown_amount == Decimal("0.00")
    with pytest.raises(ValueError, match="重复生肖"):
        service.parse_lianxiao_throw_text("龙龙羊=10")
