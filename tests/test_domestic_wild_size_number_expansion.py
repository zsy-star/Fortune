from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import pytest

import services.order_parser as order_parser
from domain.zodiac_config import get_zodiac_number_map
from schemas.draw_schema import LotteryDrawCreate
from services.draw_service import DrawService
from services.order_intake_display_formatter import format_parse_result
from services.order_intake_service import OrderIntakeService
from services.order_parser import parse_lines
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService


DOMESTIC_ZODIACS = ("牛", "马", "羊", "鸡", "狗", "猪")
WILD_ZODIACS = ("鼠", "虎", "兔", "龙", "蛇", "猴")
DOMESTIC_BIG_2026 = (25, 30, 32, 33, 34, 36, 37, 42, 44, 45, 46, 48, 49)
WILD_SMALL_2026 = (2, 3, 4, 5, 7, 11, 14, 15, 16, 17, 19, 23)


def _expected_numbers(year: int, group: str, size: str) -> tuple[int, ...]:
    mapping = get_zodiac_number_map(year)
    zodiacs = DOMESTIC_ZODIACS if group == "家肖" else WILD_ZODIACS
    minimum, maximum = (25, 49) if size == "大数" else (1, 24)
    return tuple(
        sorted(
            int(number)
            for zodiac in zodiacs
            for number in mapping[zodiac]
            if minimum <= int(number) <= maximum
        )
    )


def _parse_one(text: str, *, year: int = 2026):
    results = parse_lines(text, zodiac_year=year)
    assert len(results) == 1
    return results[0]


def test_2026_domestic_big_expands_to_thirteen_special_numbers() -> None:
    result = _parse_one("家肖的大数各100")

    assert result.success and result.category == "特码"
    assert result.numbers == DOMESTIC_BIG_2026
    assert result.amount == Decimal("100")
    assert result.total == Decimal("1300")
    assert result.number_expansion_group == "家肖"
    assert result.number_expansion_size == "大数"
    assert result.number_expansion_zodiac_year == 2026


def test_2026_wild_small_expands_to_twelve_special_numbers() -> None:
    result = _parse_one("野肖的小数各50")

    assert result.success and result.category == "特码"
    assert result.numbers == WILD_SMALL_2026
    assert result.amount == Decimal("50")
    assert result.total == Decimal("600")


def test_two_lines_keep_line_order_and_number_sort_order() -> None:
    results = parse_lines("家肖的大数各100\n野肖的小数各50", zodiac_year=2026)

    assert [result.numbers for result in results] == [DOMESTIC_BIG_2026, WILD_SMALL_2026]
    assert sum((Decimal(result.total) for result in results), Decimal("0")) == Decimal("1900")


def test_preview_and_save_create_twenty_five_independent_special_items(session_factory) -> None:
    raw_text = "家肖的大数各100\n野肖的小数各50"
    intake = OrderIntakeService(session_factory)
    preview = intake.preview_raw_text(raw_text, region="澳门", zodiac_year=2026)

    assert preview.can_save, preview.errors
    assert preview.zodiac_year == 2026
    assert preview.valid_items == 25
    assert preview.total_amount == Decimal("1900")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        *[("特码", f"{number:02d}", Decimal("100")) for number in DOMESTIC_BIG_2026],
        *[("特码", f"{number:02d}", Decimal("50")) for number in WILD_SMALL_2026],
    ]
    assert all(item.settlement_support_status == "supported" for item in preview.items)

    saved = intake.save_preview(preview)
    assert saved.success and saved.order is not None
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None
    assert detail.raw_text == raw_text
    assert detail.zodiac_year == 2026
    assert detail.total_amount == Decimal("1900")
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        *[("特码", f"{number:02d}", Decimal("100")) for number in DOMESTIC_BIG_2026],
        *[("特码", f"{number:02d}", Decimal("50")) for number in WILD_SMALL_2026],
    ]


@pytest.mark.parametrize(
    "text,group,size",
    [
        ("家肖的大数各100", "家肖", "大数"),
        ("家肖大数各100", "家肖", "大数"),
        ("家肖 大数 各100", "家肖", "大数"),
        ("家肖，大数，各100", "家肖", "大数"),
        ("家肖。大数。各100", "家肖", "大数"),
        ("家肖；大数；各100", "家肖", "大数"),
        ("野肖的小数各50", "野肖", "小数"),
        ("野肖 小数 各50", "野肖", "小数"),
        ("野肖：小数：各50", "野肖", "小数"),
    ],
)
def test_optional_de_spaces_and_chinese_punctuation(text: str, group: str, size: str) -> None:
    result = _parse_one(text)

    assert result.success
    assert result.numbers == _expected_numbers(2026, group, size)


