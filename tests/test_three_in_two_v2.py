from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from domain.play_rules import (
    DrawScope,
    DuplicatePolicy,
    FORTUNE_RULESET_2026_V1,
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
            issue_number="THREE-IN-TWO-V2-001",
            draw_date=date(2026, 7, 15),
            regular_numbers=regular_numbers or ["01", "02", "03", "04", "05", "06"],
            special_number=special_number,
        )
    )


def _configure_odds(session_factory, **tier_odds: str) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    for tier, odds in tier_odds.items():
        settings.add_item(plan.id, f"三中二{tier}", odds, "0")


def test_one_regular_hit_is_not_a_winner(session_factory) -> None:
    order, _ = _save_order(session_factory, "三中二 01,07,09 各10")
    draw = _create_draw(session_factory, special_number="09")

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.is_winner is False
    assert item.hit_count == 1
    assert item.payout_tier is None
    assert item.matched_numbers == ("01",)


def test_two_hits_use_middle_two_odds(session_factory) -> None:
    order, _ = _save_order(session_factory, "三中二 01,02,08 各10")
    _configure_odds(session_factory, 中2="2", 中3="5")
    draw = _create_draw(session_factory, special_number="08")

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)
    item = result.results[0]

    assert item.hit_count == 2
    assert item.payout_tier == "中2"
    assert item.odds_key_used == "三中二中2"
    assert item.odds == Decimal("2")
    assert item.payout_amount == Decimal("20")


def test_three_hits_use_middle_three_odds(session_factory) -> None:
    order, _ = _save_order(session_factory, "三中二 01,02,03 各10")
    _configure_odds(session_factory, 中2="2", 中3="5")
    draw = _create_draw(session_factory)

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)
    item = result.results[0]

    assert item.hit_count == 3
    assert item.payout_tier == "中3"
    assert item.odds_key_used == "三中二中3"
    assert item.odds == Decimal("5")
    assert item.payout_amount == Decimal("50")


def test_special_number_cannot_promote_middle_two_to_middle_three(session_factory) -> None:
    order, _ = _save_order(session_factory, "三中二 01,02,08 各10")
    _configure_odds(session_factory, 中2="2", 中3="5")
    draw = _create_draw(session_factory, special_number="08")

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.hit_count == 2
    assert item.payout_tier == "中2"
    assert item.matched_numbers == ("01", "02")
    assert "特码 08 不参与" in item.reason


def test_multiple_combinations_only_pay_the_winning_stake(session_factory) -> None:
    order, intake_preview = _save_order(
        session_factory,
        "三中二 (01-02-08)-(07-09-10) 各10",
    )
    _configure_odds(session_factory, 中2="2", 中3="5")
    draw = _create_draw(session_factory, special_number="08")

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert intake_preview.total_amount == Decimal("20")
    assert [item.is_winner for item in result.results] == [True, False]
    assert [item.hit_count for item in result.results] == [2, 0]
    assert result.total_bet_amount == Decimal("20")
    assert sum(
        (item.amount for item in result.results if item.is_winner), Decimal("0")
    ) == Decimal("10")
    assert result.total_payout_amount == Decimal("20")


def test_middle_two_and_middle_three_use_distinct_odds_and_snapshot_fields(session_factory) -> None:
    order, _ = _save_order(
        session_factory,
        "三中二 (01-02-08)-(03-04-05) 各10",
    )
    _configure_odds(session_factory, 中2="2", 中3="5")
    draw = _create_draw(session_factory, special_number="08")
    settlement = SettlementService(session_factory)

    result = settlement.commit_order_settlement(order.id, draw.id)

    assert [item.payout_tier for item in result.results] == ["中2", "中3"]
    assert [item.odds_key_used for item in result.results] == ["三中二中2", "三中二中3"]
    assert [item.payout_amount for item in result.results] == [Decimal("20"), Decimal("50")]
    assert result.total_payout_amount == Decimal("70")

    record = settlement.get_settlement_record_by_order_id(order.id)
    assert record is not None
    snapshot = record.result_snapshot
    assert [item["combination_index"] for item in snapshot["items"]] == [1, 2]
    assert [item["hit_count"] for item in snapshot["items"]] == [2, 3]
    assert [item["payout_tier"] for item in snapshot["items"]] == ["中2", "中3"]
    summary = snapshot["lianma_combinations"]
    assert summary["combination_count"] == 2
    assert summary["winning_combination_count"] == 2
    assert summary["hit_stake_amount"] == "20.00"
    assert summary["total_winning_amount"] == "70.00"
    assert [item["matcher_id"] for item in summary["item_results"]] == [
        "three_in_two_v2",
        "three_in_two_v2",
    ]
    assert [item["matcher_version"] for item in summary["item_results"]] == ["2.0", "2.0"]
    assert all(item["draw_scope"] == DrawScope.REGULAR_SIX.value for item in summary["item_results"])


