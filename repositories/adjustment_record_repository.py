"""Persistence helpers for adjustment records."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import AdjustmentRecord


class AdjustmentRecordRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, record: AdjustmentRecord) -> AdjustmentRecord:
        self.session.add(record)
        return record

    def get(self, record_id: int) -> AdjustmentRecord | None:
        return self.session.get(AdjustmentRecord, record_id)

    def list(
        self,
        *,
        adjustment_type: str | None = None,
        region: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AdjustmentRecord]:
        stmt = select(AdjustmentRecord)
        if adjustment_type:
            stmt = stmt.where(AdjustmentRecord.adjustment_type == adjustment_type)
        if region:
            stmt = stmt.where(AdjustmentRecord.region == region)
        stmt = stmt.order_by(AdjustmentRecord.created_at.desc(), AdjustmentRecord.id.desc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(
        self,
        *,
        adjustment_type: str | None = None,
        region: str | None = None,
    ) -> int:
        stmt = select(func.count(AdjustmentRecord.id))
        if adjustment_type:
            stmt = stmt.where(AdjustmentRecord.adjustment_type == adjustment_type)
        if region:
            stmt = stmt.where(AdjustmentRecord.region == region)
        return int(self.session.scalar(stmt) or 0)
