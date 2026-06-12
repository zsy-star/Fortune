"""Persistence helpers for lottery draws."""

from __future__ import annotations

from sqlalchemy import select
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

    def list(self, *, region: str | None = None, limit: int = 100, offset: int = 0) -> list[LotteryDraw]:
        stmt = select(LotteryDraw)
        if region:
            stmt = stmt.where(LotteryDraw.region == region)
        stmt = stmt.order_by(LotteryDraw.draw_date.desc(), LotteryDraw.id.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_latest(self, region: str) -> LotteryDraw | None:
        stmt = (
            select(LotteryDraw)
            .where(LotteryDraw.region == region)
            .order_by(LotteryDraw.draw_date.desc(), LotteryDraw.id.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()
