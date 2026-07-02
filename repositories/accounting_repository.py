"""Persistence helpers for customer accounts and ledger entries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import AccountLedgerEntry, CustomerAccount


class CustomerAccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, account: CustomerAccount) -> CustomerAccount:
        self.session.add(account)
        return account

    def get(self, account_id: int) -> CustomerAccount | None:
        return self.session.get(CustomerAccount, account_id)

    def get_by_name(self, customer_name: str) -> CustomerAccount | None:
        stmt = select(CustomerAccount).where(CustomerAccount.customer_name == customer_name)
        return self.session.scalars(stmt).first()

    def list(
        self,
        *,
        status: str | None = None,
        keyword: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[CustomerAccount]:
        stmt = select(CustomerAccount)
        if status:
            stmt = stmt.where(CustomerAccount.status == status)
        if keyword:
            stmt = stmt.where(
                CustomerAccount.customer_name.contains(keyword)
                | CustomerAccount.display_name.contains(keyword)
            )
        stmt = stmt.order_by(CustomerAccount.updated_at.desc(), CustomerAccount.id.desc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(self, *, status: str | None = None, keyword: str | None = None) -> int:
        stmt = select(func.count(CustomerAccount.id))
        if status:
            stmt = stmt.where(CustomerAccount.status == status)
        if keyword:
            stmt = stmt.where(
                CustomerAccount.customer_name.contains(keyword)
                | CustomerAccount.display_name.contains(keyword)
            )
        return int(self.session.scalar(stmt) or 0)


class AccountLedgerRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, entry: AccountLedgerEntry) -> AccountLedgerEntry:
        self.session.add(entry)
        return entry

    def get(self, entry_id: int) -> AccountLedgerEntry | None:
        return self.session.get(AccountLedgerEntry, entry_id)

    def get_by_source(self, source_type: str, source_id: int) -> AccountLedgerEntry | None:
        stmt = select(AccountLedgerEntry).where(
            AccountLedgerEntry.source_type == source_type,
            AccountLedgerEntry.source_id == source_id,
        )
        return self.session.scalars(stmt).first()

    def list(
        self,
        *,
        customer_id: int | None = None,
        customer_name: str | None = None,
        entry_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AccountLedgerEntry]:
        stmt = select(AccountLedgerEntry)
        stmt = self._apply_filters(
            stmt,
            customer_id=customer_id,
            customer_name=customer_name,
            entry_type=entry_type,
            start_date=start_date,
            end_date=end_date,
        )
        stmt = stmt.order_by(AccountLedgerEntry.created_at.desc(), AccountLedgerEntry.id.desc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(
        self,
        *,
        customer_id: int | None = None,
        customer_name: str | None = None,
        entry_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        stmt = select(func.count(AccountLedgerEntry.id))
        stmt = self._apply_filters(
            stmt,
            customer_id=customer_id,
            customer_name=customer_name,
            entry_type=entry_type,
            start_date=start_date,
            end_date=end_date,
        )
        return int(self.session.scalar(stmt) or 0)

    def _apply_filters(
        self,
        stmt,
        *,
        customer_id: int | None = None,
        customer_name: str | None = None,
        entry_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        if customer_id is not None:
            stmt = stmt.where(AccountLedgerEntry.customer_id == customer_id)
        if customer_name:
            stmt = stmt.where(AccountLedgerEntry.customer_name.contains(customer_name))
        if entry_type:
            stmt = stmt.where(AccountLedgerEntry.entry_type == entry_type)
        if start_date:
            stmt = stmt.where(AccountLedgerEntry.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AccountLedgerEntry.created_at <= end_date)
        return stmt
