"""Unified year-specific zodiac number configuration."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date

from domain.exceptions import UnsupportedYearError
from domain.number_rules import to_int_number

MIN_ZODIAC_YEAR = 2000
MAX_ZODIAC_YEAR = 2099
ZODIAC_SEQUENCE: tuple[str, ...] = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")


def get_default_zodiac_year() -> int:
    return date.today().year


def validate_zodiac_year(year: int) -> int:
    try:
        value = int(year)
    except (TypeError, ValueError):
        raise UnsupportedYearError(f"Invalid zodiac year: {year!r}") from None
    if value < MIN_ZODIAC_YEAR or value > MAX_ZODIAC_YEAR:
        raise UnsupportedYearError(
            f"Unsupported zodiac year {value}; expected {MIN_ZODIAC_YEAR}-{MAX_ZODIAC_YEAR}"
        )
    return value


def _year_zodiac_index(year: int) -> int:
    # 2020 is a Rat year, which anchors the regular Chinese zodiac cycle.
    return (validate_zodiac_year(year) - 2020) % 12


def get_zodiac_number_map(year: int) -> dict[str, list[str]]:
    year = validate_zodiac_year(year)
    year_index = _year_zodiac_index(year)
    mapping: "OrderedDict[str, list[str]]" = OrderedDict()
    for number in range(1, 50):
        zodiac = ZODIAC_SEQUENCE[(year_index - (number - 1)) % 12]
        mapping.setdefault(zodiac, []).append(f"{number:02d}")
    _validate_mapping(mapping, year)
    return dict(mapping)


def get_number_zodiac_map(year: int) -> dict[str, str]:
    zodiac_map = get_zodiac_number_map(year)
    return {number: zodiac for zodiac, numbers in zodiac_map.items() for number in numbers}


def _validate_mapping(mapping: dict[str, list[str]], year: int) -> None:
    if set(mapping) != set(ZODIAC_SEQUENCE):
        raise UnsupportedYearError(f"Zodiac mapping for {year} must contain all 12 zodiacs")
    numbers = [number for group in mapping.values() for number in group]
    expected = [f"{number:02d}" for number in range(1, 50)]
    if sorted(numbers) != expected or len(numbers) != len(set(numbers)):
        raise UnsupportedYearError(f"Zodiac mapping for {year} must contain each number 01-49 exactly once")

