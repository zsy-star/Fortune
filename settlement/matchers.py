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


def match_linked_tail(
    selection: str,
    regular_numbers: list[str],
    special_number: str,
) -> tuple[bool, str | None, str]:
    draw_numbers = [*(normalize_number(number) for number in regular_numbers), normalize_number(special_number)]
    draw_tails = {str(tail_number(number)) for number in draw_numbers}
    selected_tails = [token for token in selection.split(",") if token]
    matched_tails = [tail for tail in selected_tails if tail in draw_tails]
    matched = len(matched_tails) == len(selected_tails)
    draw_text = ",".join(draw_numbers)
    selected_text = ",".join(f"{tail}尾" for tail in selected_tails)
    matched_text = ",".join(f"{tail}尾" for tail in matched_tails) if matched_tails else "无"
    if matched:
        return True, ",".join(matched_tails), f"连尾使用全部开奖号码 {draw_text}，投注{selected_text}全部出现"
    return False, None, f"连尾使用全部开奖号码 {draw_text}，投注{selected_text}，已出现{matched_text}，未全部出现"


def match_non_hit_number(
    selection: str,
    regular_numbers: list[str],
    special_number: str,
) -> tuple[bool, str | None, str]:
    draw_numbers = [*(normalize_number(number) for number in regular_numbers), normalize_number(special_number)]
    draw_set = set(draw_numbers)
    selected_numbers = [normalize_number(token) for token in selection.split(",") if token]
    hit_numbers = [number for number in selected_numbers if number in draw_set]
    matched = not hit_numbers
    draw_text = ",".join(draw_numbers)
    selected_text = ",".join(selected_numbers)
    if matched:
        return True, None, f"不中使用全部开奖号码 {draw_text}，投注号码 {selected_text} 均未出现"
    return False, hit_numbers[0], f"不中使用全部开奖号码 {draw_text}，投注号码 {selected_text} 中出现 {','.join(hit_numbers)}"


def match_six_special_zodiac(
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
        return True, special, f"六肖中特使用特码生肖，特码 {special} 为{actual}，投注生肖列表：{selected_text}，命中生肖：{actual}"
    return False, None, f"六肖中特使用特码生肖，特码 {special} 为{actual}，投注生肖列表：{selected_text}，未命中"


def match_regular_number(
    selection: str,
    regular_numbers: list[str],
    special_number: str,
) -> tuple[bool, str | None, str]:
    normalized_regular = [normalize_number(number) for number in regular_numbers]
    selected_numbers = [normalize_number(token) for token in selection.split(",") if token]
    regular_set = set(normalized_regular)
    matched_numbers = [number for number in selected_numbers if number in regular_set]
    matched = bool(matched_numbers)
    regular_text = ",".join(normalized_regular)
    selected_text = ",".join(selected_numbers)
    special = normalize_number(special_number)
    if matched:
        return True, matched_numbers[0], f"平码只使用 6 个正码 {regular_text}，投注号码 {selected_text} 命中 {','.join(matched_numbers)}"
    return False, None, f"平码只使用 6 个正码 {regular_text}，特码 {special} 不参与，投注号码 {selected_text} 未命中"


def match_package_half_wave(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    special = normalize_number(special_number)
    wave = get_wave_color(special).removesuffix("波")
    odd_even = odd_even_label(special)
    big_small = size_label(special)
    actual_halfwaves = (f"{wave}{odd_even}", f"{wave}{big_small}")
    selected_halfwaves = [token for token in selection.split(",") if token]
    matched_halfwave = next((token for token in selected_halfwaves if token in actual_halfwaves), None)
    selected_text = ",".join(selected_halfwaves)
    actual_text = ",".join(actual_halfwaves)
    if matched_halfwave:
        return True, special, f"包半波使用特码 {special}，实际组合 {actual_text}，投注 {selected_text} 命中 {matched_halfwave}"
    return False, None, f"包半波使用特码 {special}，实际组合 {actual_text}，投注 {selected_text} 未命中"
