from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain.play_rules import FORTUNE_RULESET_2026_V1, FORTUNE_RULESET_2026_V2
from services.settlement_support_service import SettlementSupportService


def test_supported_special_number_returns_supported() -> None:
    result = SettlementSupportService().check_item("特码", "01")

    assert result.is_supported
    assert result.status == "supported"
    assert result.normalized_bet_type == "special_number"
    assert "已支持" in result.message


def test_number_fuxuan_is_blocked_even_when_note_is_valid() -> None:
    result = SettlementSupportService().check_item(
        "几中几复选",
        "01,02,03,04",
        note="复选类型=复3",
    )

    assert not result.is_supported
    assert "V2规则修复尚未完成" in result.reason


def test_ten_non_hit_is_supported_by_v2_rules() -> None:
    result = SettlementSupportService().check_item(
        "N不中",
        "01,03,06,10,13,15,18,22,31,43",
    )

    assert result.is_supported
    assert result.status == "supported"
    assert result.normalized_bet_type == "non_hit_number"


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


def test_pingte_zodiac_is_supported_as_an_independent_single_zodiac_item() -> None:
    result = SettlementSupportService().check_item("平特一肖", "龙", zodiac_year=2026)

    assert result.is_supported
    assert result.normalized_bet_type == "pingte_zodiac"


def test_lianxiao_is_supported_as_an_independent_zodiac_group() -> None:
    result = SettlementSupportService().check_item("连肖", "龙,羊", zodiac_year=2026)

    assert result.is_supported
    assert result.normalized_bet_type == "lianxiao_zodiac"


def test_unknown_play_is_unsupported_and_needs_manual_review() -> None:
    result = SettlementSupportService().check_item("未知玩法", "X")

    assert not result.is_supported
    assert "未知或未实现玩法" in result.reason
    assert "人工核对" in result.suggestion


def test_four_zodiac_accounting_play_is_explicitly_unsupported() -> None:
    result = SettlementSupportService().check_item("四肖", "鼠,虎,龙,猴")

    assert not result.is_supported
    assert result.status == "unsupported"
    assert "仅允许记账保存" in result.reason
    assert "可保存为记账订单" in result.suggestion


def test_order_item_summary_lists_unsupported_items() -> None:
    items = [
        SimpleNamespace(bet_type="特码", selection="01", note=None),
        SimpleNamespace(bet_type="特串", selection="01,02", note="结算规则待确认"),
    ]

    summary = SettlementSupportService().summarize_order_items(items)

    assert "含暂不支持正式结算玩法" in summary
    assert "特串/01,02" in summary


@pytest.mark.parametrize(
    "bet_type",
    [
        "连肖复选",
        "三中二",
        "几中几复选",
        "包半波",
        "连尾",
        "二中特",
        "二中特复选",
        "特串",
        "四肖",
        "正码特",
    ],
)
def test_v2_unsafe_plays_are_all_blocked_from_formal_settlement(bet_type: str) -> None:
    result = SettlementSupportService().check_item(bet_type, "01,02,03")

    assert not result.is_supported
    assert result.status == "unsupported"
    assert "暂不支持正式结算" in result.message


@pytest.mark.parametrize(
    ("bet_type", "single_selection", "multi_selection"),
    [
        ("二中二", "(01-02)", "(01-02)-(03-04)"),
        ("三中三", "(01-02-03)", "(01-02-03)-(04-05-06)"),
    ],
)
def test_lianma_allows_only_one_explicit_group(
    bet_type: str,
    single_selection: str,
    multi_selection: str,
) -> None:
    service = SettlementSupportService()

    assert service.check_item(bet_type, single_selection).is_supported
    blocked = service.check_item(bet_type, multi_selection)

    assert not blocked.is_supported
    assert "暂只允许单个" in blocked.reason


@pytest.mark.parametrize("ruleset_version", [FORTUNE_RULESET_2026_V1, "UNKNOWN", None, ""])
def test_non_v2_or_unknown_ruleset_blocks_formal_settlement(ruleset_version) -> None:
    service = SettlementSupportService()
    items = [SimpleNamespace(bet_type="特码", selection="01", note=None)]

    results = service.check_order_items(items, ruleset_version=ruleset_version)

    assert len(results) == 1
    assert not results[0].is_supported
    assert "禁止自动按V2解释" in results[0].reason


def test_v2_ruleset_continues_to_play_level_gate() -> None:
    service = SettlementSupportService()
    items = [SimpleNamespace(bet_type="特码", selection="01", note=None)]

    results = service.check_order_items(items, ruleset_version=FORTUNE_RULESET_2026_V2)

    assert len(results) == 1
    assert results[0].is_supported


def test_lianxiao_alias_uses_the_same_v2_group_rule() -> None:
    result = SettlementSupportService().check_item("多生肖", "马,蛇")

    assert result.is_supported
    assert result.normalized_bet_type == "lianxiao_zodiac"


def test_non_v2_multi_item_support_returns_one_blocked_result_per_item() -> None:
    items = [
        SimpleNamespace(bet_type="特码", selection="01", note=None),
        SimpleNamespace(bet_type="平码", selection="02", note=None),
    ]

    results = SettlementSupportService().check_order_items(
        items,
        ruleset_version=FORTUNE_RULESET_2026_V1,
    )

    assert [result.play_type for result in results] == ["特码", "平码"]
    assert all(not result.is_supported for result in results)
    assert all("订单规则版本门禁" in result.reason for result in results)
