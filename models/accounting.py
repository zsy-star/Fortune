"""Customer account and balance ledger ORM models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class CustomerAccount(Base):
    __tablename__ = "customer_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    ledger_entries: Mapped[list[AccountLedgerEntry]] = relationship(
        "AccountLedgerEntry",
        back_populates="customer",
        foreign_keys="AccountLedgerEntry.customer_id",
        order_by="AccountLedgerEntry.created_at.desc()",
    )

    __table_args__ = (
        Index("ix_customer_accounts_status_updated", "status", "updated_at"),
    )


class AccountLedgerEntry(Base):
    __tablename__ = "account_ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[int | None] = mapped_column(nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    settlement_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("settlement_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    adjustment_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("adjustment_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    audit_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("operation_logs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_reversed: Mapped[bool] = mapped_column(nullable=False, default=False)
    reversed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_ledger_entries.id", ondelete="SET NULL"),
        nullable=True,
    )

    customer: Mapped[CustomerAccount] = relationship(
        "CustomerAccount",
        back_populates="ledger_entries",
        foreign_keys=[customer_id],
    )
    reversed_by: Mapped[AccountLedgerEntry | None] = relationship(
        "AccountLedgerEntry",
        remote_side=[id],
        post_update=True,
    )

    __table_args__ = (
        UniqueConstraint("reversed_by_id", name="uq_account_ledger_entries_reversed_by"),
        Index("ix_account_ledger_customer_created", "customer_id", "created_at"),
        Index("ix_account_ledger_entry_type_created", "entry_type", "created_at"),
        Index("ix_account_ledger_source", "source_type", "source_id"),
    )
