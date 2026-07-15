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


def _save_special_order(session_factory, text: str):
    intake = OrderIntakeService(session_factory)
    preview = intake.preview_raw_text(text, region="澳门")
    assert preview.can_save, preview.errors
    saved = intake.save_preview(preview)
    assert saved.success and saved.order is not None
    return saved.order, preview


def _create_draw(draw_service: DrawService, *, special_number: str, regular_numbers: list[str] | None = None):
    return draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="DUP-001",
            draw_date=date(2026, 7, 15),
            regular_numbers=regular_numbers or ["01", "02", "03", "04", "05", "06"],
            special_number=special_number,
        )
    )


def _configure_special_odds(session_factory, odds: str = "2") -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "特码", odds, "0")


def test_explicit_special_number_duplicate_is_saved_as_two_independent_stakes(session_factory) -> None:
    parsed = parse_lines("特码49、49，各10")

    assert len(parsed) == 1
    assert parsed[0].success and parsed[0].category == "特码"
    assert parsed[0].numbers == (49, 49)
    assert parsed[0].amount == Decimal("10")
    assert parsed[0].total == Decimal("20")

    order, preview = _save_special_order(session_factory, "特码49、49，各10")
    detail = OrderService(session_factory).get_order(order.id)

    assert preview.total_amount == Decimal("20")
    assert detail is not None and detail.total_amount == Decimal("20")
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        ("特码", "49", Decimal("10")),
        ("特码", "49", Decimal("10")),
    ]
    assert len({item.id for item in detail.items}) == 2


def test_two_duplicate_special_number_items_both_win_and_pay_independently(session_factory) -> None:
    order, _ = _save_special_order(session_factory, "特码号码49、49，各10")
    _configure_special_odds(session_factory, "2")
    draw = _create_draw(DrawService(session_factory), special_number="49")

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert [item.is_winner for item in result.results] == [True, True]
    assert sum((item.amount for item in result.results if item.is_winner), Decimal("0")) == Decimal("20")
    assert [item.payout_amount for item in result.results] == [Decimal("20"), Decimal("20")]
    assert result.total_payout_amount == Decimal("40")
    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    snapshot_items = record.result_snapshot["items"]
    assert [item["selection"] for item in snapshot_items] == ["49", "49"]
    assert len({item["order_item_id"] for item in snapshot_items}) == 2


def test_duplicate_special_number_misses_when_only_regular_number_matches(session_factory) -> None:
    order, _ = _save_special_order(session_factory, "特码49、49，各10")
    _configure_special_odds(session_factory, "2")
    draw = _create_draw(
        DrawService(session_factory),
        special_number="48",
        regular_numbers=["01", "02", "03", "04", "05", "49"],
    )

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert [item.is_winner for item in preview.results] == [False, False]
    assert preview.total_payout_amount == Decimal("0")
    assert all(item.draw_scope == "special_only" for item in preview.results)


def test_special_number_duplicate_order_preserves_every_occurrence_in_input_order(session_factory) -> None:
    order, preview = _save_special_order(session_factory, "特码49、18、49，各10")
    detail = OrderService(session_factory).get_order(order.id)

    assert preview.total_amount == Decimal("30")
    assert detail is not None
    assert [(item.selection, item.amount) for item in detail.items] == [
        ("49", Decimal("10")),
        ("18", Decimal("10")),
        ("49", Decimal("10")),
    ]


def test_missing_special_number_odds_blocks_commit_without_writing_settlement(session_factory) -> None:
    order, _ = _save_special_order(session_factory, "特码49、49，各10")
    order_service = OrderService(session_factory)
    settlement = SettlementService(session_factory)
    draw = _create_draw(DrawService(session_factory), special_number="49")

    preview = settlement.preview_order(order.id, draw.id)
    assert all(item.missing_odds for item in preview.results)
    assert preview.settlement_ready is False

    with pytest.raises(SettlementDataError, match="特码号码赔率"):
        settlement.commit_order_settlement(order.id, draw.id)

    assert order_service.get_order(order.id).status == "active"
    assert settlement.count_settlement_records() == 0


def test_other_group_duplicate_validation_and_regular_number_behavior_remain_strict() -> None:
    normalizer = BetTypeNormalizer()

    with pytest.raises(InvalidSelectionError, match="N不中号码重复"):
        normalizer.normalize("五不中", "08,09,10,11,08")
    with pytest.raises(InvalidSelectionError, match="连肖生肖重复"):
        normalizer.normalize("连肖", "猪,龙,猪")
    with pytest.raises(InvalidSelectionError, match="平尾尾数重复"):
        normalizer.normalize("平尾", "4,1,4")

    regular = parse_lines("平码49、49各10")
    assert len(regular) == 1
    assert regular[0].success is False
    assert "号码49重复" in regular[0].error


def test_special_number_v2_metadata_keeps_repeat_as_independent_stakes() -> None:
    rule = get_play_rule("特码")

    assert rule is not None
    assert rule.availability is SettlementAvailability.SUPPORTED
    assert rule.duplicate_policy is DuplicatePolicy.REPEAT_AS_INDEPENDENT_STAKES
    assert rule.draw_scope.value == "special_only"
