"""Lottery draw ORM model."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class LotteryDraw(Base):
    __tablename__ = "lottery_draws"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(16), nullable=False)
    issue_number: Mapped[str] = mapped_column(String(32), nullable=False)
    draw_date: Mapped[date] = mapped_column(Date, nullable=False)
    regular_numbers: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    special_number: Mapped[str] = mapped_column(String(2), nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("region", "issue_number", name="uq_lottery_draw_region_issue"),
        Index("ix_lottery_draws_region_draw_date", "region", "draw_date"),
    )
