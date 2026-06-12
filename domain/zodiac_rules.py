"""Year-specific zodiac rules."""

from __future__ import annotations

from domain.exceptions import UnsupportedYearError
from domain.number_rules import to_int_number

ZODIAC_BY_YEAR: dict[int, tuple[tuple[str, tuple[int, ...]], ...]] = {
    2026: (
        ("马", (1, 13, 25, 37, 49)),
        ("蛇", (2, 14, 26, 38)),
        ("龙", (3, 15, 27, 39)),
        ("兔", (4, 16, 28, 40)),
        ("虎", (5, 17, 29, 41)),
        ("牛", (6, 18, 30, 42)),
        ("鼠", (7, 19, 31, 43)),
        ("猪", (8, 20, 32, 44)),
        ("狗", (9, 21, 33, 45)),
        ("鸡", (10, 22, 34, 46)),
        ("猴", (11, 23, 35, 47)),
        ("羊", (12, 24, 36, 48)),
    )
}


def get_zodiac_map(year: int = 2026) -> dict[str, tuple[int, ...]]:
    try:
        entries = ZODIAC_BY_YEAR[year]
    except KeyError:
        raise UnsupportedYearError(f"No zodiac rules configured for year {year}") from None
    return dict(entries)


def get_zodiac(value: int | str, year: int = 2026) -> str:
    number = to_int_number(value)
    for zodiac, numbers in get_zodiac_map(year).items():
        if number in numbers:
            return zodiac
    raise UnsupportedYearError(f"No zodiac mapping for number {number:02d} in year {year}")


def numbers_for_zodiac(zodiac: str, year: int = 2026) -> tuple[int, ...]:
    mapping = get_zodiac_map(year)
    try:
        return mapping[zodiac]
    except KeyError:
        raise UnsupportedYearError(f"Unknown zodiac {zodiac!r} for year {year}") from None
