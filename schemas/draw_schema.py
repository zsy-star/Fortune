"""Lottery draw DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domain.bet_types import normalize_region
from domain.exceptions import DuplicateDrawError
from domain.number_rules import normalize_number


@dataclass(slots=True)
class LotteryDrawCreate:
    region: str
    issue_number: str
    draw_date: date
    regular_numbers: list[int | str]
    special_number: int | str
    source: str | None = None
    status: str = "confirmed"

    def __post_init__(self) -> None:
        self.region = normalize_region(self.region)
        self.issue_number = str(self.issue_number).strip()
        if not self.issue_number:
            raise ValueError("issue_number cannot be empty")
        if not isinstance(self.draw_date, date):
            raise TypeError("draw_date must be a datetime.date")
        self.regular_numbers = [normalize_number(n) for n in self.regular_numbers]
        if len(self.regular_numbers) != 6:
            raise ValueError("regular_numbers must contain exactly 6 numbers")
        self.special_number = normalize_number(self.special_number)
        all_numbers = [*self.regular_numbers, self.special_number]
        if len(set(all_numbers)) != len(all_numbers):
            raise DuplicateDrawError("regular_numbers and special_number cannot repeat")
        if self.source is not None:
            self.source = self.source.strip() or None
        self.status = self.status.strip() or "confirmed"
