"""Shared naming rules for N不中 parsing, validation, and odds lookup."""

from __future__ import annotations

import re

NON_HIT_MIN_COUNT = 5
NON_HIT_MAX_COUNT = 27

_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def parse_non_hit_count_label(value: str) -> int | None:
    """Return the explicit N from ``十不中``/``10不中``; generic labels return None."""
    text = str(value or "").strip()
    if text.endswith("不中"):
        text = text[:-2].strip()
    if not text or text.lower() == "n":
        return None
    if text.isdigit():
        return int(text)
    if not re.fullmatch(r"[零〇一二两三四五六七八九十]+", text):
        raise ValueError(f"无法识别N不中阶数：{value}")
    if "十" not in text:
        if len(text) != 1:
            raise ValueError(f"无法识别N不中阶数：{value}")
        return _CN_DIGITS[text]
    if text.count("十") != 1:
        raise ValueError(f"无法识别N不中阶数：{value}")
    tens, ones = text.split("十", 1)
    if len(tens) > 1 or len(ones) > 1:
        raise ValueError(f"无法识别N不中阶数：{value}")
    tens_value = 1 if not tens else _CN_DIGITS.get(tens)
    ones_value = 0 if not ones else _CN_DIGITS.get(ones)
    if tens_value is None or ones_value is None:
        raise ValueError(f"无法识别N不中阶数：{value}")
    return tens_value * 10 + ones_value


def format_non_hit_count_chinese(count: int) -> str:
    """Format supported N不中 counts as conventional Chinese numerals."""
    value = int(count)
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    tens, ones = divmod(value, 10)
    prefix = "十" if tens == 1 else f"{digits[tens]}十"
    return prefix if ones == 0 else f"{prefix}{digits[ones]}"


def non_hit_odds_bet_type_candidates(count: int) -> tuple[str, ...]:
    """Return editable settings keys from most specific to generic."""
    value = int(count)
    return (
        f"{format_non_hit_count_chinese(value)}不中",
        f"{value}不中",
        "N不中",
        "不中",
    )
