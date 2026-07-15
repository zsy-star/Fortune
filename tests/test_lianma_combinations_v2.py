from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from domain.play_rules import (
    DrawScope,
    DuplicatePolicy,
    FORTUNE_RULESET_2026_V2,
    SelectionUnit,
    SettlementAvailability,
    get_play_rule,
)
from schemas.draw_schema import LotteryDrawCreate
from settlement.bet_normalizer import BetTypeNormalizer
from settlement.exceptions import InvalidSelectionError, SettlementDataError
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_parser import parse_lines
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from services.settlement_support_service import SettlementSupportService


def _save_order(session_factory, text: str):
    intake = OrderIntakeService(session_factory)
    preview = intake.preview_raw_text(text, region="澳门")
    assert preview.can_save, preview.errors
    saved = intake.save_preview(preview)
    assert saved.success and saved.order is not None
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None
    return detail, preview


def _create_draw(
    session_factory,
    *,
    regular_numbers: list[str] | None = None,
    special_number: str = "08",
):
    return DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="LIANMA-V2-001",
            draw_date=date(2026, 7, 15),
            regular_numbers=regular_numbers or ["01", "02", "03", "04", "05", "06"],
            special_number=special_number,
        )
    )


def _configure_odds(session_factory, bet_type: str, odds: str = "2") -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, bet_type, odds, "0")


def test_two_in_two_single_combination_wins_on_regular_six(session_factory) -> None:
    order, _ = _save_order(session_factory, "二中二 01,02 各10")
    _configure_odds(session_factory, "二中二")
    draw = _create_draw(session_factory)

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert len(order.items) == 1
    assert order.items[0].amount == Decimal("10")
    assert result.results[0].is_winner is True
    assert result.results[0].payout_amount == Decimal("20")
    assert result.results[0].draw_scope == DrawScope.REGULAR_SIX.value


def test_two_in_two_special_number_cannot_complete_combination(session_factory) -> None:
    order, _ = _save_order(session_factory, "二中二 01,08 各10")
    _configure_odds(session_factory, "二中二")
    draw = _create_draw(session_factory, special_number="08")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.results[0].is_winner is False
    assert preview.results[0].matched_numbers == ("01",)
    assert "特码 08 不参与" in preview.results[0].reason


def test_two_in_two_multi_combination_saves_and_pays_each_item(session_factory) -> None:
    order, preview = _save_order(session_factory, "二中二 (01-02)-(03-08) 各10")
    _configure_odds(session_factory, "二中二")
    draw = _create_draw(session_factory, special_number="08")

    assert preview.total_amount == Decimal("20")
    assert [(item.bet_type, item.selection, item.amount) for item in order.items] == [
        ("二中二", "(01-02)", Decimal("10")),
        ("二中二", "(03-08)", Decimal("10")),
    ]

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert [item.is_winner for item in result.results] == [True, False]
    assert result.total_bet_amount == Decimal("20")
    assert result.total_payout_amount == Decimal("20")
    assert sum(
        (item.amount for item in result.results if item.is_winner), Decimal("0")
    ) == Decimal("10")

    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    snapshot = record.result_snapshot
    assert [item["combination_index"] for item in snapshot["items"]] == [1, 2]
    summary = snapshot["lianma_combinations"]
    assert summary["combination_count"] == 2
    assert summary["winning_combination_count"] == 1
    assert summary["hit_stake_amount"] == "10.00"
    assert summary["total_winning_amount"] == "20.00"
    first = summary["item_results"][0]
    assert first["order_item_id"] == order.items[0].id
    assert first["selected_numbers"] == ["01", "02"]
    assert first["matched_numbers"] == ["01", "02"]
    assert first["matcher_id"] == "match_two_in_two"
    assert first["matcher_version"] == "2.0"
    assert first["draw_scope"] == DrawScope.REGULAR_SIX.value


def test_two_in_two_three_numbers_expand_to_three_stable_combinations(session_factory) -> None:
    order, preview = _save_order(session_factory, "二中二 03 01 02 各组10")

    assert preview.total_amount == Decimal("30")
    assert [(item.selection, item.amount) for item in order.items] == [
        ("(01-03)", Decimal("10")),
        ("(02-03)", Decimal("10")),
        ("(01-02)", Decimal("10")),
    ]


def test_three_in_three_single_combination_wins(session_factory) -> None:
    order, _ = _save_order(session_factory, "三中三 01,02,03 各10")
    _configure_odds(session_factory, "三中三")
    draw = _create_draw(session_factory)

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.results[0].is_winner is True
    assert result.results[0].payout_amount == Decimal("20")


