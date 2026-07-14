from __future__ import annotations

from decimal import Decimal

from services.order_intake_display_formatter import (
    OrderIntakeDisplayItem,
    format_display_item,
    format_issue_hint,
    format_nickname_recognition,
    format_nickname_without_orders,
    format_parse_result,
    format_play_context,
    format_region_recognition,
    format_total_validation,
)
from services.order_parser import parse_lines


def test_nickname_display_messages_are_separate_from_order_formatting() -> None:
    result = parse_lines("王大定:\n2.14.38.26各100")[0]

    assert format_nickname_recognition(result.nickname) == "昵称识别：王大定"
    assert format_nickname_without_orders(result.nickname) == "已识别昵称“王大定”，但未发现可保存订单。"
    assert "王大定" not in format_parse_result(result, default_region="澳门")


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


def test_hong_kong_blue_alias_parse_display_uses_canonical_name_numbers_and_total() -> None:
    result = parse_lines("香港兰波各数280")[0]

    assert format_parse_result(result) == (
        "香港: 蓝波: 03-04-09-10-14-15-20-25-26-31-36-37-41-42-47-48 "
        "每号 280，号码数 16，合计 4480"
    )


def test_hong_kong_special_context_displays_actual_numbers_instead_of_category_name() -> None:
    results = parse_lines("香港特\n11.23各数20米")

    assert format_parse_result(results[0]) == "香港: 特码: 11-23 每号 20，合计 40"
    assert "特码: 特码" not in format_parse_result(results[0])


def test_hong_kong_zodiac_package_display_is_one_special_zodiac_group() -> None:
    result = parse_lines("香港特码：蛇 包80")[0]

    assert format_parse_result(result) == "香港: 特码生肖: 蛇 整组 80，合计 80"


def test_standalone_zodiac_each_numbers_display_real_special_numbers_and_total() -> None:
    result = parse_lines("鼠各数130")[0]

    assert format_parse_result(result, default_region="澳门") == (
        "澳门: 特码: 07-19-31-43 每号 130，合计 520"
    )


def test_pingte_zodiac_is_not_relabelled_as_special_zodiac() -> None:
    result = parse_lines("平特一肖蛇各80")[0]

    assert format_parse_result(result, default_region="澳门") == "澳门: 平特一肖: 蛇 各数 80"


def test_context_and_total_validation_messages_are_preview_only_formatters() -> None:
    result = parse_lines("港76期\n12，23，12，24各20斤\n共80斤")[0]

    assert format_region_recognition(result.region) == "地区识别：香港"
    assert format_issue_hint(result.issue_hint) == "期号识别：76期（仅本次预览）"
    assert format_play_context("特码") == "玩法上下文：特码"
    assert format_total_validation(result) == "合计校验通过：80"


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
