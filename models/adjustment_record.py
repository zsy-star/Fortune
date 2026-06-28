"""Adjustment record ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class AdjustmentRecord(Base):
    __tablename__ = "adjustment_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    adjustment_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    source_filter: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    original_total: Mapped[str] = mapped_column(String(32), nullable=False)
    adjustment_total: Mapped[str] = mapped_column(String(32), nullable=False)
    after_total: Mapped[str] = mapped_column(String(32), nullable=False)
    item_count: Mapped[int] = mapped_column(nullable=False)
    positive_count: Mapped[int] = mapped_column(nullable=False)
    negative_count: Mapped[int] = mapped_column(nullable=False)
    record_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_adjustment_records_type_created", "adjustment_type", "created_at"),
        Index("ix_adjustment_records_region_created", "region", "created_at"),
    )
