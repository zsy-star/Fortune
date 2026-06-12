"""Order persistence service."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.database import SessionLocal
from domain.bet_types import BET_TYPE_NUMBER, BET_TYPE_SPECIAL, normalize_bet_type, normalize_region
from domain.exceptions import DomainError
from domain.number_rules import normalize_number
from models import Order, OrderItem
from repositories.order_repository import OrderRepository
from schemas.order_schema import (
    OrderCreate,
    OrderDetailResult,
    OrderItemResult,
    OrderResult,
    OrderSummary,
)
from services.log_service import LogService

_SELECTION_SPLIT = re.compile(r"[,，、\s]+")


def _standardize_selection(bet_type: str, selection: str) -> str:
    text = selection.strip()
    if bet_type in {BET_TYPE_SPECIAL, BET_TYPE_NUMBER}:
        parts = [part for part in _SELECTION_SPLIT.split(text) if part]
        if parts and all(part.isdigit() for part in parts):
            return ",".join(normalize_number(part) for part in parts)
    return text


class OrderService:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory
        self._log_service = LogService(session_factory)

    def create_order(self, order_create: OrderCreate) -> OrderResult:
        if not order_create.items:
            raise ValueError("Order must contain at least one item")

        region = normalize_region(order_create.region)
        total_amount = sum((Decimal(item.amount) for item in order_create.items), Decimal("0"))
        if total_amount <= 0:
            raise ValueError("Order total amount must be greater than zero")

        with self._session_factory() as session:
            try:
                repo = OrderRepository(session)
                order = Order(
                    order_no=self._generate_order_no(),
                    customer_name=order_create.customer_name,
                    channel=order_create.channel,
                    region=region,
                    source=order_create.source,
                    raw_text=order_create.raw_text,
                    total_amount=total_amount,
                    status="active",
                )
                repo.add(order)
                session.flush()

                for item_create in order_create.items:
                    bet_type = normalize_bet_type(item_create.bet_type)
                    item = OrderItem(
                        order_id=order.id,
                        bet_type=bet_type,
                        selection=_standardize_selection(bet_type, item_create.selection),
                        amount=Decimal(item_create.amount),
                        odds=Decimal(item_create.odds) if item_create.odds is not None else None,
                        note=item_create.note,
                    )
                    repo.add_item(item)

                session.flush()
                self._log_service.create_log(
                    module="order",
                    action="create",
                    description=f"Created order {order.order_no}",
                    related_type="order",
                    related_id=order.id,
                    session=session,
                )
                session.commit()
                session.refresh(order)
                return OrderResult(
                    id=order.id,
                    order_no=order.order_no,
                    region=order.region,
                    total_amount=order.total_amount,
                    status=order.status,
                    item_count=len(order.items),
                )
            except Exception:
                session.rollback()
                raise

    def get_order(self, order_id: int) -> OrderDetailResult | None:
        with self._session_factory() as session:
            order = OrderRepository(session).get(order_id)
            return self._to_detail(order) if order else None

    def get_order_by_no(self, order_no: str) -> OrderDetailResult | None:
        with self._session_factory() as session:
            order = OrderRepository(session).get_by_no(order_no)
            return self._to_detail(order) if order else None

    def list_orders(
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
    ) -> list[OrderSummary]:
        limit, offset = self._validate_limit_offset(limit, offset)
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            orders = OrderRepository(session).list(
                region=region,
                order_no=order_no,
                customer_name=customer_name,
                channel=channel,
                status=status,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )
            return [self._to_summary(order) for order in orders]

    def count_orders(
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
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            return OrderRepository(session).count(
                region=region,
                order_no=order_no,
                customer_name=customer_name,
                channel=channel,
                status=status,
                start_date=start_date,
                end_date=end_date,
            )

    def _generate_order_no(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"ORD{timestamp}{uuid4().hex[:8].upper()}"

    def _validate_limit_offset(self, limit: int, offset: int) -> tuple[int, int]:
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        if offset < 0:
            offset = 0
        return limit, offset

    def _to_summary(self, order: Order) -> OrderSummary:
        return OrderSummary(
            id=order.id,
            order_no=order.order_no,
            customer_name=order.customer_name,
            channel=order.channel,
            region=order.region,
            source=order.source,
            raw_text=order.raw_text,
            total_amount=order.total_amount,
            status=order.status,
            created_at=order.created_at,
            updated_at=order.updated_at,
            item_count=len(order.items),
        )

    def _to_detail(self, order: Order) -> OrderDetailResult:
        return OrderDetailResult(
            id=order.id,
            order_no=order.order_no,
            customer_name=order.customer_name,
            channel=order.channel,
            region=order.region,
            source=order.source,
            raw_text=order.raw_text,
            total_amount=order.total_amount,
            status=order.status,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=[
                OrderItemResult(
                    id=item.id,
                    bet_type=item.bet_type,
                    selection=item.selection,
                    amount=item.amount,
                    odds=item.odds,
                    note=item.note,
                )
                for item in order.items
            ],
        )
