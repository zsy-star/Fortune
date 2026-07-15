from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import OperationLog, Order
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_intake_schema import IntakeMetadata, IntakeTableRow
from schemas.order_schema import OrderItemCreate
from services.draw_service import DrawService
from services.log_service import LogService
from services.order_intake_mapper import (
    IntakeConversionError,
    RegionConflictError,
    convert_parse_result,
    resolve_region,
    to_decimal_amount,
)
from services.order_intake_service import OrderIntakeService
from services.order_parser import ParseOptions, parse_order
from services.settlement_service import SettlementService


def _preview(text: str, **kwargs):
    return OrderIntakeService().preview_raw_text(text, **kwargs)


def _first_valid_item(preview):
    return next(item for item in preview.items if item.is_valid)


def test_nickname_is_excluded_from_preview_and_saved_order(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    preview = service.preview_raw_text(
        "王大定:\n01/10",
        customer_name="昵称安全测试",
        channel="微信",
        region="澳门",
    )

    assert preview.can_save
    assert preview.raw_text == "01/10"
    assert preview.valid_items == 1 and preview.invalid_items == 0
    assert all("王大定" not in item.source_line for item in preview.items)
    assert all(getattr(item, "note", None) is None for item in preview.order_items)
    assert not hasattr(preview, "nickname")

    saved = service.save_preview(preview)
    assert saved.success and saved.order is not None
    detail = service._order_service.get_order(saved.order.id)
    assert detail is not None
    assert detail.raw_text == "01/10"
    assert detail.customer_name == "昵称安全测试"
    assert all("王大定" not in (item.note or "") for item in detail.items)


def test_nickname_is_excluded_from_adjusted_table_raw_text() -> None:
    service = OrderIntakeService()
    preview = service.preview_table_rows(
        [
            IntakeTableRow(
                row_number=1,
                region="澳门",
                bet_type="特码",
                selection="01",
                total_amount="10",
                per_item_amount="10",
                note="原备注",
            )
        ],
        IntakeMetadata(
            channel="微信",
            region="澳门",
            source="record_window_adjusted",
            raw_text="王大定:\n01/10",
        ),
    )

    assert preview.can_save
    assert preview.raw_text == "01/10"
    assert preview.order_items[0].note == "原备注"


def test_nickname_does_not_count_as_partial_failure() -> None:
    with_nickname = _preview("王大定:\n01/10\n50/10", region="澳门")
    baseline = _preview("01/10\n50/10", region="澳门")

    assert (with_nickname.valid_items, with_nickname.invalid_items) == (
        baseline.valid_items,
        baseline.invalid_items,
    ) == (1, 1)
    assert all("王大定" not in item.source_line for item in with_nickname.items)


def test_nickname_only_cannot_create_preview_order() -> None:
    preview = _preview("王大定:", region="澳门")

    assert not preview.can_save
    assert preview.raw_text == ""
    assert preview.items == []
    assert preview.valid_items == preview.invalid_items == 0
    assert preview.errors == ["输入为空"]


def test_nickname_does_not_change_four_zodiac_settlement_support() -> None:
    preview = _preview("王大定:\n虎猴鼠龙。兔羊猪鸡四肖各10块钱", region="澳门")

    assert preview.can_save
    assert preview.raw_text == "虎猴鼠龙。兔羊猪鸡四肖各10块钱"
    assert len(preview.order_items) == 2
    assert all(item.bet_type == "四肖" for item in preview.order_items)
    assert all(item.settlement_support_status == "unsupported" for item in preview.items)


def test_hong_kong_blue_wave_alias_uses_existing_intake_and_settlement_mapping() -> None:
    preview = _preview("香港兰波各数280")

    assert preview.can_save
    assert preview.region == "香港"
    assert preview.total_amount == Decimal("4480")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("特码波色", "蓝波", Decimal("4480")),
    ]
    valid_item = _first_valid_item(preview)
    assert valid_item.settlement_support_status == "supported"


def test_mixed_zodiac_and_number_amount_pairs_expand_and_preserve_additional_stakes() -> None:
    preview = _preview("鼠各数130-31/75-43/75", region="香港")

    assert preview.can_save
    assert preview.total_amount == Decimal("670")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("特码", "07", Decimal("130")),
        ("特码", "19", Decimal("130")),
        ("特码", "31", Decimal("130")),
        ("特码", "43", Decimal("130")),
        ("特码", "31", Decimal("75")),
        ("特码", "43", Decimal("75")),
    ]
    assert all(item.normalized_bet_type == "special_number" for item in preview.items if item.is_valid)


