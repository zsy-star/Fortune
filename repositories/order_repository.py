"""Persistence helpers for orders."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

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

    def _apply_filters(
        self,
        stmt,
        *,
        region: str | None = None,
        order_no: str | None = None,
        customer_name: str | None = None,
        channel: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        if region:
            stmt = stmt.where(Order.region == region)
        if order_no:
            stmt = stmt.where(Order.order_no.contains(order_no))
        if customer_name:
            stmt = stmt.where(Order.customer_name.contains(customer_name))
        if channel:
            stmt = stmt.where(Order.channel.contains(channel))
        if status:
            stmt = stmt.where(Order.status == status)
        if start_date:
            stmt = stmt.where(Order.created_at >= start_date)
        if end_date:
            stmt = stmt.where(Order.created_at <= end_date)
        return stmt

    def list(
        self,
        *,
        region: str | None = None,
        order_no: str | None = None,
        customer_name: str | None = None,
        channel: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Order]:
        stmt: Select[tuple[Order]] = select(Order).options(selectinload(Order.items))
        stmt = self._apply_filters(
            stmt,
            region=region,
            order_no=order_no,
            customer_name=customer_name,
            channel=channel,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )
        stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(
        self,
        *,
        region: str | None = None,
        order_no: str | None = None,
        customer_name: str | None = None,
        channel: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        stmt = select(func.count(Order.id))
        stmt = self._apply_filters(
            stmt,
            region=region,
            order_no=order_no,
            customer_name=customer_name,
            channel=channel,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )
        return int(self.session.scalar(stmt) or 0)

    def sum_amount(
        self,
        *,
        region: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(Order.total_amount), 0))
        stmt = self._apply_filters(
            stmt,
            region=region,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )
        return Decimal(self.session.scalar(stmt) or 0)

    def count_by_region(self) -> dict[str, int]:
        stmt = select(Order.region, func.count(Order.id)).group_by(Order.region)
        return {region: int(count) for region, count in self.session.execute(stmt)}

    def count_by_status(self) -> dict[str, int]:
        stmt = select(Order.status, func.count(Order.id)).group_by(Order.status)
        return {status: int(count) for status, count in self.session.execute(stmt)}

    def amount_by_bet_type(
        self,
        *,
        region: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 20,
    ) -> list[tuple[str, Decimal]]:
        stmt = (
            select(OrderItem.bet_type, func.coalesce(func.sum(OrderItem.amount), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .group_by(OrderItem.bet_type)
            .order_by(func.sum(OrderItem.amount).desc(), OrderItem.bet_type.asc())
        )
        stmt = self._apply_filters(stmt, region=region, start_date=start_date, end_date=end_date)
        if limit > 0:
            stmt = stmt.limit(limit)
        return [(bet_type, Decimal(amount or 0)) for bet_type, amount in self.session.execute(stmt)]

    def add_item(self, item: OrderItem) -> OrderItem:
        self.session.add(item)
        return item
