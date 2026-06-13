"""Persistence helpers for operation logs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models import OperationLog


class LogRepository:
    def __init__(self, session: Session):
        self.session = session

    def _apply_filters(
        self,
        stmt,
        *,
        module: str | None = None,
        action: str | None = None,
        operator: str | None = None,
        related_type: str | None = None,
        related_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        keyword: str | None = None,
    ):
        if module:
            stmt = stmt.where(OperationLog.module.contains(module))
        if action:
            stmt = stmt.where(OperationLog.action.contains(action))
        if operator:
            stmt = stmt.where(OperationLog.operator.contains(operator))
        if related_type:
            stmt = stmt.where(OperationLog.related_type.contains(related_type))
        if related_id is not None:
            stmt = stmt.where(OperationLog.related_id == related_id)
        if start_date:
            stmt = stmt.where(OperationLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(OperationLog.created_at <= end_date)
        if keyword:
            stmt = stmt.where(OperationLog.description.contains(keyword))
        return stmt

    def add(self, log: OperationLog) -> OperationLog:
        self.session.add(log)
        return log

    def list(
        self,
        *,
        module: str | None = None,
        action: str | None = None,
        operator: str | None = None,
        related_type: str | None = None,
        related_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        keyword: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[OperationLog]:
        stmt = select(OperationLog)
        stmt = self._apply_filters(
            stmt,
            module=module,
            action=action,
            operator=operator,
            related_type=related_type,
            related_id=related_id,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
        )
        stmt = stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(
        self,
        *,
        module: str | None = None,
        action: str | None = None,
        operator: str | None = None,
        related_type: str | None = None,
        related_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        keyword: str | None = None,
    ) -> int:
        stmt = select(func.count(OperationLog.id))
        stmt = self._apply_filters(
            stmt,
            module=module,
            action=action,
            operator=operator,
            related_type=related_type,
            related_id=related_id,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
        )
        return int(self.session.scalar(stmt) or 0)