def test_hong_kong_special_block_excludes_header_and_summary_from_persistence() -> None:
    raw = (
        "香港特\n11.23各数20米\n35.47各数10米\n"
        "鼠猪鸡兔各数5米\n02.03.13.33各数5米\n共计:160米"
    )
    preview = _preview(raw)

    assert preview.can_save and preview.region == "香港"
    assert preview.total_amount == Decimal("160")
    assert len(preview.order_items) == 24
    assert all(item.bet_type == "特码" for item in preview.order_items)
    assert "香港特" not in preview.raw_text
    assert "共计" not in preview.raw_text
    assert preview.raw_text.splitlines() == [
        "11.23各数20米", "35.47各数10米", "鼠猪鸡兔各数5米", "02.03.13.33各数5米"
    ]


def test_declared_total_mismatch_blocks_save_without_creating_summary_item() -> None:
    preview = _preview("香港特\n11.23各数20米\n共计:50米")

    assert not preview.can_save
    assert preview.total_amount == Decimal("40")
    assert preview.errors == ["输入合计50，识别合计40，相差10"]
    assert len(preview.order_items) == 2
    assert all("共计" not in item.selection for item in preview.order_items)
    assert preview.raw_text == "11.23各数20米"


def test_hong_kong_issue_batch_preserves_duplicate_number_order_items() -> None:
    raw = (
        "港76期\n主猴羊各数20斤\n12，23，12，24各20斤\n"
        "10，17，29，41，20，22，34，46各10斤\n共320斤"
    )
    preview = _preview(raw)

    assert preview.can_save and preview.total_amount == Decimal("320")
    repeated_twelves = [item for item in preview.order_items if item.selection == "12"]
    assert len(repeated_twelves) == 3
    assert [item.amount for item in repeated_twelves] == [Decimal("20")] * 3
    assert "76期" not in preview.raw_text and "共320" not in preview.raw_text


def test_zodiac_package_saves_as_real_special_zodiac_and_order_detail_matches(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    preview = service.preview_raw_text("香港特码：蛇 包80")

    assert preview.can_save and preview.total_amount == Decimal("80")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("特码生肖", "蛇", Decimal("80")),
    ]
    valid_item = _first_valid_item(preview)
    assert valid_item.original_bet_type == "特码生肖"
    assert valid_item.order_bet_type == "特码生肖"
    assert valid_item.normalized_bet_type == "special_zodiac"
    assert valid_item.settlement_support_status == "supported"

    saved = service.save_preview(preview)
    assert saved.success and saved.order is not None
    detail = service._order_service.get_order(saved.order.id)
    assert detail is not None
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        ("特码生肖", "蛇", Decimal("80")),
    ]


@pytest.mark.parametrize(
    ("text", "category", "norm_type", "order_type"),
    [
        ("01/10", "单号投注", "special_number", "特码"),
        ("1 2各10", "纯数字", "special_number", "特码"),
        ("兔各10", "兔", "special_zodiac", "特码"),
        ("红波各10", "红波", "special_color", "特码波色"),
        ("红单各10", "红单", "special_half_wave", "包半波"),
        ("大各10", "大", "special_size", "特码两面"),
        ("小各10", "小", "special_size", "特码两面"),
        ("单各10", "单", "special_parity", "特码两面"),
        ("双各10", "双", "special_parity", "特码两面"),
        ("尾1各10", "尾1", "special_tail", "特码"),
        ("1头各10", "1头", "special_head", "特码"),
        ("合单各10", "合单", "special_sum_parity", "特码"),
        ("合大各10", "合大", "special_sum_size", "特码"),
        ("金各10", "金", "special_element", "特码"),
    ],
)
def test_category_conversion(text, category, norm_type, order_type) -> None:
    preview = _preview(text, region="澳门")
    assert preview.can_save
    assert preview.region == "澳门"
    item = _first_valid_item(preview)
    assert item.original_bet_type == category
    assert item.normalized_bet_type == norm_type
    assert item.order_bet_type == order_type


