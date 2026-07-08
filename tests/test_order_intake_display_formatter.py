from __future__ import annotations

from decimal import Decimal

from services.order_intake_display_formatter import (
    OrderIntakeDisplayItem,
    format_display_item,
    format_parse_result,
)
from services.order_parser import parse_lines


def test_single_number_display() -> None:
    item = OrderIntakeDisplayItem("澳门", "特码号码", "1", Decimal("2"))

    assert format_display_item(item) == "澳门: 特码: 1 各数 2"


def test_multiple_numbers_display() -> None:
    item = OrderIntakeDisplayItem("澳门", "特码号码", "03,13,23", Decimal("10"))

    assert format_display_item(item) == "澳门: 特码: 03-13-23 各数 10"


def test_multiple_zodiacs_display() -> None:
    item = OrderIntakeDisplayItem("香港", "特码生肖", "龙,鸡", Decimal("25"))

    assert format_display_item(item) == "香港: 特码: 龙-鸡 各数 25"


def test_single_zodiac_category_displays_as_special() -> None:
    result = parse_lines("兔各10")[0]

    assert format_parse_result(result, default_region="澳门") == "澳门: 特码: 兔 各数 10"


def test_wave_color_display() -> None:
    item = OrderIntakeDisplayItem("澳门", "特码波色", "红波", Decimal("5"))

    assert format_display_item(item) == "澳门: 特码: 红波 各数 5"


def test_size_display() -> None:
    item = OrderIntakeDisplayItem("澳门", "特码大小", "大", Decimal("10"))

    assert format_display_item(item) == "澳门: 特码: 大 各数 10"


def test_tail_display() -> None:
    item = OrderIntakeDisplayItem("澳门", "特码尾数", "尾1", Decimal("10"))

    assert format_display_item(item) == "澳门: 特码: 尾1 各数 10"


def test_error_display_contains_source_and_reason() -> None:
    item = OrderIntakeDisplayItem("澳门", "特码号码", "未知玩法各10", None, error="无法识别的类别")

    output = format_display_item(item)

    assert "无法识别" in output
    assert "原因" in output


def test_parse_result_slash_number_display() -> None:
    result = parse_lines("1/2")[0]

    assert format_parse_result(result, default_region="澳门") == "澳门: 特码: 1 各数 2"


def test_parse_result_preserves_multi_number_tokens() -> None:
    result = parse_lines("03,13,23各10")[0]

    assert format_parse_result(result, default_region="澳门") == "澳门: 特码: 03-13-23 各数 10"
