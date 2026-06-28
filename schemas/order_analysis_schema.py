"""DTOs for the read-only order analysis workbench."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class NumberAnalysisRow:
    row_id: int
    number: int
    zodiac: str
    display: str
    bet_amount: Decimal
    profit_loss: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ZodiacFrequencyRow:
    zodiac: str
    count: int


@dataclass(frozen=True, slots=True)
class ZodiacAmountRow:
    zodiac: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class OrderAnalysisWorkbench:
    filter_key: str
    filter_label: str
    order_count: int
    item_count: int
    total_amount: Decimal
    number_rows: tuple[NumberAnalysisRow, ...]
    lianxiao_frequency: tuple[ZodiacFrequencyRow, ...]
    pingte_zodiac_amounts: tuple[ZodiacAmountRow, ...]
    report_text: str

    @property
    def total_order_count(self) -> int:
        return self.order_count
