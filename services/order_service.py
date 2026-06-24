"""Order persistence service."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
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
from repositories.settlement_record_repository import SettlementRecordRepository
from schemas.order_schema import (
    OrderAnalysisGroup,
    OrderAnalysisSummary,
    OrderCreate,
    OrderDashboardSummary,
    OrderDetailResult,
    OrderItemResult,
    OrderResult,
    OrderSummary,
    OrderVoidResult,
)
from schemas.settlement_schema import SettlementLedgerResult
from services.log_service import LogService

_SELECTION_SPLIT = re.compile(r"[,，、\s]+")
ORDER_STATUS_ACTIVE = "active"
ORDER_STATUS_PENDING = "pending"
ORDER_STATUS_SETTLED = "settled"
ORDER_STATUS_VOIDED = "voided"
_VOIDABLE_STATUSES = {ORDER_STATUS_ACTIVE, ORDER_STATUS_PENDING}
_EXCLUDED_FROM_EFFECTIVE_STATS = (ORDER_STATUS_VOIDED,)


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
                now = datetime.now()
                order = Order(
                    order_no=self._generate_order_no(),
                    customer_name=order_create.customer_name,
                    channel=order_create.channel,
                    region=region,
                    source=order_create.source,
                    raw_text=order_create.raw_text,
                    total_amount=total_amount,
                    status="active",
                    created_at=now,
                    updated_at=now,
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
                log_description = f"Created order {order.order_no}"
                if order.customer_name:
                    log_description += f"; declarer={order.customer_name}"
                self._log_service.create_log(
                    module="order",
                    action="create",
                    description=log_description,
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

    def void_order(
        self,
        order_id: int,
        reason: str,
        operator: str = "system",
    ) -> OrderVoidResult:
        reason = str(reason).strip()
        if not reason:
            raise DomainError("Order void reason cannot be empty")
        operator = str(operator).strip() or "system"

        with self._session_factory() as session:
            try:
                repo = OrderRepository(session)
                order = repo.get(order_id)
                if order is None:
                    raise DomainError(f"Order not found: {order_id}")
                if order.status == ORDER_STATUS_SETTLED:
                    raise DomainError(f"Settled order cannot be voided: {order.order_no}")
                if order.status == ORDER_STATUS_VOIDED:
                    raise DomainError(f"Order already voided: {order.order_no}")
                if order.status not in _VOIDABLE_STATUSES:
                    raise DomainError(f"Order status cannot be voided: {order.status}")

                status_before = order.status
                voided_at = datetime.now()
                order.status = ORDER_STATUS_VOIDED
                order.updated_at = voided_at
                log = self._log_service.create_log(
                    module="order",
                    action="void",
                    description=(
                        f"Voided order {order.order_no}; order_id={order.id}; "
                        f"reason={reason}; status_before={status_before}; "
                        f"status_after={ORDER_STATUS_VOIDED}; operator={operator}; result=success"
                    ),
                    operator=operator,
                    related_type="order",
                    related_id=order.id,
                    session=session,
                )
                session.flush()
                result = OrderVoidResult(
                    order_id=order.id,
                    order_no=order.order_no,
                    status_before=status_before,
                    status_after=order.status,
                    reason=reason,
                    operator=operator,
                    operation_log_id=log.id,
                    voided_at=voided_at,
                )
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise

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

    def list_settlement_ledger(
        self,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SettlementLedgerResult]:
        limit, offset = self._validate_limit_offset(limit, offset)
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            records = SettlementRecordRepository(session).list(
                region=region,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )
            return [self._to_settlement_ledger_result(record) for record in records]

    def count_settlement_ledger(
        self,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            return SettlementRecordRepository(session).count(
                region=region,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
            )

    def get_dashboard_summary(
        self,
        *,
        region: str | None = None,
        today: date | None = None,
        recent_limit: int = 5,
    ) -> OrderDashboardSummary:
        target_day = today or datetime.now().date()
        day_start = datetime.combine(target_day, time.min)
        day_end = datetime.combine(target_day, time.max)
        recent_limit, _ = self._validate_limit_offset(recent_limit, 0)
        detail_region = normalize_region(region) if region is not None else None

        with self._session_factory() as session:
            repo = OrderRepository(session)
            region_counts = repo.count_by_region(exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS)
            status_counts = repo.count_by_status(exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS)
            recent_orders = tuple(
                self._to_summary(order)
                for order in repo.list(
                    region=detail_region,
                    limit=recent_limit,
                    exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                )
            )
            return OrderDashboardSummary(
                total_order_count=repo.count(exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS),
                today_order_count=repo.count(
                    start_date=day_start,
                    end_date=day_end,
                    exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                ),
                total_amount=repo.sum_amount(exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS),
                today_amount=repo.sum_amount(
                    start_date=day_start,
                    end_date=day_end,
                    exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                ),
                macau_order_count=region_counts.get("澳门", 0),
                hong_kong_order_count=region_counts.get("香港", 0),
                pending_order_count=status_counts.get(ORDER_STATUS_ACTIVE, 0)
                + status_counts.get(ORDER_STATUS_PENDING, 0),
                settled_order_count=status_counts.get(ORDER_STATUS_SETTLED, 0),
                recent_orders=recent_orders,
                amount_by_bet_type=tuple(
                    repo.amount_by_bet_type(
                        region=detail_region,
                        exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                    )
                ),
            )

    def get_order_analysis_summary(
        self,
        *,
        region: str | None = None,
        today: date | None = None,
        recent_limit: int = 8,
    ) -> OrderAnalysisSummary:
        target_day = today or datetime.now().date()
        trend_start_day = target_day - timedelta(days=6)
        trend_start = datetime.combine(trend_start_day, time.min)
        trend_end = datetime.combine(target_day, time.max)
        recent_limit, _ = self._validate_limit_offset(recent_limit, 0)
        detail_region = normalize_region(region) if region is not None else None

        with self._session_factory() as session:
            repo = OrderRepository(session)
            total_order_count = repo.count(
                region=detail_region,
                exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
            )
            total_amount = repo.sum_amount(
                region=detail_region,
                exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
            )
            average_order_amount = (
                (total_amount / Decimal(total_order_count)).quantize(Decimal("0.01"))
                if total_order_count
                else Decimal("0")
            )
            trend_by_label = {
                label: OrderAnalysisGroup(label, count, amount)
                for label, count, amount in repo.stats_by_date(
                    region=detail_region,
                    start_date=trend_start,
                    end_date=trend_end,
                    exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                )
            }
            trend = []
            for offset in range(7):
                label = (trend_start_day + timedelta(days=offset)).isoformat()
                trend.append(trend_by_label.get(label, OrderAnalysisGroup(label, 0, Decimal("0"))))

            return OrderAnalysisSummary(
                total_order_count=total_order_count,
                total_amount=total_amount,
                average_order_amount=average_order_amount,
                by_region=self._to_analysis_groups(
                    repo.stats_by_region(
                        region=detail_region,
                        exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                    )
                ),
                by_status=self._to_analysis_groups(
                    repo.stats_by_status(
                        region=detail_region,
                        exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                    )
                ),
                by_date=self._to_analysis_groups(
                    repo.stats_by_date(
                        region=detail_region,
                        exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                    )
                ),
                by_bet_type=self._to_analysis_groups(
                    repo.stats_by_bet_type(
                        region=detail_region,
                        exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                    )
                ),
                recent_7_day_trend=tuple(trend),
                recent_orders=tuple(
                    self._to_summary(order)
                    for order in repo.list(
                        region=detail_region,
                        limit=recent_limit,
                        exclude_statuses=_EXCLUDED_FROM_EFFECTIVE_STATS,
                    )
                ),
            )

    def _to_analysis_groups(self, rows: list[tuple[str, int, Decimal]]) -> tuple[OrderAnalysisGroup, ...]:
        return tuple(OrderAnalysisGroup(label, count, amount) for label, count, amount in rows)

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

    def _to_settlement_ledger_result(self, record) -> SettlementLedgerResult:
        order = record.order
        log = record.operation_log
        return SettlementLedgerResult(
            id=record.id,
            order_id=record.order_id,
            draw_id=record.draw_id,
            operation_log_id=record.operation_log_id,
            order_no=order.order_no,
            customer_name=order.customer_name,
            region=record.region,
            order_status=order.status,
            total_amount=record.total_amount,
            settled_at=record.settled_at,
            issue_number=record.issue_number,
            total_items=record.total_items,
            hit_count=record.hit_count,
            miss_count=record.miss_count,
            unsupported_count=record.unsupported_count,
            result_snapshot=record.result_snapshot,
            order_created_at=order.created_at,
            order_updated_at=order.updated_at,
            operation_log_description=log.description if log else None,
        )
