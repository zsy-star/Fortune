"""DTOs for customer accounts and balance ledger entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CustomerAccountResult:
    id: int
    customer_name: str
    display_name: str | None
    balance: Decimal
    status: str
    note: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AccountLedgerEntryResult:
    id: int
    customer_id: int
    customer_name: str
    direction: str
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    entry_type: str
    source_type: str | None
    source_id: int | None
    order_id: int | None
    settlement_record_id: int | None
    adjustment_record_id: int | None
    reason: str
    operator: str | None
    created_at: datetime
    audit_log_id: int | None
    is_reversed: bool
    reversed_by_id: int | None


@dataclass(frozen=True, slots=True)
class LedgerMutationResult:
    account: CustomerAccountResult
    entry: AccountLedgerEntryResult
    operation_log_id: int
