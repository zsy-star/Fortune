from __future__ import annotations

import pytest

from domain.color_rules import get_five_element, get_half_wave, get_wave_color
from domain.exceptions import InvalidNumberError, UnsupportedYearError
from domain.number_rules import (
    composite_odd_even_label,
    composite_size_label,
    head_number,
    normalize_number,
    odd_even_label,
    size_label,
    tail_number,
)
from domain.zodiac_config import get_number_zodiac_map, get_zodiac_number_map
from domain.zodiac_rules import get_zodiac


def test_number_normalization() -> None:
    assert normalize_number(1) == "01"
    assert normalize_number("49") == "49"
    with pytest.raises(InvalidNumberError):
        normalize_number(0)
    with pytest.raises(InvalidNumberError):
        normalize_number(50)
    with pytest.raises(InvalidNumberError):
        normalize_number("abc")


def test_2026_zodiac_rules_do_not_use_simple_modulo() -> None:
    assert get_zodiac(1, year=2026) == "马"
    assert get_zodiac(49, year=2026) == "马"
    assert get_zodiac(10, year=2026) == "鸡"
    assert get_zodiac(12, year=2026) == "羊"
    assert get_zodiac(1, year=2025) == "蛇"


def test_unified_zodiac_config_2026_baseline() -> None:
    mapping = get_zodiac_number_map(2026)

    assert mapping["马"] == ["01", "13", "25", "37", "49"]
    assert mapping["蛇"] == ["02", "14", "26", "38"]
    assert mapping["兔"] == ["04", "16", "28", "40"]


def test_zodiac_config_rotates_by_year_and_covers_all_numbers() -> None:
    assert get_zodiac_number_map(2025) != get_zodiac_number_map(2026)
    assert get_number_zodiac_map(2025)["01"] != get_number_zodiac_map(2026)["01"]

    for year in (2025, 2026, 2027):
        mapping = get_zodiac_number_map(year)
        all_numbers = [number for numbers in mapping.values() for number in numbers]
        assert len(mapping) == 12
        assert sorted(all_numbers) == [f"{number:02d}" for number in range(1, 50)]
        assert len(all_numbers) == len(set(all_numbers))


def test_zodiac_config_rejects_out_of_range_year() -> None:
    with pytest.raises(UnsupportedYearError):
        get_zodiac_number_map(1999)


def test_wave_and_half_wave_rules() -> None:
    assert get_wave_color(1) == "红波"
    assert get_wave_color(3) == "蓝波"
    assert get_wave_color(5) == "绿波"
    assert get_half_wave(1) == "红单"
    assert get_half_wave(2) == "红双"


def test_five_element_rules() -> None:
    assert get_five_element(3) == "金"
    assert get_five_element(7) == "木"
    assert get_five_element(13) == "水"
    assert get_five_element(1) == "火"
    assert get_five_element(5) == "土"


def test_number_derived_rules() -> None:
    assert size_label(24) == "小"
    assert size_label(25) == "大"
    assert odd_even_label(7) == "单"
    assert odd_even_label(8) == "双"
    assert tail_number(49) == 9
    assert head_number(37) == 3
    assert composite_odd_even_label(10) == "合单"
    assert composite_odd_even_label(11) == "合双"
    assert composite_size_label(49) == "合小"
    assert composite_size_label(27) == "合大"
