"""Pure settlement matcher functions."""

from __future__ import annotations

import re
from itertools import combinations

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
from domain.zodiac_config import get_default_zodiac_year


def match_special_number(selection: str, special_number: str) -> tuple[bool, str | None, str]:
    selected = {normalize_number(token) for token in selection.split(",") if token}
    special = normalize_number(special_number)
    matched = special in selected
    return matched, special if matched else None, f"特码 {special} {'命中' if matched else '未命中'}号码 {selection}"


def match_zodiac(selection: str, special_number: str, *, year: int | None = None) -> tuple[bool, str | None, str]:
    selected_year = year or get_default_zodiac_year()
    special = normalize_number(special_number)
    actual = get_zodiac(special, year=selected_year)
    matched = actual == selection
    return matched, special if matched else None, f"特码 {special} 生肖为{actual}，投注{selection}"


def match_pingte_zodiac_v2(
    selection: str,
    regular_numbers: list[str],
    special_number: str,
    *,
    year: int | None = None,
) -> tuple[bool, str | None, str]:
    """Match one 平特一肖 selection against all six regular numbers plus special."""
    selected_year = year or get_default_zodiac_year()
    draw_numbers = [
        *(normalize_number(number) for number in regular_numbers),
        normalize_number(special_number),
    ]
    drawn_zodiacs = [get_zodiac(number, year=selected_year) for number in draw_numbers]
    matched_numbers = [
        number for number, zodiac in zip(draw_numbers, drawn_zodiacs) if zodiac == selection
    ]
    draw_text = ",".join(draw_numbers)
    zodiac_text = "、".join(drawn_zodiacs)
    if matched_numbers:
        return (
            True,
            matched_numbers[0],
            f"平特一肖检查全部7个开奖号 {draw_text}（生肖：{zodiac_text}），"
            f"投注{selection}命中号码 {','.join(matched_numbers)}；同一生肖只计一注",
        )
    return (
        False,
        None,
        f"平特一肖检查全部7个开奖号 {draw_text}（生肖：{zodiac_text}），"
        f"投注{selection}未命中",
    )


def match_zodiac_group(
    selection: str,
    special_number: str,
    *,
    year: int | None = None,
) -> tuple[bool, str | None, str]:
    selected_year = year or get_default_zodiac_year()
    special = normalize_number(special_number)
    actual = get_zodiac(special, year=selected_year)
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


def parse_lianma_groups(selection: str) -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []
    for match in re.finditer(r"\(([^()]*)\)", selection):
        numbers = tuple(normalize_number(token) for token in re.split(r"[\s,，、\-]+", match.group(1)) if token)
        if numbers:
            groups.append(numbers)
    if groups:
        return tuple(groups)
    numbers = tuple(normalize_number(token) for token in re.split(r"[\s,，、\-]+", selection.strip()) if token)
    return (numbers,) if numbers else ()


def format_lianma_group(group: tuple[str, ...]) -> str:
    return "(" + "-".join(group) + ")"


def matched_lianma_groups(
    selection: str,
    regular_numbers: list[str],
    *,
    group_size: int,
    required_hits: int,
) -> tuple[tuple[str, ...], ...]:
    regular_set = {normalize_number(number) for number in regular_numbers}
    matched_groups: list[tuple[str, ...]] = []
    for group in parse_lianma_groups(selection):
        if len(group) != group_size or len(set(group)) != len(group):
            continue
        hit_count = sum(1 for number in group if number in regular_set)
        if hit_count >= required_hits:
            matched_groups.append(group)
    return tuple(matched_groups)


def match_ping_tail(
    selection: str,
    regular_numbers: list[str],
    special_number: str,
) -> tuple[bool, str | None, str]:
    normalized_regular = [normalize_number(number) for number in regular_numbers]
    regular_tails = {str(tail_number(number)) for number in normalized_regular}
    selected_tails = [token for token in selection.split(",") if token]
    matched_tails = [tail for tail in selected_tails if tail in regular_tails]
    regular_text = ",".join(normalized_regular)
    selected_text = ",".join(f"{tail}尾" for tail in selected_tails)
    special = normalize_number(special_number)
    if matched_tails:
        return (
            True,
            ",".join(matched_tails),
            f"平尾只使用 6 个正码 {regular_text}，投注{selected_text} 命中 {','.join(matched_tails)}尾",
        )
    return (
        False,
        None,
        f"平尾只使用 6 个正码 {regular_text}，特码 {special} 不参与，投注{selected_text} 未命中",
    )


