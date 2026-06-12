from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService


def create_order(service: OrderService, *, region: str, customer: str, channel: str, amount: str = "10"):
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel=channel,
            region=region,
            raw_text=f"{customer}{amount}",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="1", amount=amount)],
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
