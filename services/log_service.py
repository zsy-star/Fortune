"""Operation log service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models import OperationLog
from repositories.log_repository import LogRepository


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
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[OperationLog]:
        with self._session_factory() as session:
            return LogRepository(session).list(
                module=module,
                start_at=start_at,
                end_at=end_at,
                limit=limit,
                offset=offset,
            )
