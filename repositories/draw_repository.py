"""Persistence helpers for lottery draws."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import LotteryDraw


class DrawRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, draw: LotteryDraw) -> LotteryDraw:
        self.session.add(draw)
        return draw

    def flush(self) -> None:
        self.session.flush()

    def get(self, region: str, issue_number: str) -> LotteryDraw | None:
        stmt = select(LotteryDraw).where(
            LotteryDraw.region == region,
            LotteryDraw.issue_number == issue_number,
        )
        return self.session.scalars(stmt).first()

    def get_by_id(self, draw_id: int) -> LotteryDraw | None:
        return self.session.get(LotteryDraw, draw_id)

    def _apply_filters(
        self,
        stmt,
        *,
        region: str | None = None,
        issue_number: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        if region:
            stmt = stmt.where(LotteryDraw.region == region)
        if issue_number:
            stmt = stmt.where(LotteryDraw.issue_number.contains(issue_number))
        if start_date:
            stmt = stmt.where(LotteryDraw.draw_date >= start_date)
        if end_date:
            stmt = stmt.where(LotteryDraw.draw_date <= end_date)
        return stmt

    def list(
        self,
        *,
        region: str | None = None,
        issue_number: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LotteryDraw]:
        stmt = select(LotteryDraw)
        stmt = self._apply_filters(
            stmt,
            region=region,
            issue_number=issue_number,
            start_date=start_date,
            end_date=end_date,
        )
        stmt = stmt.order_by(
            LotteryDraw.draw_date.desc(),
            LotteryDraw.issue_number.desc(),
            LotteryDraw.id.desc(),
        ).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(
        self,
        *,
        region: str | None = None,
        issue_number: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        stmt = select(func.count(LotteryDraw.id))
        stmt = self._apply_filters(
            stmt,
            region=region,
            issue_number=issue_number,
            start_date=start_date,
            end_date=end_date,
        )
        return int(self.session.scalar(stmt) or 0)

    def get_latest(self, region: str) -> LotteryDraw | None:
        stmt = (
            select(LotteryDraw)
            .where(LotteryDraw.region == region)
            .order_by(LotteryDraw.draw_date.desc(), LotteryDraw.issue_number.desc(), LotteryDraw.id.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()