def match_lianma(
    selection: str,
    regular_numbers: list[str],
    special_number: str,
    *,
    group_size: int,
    required_hits: int,
    label: str,
) -> tuple[bool, str | None, str]:
    normalized_regular = [normalize_number(number) for number in regular_numbers]
    matched_groups = matched_lianma_groups(
        selection,
        normalized_regular,
        group_size=group_size,
        required_hits=required_hits,
    )
    regular_text = ",".join(normalized_regular)
    special = normalize_number(special_number)
    if matched_groups:
        matched_text = "-".join(format_lianma_group(group) for group in matched_groups)
        return True, matched_text, f"{label}只使用 6 个正码 {regular_text}，命中组合 {matched_text}"
    return False, None, f"{label}只使用 6 个正码 {regular_text}，特码 {special} 不参与，未命中"


def match_two_in_two(selection: str, regular_numbers: list[str], special_number: str) -> tuple[bool, str | None, str]:
    return match_lianma(selection, regular_numbers, special_number, group_size=2, required_hits=2, label="二中二")


def match_three_in_three(selection: str, regular_numbers: list[str], special_number: str) -> tuple[bool, str | None, str]:
    return match_lianma(selection, regular_numbers, special_number, group_size=3, required_hits=3, label="三中三")


def match_three_in_two(selection: str, regular_numbers: list[str], special_number: str) -> tuple[bool, str | None, str]:
    return match_lianma(selection, regular_numbers, special_number, group_size=3, required_hits=2, label="三中二")


def parse_number_fuxuan_selection(selection: str) -> tuple[int, tuple[str, ...]]:
    if "|" not in selection:
        raise ValueError("missing fuxuan type")
    fuxuan_type, numbers_text = selection.split("|", 1)
    if not re.fullmatch(r"复[23]", fuxuan_type):
        raise ValueError("unsupported fuxuan type")
    numbers = tuple(normalize_number(token) for token in numbers_text.split(",") if token)
    return int(fuxuan_type[1:]), numbers


def fuxuan_groups(selection: str) -> tuple[tuple[str, ...], ...]:
    k, numbers = parse_number_fuxuan_selection(selection)
    return tuple(tuple(group) for group in combinations(numbers, k))


def match_number_fuxuan(
    selection: str,
    regular_numbers: list[str],
    special_number: str,
) -> tuple[bool, str | None, str]:
    k, _numbers = parse_number_fuxuan_selection(selection)
    groups = fuxuan_groups(selection)
    normalized_regular = [normalize_number(number) for number in regular_numbers]
    regular_set = set(normalized_regular)
    matched_groups = tuple(group for group in groups if all(number in regular_set for number in group))
    regular_text = ",".join(normalized_regular)
    special = normalize_number(special_number)
    label = f"复{k}"
    if matched_groups:
        matched_text = "-".join(format_lianma_group(group) for group in matched_groups)
        return True, matched_text, f"几中几复选{label}只使用 6 个正码 {regular_text}，命中组合 {matched_text}"
    return False, None, f"几中几复选{label}只使用 6 个正码 {regular_text}，特码 {special} 不参与，未命中"


def match_non_hit_number(
    selection: str,
    regular_numbers: list[str],
    _special_number: str,
) -> tuple[bool, str | None, str]:
    normalized_regular = [normalize_number(number) for number in regular_numbers]
    regular_set = set(normalized_regular)
    selected_numbers = [normalize_number(token) for token in selection.split(",") if token]
    hit_regular_numbers = [number for number in selected_numbers if number in regular_set]
    matched = not hit_regular_numbers
    regular_text = ",".join(normalized_regular)
    selected_text = ",".join(selected_numbers)
    if matched:
        return (
            True,
            None,
            f"N不中只检查前6个平码 {regular_text}，投注号码 {selected_text} 均未出现；"
            "特别号不参与N不中判断",
        )
    return (
        False,
        hit_regular_numbers[0],
        f"N不中只检查前6个平码 {regular_text}，投注号码 {selected_text} 中出现 "
        f"{','.join(hit_regular_numbers)}；特别号不参与N不中判断",
    )


def match_six_special_zodiac(
    selection: str,
    special_number: str,
    *,
    year: int | None = None,
) -> tuple[bool, str | None, str]:
    selected_year = year or get_default_zodiac_year()
    special = normalize_number(special_number)
    actual = get_zodiac(special, year=selected_year)
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
