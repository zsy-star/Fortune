"""Order DTOs used between parsers, UI, and services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from domain.bet_types import normalize_bet_type, normalize_region
from domain.exceptions import InvalidAmountError


def to_decimal_amount(value: Decimal | int | float | str, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise InvalidAmountError(f"Invalid amount: {value!r}") from None

    if not amount.is_finite():
        raise InvalidAmountError(f"Amount must be finite: {value!r}")
    if allow_zero:
        if amount < 0:
            raise InvalidAmountError(f"Amount cannot be negative: {value!r}")
    elif amount <= 0:
        raise InvalidAmountError(f"Amount must be greater than zero: {value!r}")
    return amount


@dataclass(slots=True)
class OrderItemCreate:
    bet_type: str
    selection: str
    amount: Decimal | int | float | str
    odds: Decimal | int | float | str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        self.bet_type = normalize_bet_type(self.bet_type)
        self.selection = str(self.selection).strip()
        if not self.selection:
            raise ValueError("Order item selection cannot be empty")
        self.amount = to_decimal_amount(self.amount)
        if self.odds is not None:
            self.odds = to_decimal_amount(self.odds)
        if self.note is not None:
            self.note = self.note.strip() or None


@dataclass(slots=True)
class OrderCreate:
    region: str
    raw_text: str
    source: str
    items: list[OrderItemCreate]
    customer_name: str | None = None
    channel: str | None = None

    def __post_init__(self) -> None:
        self.region = normalize_region(self.region)
        self.raw_text = str(self.raw_text).strip()
        if not self.raw_text:
            raise ValueError("Order raw_text cannot be empty")
        self.source = str(self.source).strip()
        if not self.source:
            raise ValueError("Order source cannot be empty")
        if not self.items:
            raise ValueError("Order must contain at least one item")
        normalized_items: list[OrderItemCreate] = []
        for item in self.items:
            if not isinstance(item, OrderItemCreate):
                raise TypeError("Order items must be OrderItemCreate instances")
            normalized_items.append(item)
        self.items = normalized_items
        if self.customer_name is not None:
            self.customer_name = self.customer_name.strip() or None
        if self.channel is not None:
            self.channel = self.channel.strip() or None


@dataclass(frozen=True, slots=True)
class OrderResult:
    id: int
    order_no: str
    region: str
    total_amount: Decimal
    status: str
    item_count: int


@dataclass(frozen=True, slots=True)
class OrderItemResult:
    id: int
    bet_type: str
    selection: str
    amount: Decimal
    odds: Decimal | None
    note: str | None


@dataclass(frozen=True, slots=True)
class OrderSummary:
    id: int
    order_no: str
    customer_name: str | None
    channel: str | None
    region: str
    source: str | None
    raw_text: str
    total_amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
    item_count: int


@dataclass(frozen=True, slots=True)
class OrderDetailResult:
    id: int
    order_no: str
    customer_name: str | None
    channel: str | None
    region: str
    source: str | None
    raw_text: str
    total_amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResult]
