"""DTOs for settlement preview results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


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
    draw_special_number: str | None = None
    draw_special_zodiac: str | None = None
    draw_numbers: tuple[str, ...] = ()
    draw_tails: tuple[str, ...] = ()
    draw_regular_numbers: tuple[str, ...] = ()
    selected_zodiacs: tuple[str, ...] = ()
    matched_zodiac: str | None = None
    selected_tails: tuple[str, ...] = ()
    matched_tails: tuple[str, ...] = ()
    selected_numbers: tuple[str, ...] = ()
    hit_numbers: tuple[str, ...] = ()
    matched_numbers: tuple[str, ...] = ()
    draw_special_wave: str | None = None
    draw_special_odd_even: str | None = None
    draw_special_big_small: str | None = None
    selected_halfwaves: tuple[str, ...] = ()
    matched_halfwave: str | None = None
    unsupported_reason: str | None = None


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
    settlement_record_id: int
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


@dataclass(frozen=True, slots=True)
class SettlementLedgerResult:
    id: int
    order_id: int
    draw_id: int
    operation_log_id: int | None
    order_no: str
    customer_name: str | None
    region: str
    order_status: str
    total_amount: Decimal
    settled_at: datetime
    issue_number: str
    total_items: int
    hit_count: int
    miss_count: int
    unsupported_count: int
    result_snapshot: dict[str, Any]
    order_created_at: datetime
    order_updated_at: datetime
    operation_log_description: str | None = None
