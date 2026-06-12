"""Number validation and common 01-49 derived rules."""

from __future__ import annotations

from domain.exceptions import InvalidNumberError

MIN_NUMBER = 1
MAX_NUMBER = 49


def to_int_number(value: int | str) -> int:
    """Convert a lottery number to int and validate the 01-49 range."""
    try:
        if isinstance(value, str):
            text = value.strip()
            if not text or not text.isdigit():
                raise ValueError
            number = int(text)
        else:
            number = int(value)
    except (TypeError, ValueError):
        raise InvalidNumberError(f"Invalid lottery number: {value!r}") from None

    if number < MIN_NUMBER or number > MAX_NUMBER:
        raise InvalidNumberError(f"Lottery number must be between 01 and 49: {value!r}")
    return number


def normalize_number(value: int | str) -> str:
    """Return a validated lottery number as a two-digit string."""
    return f"{to_int_number(value):02d}"


def normalize_numbers(values: list[int | str] | tuple[int | str, ...]) -> list[str]:
    return [normalize_number(value) for value in values]


def is_big(value: int | str) -> bool:
    return to_int_number(value) >= 25


def size_label(value: int | str) -> str:
    return "大" if is_big(value) else "小"


def odd_even_label(value: int | str) -> str:
    return "单" if to_int_number(value) % 2 else "双"


def tail_number(value: int | str) -> int:
    return to_int_number(value) % 10


def head_number(value: int | str) -> int:
    number = to_int_number(value)
    return number // 10


def digit_sum(value: int | str) -> int:
    number = to_int_number(value)
    return sum(int(char) for char in f"{number:02d}")


def digit_root(value: int | str) -> int:
    result = digit_sum(value)
    while result >= 10:
        result = sum(int(char) for char in str(result))
    return result


def composite_odd_even_label(value: int | str) -> str:
    return "合单" if digit_sum(value) % 2 else "合双"


def composite_size_label(value: int | str) -> str:
    return "合大" if digit_root(value) >= 5 else "合小"