def test_four_numbers_expand_to_four_independent_items(session_factory) -> None:
    order, preview = _save_order(session_factory, "三中二 04 01 03 02 复式 各10")

    assert preview.total_amount == Decimal("40")
    assert [(item.selection, item.amount) for item in order.items] == [
        ("(01-03-04)", Decimal("10")),
        ("(01-02-04)", Decimal("10")),
        ("(02-03-04)", Decimal("10")),
        ("(01-02-03)", Decimal("10")),
    ]


def test_three_in_two_rejects_duplicate_numbers_and_unordered_groups() -> None:
    parsed = parse_lines("三中二 01 01 02 03 复式 各10")
    assert len(parsed) == 1
    assert parsed[0].success is False
    assert "重复" in parsed[0].error

    with pytest.raises(InvalidSelectionError, match="重复的无序组合"):
        BetTypeNormalizer().normalize("三中二", "(01-02-03)-(03-02-01)")


@pytest.mark.parametrize(
    ("text", "configured_odds", "expected_tier", "missing_key"),
    [
        ("三中二 01,02,08 各10", {"中2": "2", "三中二": "99"}, "中2", "三中二中3"),
        ("三中二 01,02,03 各10", {"中3": "5", "三中二": "99"}, "中3", "三中二中2"),
    ],
)
def test_missing_either_tier_odds_blocks_commit_without_fallback_or_writes(
    session_factory,
    text: str,
    configured_odds: dict[str, str],
    expected_tier: str,
    missing_key: str,
) -> None:
    order, _ = _save_order(session_factory, text)
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    for key, odds in configured_odds.items():
        bet_type = key if key == "三中二" else f"三中二{key}"
        settings.add_item(plan.id, bet_type, odds, "0")
    draw = _create_draw(session_factory, special_number="08")
    settlement = SettlementService(session_factory)

    preview = settlement.preview_order(order.id, draw.id)
    item = preview.results[0]
    assert item.payout_tier == expected_tier
    assert item.odds_key_candidates == ("三中二中2", "三中二中3")
    assert item.odds_key_used is None
    assert item.missing_odds is True
    assert item.settlement_ready is False

    with pytest.raises(SettlementDataError, match=missing_key):
        settlement.commit_order_settlement(order.id, draw.id)

    assert settlement.get_settlement_record_by_order_id(order.id) is None
    assert OrderService(session_factory).get_order(order.id).status == "active"


def test_losing_item_still_requires_both_tier_odds(session_factory) -> None:
    order, _ = _save_order(session_factory, "三中二 07,08,09 各10")
    _configure_odds(session_factory, 中2="2")
    draw = _create_draw(session_factory, special_number="09")
    settlement = SettlementService(session_factory)

    preview = settlement.preview_order(order.id, draw.id)
    item = preview.results[0]
    assert item.is_winner is False
    assert item.hit_count == 0
    assert item.payout_tier is None
    assert item.odds_key_candidates == ("三中二中2", "三中二中3")
    assert item.missing_odds is True
    assert item.settlement_ready is False
    assert "三中二中3" in (item.blocking_reason or "")

    with pytest.raises(SettlementDataError, match="三中二中3"):
        settlement.commit_order_settlement(order.id, draw.id)

    assert settlement.get_settlement_record_by_order_id(order.id) is None
    assert OrderService(session_factory).get_order(order.id).status == "active"


def test_three_in_two_v2_metadata_and_ruleset_gate() -> None:
    rule = get_play_rule("三中二")
    assert rule is not None
    assert rule.normalized_type == "lianma_three_two"
    assert rule.availability is SettlementAvailability.SUPPORTED
    assert rule.draw_scope is DrawScope.REGULAR_SIX
    assert rule.selection_unit is SelectionUnit.COMBINATION
    assert rule.duplicate_policy is DuplicatePolicy.FORBID_WITHIN_GROUP
    assert rule.odds_keys == ("三中二中2", "三中二中3")
    assert rule.payout_tiers == ("中2", "中3")
    assert rule.matcher_id == "three_in_two_v2"
    assert rule.matcher_version == "2.0"

    item = SimpleNamespace(bet_type="三中二", selection="(01-02-03)", note=None)
    support = SettlementSupportService()
    assert support.check_order_items([item], ruleset_version=FORTUNE_RULESET_2026_V2)[0].is_supported
    assert not support.check_order_items([item], ruleset_version=FORTUNE_RULESET_2026_V1)[0].is_supported
    assert not support.check_order_items([item], ruleset_version="UNKNOWN_RULESET")[0].is_supported
