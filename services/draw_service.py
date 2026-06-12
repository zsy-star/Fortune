"""Lottery draw persistence service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

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

    def save_draw(self, draw_create: LotteryDrawCreate) -> tuple[LotteryDraw, str]:
        """Insert, skip, or update one draw.

        Returns:
            ``(draw, action)`` where action is ``created``, ``skipped``, or ``updated``.
        """
        with self._session_factory() as session:
            repo = DrawRepository(session)
            try:
                existing = repo.get(draw_create.region, draw_create.issue_number)
                if existing is None:
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
                        action="sync_create",
                        description=f"Synced new draw {draw.region} {draw.issue_number}",
                        related_type="lottery_draw",
                        related_id=draw.id,
                        session=session,
                    )
                    session.commit()
                    session.refresh(draw)
                    return draw, "created"

                changed = (
                    existing.draw_date != draw_create.draw_date
                    or list(existing.regular_numbers) != list(draw_create.regular_numbers)
                    or existing.special_number != draw_create.special_number
                    or existing.source != draw_create.source
                    or existing.status != draw_create.status
                )
                if not changed:
                    session.commit()
                    return existing, "skipped"

                existing.draw_date = draw_create.draw_date
                existing.regular_numbers = list(draw_create.regular_numbers)
                existing.special_number = draw_create.special_number
                existing.source = draw_create.source
                existing.status = draw_create.status
                session.flush()
                self._log_service.create_log(
                    module="draw",
                    action="sync_update",
                    description=f"Updated draw {existing.region} {existing.issue_number}",
                    related_type="lottery_draw",
                    related_id=existing.id,
                    session=session,
                )
                session.commit()
                session.refresh(existing)
                return existing, "updated"
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
        issue_number: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LotteryDraw]:
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            return DrawRepository(session).list(
                region=region,
                issue_number=issue_number,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )

    def count_draws(
        self,
        *,
        region: str | None = None,
        issue_number: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            return DrawRepository(session).count(
                region=region,
                issue_number=issue_number,
                start_date=start_date,
                end_date=end_date,
            )

    def get_latest_draw(self, region: str) -> LotteryDraw | None:
        region = normalize_region(region)
        with self._session_factory() as session:
            return DrawRepository(session).get_latest(region)
