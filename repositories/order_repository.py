"""Persistence helpers for orders."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from models import Order, OrderItem, SettlementRecord

WINNING_STATUS_UNSETTLED = "未结算"
WINNING_STATUS_SETTLED = "已结算"
WINNING_STATUS_HIT = "命中"
WINNING_STATUS_MISS = "未中"
WINNING_STATUS_PARTIAL = "部分命中"
WINNING_STATUS_UNSUPPORTED = "含不支持"


def _is_missing_zodiac_year_error(exc: OperationalError) -> bool:
    return "zodiac_year" in str(exc)


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
        declarer_name: str | None = None,
        channel: str | None = None,
        bet_type: str | None = None,
        winning_status: str | None = None,
        status: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        if region:
            stmt = stmt.where(Order.region == region)
        if order_no:
            stmt = stmt.where(Order.order_no.contains(order_no))
        if customer_name:
            stmt = stmt.where(Order.customer_name.contains(customer_name))
        if declarer_name:
            stmt = stmt.where(Order.customer_name == declarer_name)
        if channel:
            stmt = stmt.where(Order.channel.contains(channel))
        if bet_type:
            stmt = stmt.where(Order.items.any(OrderItem.bet_type == bet_type))
        if status:
            stmt = stmt.where(Order.status == status)
        if winning_status:
            stmt = self._apply_winning_status_filter(stmt, winning_status)
        if exclude_statuses:
            stmt = stmt.where(Order.status.not_in(exclude_statuses))
        if start_date:
            stmt = stmt.where(Order.created_at >= start_date)
        if end_date:
            stmt = stmt.where(Order.created_at <= end_date)
        return stmt

    def _apply_winning_status_filter(self, stmt, winning_status: str):
        stmt = stmt.outerjoin(SettlementRecord, SettlementRecord.order_id == Order.id)
        if winning_status == WINNING_STATUS_UNSETTLED:
            return stmt.where(Order.status.in_(("active", "pending")))
        if winning_status == WINNING_STATUS_SETTLED:
            return stmt.where(Order.status == "settled")
        if winning_status == WINNING_STATUS_UNSUPPORTED:
            return stmt.where(SettlementRecord.unsupported_count > 0)
        if winning_status == WINNING_STATUS_PARTIAL:
            return stmt.where(
                SettlementRecord.unsupported_count == 0,
                SettlementRecord.hit_count > 0,
                SettlementRecord.miss_count > 0,
            )
        if winning_status == WINNING_STATUS_HIT:
            return stmt.where(
                SettlementRecord.unsupported_count == 0,
                SettlementRecord.hit_count > 0,
                SettlementRecord.miss_count == 0,
            )
        if winning_status == WINNING_STATUS_MISS:
            return stmt.where(
                SettlementRecord.unsupported_count == 0,
                SettlementRecord.hit_count == 0,
                SettlementRecord.miss_count > 0,
            )
        return stmt

    def list(
        self,
        *,
        region: str | None = None,
        order_no: str | None = None,
        customer_name: str | None = None,
        declarer_name: str | None = None,
        channel: str | None = None,
        bet_type: str | None = None,
        winning_status: str | None = None,
        status: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
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
            declarer_name=declarer_name,
            channel=channel,
            bet_type=bet_type,
            winning_status=winning_status,
            status=status,
            exclude_statuses=exclude_statuses,
            start_date=start_date,
            end_date=end_date,
        )
        if winning_status:
            stmt = stmt.distinct()
        stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)
        try:
            return list(self.session.scalars(stmt))
        except OperationalError as exc:
            if not _is_missing_zodiac_year_error(exc):
                raise
            self.session.rollback()
            return []

    def list_for_analysis(
        self,
        *,
        exclude_statuses: tuple[str, ...] | None = None,
    ) -> list[Order]:
        stmt: Select[tuple[Order]] = select(Order).options(selectinload(Order.items))
        stmt = self._apply_filters(stmt, exclude_statuses=exclude_statuses)
        stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc())
        try:
            return list(self.session.scalars(stmt))
        except OperationalError as exc:
            if not _is_missing_zodiac_year_error(exc):
                raise
            self.session.rollback()
            return []

    def _apply_settlement_ledger_filters(
        self,
        stmt,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        stmt = stmt.where(Order.status == "settled")
        if region:
            stmt = stmt.where(Order.region == region)
        if keyword:
            keyword = keyword.strip()
            if keyword.isdigit():
                stmt = stmt.where(Order.id == int(keyword))
            else:
                stmt = stmt.where(Order.order_no.contains(keyword))
        if start_date:
            stmt = stmt.where(Order.updated_at >= start_date)
        if end_date:
            stmt = stmt.where(Order.updated_at <= end_date)
        return stmt

    def list_settlement_ledger(
        self,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Order]:
        stmt: Select[tuple[Order]] = select(Order).options(selectinload(Order.items))
        stmt = self._apply_settlement_ledger_filters(
            stmt,
            region=region,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
        )
        stmt = stmt.order_by(Order.updated_at.desc(), Order.id.desc()).limit(limit).offset(offset)
        try:
            return list(self.session.scalars(stmt))
        except OperationalError as exc:
            if not _is_missing_zodiac_year_error(exc):
                raise
            self.session.rollback()
            return []

    def count_settlement_ledger(
        self,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        stmt = select(func.count(Order.id))
        stmt = self._apply_settlement_ledger_filters(
            stmt,
            region=region,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
        )
        return int(self.session.scalar(stmt) or 0)

    def count(
        self,
        *,
        region: str | None = None,
        order_no: str | None = None,
        customer_name: str | None = None,
        declarer_name: str | None = None,
        channel: str | None = None,
        bet_type: str | None = None,
        winning_status: str | None = None,
        status: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        stmt = select(func.count(func.distinct(Order.id)))
        stmt = self._apply_filters(
            stmt,
            region=region,
            order_no=order_no,
            customer_name=customer_name,
            declarer_name=declarer_name,
            channel=channel,
            bet_type=bet_type,
            winning_status=winning_status,
            status=status,
            exclude_statuses=exclude_statuses,
            start_date=start_date,
            end_date=end_date,
        )
        return int(self.session.scalar(stmt) or 0)

    def list_declarer_names(self) -> list[str]:
        stmt = (
            select(Order.customer_name)
            .where(Order.customer_name.is_not(None), func.trim(Order.customer_name) != "")
            .distinct()
            .order_by(Order.customer_name.asc())
        )
        return [str(name).strip() for name in self.session.scalars(stmt) if str(name).strip()]

    def list_bet_types(self) -> list[str]:
        stmt = (
            select(OrderItem.bet_type)
            .where(func.trim(OrderItem.bet_type) != "")
            .distinct()
            .order_by(OrderItem.bet_type.asc())
        )
        return [str(bet_type).strip() for bet_type in self.session.scalars(stmt) if str(bet_type).strip()]

    def sum_amount(
        self,
        *,
        region: str | None = None,
        status: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(Order.total_amount), 0))
        stmt = self._apply_filters(
            stmt,
            region=region,
            status=status,
            exclude_statuses=exclude_statuses,
            start_date=start_date,
            end_date=end_date,
        )
        return Decimal(self.session.scalar(stmt) or 0)

    def count_by_region(self, *, exclude_statuses: tuple[str, ...] | None = None) -> dict[str, int]:
        stmt = select(Order.region, func.count(Order.id)).group_by(Order.region)
        stmt = self._apply_filters(stmt, exclude_statuses=exclude_statuses)
        return {region: int(count) for region, count in self.session.execute(stmt)}

    def count_by_status(self, *, exclude_statuses: tuple[str, ...] | None = None) -> dict[str, int]:
        stmt = select(Order.status, func.count(Order.id)).group_by(Order.status)
        stmt = self._apply_filters(stmt, exclude_statuses=exclude_statuses)
        return {status: int(count) for status, count in self.session.execute(stmt)}

    def stats_by_region(
        self,
        *,
        region: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[tuple[str, int, Decimal]]:
        stmt = (
            select(Order.region, func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
            .group_by(Order.region)
            .order_by(Order.region.asc())
        )
        stmt = self._apply_filters(
            stmt,
            region=region,
            exclude_statuses=exclude_statuses,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            (label, int(count), Decimal(amount or 0))
            for label, count, amount in self.session.execute(stmt)
        ]

    def stats_by_status(
        self,
        *,
        region: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[tuple[str, int, Decimal]]:
        stmt = (
            select(Order.status, func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
            .group_by(Order.status)
            .order_by(Order.status.asc())
        )
        stmt = self._apply_filters(
            stmt,
            region=region,
            exclude_statuses=exclude_statuses,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            (label, int(count), Decimal(amount or 0))
            for label, count, amount in self.session.execute(stmt)
        ]

    def stats_by_date(
        self,
        *,
        region: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[tuple[str, int, Decimal]]:
        day = func.date(Order.created_at)
        stmt = (
            select(day, func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
            .group_by(day)
            .order_by(day.asc())
        )
        stmt = self._apply_filters(
            stmt,
            region=region,
            exclude_statuses=exclude_statuses,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            (str(label), int(count), Decimal(amount or 0))
            for label, count, amount in self.session.execute(stmt)
        ]

    def stats_by_bet_type(
        self,
        *,
        region: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 20,
    ) -> list[tuple[str, int, Decimal]]:
        stmt = (
            select(
                OrderItem.bet_type,
                func.count(func.distinct(Order.id)),
                func.coalesce(func.sum(OrderItem.amount), 0),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .group_by(OrderItem.bet_type)
            .order_by(func.sum(OrderItem.amount).desc(), OrderItem.bet_type.asc())
        )
        stmt = self._apply_filters(
            stmt,
            region=region,
            exclude_statuses=exclude_statuses,
            start_date=start_date,
            end_date=end_date,
        )
        if limit > 0:
            stmt = stmt.limit(limit)
        return [
            (label, int(count), Decimal(amount or 0))
            for label, count, amount in self.session.execute(stmt)
        ]

    def amount_by_bet_type(
        self,
        *,
        region: str | None = None,
        exclude_statuses: tuple[str, ...] | None = None,
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
        stmt = self._apply_filters(
            stmt,
            region=region,
            exclude_statuses=exclude_statuses,
            start_date=start_date,
            end_date=end_date,
        )
        if limit > 0:
            stmt = stmt.limit(limit)
        return [(bet_type, Decimal(amount or 0)) for bet_type, amount in self.session.execute(stmt)]

    def add_item(self, item: OrderItem) -> OrderItem:
        self.session.add(item)
        return item
