from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from domain.exceptions import InvalidNumberError
from models import OperationLog, Order
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService


def test_create_order_with_multiple_items(session_factory) -> None:
    service = OrderService(session_factory)
    result = service.create_order(
        OrderCreate(
            customer_name="张三",
            channel="个人微信",
            region="澳门",
            raw_text="1各0.10\n2各0.20",
            source="manual",
            zodiac_year=2025,
            items=[
                OrderItemCreate(bet_type="特码", selection="1", amount="0.10"),
                OrderItemCreate(bet_type="特码", selection="2", amount=Decimal("0.20")),
            ],
        )
    )

    assert result.total_amount == Decimal("0.30")
    assert result.item_count == 2
    assert result.zodiac_year == 2025

    with session_factory() as session:
        order = session.scalars(select(Order).where(Order.id == result.id)).one()
        assert order.total_amount == Decimal("0.30")
        assert order.zodiac_year == 2025
        assert [item.selection for item in order.items] == ["01", "02"]
        logs = session.scalars(select(OperationLog)).all()
        assert len(logs) == 1
        assert logs[0].module == "order"
        assert logs[0].related_id == order.id


def test_create_order_rolls_back_on_invalid_item(session_factory) -> None:
    service = OrderService(session_factory)

    with pytest.raises(InvalidNumberError):
        service.create_order(
            OrderCreate(
                region="澳门",
                raw_text="1各10\n0各10",
                source="manual",
                items=[
                    OrderItemCreate(bet_type="特码", selection="1", amount="10"),
                    OrderItemCreate(bet_type="特码", selection="0", amount="10"),
                ],
            )
        )

    with session_factory() as session:
        assert session.scalar(select(func.count(Order.id))) == 0
        assert session.scalars(select(Order)).all() == []
        assert session.scalars(select(OperationLog)).all() == []
