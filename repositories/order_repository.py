"""Persistence helpers for orders."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from models import Order, OrderItem


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, order: Order) -> Order:
        self.session.add(order)
        return order

    def get(self, order_id: int) -> Order | None:
        return self.session.get(
            Order,
            order_id,
            options=[selectinload(Order.items)],
        )

    def get_by_no(self, order_no: str) -> Order | None:
        stmt = select(Order).where(Order.order_no == order_no).options(selectinload(Order.items))
        return self.session.scalars(stmt).first()

    def list(self, *, region: str | None = None, limit: int = 100, offset: int = 0) -> list[Order]:
        stmt: Select[tuple[Order]] = select(Order).options(selectinload(Order.items))
        if region:
            stmt = stmt.where(Order.region == region)
        stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(self, *, region: str | None = None) -> int:
        stmt = select(func.count(Order.id))
        if region:
            stmt = stmt.where(Order.region == region)
        return int(self.session.scalar(stmt) or 0)

    def add_item(self, item: OrderItem) -> OrderItem:
        self.session.add(item)
        return item
