"""Settlement record ORM model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class SettlementRecord(Base):
    __tablename__ = "settlement_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    draw_id: Mapped[int] = mapped_column(
        ForeignKey("lottery_draws.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("operation_logs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    region: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    issue_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    total_items: Mapped[int] = mapped_column(nullable=False)
    hit_count: Mapped[int] = mapped_column(nullable=False)
    miss_count: Mapped[int] = mapped_column(nullable=False)
    unsupported_count: Mapped[int] = mapped_column(nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    order = relationship("Order")
    draw = relationship("LotteryDraw")
    operation_log = relationship("OperationLog")

    __table_args__ = (
        UniqueConstraint("order_id", name="uq_settlement_records_order_id"),
        Index("ix_settlement_records_region_settled_at", "region", "settled_at"),
        Index("ix_settlement_records_issue", "region", "issue_number"),
    )
