"""Wave color, half-wave, and five-element rules."""

from __future__ import annotations

from domain.exceptions import DomainError
from domain.number_rules import odd_even_label, to_int_number

WAVE_NUMBERS: dict[str, set[int]] = {
    "红波": {1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46},
    "蓝波": {3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48},
    "绿波": {5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49},
}

FIVE_ELEMENT_NUMBERS: dict[str, set[int]] = {
    "金": {3, 4, 11, 12, 25, 26, 33, 34, 41, 42},
    "木": {7, 8, 15, 16, 23, 24, 37, 38, 45, 46},
    "水": {13, 14, 21, 22, 29, 30, 43, 44},
    "火": {1, 2, 9, 10, 17, 18, 31, 32, 39, 40, 47, 48},
    "土": {5, 6, 19, 20, 27, 28, 35, 36, 49},
}


def get_wave_color(value: int | str) -> str:
    number = to_int_number(value)
    for color, numbers in WAVE_NUMBERS.items():
        if number in numbers:
            return color
    raise DomainError(f"No wave color configured for number {number:02d}")


def get_half_wave(value: int | str) -> str:
    color = get_wave_color(value).removesuffix("波")
    return f"{color}{odd_even_label(value)}"


def get_five_element(value: int | str) -> str:
    number = to_int_number(value)
    for element, numbers in FIVE_ELEMENT_NUMBERS.items():
        if number in numbers:
            return element
    raise DomainError(f"No five-element rule configured for number {number:02d}")
