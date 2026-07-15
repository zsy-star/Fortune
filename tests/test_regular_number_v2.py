from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.play_rules import DuplicatePolicy, SettlementAvailability, get_play_rule
from schemas.draw_schema import LotteryDrawCreate
from settlement.bet_normalizer import BetTypeNormalizer
from settlement.exceptions import InvalidSelectionError, SettlementDataError
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_parser import parse_lines
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService


def _save_regular_order(session_factory, text: str):
    intake = OrderIntakeService(session_factory)
    preview = intake.preview_raw_text(text, region="澳门")
    assert preview.can_save, preview.errors
    saved = intake.save_preview(preview)
    assert saved.success and saved.order is not None
    return saved.order, preview


def _create_draw(
    draw_service: DrawService,
    *,
    special_number: str,
    regular_numbers: list[str] | None = None,
):
    return draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="REG-001",
            draw_date=date(2026, 7, 15),
            regular_numbers=regular_numbers or ["01", "02", "03", "04", "05", "06"],
            special_number=special_number,
        )
    )


def _configure_regular_odds(session_factory, odds: str = "2") -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平码", odds, "0")


def test_explicit_regular_number_duplicate_is_saved_as_two_independent_stakes(session_factory) -> None:
    parsed = parse_lines("平码22、22，各10")

    assert len(parsed) == 1
    assert parsed[0].success and parsed[0].category == "平码"
    assert parsed[0].numbers == (22, 22)
    assert parsed[0].amount == Decimal("10")
    assert parsed[0].total == Decimal("20")

    order, preview = _save_regular_order(session_factory, "平码22、22，各10")
    detail = OrderService(session_factory).get_order(order.id)

    assert preview.total_amount == Decimal("20")
    assert detail is not None and detail.total_amount == Decimal("20")
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        ("平码", "22", Decimal("10")),
        ("平码", "22", Decimal("10")),
    ]
    assert len({item.id for item in detail.items}) == 2


def test_duplicate_regular_number_items_both_win_and_pay_independently(session_factory) -> None:
    order, _ = _save_regular_order(session_factory, "平码22、22，各10")
    _configure_regular_odds(session_factory, "2")
    draw = _create_draw(
        DrawService(session_factory),
        regular_numbers=["01", "02", "03", "04", "05", "22"],
        special_number="49",
    )

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert [item.is_winner for item in result.results] == [True, True]
    assert sum((item.amount for item in result.results if item.is_winner), Decimal("0")) == Decimal("20")
    assert [item.payout_amount for item in result.results] == [Decimal("20"), Decimal("20")]
    assert result.total_payout_amount == Decimal("40")
    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    snapshot_items = record.result_snapshot["items"]
    assert [item["selection"] for item in snapshot_items] == ["22", "22"]
    assert len({item["order_item_id"] for item in snapshot_items}) == 2


def test_duplicate_regular_number_misses_when_only_special_number_matches(session_factory) -> None:
    order, _ = _save_regular_order(session_factory, "平码22、22，各10")
    _configure_regular_odds(session_factory, "2")
    draw = _create_draw(DrawService(session_factory), special_number="22")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert [item.is_winner for item in preview.results] == [False, False]
    assert preview.total_payout_amount == Decimal("0")
    assert all(item.draw_scope == "regular_six" for item in preview.results)


def test_regular_number_occurrences_keep_input_order_and_settle_independently(session_factory) -> None:
    order, preview = _save_regular_order(session_factory, "平码22、18、22，各10")
    detail = OrderService(session_factory).get_order(order.id)

    assert preview.total_amount == Decimal("30")
    assert detail is not None
    assert [(item.selection, item.amount) for item in detail.items] == [
        ("22", Decimal("10")),
        ("18", Decimal("10")),
        ("22", Decimal("10")),
    ]

    _configure_regular_odds(session_factory, "2")
    draw = _create_draw(
        DrawService(session_factory),
        regular_numbers=["01", "02", "03", "04", "18", "22"],
        special_number="49",
    )
    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert [item.is_winner for item in result.results] == [True, True, True]
    assert result.total_payout_amount == Decimal("60")


def test_missing_regular_odds_blocks_commit_without_special_odds_fallback(session_factory) -> None:
    order, _ = _save_regular_order(session_factory, "平码22、22，各10")
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "特码", "2", "0")
    order_service = OrderService(session_factory)
    settlement = SettlementService(session_factory)
    draw = _create_draw(DrawService(session_factory), special_number="49")

    preview = settlement.preview_order(order.id, draw.id)
    assert all(item.missing_odds for item in preview.results)
    assert all(item.odds_key_candidates == ("平码",) for item in preview.results)
    assert preview.settlement_ready is False

    with pytest.raises(SettlementDataError):
        settlement.commit_order_settlement(order.id, draw.id)

    assert order_service.get_order(order.id).status == "active"
    assert settlement.count_settlement_records() == 0


def test_regular_number_normalization_preserves_duplicates_but_other_group_rules_remain_strict() -> None:
    normalizer = BetTypeNormalizer()

    assert normalizer.normalize("平码", "22,22").selection == "22,22"
    with pytest.raises(InvalidSelectionError, match="N不中号码重复"):
        normalizer.normalize("五不中", "08,09,10,11,08")
    with pytest.raises(InvalidSelectionError, match="连肖生肖重复"):
        normalizer.normalize("连肖", "猪,龙,猪")
    with pytest.raises(InvalidSelectionError, match="平尾尾数重复"):
        normalizer.normalize("平尾", "4,1,4")


def test_regular_number_v2_metadata_keeps_repeat_as_independent_stakes() -> None:
    rule = get_play_rule("平码")

    assert rule is not None
    assert rule.availability is SettlementAvailability.SUPPORTED
    assert rule.duplicate_policy is DuplicatePolicy.REPEAT_AS_INDEPENDENT_STAKES
    assert rule.draw_scope.value == "regular_six"
