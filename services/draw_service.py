"""Lottery draw persistence service."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.database import SessionLocal
from domain.bet_types import normalize_region
from domain.exceptions import DuplicateDrawError
from models import LotteryDraw
from repositories.draw_repository import DrawRepository
from schemas.draw_schema import LotteryDrawCreate
from services.log_service import LogService


class DrawService:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory
        self._log_service = LogService(session_factory)

    def create_draw(self, draw_create: LotteryDrawCreate) -> LotteryDraw:
        with self._session_factory() as session:
            try:
                repo = DrawRepository(session)
                existing = repo.get(draw_create.region, draw_create.issue_number)
                if existing is not None:
                    raise DuplicateDrawError(
                        f"Draw already exists: {draw_create.region} {draw_create.issue_number}"
                    )

                draw = LotteryDraw(
                    region=draw_create.region,
                    issue_number=draw_create.issue_number,
                    draw_date=draw_create.draw_date,
                    regular_numbers=list(draw_create.regular_numbers),
                    special_number=draw_create.special_number,
                    source=draw_create.source,
                    status=draw_create.status,
                )
                repo.add(draw)
                session.flush()
                self._log_service.create_log(
                    module="draw",
                    action="create",
                    description=f"Created draw {draw.region} {draw.issue_number}",
                    related_type="lottery_draw",
                    related_id=draw.id,
                    session=session,
                )
                session.commit()
                session.refresh(draw)
                return draw
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateDrawError("Draw violates unique constraints") from exc
            except Exception:
                session.rollback()
                raise

    def get_draw(self, region: str, issue_number: str) -> LotteryDraw | None:
        region = normalize_region(region)
        with self._session_factory() as session:
            return DrawRepository(session).get(region, issue_number)

    def list_draws(
        self,
        *,
        region: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LotteryDraw]:
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            return DrawRepository(session).list(region=region, limit=limit, offset=offset)

    def get_latest_draw(self, region: str) -> LotteryDraw | None:
        region = normalize_region(region)
        with self._session_factory() as session:
            return DrawRepository(session).get_latest(region)
