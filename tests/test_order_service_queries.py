from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from models import Order
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService


def create_order(
    service: OrderService,
    *,
    region: str,
    customer: str,
    channel: str,
    amount: str = "10",
    items: list[OrderItemCreate] | None = None,
):
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel=channel,
            region=region,
            raw_text=f"{customer}{amount}",
            source="test",
            items=items or [OrderItemCreate(bet_type="特码", selection="1", amount=amount)],
        )
    )


def test_order_service_query_filters_and_detached_dto(session_factory) -> None:
    service = OrderService(session_factory)
    first = create_order(service, region="澳门", customer="张三", channel="微信", amount="10.50")
    second = create_order(service, region="香港", customer="李四", channel="现金", amount="20.00")

    assert [o.id for o in service.list_orders(limit=10)] == [second.id, first.id]
    assert service.count_orders() == 2
    assert service.count_orders(region="澳门") == 1
    assert [o.id for o in service.list_orders(region="澳门")] == [first.id]
    assert service.list_orders(order_no=first.order_no[-6:])[0].id == first.id
    assert service.list_orders(customer_name="李")[0].id == second.id
    assert service.list_orders(channel="现")[0].id == second.id
    assert service.count_orders(status="active") == 2

    now = datetime.now()
    assert service.count_orders(start_date=now - timedelta(days=1), end_date=now + timedelta(days=1)) == 2
    assert [o.id for o in service.list_orders(limit=1, offset=1)] == [first.id]

    detail = service.get_order(first.id)
    assert detail is not None
    assert detail.order_no == first.order_no
    assert detail.items[0].amount == Decimal("10.50")
    assert detail.items[0].selection == "01"

    by_no = service.get_order_by_no(first.order_no)
    assert by_no is not None
    assert by_no.items[0].bet_type == "特码"


def test_order_service_dashboard_summary_counts_amounts_and_recent_orders(session_factory) -> None:
    service = OrderService(session_factory)
    macau = create_order(
        service,
        region="澳门",
        customer="澳门客",
        channel="微信",
        amount="30",
        items=[
            OrderItemCreate(bet_type="特码", selection="1", amount="10"),
            OrderItemCreate(bet_type="特码", selection="2", amount="10"),
            OrderItemCreate(bet_type="特码", selection="3", amount="10"),
        ],
    )
    hk = create_order(service, region="香港", customer="香港客", channel="现金", amount="20")
    old = create_order(service, region="澳门", customer="旧订单", channel="微信", amount="5")

    with session_factory() as session:
        old_order = session.get(Order, old.id)
        hk_order = session.get(Order, hk.id)
        assert old_order is not None
        assert hk_order is not None
        old_order.created_at = datetime.now() - timedelta(days=1)
        old_order.updated_at = old_order.created_at
        hk_order.status = "settled"
        session.commit()

    summary = service.get_dashboard_summary(recent_limit=10)
    assert summary.total_order_count == 3
    assert summary.today_order_count == 2
    assert summary.total_amount == Decimal("55.00")
    assert summary.today_amount == Decimal("50.00")
    assert summary.macau_order_count == 2
    assert summary.hong_kong_order_count == 1
    assert summary.pending_order_count == 2
    assert summary.settled_order_count == 1
    assert summary.amount_by_bet_type == (("特码", Decimal("55.00")),)
    assert [order.id for order in summary.recent_orders][:2] == [hk.id, macau.id]

    hk_summary = service.get_dashboard_summary(region="香港", recent_limit=10)
    assert hk_summary.total_order_count == 3
    assert hk_summary.amount_by_bet_type == (("特码", Decimal("20.00")),)
    assert [order.id for order in hk_summary.recent_orders] == [hk.id]


def test_order_service_analysis_summary_groups_amounts_and_trend(session_factory) -> None:
    service = OrderService(session_factory)
    today = datetime.now().date()
    macau = create_order(
        service,
        region="澳门",
        customer="分析澳门",
        channel="微信",
        amount="30",
        items=[
            OrderItemCreate(bet_type="特码", selection="1", amount="10"),
            OrderItemCreate(bet_type="特码", selection="2", amount="10"),
            OrderItemCreate(bet_type="特码", selection="3", amount="10"),
        ],
    )
    hk = create_order(
        service,
        region="香港",
        customer="分析香港",
        channel="现金",
        amount="20",
        items=[OrderItemCreate(bet_type="包半波", selection="红单", amount="20")],
    )
    old = create_order(service, region="澳门", customer="前日澳门", channel="微信", amount="5")

    old_day = today - timedelta(days=2)
    with session_factory() as session:
        old_order = session.get(Order, old.id)
        hk_order = session.get(Order, hk.id)
        assert old_order is not None
        assert hk_order is not None
        old_order.created_at = datetime.combine(old_day, datetime.min.time())
        old_order.updated_at = old_order.created_at
        hk_order.status = "settled"
        session.commit()

    summary = service.get_order_analysis_summary(recent_limit=10)
    assert summary.total_order_count == 3
    assert summary.total_amount == Decimal("55.00")
    assert summary.average_order_amount == Decimal("18.33")
    assert [(g.label, g.order_count, g.total_amount) for g in summary.by_region] == [
        ("澳门", 2, Decimal("35.00")),
        ("香港", 1, Decimal("20.00")),
    ]
    assert ("active", 2, Decimal("35.00")) in [
        (g.label, g.order_count, g.total_amount) for g in summary.by_status
    ]
    assert ("settled", 1, Decimal("20.00")) in [
        (g.label, g.order_count, g.total_amount) for g in summary.by_status
    ]
    by_date = {g.label: (g.order_count, g.total_amount) for g in summary.by_date}
    assert by_date[today.isoformat()] == (2, Decimal("50.00"))
    assert by_date[old_day.isoformat()] == (1, Decimal("5.00"))
    by_bet_type = {g.label: (g.order_count, g.total_amount) for g in summary.by_bet_type}
    assert by_bet_type["特码"] == (2, Decimal("35.00"))
    assert by_bet_type["包半波"] == (1, Decimal("20.00"))
    trend = {g.label: (g.order_count, g.total_amount) for g in summary.recent_7_day_trend}
    assert trend[today.isoformat()] == (2, Decimal("50.00"))
    assert trend[old_day.isoformat()] == (1, Decimal("5.00"))
    assert len(summary.recent_7_day_trend) == 7
    assert [order.id for order in summary.recent_orders][:2] == [hk.id, macau.id]

    hk_summary = service.get_order_analysis_summary(region="香港")
    assert hk_summary.total_order_count == 1
    assert hk_summary.total_amount == Decimal("20.00")
    assert [(g.label, g.order_count, g.total_amount) for g in hk_summary.by_region] == [
        ("香港", 1, Decimal("20.00"))
    ]