@pytest.mark.parametrize(
    "text,group,size",
    [
        ("家肖小数各10", "家肖", "小数"),
        ("野肖大数各10", "野肖", "大数"),
    ],
)
def test_other_two_explicit_intersections_expand_dynamically(text: str, group: str, size: str) -> None:
    result = _parse_one(text)

    assert result.numbers == _expected_numbers(2026, group, size)
    assert result.total == Decimal("10") * len(result.numbers)


def test_selected_zodiac_year_changes_the_expansion() -> None:
    result_2025 = _parse_one("家肖大数各10", year=2025)
    result_2026 = _parse_one("家肖大数各10", year=2026)

    assert result_2025.numbers == _expected_numbers(2025, "家肖", "大数")
    assert result_2026.numbers == _expected_numbers(2026, "家肖", "大数")
    assert result_2025.numbers != result_2026.numbers
    assert result_2025.number_expansion_zodiac_year == 2025


def test_production_expansion_function_does_not_embed_2026_golden_number_lists() -> None:
    source = inspect.getsource(order_parser.parse_domestic_wild_size_number_expansion)

    assert repr(DOMESTIC_BIG_2026) not in source
    assert repr(WILD_SMALL_2026) not in source
    assert "get_zodiac_number_map" in source


def test_recognition_display_explains_source_count_total_and_year() -> None:
    result = _parse_one("家肖的大数各100")
    display = format_parse_result(result, default_region="澳门")

    assert "类别：特码号码" in display
    assert "来源：家肖 ∩ 大数" in display
    assert "展开号码：25、30、32、33、34、36、37、42、44、45、46、48、49" in display
    assert "每号金额：100" in display
    assert "注数：13" in display
    assert "小计：1300" in display
    assert "生肖年份：2026" in display


@pytest.mark.parametrize(
    "text,error_text",
    [
        ("家肖野肖大数各10", "家肖/野肖不能同时出现"),
        ("家肖大数小数各10", "大数/小数不能同时出现"),
        ("家肖大数", "缺少金额"),
        ("家肖大数各", "金额不能为空"),
        ("家肖大数各0", "金额必须大于 0"),
        ("家肖大数各-10", "金额必须大于 0"),
        ("家肖各10", "必须同时指定大数或小数"),
        ("家肖大数包10", "只支持「各金额」"),
        ("家肖大数各包10", "金额格式无效"),
    ],
)
def test_invalid_or_ambiguous_phrases_return_clear_errors(text: str, error_text: str) -> None:
    result = _parse_one(text)

    assert not result.success
    assert error_text in result.error


def test_empty_intersection_returns_a_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(
        order_parser,
        "get_zodiac_number_map",
        lambda _year: {zodiac: [] for zodiac in (*DOMESTIC_ZODIACS, *WILD_ZODIACS)},
    )

    result = _parse_one("家肖大数各10")

    assert not result.success
    assert "交集为空" in result.error


def test_one_invalid_line_does_not_hide_another_valid_line() -> None:
    results = parse_lines("家肖大数各100\n野肖小数", zodiac_year=2026)

    assert len(results) == 2
    assert results[0].success and results[0].total == Decimal("1300")
    assert not results[1].success and "缺少金额" in results[1].error


def test_existing_play_priorities_do_not_regress() -> None:
    standalone_big = _parse_one("大数各100")
    pingte = _parse_one("龙羊猴各80")
    lianxiao = _parse_one("龙羊虎连肖100")
    zodiac_numbers = _parse_one("鼠各数130")
    special_zodiac = _parse_one("香港特码：蛇包80")
    duplicate_special = _parse_one("特码49、49，各10")

    assert standalone_big.success and standalone_big.category == "大"
    assert pingte.success and pingte.category == "多生肖" and pingte.total == Decimal("240")
    assert lianxiao.success and lianxiao.category == "连肖" and lianxiao.total == Decimal("100")
    assert zodiac_numbers.category == "特码" and zodiac_numbers.numbers == (7, 19, 31, 43)
    assert special_zodiac.category == "特码生肖" and special_zodiac.numbers == ()
    assert duplicate_special.category == "特码" and duplicate_special.numbers == (49, 49)


def test_saved_expansion_settles_with_existing_special_number_matcher(session_factory) -> None:
    intake = OrderIntakeService(session_factory)
    preview = intake.preview_raw_text("家肖大数各100", region="澳门", zodiac_year=2026)
    saved = intake.save_preview(preview)
    assert saved.success and saved.order is not None

    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "特码", "2", "0")
    draw = DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="DOMESTIC-WILD-001",
            draw_date=date(2026, 7, 15),
            regular_numbers=["30", "01", "02", "03", "04", "05"],
            special_number="25",
        )
    )

    settlement = SettlementService(session_factory).commit_order_settlement(saved.order.id, draw.id)

    assert len(settlement.results) == 13
    assert [item.selection for item in settlement.results if item.is_winner] == ["25"]
    assert all(item.draw_scope == "special_only" for item in settlement.results)
    assert settlement.total_payout_amount == Decimal("200")