def test_decimal_amounts_and_multi_number_total() -> None:
    preview = _preview("1,2,03各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("30.00")
    amounts = [item.amount for item in preview.items if item.is_valid]
    assert amounts == [Decimal("10.00"), Decimal("10.00"), Decimal("10.00")]
    assert preview.order_items[0].selection == "01"
    assert preview.order_items[2].selection == "03"


def test_no_double_multiply_for_category_bet() -> None:
    preview = _preview("红波各10", region="澳门")
    assert preview.can_save
    assert len(preview.order_items) == 1
    expected_total = Decimal(str(parse_order("红波各10").total))
    assert preview.order_items[0].amount == expected_total
    assert preview.total_amount == expected_total


def test_preview_raw_text_passes_zodiac_year_to_parser() -> None:
    preview = _preview("兔各10", region="澳门", parse_options=ParseOptions(zodiac_year=2025))

    assert preview.can_save
    assert preview.zodiac_year == 2025
    assert [item.selection for item in preview.order_items] == ["03", "15", "27", "39"]
    assert [item.amount for item in preview.order_items] == [Decimal("10")] * 4
    assert preview.total_amount == Decimal("40")


def test_reject_zero_negative_and_invalid_amounts() -> None:
    with pytest.raises(IntakeConversionError):
        to_decimal_amount(0)
    with pytest.raises(IntakeConversionError):
        to_decimal_amount(-1)
    with pytest.raises(IntakeConversionError):
        to_decimal_amount("abc")

    preview = _preview("兔各0", region="澳门")
    assert not preview.can_save
    assert preview.invalid_items >= 1


def test_selection_normalization() -> None:
    preview = _preview("1,2,03各10", region="澳门")
    selections = [item.normalized_selection for item in preview.items if item.is_valid]
    assert selections == ["01", "02", "03"]


def test_invalid_number_rejected() -> None:
    preview = _preview("50各10", region="澳门")
    assert not preview.can_save
    assert preview.errors or preview.invalid_items > 0


def test_region_macau_and_hong_kong() -> None:
    macau = _preview("01/10", region="澳门")
    hk = _preview("香港01/10", region="香港")
    assert macau.region == "澳门"
    assert hk.region == "香港"


def test_region_text_and_param_agree() -> None:
    preview = _preview("澳门01/10", region="澳门")
    assert preview.can_save
    assert preview.region == "澳门"


def test_region_conflict_rejected() -> None:
    with pytest.raises(RegionConflictError):
        resolve_region(text_region="香港", param_region="澳门")

    preview = _preview("香港01/10", region="澳门")
    assert not preview.can_save
    assert any("不一致" in error for error in preview.errors)


def test_default_region_macau() -> None:
    preview = _preview("01/10")
    assert preview.region == "澳门"


def test_multi_zodiac_converts_to_independent_zodiac_items() -> None:
    preview = _preview("兔龙蛇各20", region="澳门")
    assert preview.can_save
    assert len(preview.order_items) == 3
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("平特一肖", "兔", Decimal("20")),
        ("平特一肖", "龙", Decimal("20")),
        ("平特一肖", "蛇", Decimal("20")),
    ]
    assert preview.total_amount == Decimal("60")


