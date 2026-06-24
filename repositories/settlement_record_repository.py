"""Persistence helpers for settlement records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from models import Order, SettlementRecord


class SettlementRecordRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, record: SettlementRecord) -> SettlementRecord:
        self.session.add(record)
        return record

    def get(self, record_id: int) -> SettlementRecord | None:
        return self.session.get(
            SettlementRecord,
            record_id,
            options=[
                selectinload(SettlementRecord.order),
                selectinload(SettlementRecord.draw),
                selectinload(SettlementRecord.operation_log),
            ],
        )

    def get_by_order_id(self, order_id: int) -> SettlementRecord | None:
        stmt = (
            self._base_select()
            .where(SettlementRecord.order_id == order_id)
            .order_by(SettlementRecord.settled_at.desc(), SettlementRecord.id.desc())
        )
        return self.session.scalars(stmt).first()

    def get_by_order_ids(self, order_ids: list[int]) -> list[SettlementRecord]:
        normalized_ids = list(dict.fromkeys(order_id for order_id in order_ids if order_id > 0))
        if not normalized_ids:
            return []
        stmt = (
            self._base_select()
            .where(SettlementRecord.order_id.in_(normalized_ids))
            .order_by(SettlementRecord.settled_at.desc(), SettlementRecord.id.desc())
        )
        return list(self.session.scalars(stmt))

    def _base_select(self) -> Select[tuple[SettlementRecord]]:
        return select(SettlementRecord).options(
            selectinload(SettlementRecord.order),
            selectinload(SettlementRecord.draw),
            selectinload(SettlementRecord.operation_log),
        )

    def _apply_filters(
        self,
        stmt,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        stmt = stmt.join(Order, Order.id == SettlementRecord.order_id)
        if region:
            stmt = stmt.where(SettlementRecord.region == region)
        if keyword:
            keyword = keyword.strip()
            if keyword.isdigit():
                stmt = stmt.where(Order.id == int(keyword))
            else:
                stmt = stmt.where(Order.order_no.contains(keyword))
        if start_date:
            stmt = stmt.where(SettlementRecord.settled_at >= start_date)
        if end_date:
            stmt = stmt.where(SettlementRecord.settled_at <= end_date)
        return stmt

    def list(
        self,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SettlementRecord]:
        stmt = self._base_select()
        stmt = self._apply_filters(
            stmt,
            region=region,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
        )
        stmt = stmt.order_by(SettlementRecord.settled_at.desc(), SettlementRecord.id.desc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(
        self,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        stmt = select(func.count(SettlementRecord.id))
        stmt = self._apply_filters(
            stmt,
            region=region,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
        )
        return int(self.session.scalar(stmt) or 0)
