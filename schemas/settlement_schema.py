"""DTOs for settlement preview results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ItemSettlementResult:
    order_item_id: int | None
    bet_type: str
    normalized_bet_type: str | None
    selection: str
    amount: Decimal
    is_supported: bool
    is_winner: bool | None
    matched_number: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class UnsupportedBetResult:
    bet_type: str
    selection: str
    reason: str


@dataclass(frozen=True, slots=True)
class OrderSettlementPreview:
    order_id: int
    order_no: str
    region: str
    issue_number: str
    draw_date: date
    regular_numbers: list[str]
    special_number: str
    total_items: int
    supported_items: int
    unsupported_items: int
    winning_items: int
    losing_items: int
    results: list[ItemSettlementResult]


@dataclass(frozen=True, slots=True)
class OrderSettlementCommitResult:
    order_id: int
    draw_id: int
    region: str
    issue_number: str
    total_items: int
    supported_items: int
    unsupported_items: int
    win_count: int
    lose_count: int
    order_status_before: str
    order_status_after: str
    results: list[ItemSettlementResult]
    warnings: list[str]
    operation_log_id: int
