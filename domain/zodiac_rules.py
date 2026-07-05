"""Compatibility wrappers for year-specific zodiac rules."""

from __future__ import annotations

from domain.exceptions import UnsupportedYearError
from domain.number_rules import to_int_number
from domain.zodiac_config import get_default_zodiac_year, get_number_zodiac_map, get_zodiac_number_map


def get_zodiac_map(year: int | None = None) -> dict[str, tuple[int, ...]]:
    selected_year = get_default_zodiac_year() if year is None else year
    return {
        zodiac: tuple(int(number) for number in numbers)
        for zodiac, numbers in get_zodiac_number_map(selected_year).items()
    }


def get_zodiac(value: int | str, year: int | None = None) -> str:
    selected_year = get_default_zodiac_year() if year is None else year
    number = to_int_number(value)
    try:
        return get_number_zodiac_map(selected_year)[f"{number:02d}"]
    except KeyError:
        raise UnsupportedYearError(f"No zodiac mapping for number {number:02d} in year {selected_year}") from None


def numbers_for_zodiac(zodiac: str, year: int | None = None) -> tuple[int, ...]:
    selected_year = get_default_zodiac_year() if year is None else year
    mapping = get_zodiac_map(selected_year)
    try:
        return mapping[zodiac]
    except KeyError:
        raise UnsupportedYearError(f"Unknown zodiac {zodiac!r} for year {selected_year}") from None
