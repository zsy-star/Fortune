from __future__ import annotations

import pytest

from domain.color_rules import FIVE_ELEMENT_NUMBERS, WAVE_NUMBERS
from domain.number_catalog_data import (
    ALL_NUMBERS,
    REFERENCE_FIVE_ELEMENT_NUMBERS_2026,
    composite_size_reference_groups,
    digit_sum_groups,
    half_wave_groups,
    head_groups,
    modulo_groups,
    size_groups,
    size_parity_groups,
    sum_parity_groups,
    sum_tail_groups,
    tail_size_groups,
    validate_catalog_data,
    validate_number_group,
    validate_partition,
)
from domain.number_rules import composite_size_label
from domain.zodiac_config import get_zodiac_number_map


def _flatten(groups) -> list[int]:
    return [number for numbers in groups.values() for number in numbers]


def test_2026_zodiac_numbers_cover_01_to_49_once() -> None:
    mapping = get_zodiac_number_map(2026)

    assert mapping["马"] == ["01", "13", "25", "37", "49"]
    assert mapping["蛇"] == ["02", "14", "26", "38"]
    numbers = [int(number) for group in mapping.values() for number in group]
    assert sorted(numbers) == list(ALL_NUMBERS)
    assert len(numbers) == len(set(numbers))


def test_wave_and_derived_partitions_cover_01_to_49_once() -> None:
    partitions = (
        WAVE_NUMBERS,
        REFERENCE_FIVE_ELEMENT_NUMBERS_2026,
        half_wave_groups(),
        sum_parity_groups(),
        size_groups(),
        digit_sum_groups(),
        head_groups(),
        composite_size_reference_groups(),
        tail_size_groups(),
        size_parity_groups(),
        sum_tail_groups(),
    )
    for groups in partitions:
        numbers = _flatten(groups)
        assert sorted(numbers) == list(ALL_NUMBERS)
        assert len(numbers) == len(set(numbers))

    for modulus in range(3, 8):
        numbers = _flatten(modulo_groups(modulus))
        assert sorted(numbers) == list(ALL_NUMBERS)
        assert len(numbers) == len(set(numbers))


def test_generated_groups_match_supplied_reference_examples() -> None:
    assert half_wave_groups()["红双"] == (2, 8, 12, 18, 24, 30, 34, 40, 46)
    assert half_wave_groups()["绿单"] == (5, 11, 17, 21, 27, 33, 39, 43, 49)
    assert sum_parity_groups()["合数单"][:10] == (1, 3, 5, 7, 9, 10, 12, 14, 16, 18)
    assert digit_sum_groups()["13合"] == (49,)
    assert modulo_groups(7)["7余0"] == (7, 14, 21, 28, 35, 42, 49)


def test_catalog_validation_accepts_complete_reference_data() -> None:
    validate_catalog_data(2026)


def test_partition_validation_reports_missing_duplicate_and_out_of_range() -> None:
    with pytest.raises(ValueError, match="未覆盖号码"):
        validate_partition("漏号测试", {"一组": range(1, 49)})

    with pytest.raises(ValueError, match="同时出现在"):
        validate_partition("跨组重复测试", {"甲": range(1, 26), "乙": range(25, 50)})

    with pytest.raises(ValueError, match="重复号码"):
        validate_number_group("组内重复测试", (1, 1, 2))

    with pytest.raises(ValueError, match="超出 01-49"):
        validate_number_group("越界测试", (0, 1, 50))


def test_static_reference_conflicts_are_isolated_from_business_rules() -> None:
    assert REFERENCE_FIVE_ELEMENT_NUMBERS_2026 != {
        name: tuple(sorted(numbers)) for name, numbers in FIVE_ELEMENT_NUMBERS.items()
    }
    assert 49 in composite_size_reference_groups()["合大"]
    assert composite_size_label(49) == "合小"
