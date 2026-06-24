"""Persistent configuration models for the local settings center."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class OddsRebatePlan(Base):
    __tablename__ = "odds_rebate_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list[OddsRebateItem]] = relationship(
        "OddsRebateItem",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="OddsRebateItem.id",
    )
    declarers: Mapped[list[DeclarerSetting]] = relationship(
        "DeclarerSetting",
        back_populates="plan",
    )


class OddsRebateItem(Base):
    __tablename__ = "odds_rebate_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("odds_rebate_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bet_type: Mapped[str] = mapped_column(String(128), nullable=False)
    odds: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    rebate: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    plan: Mapped[OddsRebatePlan] = relationship("OddsRebatePlan", back_populates="items")

    __table_args__ = (
        UniqueConstraint("plan_id", "bet_type", name="uq_odds_rebate_items_plan_bet_type"),
    )


class DeclarerSetting(Base):
    __tablename__ = "declarer_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("odds_rebate_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    plan: Mapped[OddsRebatePlan] = relationship("OddsRebatePlan", back_populates="declarers")
