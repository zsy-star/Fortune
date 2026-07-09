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


def test_lianxiao_not_converted_to_single_zodiac() -> None:
    preview = _preview("兔龙蛇各20", region="澳门")
    assert preview.can_save
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "连肖"
    assert preview.order_items[0].selection == "兔,龙,蛇"
    assert preview.order_items[0].amount == Decimal(str(parse_order("兔龙蛇各20").total))
    assert any("整组金额" in warning for warning in preview.warnings)


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
    assert row.normalized_bet_type == "special_zodiac_group"
    assert row.normalized_selection == "龙,羊,猴"


def test_explicit_lianxiao_long_selection_is_not_multiplied() -> None:
    preview = _preview("连肖 狗鼠龙羊猴 各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("10.00")
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "连肖"
    assert preview.order_items[0].selection == "狗,鼠,龙,羊,猴"
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
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "平特一肖"
    assert preview.order_items[0].selection == "马,蛇"
    assert preview.order_items[0].amount == Decimal("20.00")


def test_default_multi_zodiac_intake_keeps_previous_total_and_bet_type() -> None:
    preview = _preview("羊马各10", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("90.00")
    assert preview.order_items[0].bet_type == "连肖"
    assert preview.order_items[0].selection == "羊,马"
    assert preview.order_items[0].amount == Decimal("90.00")


def test_zodiac_each_parse_options_count_zodiac_groups() -> None:
    preview = _preview("羊马各10", region="澳门", parse_options=ParseOptions(zodiac_each_mode=True))
    assert preview.can_save
    assert preview.total_amount == Decimal("20.00")
    assert preview.order_items[0].bet_type == "平特一肖"
    assert preview.order_items[0].selection == "羊,马"


def test_age_writing_parse_options_are_opt_in_for_intake() -> None:
    disabled = _preview("25岁各10", region="澳门")
    assert not disabled.can_save
    assert disabled.invalid_items == 1

    enabled = _preview("25岁各10", region="澳门", parse_options=ParseOptions(age_writing=True))
    assert enabled.can_save
    assert enabled.total_amount == Decimal("10.00")
    assert enabled.order_items[0].bet_type == "特码"
    assert enabled.order_items[0].selection == "25"


def test_multi_zodiac_not_silently_split() -> None:
    preview = _preview("鼠牛各10", region="澳门")
    assert preview.order_items[0].bet_type == "连肖"
    assert "鼠,牛" in preview.order_items[0].selection


def test_full_package_not_silently_dropped() -> None:
    preview = _preview("全包各10", region="澳门")
    assert not preview.can_save
    assert any("全包" in error for error in preview.errors)


@pytest.mark.parametrize(
    ("text", "selection"),
    [
        ("N不中 08,09,10 各100", "08,09,10"),
        ("不中 08,09,10 各100", "08,09,10"),
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
    assert row.settlement_support_status == "supported"


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


def test_pingwei_intake_saves_one_summary_item() -> None:
    preview = _preview("平尾 1,3,4,6 各1000", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("4000.00")
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert item.bet_type == "平尾"
    assert item.selection == "1,3,4,6"
    assert item.amount == Decimal("4000.00")
    assert item.note == "平尾尾数个数=4"
    assert not any("平尾" in warning for warning in preview.warnings)
    row = _first_valid_item(preview)
    assert row.original_bet_type == "平尾"
    assert row.order_selection == "1,3,4,6"
    assert row.normalized_bet_type == "ping_tail"


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
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "平尾"
    assert preview.order_items[0].selection == "1,3,4,6"


def test_pingwei_intake_deduplicates_tails() -> None:
    preview = _preview("平尾 4,1,4,3 各100", region="澳门")
    assert preview.can_save
    assert preview.total_amount == Decimal("300.00")
    assert preview.order_items[0].selection == "1,3,4"
    assert preview.order_items[0].note == "平尾尾数个数=3"


def test_pingwei_intake_save_and_read_preserves_summary_item(session_factory) -> None:
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
    assert save_result.order.item_count == 1

    detail = service._order_service.get_order(save_result.order.id)
    assert detail is not None
    assert len(detail.items) == 1
    assert detail.items[0].bet_type == "平尾"
    assert detail.items[0].selection == "1,3,4,6"
    assert detail.items[0].amount == Decimal("4000.00")
    assert detail.items[0].note == "平尾尾数个数=4"


def test_complex_play_warning_when_saveable() -> None:
    preview = _preview("连兔龙蛇各20", region="澳门")
    assert preview.can_save
    assert preview.order_items[0].bet_type == "连肖"
    assert any("简化口径" in warning for warning in preview.warnings)


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


def test_invalid_item_blocks_whole_order_save(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    preview = service.preview_raw_text("01/10\n50/10", region="澳门")
    assert not preview.can_save

    save_result = service.save_preview(preview)
    assert not save_result.success

    with session_factory() as session:
        assert session.scalar(select(func.count(Order.id))) == 0
        assert session.scalar(select(func.count(OperationLog.id))) == 0


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
