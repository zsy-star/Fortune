"""Operation log service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models import OperationLog
from repositories.log_repository import LogRepository
from schemas.log_schema import OperationLogResult


class LogService:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory

    def create_log(
        self,
        *,
        module: str,
        action: str,
        description: str,
        operator: str | None = None,
        related_type: str | None = None,
        related_id: int | None = None,
        session: Session | None = None,
    ) -> OperationLog:
        log = OperationLog(
            module=module,
            action=action,
            description=description,
            operator=operator,
            related_type=related_type,
            related_id=related_id,
        )
        if session is not None:
            LogRepository(session).add(log)
            return log

        with self._session_factory() as local_session:
            LogRepository(local_session).add(log)
            local_session.commit()
            local_session.refresh(log)
            return log

    def list_logs(
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
    ) -> list[OperationLogResult]:
        limit, offset = self._validate_limit_offset(limit, offset)
        with self._session_factory() as session:
            logs = LogRepository(session).list(
                module=module,
                action=action,
                operator=operator,
                related_type=related_type,
                related_id=related_id,
                start_date=start_date,
                end_date=end_date,
                keyword=keyword,
                limit=limit,
                offset=offset,
            )
            return [self._to_result(log) for log in logs]

    def count_logs(
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
        with self._session_factory() as session:
            return LogRepository(session).count(
                module=module,
                action=action,
                operator=operator,
                related_type=related_type,
                related_id=related_id,
                start_date=start_date,
                end_date=end_date,
                keyword=keyword,
            )

    def _validate_limit_offset(self, limit: int, offset: int) -> tuple[int, int]:
        if limit < 1:
            limit = 1
        if limit > 500:
            limit = 500
        if offset < 0:
            offset = 0
        return limit, offset

    def _to_result(self, log: OperationLog) -> OperationLogResult:
        return OperationLogResult(
            id=log.id,
            module=log.module,
            action=log.action,
            description=log.description,
            operator=log.operator,
            related_type=log.related_type,
            related_id=log.related_id,
            created_at=log.created_at,
        )
