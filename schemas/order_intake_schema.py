"""DTOs for order intake preview and save results."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.zodiac_config import get_default_zodiac_year, validate_zodiac_year
from schemas.order_schema import OrderCreate, OrderItemCreate, OrderResult


@dataclass(slots=True)
class IntakeMetadata:
    customer_name: str | None = None
    config_plan_name: str | None = None
    channel: str | None = None
    region: str | None = None
    source: str = "record_window"
    raw_text: str = ""
    zodiac_year: int | None = None

    def __post_init__(self) -> None:
        self.zodiac_year = validate_zodiac_year(self.zodiac_year or get_default_zodiac_year())


@dataclass(slots=True)
class IntakeItemPreview:
    source_line: str
    original_bet_type: str
    normalized_bet_type: str | None
    original_selection: str
    normalized_selection: str | None
    amount: Decimal | None
    is_valid: bool
    warning: str | None = None
    error: str | None = None
    order_bet_type: str | None = None
    order_selection: str | None = None
    settlement_support_status: str | None = None
    settlement_support_message: str | None = None
    settlement_support_suggestion: str | None = None


@dataclass(slots=True)
class IntakeTableRow:
    row_number: int
    region: str
    bet_type: str
    selection: str
    total_amount: Decimal | int | float | str
    per_item_amount: Decimal | int | float | str | None = None
    note: str | None = None
    source_line: str | None = None


@dataclass(slots=True)
class OrderIntakePreview:
    raw_text: str
    region: str | None
    customer_name: str | None
    channel: str | None
    source: str
    config_plan_name: str | None = None
    zodiac_year: int | None = None
    items: list[IntakeItemPreview] = field(default_factory=list)
    total_amount: Decimal = Decimal("0")
    valid_items: int = 0
    invalid_items: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    can_save: bool = False
    order_items: list[OrderItemCreate] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.total_amount = Decimal(str(self.total_amount))
        self.zodiac_year = validate_zodiac_year(self.zodiac_year or get_default_zodiac_year())


@dataclass(slots=True)
class OrderIntakeSaveResult:
    success: bool
    order: OrderResult | None = None
    preview: OrderIntakePreview | None = None
    error: str | None = None