def test_three_in_three_two_regular_plus_special_is_not_a_win(session_factory) -> None:
    order, _ = _save_order(session_factory, "三中三 01,02,08 各10")
    _configure_odds(session_factory, "三中三")
    draw = _create_draw(session_factory, special_number="08")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.results[0].is_winner is False
    assert preview.results[0].matched_numbers == ("01", "02")


def test_three_in_three_multi_combination_only_pays_winning_item(session_factory) -> None:
    order, preview = _save_order(session_factory, "三中三 (01-02-03)-(04-05-08) 各10")
    _configure_odds(session_factory, "三中三")
    draw = _create_draw(session_factory, special_number="08")

    assert preview.total_amount == Decimal("20")
    assert [(item.selection, item.amount) for item in order.items] == [
        ("(01-02-03)", Decimal("10")),
        ("(04-05-08)", Decimal("10")),
    ]

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert [item.is_winner for item in result.results] == [True, False]
    assert result.total_bet_amount == Decimal("20")
    assert result.total_payout_amount == Decimal("20")
    assert sum(
        (item.amount for item in result.results if item.is_winner), Decimal("0")
    ) == Decimal("10")


def test_three_in_three_four_numbers_expand_to_four_stable_combinations(session_factory) -> None:
    order, preview = _save_order(session_factory, "三中三 04 01 03 02 复式 各10")

    assert preview.total_amount == Decimal("40")
    assert [(item.selection, item.amount) for item in order.items] == [
        ("(01-03-04)", Decimal("10")),
        ("(01-02-04)", Decimal("10")),
        ("(02-03-04)", Decimal("10")),
        ("(01-02-03)", Decimal("10")),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "二中二 01 01 02 各组10",
        "三中三 01 02 02 03 复式 各10",
    ],
)
def test_lianma_combination_source_numbers_reject_duplicates(text: str) -> None:
    parsed = parse_lines(text)

    assert len(parsed) == 1
    assert parsed[0].success is False
    assert "重复" in parsed[0].error


@pytest.mark.parametrize(
    ("bet_type", "selection"),
    [
        ("二中二", "(01-02)-(02-01)"),
        ("三中三", "(01-02-03)-(03-02-01)"),
    ],
)
def test_same_unordered_combination_is_rejected(bet_type: str, selection: str) -> None:
    normalizer = BetTypeNormalizer()

    with pytest.raises(InvalidSelectionError, match="重复的无序组合"):
        normalizer.normalize(bet_type, selection)


@pytest.mark.parametrize(
    ("bet_type", "text"),
    [
        ("二中二", "二中二 (01-02)-(03-08) 各10"),
        ("三中三", "三中三 (01-02-03)-(04-05-08) 各10"),
    ],
)
def test_missing_lianma_odds_blocks_commit_without_writes(
    session_factory,
    bet_type: str,
    text: str,
) -> None:
    order, _ = _save_order(session_factory, text)
    settlement = SettlementService(session_factory)
    draw = _create_draw(session_factory, special_number="08")

    preview = settlement.preview_order(order.id, draw.id)
    assert all(item.missing_odds for item in preview.results)
    assert all(item.odds_key_candidates == (bet_type,) for item in preview.results)
    assert preview.settlement_ready is False

    with pytest.raises(SettlementDataError):
        settlement.commit_order_settlement(order.id, draw.id)

    assert OrderService(session_factory).get_order(order.id).status == "active"
    assert settlement.count_settlement_records() == 0


def test_lianma_v2_metadata_and_pending_rules_stay_separate() -> None:
    for bet_type, normalized_type in (
        ("二中二", "lianma_two_two"),
        ("三中三", "lianma_three_three"),
    ):
        rule = get_play_rule(bet_type)
        assert rule is not None
        assert rule.normalized_type == normalized_type
        assert rule.availability is SettlementAvailability.SUPPORTED
        assert rule.selection_unit is SelectionUnit.COMBINATION
        assert rule.draw_scope is DrawScope.REGULAR_SIX
        assert rule.duplicate_policy is DuplicatePolicy.FORBID_WITHIN_GROUP
        assert rule.matcher_version == "2.0"

    support = SettlementSupportService()
    three_in_two, number_fuxuan = support.check_order_items(
        [
            SimpleNamespace(bet_type="三中二", selection="(01-02-03)", note=None),
            SimpleNamespace(
                bet_type="几中几复选",
                selection="01,02,03,04",
                note="复选类型=复3",
            ),
        ],
        ruleset_version=FORTUNE_RULESET_2026_V2,
    )
    assert three_in_two.is_supported is False
    assert number_fuxuan.is_supported is False
