"""Persistence helpers for operation logs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import OperationLog


class LogRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, log: OperationLog) -> OperationLog:
        self.session.add(log)
        return log

    def list(
        self,
        *,
        module: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[OperationLog]:
        stmt = select(OperationLog)
        if module:
            stmt = stmt.where(OperationLog.module == module)
        if start_at:
            stmt = stmt.where(OperationLog.created_at >= start_at)
        if end_at:
            stmt = stmt.where(OperationLog.created_at <= end_at)
        stmt = stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))