def test_explicit_lianxiao_intake_uses_group_amount() -> None:
    preview = _preview("连肖 龙羊猴 各30", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("30.00")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "连肖"
    assert item.selection == "龙,羊,猴"
    assert item.amount == Decimal("30.00")
    row = _first_valid_item(preview)
    assert row.original_bet_type == "连肖"
    assert row.normalized_bet_type == "lianxiao_zodiac"
    assert row.normalized_selection == "龙,羊,猴"


def test_explicit_lianxiao_long_selection_is_not_multiplied() -> None:
    preview = _preview("连肖 狗鼠龙羊猴 各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("10.00")
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "连肖"
    assert preview.order_items[0].selection == "鼠,龙,羊,猴,狗"
    assert preview.order_items[0].amount == Decimal("10.00")


def test_lianxiao_suffix_intake_uses_group_amount() -> None:
    preview = _preview("龙羊猴连肖30", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("30.00")
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "连肖"
    assert preview.order_items[0].selection == "龙,羊,猴"
    assert preview.order_items[0].amount == Decimal("30.00")


def test_explicit_lianxiao_save_and_read_keeps_one_group_item(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    save_result = service.parse_and_save(
        "连肖 龙羊猴 各30",
        region="澳门",
        source="test",
        customer_name="连肖保存测试",
        channel="微信",
    )
    assert save_result.success
    assert save_result.order is not None
    assert save_result.order.total_amount == Decimal("30.00")
    assert save_result.order.item_count == 1

    detail = service._order_service.get_order(save_result.order.id)
    assert detail is not None
    assert len(detail.items) == 1
    assert detail.items[0].bet_type == "连肖"
    assert detail.items[0].selection == "龙,羊,猴"
    assert detail.items[0].amount == Decimal("30.00")


def test_special_zodiac_parse_options_save_as_pingte_zodiac() -> None:
    preview = _preview("马蛇10", region="澳门", parse_options=ParseOptions(special_zodiac_mode=True))
    assert preview.can_save
    assert preview.total_amount == Decimal("20.00")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("平特一肖带主肖", "马", Decimal("10.00")),
        ("平特一肖", "蛇", Decimal("10.00")),
    ]


def test_default_multi_zodiac_intake_counts_zodiac_items() -> None:
    preview = _preview("羊马各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("20.00")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("平特一肖", "羊", Decimal("10")),
        ("平特一肖带主肖", "马", Decimal("10")),
    ]


def test_zodiac_each_parse_options_count_zodiac_groups() -> None:
    preview = _preview("羊马各10", region="澳门", parse_options=ParseOptions(zodiac_each_mode=True))
    assert preview.can_save
    assert preview.total_amount == Decimal("20.00")
    assert [(item.bet_type, item.selection) for item in preview.order_items] == [
        ("平特一肖", "羊"),
        ("平特一肖带主肖", "马"),
    ]


def test_age_writing_parse_options_are_opt_in_for_intake() -> None:
    disabled = _preview("25岁各10", region="澳门")
    assert not disabled.can_save
    assert disabled.invalid_items == 1

    enabled = _preview("25岁各10", region="澳门", parse_options=ParseOptions(age_writing=True))
    assert enabled.can_save
    assert enabled.total_amount == Decimal("10.00")
    assert enabled.order_items[0].bet_type == "特码"
    assert enabled.order_items[0].selection == "25"


def test_multi_zodiac_is_intentionally_split_by_zodiac() -> None:
    preview = _preview("鼠牛各10", region="澳门")
    assert [(item.bet_type, item.selection) for item in preview.order_items] == [
        ("平特一肖", "鼠"),
        ("平特一肖", "牛"),
    ]


def test_each_package_multi_zodiac_matches_existing_each_output() -> None:
    packaged = _preview("牛兔马猪各包10", region="澳门")
    existing = _preview("牛兔马猪各10", region="澳门")

    assert packaged.can_save and existing.can_save
    assert packaged.total_amount == existing.total_amount == Decimal("40")
    assert packaged.order_items == existing.order_items
    assert [(item.bet_type, item.selection, item.amount) for item in packaged.order_items] == [
        ("平特一肖", "牛", Decimal("10")),
        ("平特一肖", "兔", Decimal("10")),
        ("平特一肖带主肖", "马", Decimal("10")),
        ("平特一肖", "猪", Decimal("10")),
    ]
    assert all(row.settlement_support_status == "supported" for row in packaged.items)


def test_each_package_normalization_does_not_change_package_bet_names() -> None:
    package_half_wave = parse_order("包半波红单各10")
    full_package = parse_order("全包各10")

    assert package_half_wave.success
    assert package_half_wave.category == "包半波"
    assert full_package.success
    assert full_package.category == "全包"


def test_full_package_not_silently_dropped() -> None:
    preview = _preview("全包各10", region="澳门")
    assert not preview.can_save
    assert any("全包" in error for error in preview.errors)


@pytest.mark.parametrize(
    ("text", "selection"),
    [
        ("N不中 08,09,10,11,12 各100", "08,09,10,11,12"),
        ("不中 08,09,10,11,12 各100", "08,09,10,11,12"),
        ("5不中 08,09,10,11,12 各100", "08,09,10,11,12"),
        ("六不中 08,09,10,11,12,13 各100", "08,09,10,11,12,13"),
    ],
)
def test_non_hit_intake_saves_one_group_item(text: str, selection: str) -> None:
    preview = _preview(text, region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("100.00")
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "N不中"
    assert preview.order_items[0].selection == selection
    assert preview.order_items[0].amount == Decimal("100.00")


@pytest.mark.parametrize(
    "text",
    [
        "6 18 31 43 22 10 03 15 01 13 十不中 4000",
        "6.18.31.43.22.10.03.15.01.13十不中4000",
        "6/18/31/43/22/10/03/15/01/13十不中各4000",
    ],
)
def test_ten_non_hit_intake_saves_one_group_item(text: str) -> None:
    preview = _preview(text, region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("4000")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "N不中"
    assert item.selection == "01,03,06,10,13,15,18,22,31,43"
    assert item.amount == Decimal("4000")
    assert preview.items[0].settlement_support_status == "supported"


def test_number_fuxuan_intake_saves_one_summary_item_with_note() -> None:
    preview = _preview("复3 01,02,03,04 各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("40.00")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "几中几复选"
    assert item.selection == "01,02,03,04"
    assert item.amount == Decimal("40.00")
    assert item.note == "复选类型=复3"
    assert not any("复选类玩法" in warning for warning in preview.warnings)
    row = _first_valid_item(preview)
    assert row.original_bet_type == "几中几复选"
    assert row.order_selection == "01,02,03,04"
    assert row.normalized_bet_type == "number_fuxuan"
    assert row.settlement_support_status == "unsupported"


def test_lianxiao_fuxuan_intake_saves_one_summary_item_with_note() -> None:
    preview = _preview("兔狗虎蛇龙 复4 各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("50.00")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "连肖复选"
    assert item.selection == "兔,狗,虎,蛇,龙"
    assert item.amount == Decimal("50.00")
    assert item.note == "复选类型=复4"
    assert any("复选类玩法" in warning for warning in preview.warnings)
    row = _first_valid_item(preview)
    assert row.settlement_support_status == "unsupported"
    assert "暂不支持正式结算" in (row.settlement_support_message or "")
    assert any("暂不支持正式结算" in warning for warning in preview.warnings)


def test_reference_fushi_lianxiao_intake_preserves_combo_note() -> None:
    preview = _preview("牛鸡猪狗虎复试3.4.5连各组50", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("800.00")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "连肖复选"
    assert item.selection == "牛,鸡,猪,狗,虎"
    assert item.amount == Decimal("800.00")
    assert "复选类型=复3.4.5" in (item.note or "")
    assert "组合数=16" in (item.note or "")


def test_reference_smart_intake_split_preview_and_exclusion_note() -> None:
    preview = _preview("羊猪狗兔马龙各数10，1号不要，猴鸡数各5", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("280.00")
    assert len(preview.order_items) == 32
    assert all(item.selection != "01" for item in preview.order_items)
    assert any(item.note == "排除号码=01" for item in preview.order_items)
    assert any("已排除号码" in warning for warning in preview.warnings)


def test_unsupported_settlement_combo_is_saveable_with_warning() -> None:
    preview = _preview("二中特 01 02 各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("10.00")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "二中特"
    assert item.selection == "01,02"
    assert item.note == "结算规则待确认"
    assert any("结算预览暂不支持" in warning for warning in preview.warnings)
    row = _first_valid_item(preview)
    assert row.settlement_support_status == "unsupported"
    assert "暂不支持正式结算" in (row.settlement_support_message or "")


def test_fuxuan_intake_save_and_read_preserves_fuxuan_type_note(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    save_result = service.parse_and_save(
        "复2 01,02,03,04,05 各10",
        region="澳门",
        source="test",
        customer_name="复选保存测试",
        channel="微信",
    )
    assert save_result.success
    assert save_result.order is not None
    assert save_result.order.total_amount == Decimal("100.00")

    detail = service._order_service.get_order(save_result.order.id)
    assert detail is not None
    assert len(detail.items) == 1
    assert detail.items[0].bet_type == "几中几复选"
    assert detail.items[0].selection == "01,02,03,04,05"
    assert detail.items[0].amount == Decimal("100.00")
    assert detail.items[0].note == "复选类型=复2"


def test_lianma_intake_saves_stable_selection_and_note() -> None:
    preview = _preview("二中二 (01-02)-(03-04) 各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("20.00")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "二中二"
    assert item.selection == "(01-02)-(03-04)"
    assert item.amount == Decimal("20.00")
    assert item.note == "连码组合数=2;连码组大小=2"
    assert not any("连码类玩法" in warning for warning in preview.warnings)
    row = _first_valid_item(preview)
    assert row.original_bet_type == "二中二"
    assert row.order_selection == "(01-02)-(03-04)"
    assert row.normalized_bet_type == "lianma_two_two"


def test_lianma_drag_intake_saves_one_summary_item() -> None:
    preview = _preview("二中二 01,02,03,04,05 拖 06,07,08,09,10 各5", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("125.00")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "二中二"
    assert item.selection.startswith("(01-06)-(01-07)-(01-08)")
    assert item.selection.endswith("(05-10)")
    assert item.amount == Decimal("125.00")
    assert item.note == "拖式组合数=25;连码组大小=2"


@pytest.mark.parametrize(
    ("text", "bet_type", "selection", "amount", "note"),
    [
        ("三中三 01,02,03 各10", "三中三", "(01-02-03)", Decimal("10.00"), "连码组合数=1;连码组大小=3"),
        (
            "三中三 (01-02-03)-(04-05-06) 各10",
            "三中三",
            "(01-02-03)-(04-05-06)",
            Decimal("20.00"),
            "连码组合数=2;连码组大小=3",
        ),
        ("三中二 01,02,03 各10", "三中二", "(01-02-03)", Decimal("10.00"), "连码组合数=1;连码组大小=3"),
        (
            "三中二 (01-02-03)-(04-05-06) 各10",
            "三中二",
            "(01-02-03)-(04-05-06)",
            Decimal("20.00"),
            "连码组合数=2;连码组大小=3",
        ),
    ],
)
def test_lianma_intake_amount_preview(
    text: str,
    bet_type: str,
    selection: str,
    amount: Decimal,
    note: str,
) -> None:
    preview = _preview(text, region="澳门")
    assert preview.can_save
    assert preview.total_amount == amount
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == bet_type
    assert preview.order_items[0].selection == selection
    assert preview.order_items[0].amount == amount
    assert preview.order_items[0].note == note


def test_lianma_intake_save_and_read_preserves_note(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    save_result = service.parse_and_save(
        "二中二 (01-02)-(03-04) 各10",
        region="澳门",
        source="test",
        customer_name="连码保存测试",
        channel="微信",
    )
    assert save_result.success
    assert save_result.order is not None
    assert save_result.order.total_amount == Decimal("20.00")
    assert save_result.order.item_count == 1

    detail = service._order_service.get_order(save_result.order.id)
    assert detail is not None
    assert len(detail.items) == 1
    assert detail.items[0].bet_type == "二中二"
    assert detail.items[0].selection == "(01-02)-(03-04)"
    assert detail.items[0].amount == Decimal("20.00")
    assert detail.items[0].note == "连码组合数=2;连码组大小=2"


def test_pingwei_intake_saves_independent_tail_items() -> None:
    preview = _preview("平尾 1,3,4,6 各1000", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("4000.00")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("平尾", "1", Decimal("1000.00")),
        ("平尾", "3", Decimal("1000.00")),
        ("平尾", "4", Decimal("1000.00")),
        ("平尾", "6", Decimal("1000.00")),
    ]
    assert all(row.normalized_bet_type == "ping_tail" for row in preview.items)
    assert all(row.settlement_support_status == "supported" for row in preview.items)


@pytest.mark.parametrize(
    "text",
    [
        "平尾 1-3-4-6 各1000",
        "1,3,4,6 平尾 各1000",
        "1-3-4-6平尾1000",
    ],
)
def test_pingwei_intake_supported_formats(text: str) -> None:
    preview = _preview(text, region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("4000.00")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("平尾", "1", Decimal("1000.00")),
        ("平尾", "3", Decimal("1000.00")),
        ("平尾", "4", Decimal("1000.00")),
        ("平尾", "6", Decimal("1000.00")),
    ]


def test_pingwei_intake_rejects_duplicate_tails() -> None:
    preview = _preview("平尾 4,1,4,3 各100", region="澳门")
    assert not preview.can_save
    assert any("重复" in error for error in preview.errors)


def test_pingwei_intake_save_and_read_preserves_independent_tail_items(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    save_result = service.parse_and_save(
        "平尾 1,3,4,6 各1000",
        region="澳门",
        source="test",
        customer_name="平尾保存测试",
        channel="微信",
    )
    assert save_result.success
    assert save_result.order is not None
    assert save_result.order.total_amount == Decimal("4000.00")
    assert save_result.order.item_count == 4

    detail = service._order_service.get_order(save_result.order.id)
    assert detail is not None
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        ("平尾", "1", Decimal("1000.00")),
        ("平尾", "3", Decimal("1000.00")),
        ("平尾", "4", Decimal("1000.00")),
        ("平尾", "6", Decimal("1000.00")),
    ]


def test_complex_play_warning_when_saveable() -> None:
    preview = _preview("连兔龙蛇各20", region="澳门")
    assert preview.can_save
    assert preview.order_items[0].bet_type == "连肖"
    assert preview.items[0].settlement_support_status == "supported"
    assert not any("简化口径" in warning for warning in preview.warnings)


def test_convert_parse_result_integration_with_parser() -> None:
    result = parse_order("01/10")
    previews, order_items, warnings, errors = convert_parse_result(result, "01/10")
    assert not errors
    assert len(order_items) == 1
    assert order_items[0].bet_type == "特码"
    assert order_items[0].selection == "01"
    assert order_items[0].amount == Decimal("10")


def test_save_end_to_end(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    preview = service.preview_raw_text(
        "01/10\n02/20",
        customer_name="接入测试",
        channel="微信",
        region="澳门",
        source="test",
    )
    assert preview.can_save
    assert preview.total_amount == Decimal("30.00")

    save_result = service.save_preview(preview)
    assert save_result.success
    assert save_result.order is not None
    assert save_result.order.item_count == 2
    assert save_result.order.total_amount == Decimal("30.00")

    with session_factory() as session:
        order_count = session.scalar(select(func.count(Order.id)))
        log_count = session.scalar(select(func.count(OperationLog.id)))
        assert order_count == 1
        assert log_count == 1
    assert save_result.order.item_count == 2

    detail = service._order_service.get_order(save_result.order.id)
    assert detail is not None
    assert detail.status == "active"
    assert {item.selection for item in detail.items} == {"01", "02"}


def test_preview_table_rows_recalculates_total_and_expands_numbers() -> None:
    service = OrderIntakeService()
    preview = service.preview_table_rows(
        [
            IntakeTableRow(
                row_number=1,
                region="澳门",
                bet_type="特码",
                selection="01,02",
                total_amount="30",
                per_item_amount="10",
                note="manual row",
            )
        ],
        IntakeMetadata(channel="个人微信", region="澳门", source="record_window_adjusted", raw_text="01,02各10"),
    )

    assert preview.can_save
    assert preview.total_amount == Decimal("30.00")
    assert [item.selection for item in preview.order_items] == ["01", "02"]
    assert [item.amount for item in preview.order_items] == [Decimal("15.00"), Decimal("15.00")]


def test_adjusted_table_preview_and_save_preserve_declarer(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    preview = service.preview_table_rows(
        [
            IntakeTableRow(
                row_number=1,
                region="澳门",
                bet_type="特码",
                selection="01",
                total_amount="10",
            )
        ],
        IntakeMetadata(
            customer_name="林林",
            config_plan_name="46倍6水",
            channel="个人微信",
            region="澳门",
            source="record_window_adjusted",
            raw_text="01/10",
        ),
    )

    assert preview.can_save
    assert preview.customer_name == "林林"
    assert preview.config_plan_name == "46倍6水"
    saved = service.save_preview(preview)
    assert saved.success
    detail = service._order_service.get_order(saved.order.id)
    assert detail is not None
    assert detail.customer_name == "林林"
    logs = LogService(session_factory).list_logs(module="order", action="create")
    assert len(logs) == 1
    assert "declarer=林林" in logs[0].description
    assert "config_plan=46倍6水" in logs[0].description


def test_preview_table_rows_rejects_invalid_amount() -> None:
    service = OrderIntakeService()
    preview = service.preview_table_rows(
        [
            IntakeTableRow(
                row_number=1,
                region="澳门",
                bet_type="特码",
                selection="01",
                total_amount="abc",
            )
        ],
        IntakeMetadata(channel="个人微信", region="澳门", source="record_window_adjusted", raw_text="01/10"),
    )

    assert not preview.can_save
    assert any("第 1 行金额不是有效数字" in error for error in preview.errors)


def test_preview_table_rows_rejects_mixed_regions() -> None:
    service = OrderIntakeService()
    preview = service.preview_table_rows(
        [
            IntakeTableRow(row_number=1, region="澳门", bet_type="特码", selection="01", total_amount="10"),
            IntakeTableRow(row_number=2, region="香港", bet_type="特码", selection="02", total_amount="10"),
        ],
        IntakeMetadata(channel="个人微信", region="澳门", source="record_window_adjusted", raw_text="mixed"),
    )

    assert not preview.can_save
    assert any("表格地区不一致" in error for error in preview.errors)


def test_invalid_item_allows_confirmed_success_only_save(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    preview = service.preview_raw_text("01/10\n50/10", region="澳门")
    assert preview.can_save
    assert preview.valid_items == 1
    assert preview.invalid_items == 1
    assert any("仅保存" in warning for warning in preview.warnings)

    unconfirmed = service.save_preview(preview)
    assert not unconfirmed.success
    assert "明确确认" in (unconfirmed.error or "")

    save_result = service.save_preview(preview, allow_partial=True)
    assert save_result.success

    with session_factory() as session:
        assert session.scalar(select(func.count(Order.id))) == 1
        assert session.scalar(select(func.count(OperationLog.id))) == 1


def test_saved_order_can_be_settlement_previewed(session_factory) -> None:
    order_service = OrderIntakeService(session_factory)._order_service
    draw_service = DrawService(session_factory)
    intake = OrderIntakeService(session_factory)

    save_result = intake.parse_and_save(
        "01/10",
        region="澳门",
        source="test",
        customer_name="结算联调",
        channel="微信",
    )
    assert save_result.success
    order = save_result.order
    draw = draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="162",
            draw_date=date(2026, 6, 11),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="01",
        )
    )
    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    assert preview.winning_items == 1


def test_real_sample_fushi_three_in_two_intake_summary() -> None:
    preview = _preview("10 11 24 38复式三中二一组20", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("80")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "三中二"
    assert item.selection == "(10-11-24)-(10-11-38)-(10-24-38)-(11-24-38)"
    assert item.amount == Decimal("80")
    assert item.note == "连码组合数=4;连码组大小=3"


def test_real_sample_pingte_six_tail_intake_is_supported_by_v2() -> None:
    preview = _preview("平特6尾1000", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("1000")
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "平尾"
    assert preview.order_items[0].selection == "6"
    assert _first_valid_item(preview).settlement_support_status == "supported"


def test_real_sample_partial_success_preview_keeps_error_and_four_zodiacs() -> None:
    preview = _preview("27.49.47.27.44.32各5，龙猪鸡猴各20", region="澳门")
    assert preview.can_save
    assert preview.valid_items == 4
    assert preview.invalid_items == 1
    assert preview.total_amount == Decimal("80")
    assert "号码27重复" in preview.errors[0]
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("平特一肖", "龙", Decimal("20")),
        ("平特一肖", "猪", Decimal("20")),
        ("平特一肖", "鸡", Decimal("20")),
        ("平特一肖", "猴", Decimal("20")),
    ]


def test_real_sample_four_zodiac_groups_are_accounting_only() -> None:
    preview = _preview("虎猴鼠龙。兔羊猪鸡四肖各10块钱", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("20")
    assert len(preview.order_items) == 2
    assert all(item.bet_type == "四肖" and item.amount == Decimal("10") for item in preview.order_items)
    valid_rows = [row for row in preview.items if row.is_valid]
    assert all(row.settlement_support_status == "unsupported" for row in valid_rows)
    assert all(row.order_bet_type != "连肖" for row in valid_rows)


def test_real_sample_spoken_zodiacs_and_block_region_intake() -> None:
    preview = _preview("蛇马羊猴鸡鼠，各数5米，澳门。", region="澳门")
    assert preview.can_save
    assert preview.region == "澳门"
    assert preview.total_amount == Decimal("30")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("平特一肖", "蛇", Decimal("5")),
        ("平特一肖带主肖", "马", Decimal("5")),
        ("平特一肖", "羊", Decimal("5")),
        ("平特一肖", "猴", Decimal("5")),
        ("平特一肖", "鸡", Decimal("5")),
        ("平特一肖", "鼠", Decimal("5")),
    ]


def test_real_sample_new_macau_special_title_intake() -> None:
    preview = _preview(
        "新奥\n特\n02,06,20,22,26,28,32,40,42,48 各5",
        region="澳门",
    )
    assert preview.can_save
    assert preview.total_amount == Decimal("50")
    assert len(preview.order_items) == 10
    assert all(item.bet_type == "特码" and item.amount == Decimal("5") for item in preview.order_items)
