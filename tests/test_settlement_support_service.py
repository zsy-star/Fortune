from __future__ import annotations

from types import SimpleNamespace

from services.settlement_support_service import SettlementSupportService


def test_supported_special_number_returns_supported() -> None:
    result = SettlementSupportService().check_item("特码", "01")

    assert result.is_supported
    assert result.status == "supported"
    assert result.normalized_bet_type == "special_number"
    assert "已支持" in result.message


def test_supported_number_fuxuan_reads_note() -> None:
    result = SettlementSupportService().check_item(
        "几中几复选",
        "01,02,03,04",
        note="复选类型=复3",
    )

    assert result.is_supported
    assert result.normalized_bet_type == "number_fuxuan"


def test_unsupported_saveable_play_returns_user_readable_message() -> None:
    result = SettlementSupportService().check_item(
        "连肖复选",
        "兔,狗,虎,蛇,龙",
        note="复选类型=复4",
    )

    assert not result.is_supported
    assert result.status == "unsupported"
    assert "暂不支持正式结算" in result.message
    assert "可保存为记账订单" in result.suggestion


def test_saveable_pingte_zodiac_order_type_is_unsupported_until_normalized() -> None:
    result = SettlementSupportService().check_item("平特一肖", "马,蛇")

    assert not result.is_supported
    assert "暂不支持正式结算" in result.message


def test_unknown_play_is_unsupported_and_needs_manual_review() -> None:
    result = SettlementSupportService().check_item("未知玩法", "X")

    assert not result.is_supported
    assert "未知或未实现玩法" in result.reason
    assert "人工核对" in result.suggestion


def test_order_item_summary_lists_unsupported_items() -> None:
    items = [
        SimpleNamespace(bet_type="特码", selection="01", note=None),
        SimpleNamespace(bet_type="特串", selection="01,02", note="结算规则待确认"),
    ]

    summary = SettlementSupportService().summarize_order_items(items)

    assert "含暂不支持正式结算玩法" in summary
    assert "特串/01,02" in summary
