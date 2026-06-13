from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from domain.bet_types import BET_TYPE_SPECIAL, REGION_HONG_KONG, REGION_MACAU
from domain.exceptions import DomainError
from models import Order, OrderItem
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.log_service import LogService
from services.order_service import OrderService


def create_order(
    service: OrderService,
    *,
    region: str = REGION_MACAU,
    amount: str = "10",
    items: list[OrderItemCreate] | None = None,
):
    return service.create_order(
        OrderCreate(
            customer_name="void-test",
            channel="test",
            region=region,
            raw_text=f"void test {amount}",
            source="test",
            items=items or [OrderItemCreate(bet_type=BET_TYPE_SPECIAL, selection="01", amount=amount)],
        )
    )


def order_void_logs(session_factory) -> list:
    return LogService(session_factory).list_logs(module="order", action="void")


def test_void_missing_order_fails_without_log(session_factory) -> None:
    service = OrderService(session_factory)

    with pytest.raises(DomainError, match="Order not found"):
        service.void_order(999999, "wrong order")

    assert order_void_logs(session_factory) == []


def test_void_empty_reason_fails_without_log(session_factory) -> None:
    service = OrderService(session_factory)
    order = create_order(service)

    with pytest.raises(DomainError, match="reason cannot be empty"):
        service.void_order(order.id, "  ")

    assert service.get_order(order.id).status == "active"
    assert order_void_logs(session_factory) == []


def test_active_order_can_be_voided_and_writes_operation_log(session_factory) -> None:
    service = OrderService(session_factory)
    order = create_order(service)

    result = service.void_order(order.id, "input mistake", operator="tester")

    assert result.order_id == order.id
    assert result.order_no == order.order_no
    assert result.status_before == "active"
    assert result.status_after == "voided"
    assert result.reason == "input mistake"
    assert result.operator == "tester"
    assert result.operation_log_id > 0
    assert service.get_order(order.id).status == "voided"

    logs = order_void_logs(session_factory)
    assert len(logs) == 1
    assert logs[0].id == result.operation_log_id
    assert logs[0].operator == "tester"
    assert logs[0].related_type == "order"
    assert logs[0].related_id == order.id
    assert order.order_no in logs[0].description
    assert "input mistake" in logs[0].description
    assert "status_before=active" in logs[0].description
    assert "status_after=voided" in logs[0].description


def test_voided_order_is_not_physically_deleted_and_items_remain(session_factory) -> None:
    service = OrderService(session_factory)
    order = create_order(
        service,
        items=[
            OrderItemCreate(bet_type=BET_TYPE_SPECIAL, selection="01", amount="10"),
            OrderItemCreate(bet_type=BET_TYPE_SPECIAL, selection="02", amount="20"),
        ],
    )

    service.void_order(order.id, "keep audit trail")

    with session_factory() as session:
        saved = session.get(Order, order.id)
        item_count = session.scalar(select(func.count(OrderItem.id)).where(OrderItem.order_id == order.id))

    assert saved is not None
    assert saved.status == "voided"
    assert item_count == 2


def test_settled_order_cannot_be_voided(session_factory) -> None:
    service = OrderService(session_factory)
    order = create_order(service)
    with session_factory() as session:
        saved = session.get(Order, order.id)
        assert saved is not None
        saved.status = "settled"
        session.commit()

    with pytest.raises(DomainError, match="Settled order cannot be voided"):
        service.void_order(order.id, "settled mistake")

    assert service.get_order(order.id).status == "settled"
    assert order_void_logs(session_factory) == []


def test_voided_order_cannot_be_voided_twice(session_factory) -> None:
    service = OrderService(session_factory)
    order = create_order(service)
    service.void_order(order.id, "first void")

    with pytest.raises(DomainError, match="already voided"):
        service.void_order(order.id, "second void")

    assert service.get_order(order.id).status == "voided"
    assert len(order_void_logs(session_factory)) == 1


def test_void_failure_rolls_back_status_and_success_log(monkeypatch, session_factory) -> None:
    service = OrderService(session_factory)
    order = create_order(service)

    def fail_create_log(**kwargs):
        raise RuntimeError("log store unavailable")

    monkeypatch.setattr(service._log_service, "create_log", fail_create_log)

    with pytest.raises(RuntimeError, match="log store unavailable"):
        service.void_order(order.id, "should rollback")

    assert service.get_order(order.id).status == "active"
    assert order_void_logs(session_factory) == []


def test_voided_orders_are_excluded_from_dashboard_effective_statistics(session_factory) -> None:
    service = OrderService(session_factory)
    active = create_order(service, region=REGION_MACAU, amount="10")
    voided = create_order(service, region=REGION_HONG_KONG, amount="20")
    service.void_order(voided.id, "exclude from totals")

    summary = service.get_dashboard_summary(recent_limit=10)

    assert service.count_orders() == 2
    assert summary.total_order_count == 1
    assert summary.today_order_count == 1
    assert summary.total_amount == Decimal("10.00")
    assert summary.today_amount == Decimal("10.00")
    assert summary.pending_order_count == 1
    assert summary.settled_order_count == 0
    assert [order.id for order in summary.recent_orders] == [active.id]
    assert summary.amount_by_bet_type == ((BET_TYPE_SPECIAL, Decimal("10.00")),)


def test_voided_orders_are_excluded_from_analysis_effective_statistics(session_factory) -> None:
    service = OrderService(session_factory)
    active = create_order(service, region=REGION_MACAU, amount="10")
    voided = create_order(service, region=REGION_HONG_KONG, amount="20")
    service.void_order(voided.id, "exclude from analysis")

    summary = service.get_order_analysis_summary(recent_limit=10)

    assert summary.total_order_count == 1
    assert summary.total_amount == Decimal("10.00")
    assert summary.average_order_amount == Decimal("10.00")
    assert [(g.label, g.order_count, g.total_amount) for g in summary.by_region] == [
        (REGION_MACAU, 1, Decimal("10.00"))
    ]
    assert [(g.label, g.order_count, g.total_amount) for g in summary.by_status] == [
        ("active", 1, Decimal("10.00"))
    ]
    assert {g.label: (g.order_count, g.total_amount) for g in summary.by_bet_type} == {
        BET_TYPE_SPECIAL: (1, Decimal("10.00"))
    }
    assert [order.id for order in summary.recent_orders] == [active.id]


def test_voided_orders_do_not_appear_in_settlement_ledger(session_factory) -> None:
    service = OrderService(session_factory)
    voided = create_order(service)
    service.void_order(voided.id, "not settled ledger")

    assert service.count_settlement_ledger() == 0
    assert service.list_settlement_ledger() == []
