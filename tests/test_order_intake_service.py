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
    assert any("结算预览" in warning for warning in preview.warnings)


def test_special_zodiac_parse_options_save_as_pingte_zodiac() -> None:
    preview = _preview("马蛇10", region="澳门", parse_options=ParseOptions(special_zodiac_mode=True))
    assert preview.can_save
    assert preview.total_amount == Decimal("20.00")
    assert len(preview.order_items) == 1
    assert preview.order_items[0].bet_type == "平特一肖"
    assert preview.order_items[0].selection == "马,蛇"
    assert preview.order_items[0].amount == Decimal("20.00")


def test_zodiac_each_parse_options_count_zodiac_groups() -> None:
    preview = _preview("羊马各10", region="澳门", parse_options=ParseOptions(zodiac_each_mode=True))
    assert preview.can_save
    assert preview.total_amount == Decimal("20.00")
    assert preview.order_items[0].bet_type == "平特一肖"
    assert preview.order_items[0].selection == "羊,马"


def test_multi_zodiac_not_silently_split() -> None:
    preview = _preview("鼠牛各10", region="澳门")
    assert preview.order_items[0].bet_type == "连肖"
    assert "鼠,牛" in preview.order_items[0].selection


def test_full_package_not_silently_dropped() -> None:
    preview = _preview("全包各10", region="澳门")
    assert not preview.can_save
    assert any("全包" in error for error in preview.errors)


def test_complex_play_warning_when_saveable() -> None:
    preview = _preview("连兔龙蛇各20", region="澳门")
    assert preview.can_save
    assert preview.order_items[0].bet_type == "连肖"
    assert any("结算预览" in warning for warning in preview.warnings)


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
