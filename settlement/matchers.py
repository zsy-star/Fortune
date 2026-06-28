"""Pure settlement matcher functions."""

from __future__ import annotations

from domain.color_rules import get_five_element, get_half_wave, get_wave_color
from domain.number_rules import (
    composite_odd_even_label,
    composite_size_label,
    head_number,
    normalize_number,
    odd_even_label,
    size_label,
    tail_number,
)
from domain.zodiac_rules import get_zodiac


def match_special_number(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    selected = {normalize_number(token) for token in selection.split(",") if token}
    special = normalize_number(special_number)
    matched = special in selected
    return matched, special if matched else None, f"特码 {special} {'命中' if matched else '未命中'}号码 {selection}"


def match_zodiac(selection: str, special_number: str, *, year: int = 2026) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = get_zodiac(special, year=year)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 生肖为{actual}，投注{selection}"


def match_zodiac_group(
    selection: str,
    special_number: str,
    *,
    year: int = 2026,
) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = get_zodiac(special, year=year)
    selected = [token for token in selection.split(",") if token]
    matched = actual in selected
    selected_text = "、".join(selected)
    if matched:
        return (
            True,
            special,
            f"特码 {special} 生肖为{actual}，投注生肖列表：{selected_text}，命中生肖：{actual}",
        )
    return (
        False,
        None,
        f"特码 {special} 生肖为{actual}，投注生肖列表：{selected_text}，未命中",
    )


def match_color(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = get_wave_color(special)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 波色为{actual}，投注{selection}"


def match_half_color(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = get_half_wave(special)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 半波为{actual}，投注{selection}"


def match_size(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = size_label(special)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 大小为{actual}，投注{selection}"


def match_parity(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = odd_even_label(special)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 单双为{actual}，投注{selection}"


def match_tail(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = f"尾{tail_number(special)}"
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 尾数为{actual}，投注{selection}"


def match_head(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = f"{head_number(special)}头"
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 头数为{actual}，投注{selection}"


def match_sum_parity(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = composite_odd_even_label(special)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 合数单双为{actual}，投注{selection}"


def match_sum_size(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = composite_size_label(special)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 合数大小为{actual}，投注{selection}"


def match_element(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    actual = get_five_element(special)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 五行为{actual}，投注{selection}"
