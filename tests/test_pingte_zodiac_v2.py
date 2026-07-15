from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from domain.play_rules import FORTUNE_RULESET_2026_V1, FORTUNE_RULESET_2026_V2
from domain.zodiac_config import get_main_zodiac, is_main_zodiac
from models import Order
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from settlement.bet_normalizer import PINGTE_MAIN_ZODIAC, PINGTE_ZODIAC
from settlement.exceptions import SettlementDataError


def _create_draw(
    session_factory,
    *,
    regular_numbers: list[str],
    special_number: str,
    issue_number: str,
):
    return DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number=issue_number,
            draw_date=date(2026, 7, 15),
            regular_numbers=regular_numbers,
            special_number=special_number,
            source="test",
        )
    )


def _create_order(session_factory, *, items: list[OrderItemCreate], zodiac_year: int = 2026):
    return OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="平特一肖 V2 测试",
            source="test",
            zodiac_year=zodiac_year,
            items=items,
        )
    )


def test_pingte_v2_golden_parse_save_commit_and_snapshot(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平特一肖", "2.0", "1")
    intake = OrderIntakeService(session_factory)

    saved = intake.parse_and_save(
        "平特一肖 龙-羊-猴，各80",
        region="澳门",
        source="test",
        zodiac_year=2026,
    )

    assert saved.success and saved.order is not None
    assert saved.order.total_amount == Decimal("240.00")
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        ("平特一肖", "龙", Decimal("80.00")),
        ("平特一肖", "羊", Decimal("80.00")),
        ("平特一肖", "猴", Decimal("80.00")),
    ]
    draw = _create_draw(
        session_factory,
        regular_numbers=["24", "08", "03", "14", "32", "49"],
        special_number="17",
        issue_number="PINGTE-GOLDEN",
    )

    result = SettlementService(session_factory).commit_order_settlement(saved.order.id, draw.id)

    assert result.total_bet_amount == Decimal("240.00")
    assert result.win_count == 2
    assert result.lose_count == 1
    assert [item.is_winner for item in result.results] == [True, True, False]
    assert [item.matched_numbers for item in result.results] == [("03",), ("24",), ()]
    assert sum(item.amount for item in result.results if item.is_winner) == Decimal("160.00")
    assert result.total_payout_amount == Decimal("320.00")
    assert all(item.normalized_bet_type == PINGTE_ZODIAC for item in result.results)
    record = SettlementService(session_factory).get_settlement_record_by_order_id(saved.order.id)
    assert record is not None
    snapshot = record.result_snapshot
    assert snapshot["pingte_zodiac"]["drawn_zodiacs"] == ["羊", "猪", "龙", "蛇", "猪", "马", "虎"]
    assert snapshot["pingte_zodiac"]["hit_selection_count"] == 2
    assert snapshot["pingte_zodiac"]["hit_stake_amount"] == "160.00"
    assert [entry["selected_zodiac"] for entry in snapshot["pingte_zodiac"]["item_results"]] == ["龙", "羊", "猴"]
    assert all(item["matcher_id"] == "pingte_zodiac_v2" for item in snapshot["items"])
    assert all(item["matcher_version"] == "2.0" for item in snapshot["items"])
    assert all(item["draw_scope"] == "all_seven" for item in snapshot["items"])
    assert all(item["selection_unit"] == "zodiac" for item in snapshot["items"])
    assert all(item["duplicate_policy"] == "forbid_within_group" for item in snapshot["items"])
    assert all(item["missing_odds"] is False for item in snapshot["items"])
    assert all(item["settlement_ready"] is True for item in snapshot["items"])
    assert snapshot["items"][0]["odds_key_candidates"] == ["平特一肖", "平肖", "生肖"]


@pytest.mark.parametrize(
    ("selection", "regular_numbers", "special_number", "expected_winner", "expected_matches"),
    [
        ("虎", ["02", "04", "07", "09", "11", "12"], "17", True, ("17",)),
        ("龙", ["03", "04", "07", "09", "11", "12"], "17", True, ("03",)),
        ("猪", ["08", "32", "04", "07", "11", "12"], "17", True, ("08", "32")),
        ("猴", ["02", "04", "07", "09", "12", "14"], "17", False, ()),
    ],
)
def test_pingte_v2_all_seven_golden_matcher_cases(
    session_factory,
    selection: str,
    regular_numbers: list[str],
    special_number: str,
    expected_winner: bool,
    expected_matches: tuple[str, ...],
) -> None:
    if selection == "猪":
        settings = SettingsService(session_factory)
        plan = settings.ensure_default_plan()
        settings.add_item(plan.id, "平特一肖", "2.0", "0")
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="平特一肖", selection=selection, amount="80")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=regular_numbers,
        special_number=special_number,
        issue_number=f"PINGTE-{selection}-{special_number}",
    )

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.normalized_bet_type == PINGTE_ZODIAC
    assert item.is_winner is expected_winner
    assert item.matched_numbers == expected_matches
    assert len(item.drawn_zodiacs) == 7
    assert "全部7个开奖号" in item.reason
    if selection == "猪":
        assert len(item.matched_numbers) == 2
        assert item.payout_amount == Decimal("160.00")


def test_pingte_v2_main_zodiac_is_dynamic_and_uses_only_main_odds_keys(session_factory) -> None:
    assert get_main_zodiac(2026) == "马"
    assert is_main_zodiac(2026, "马")
    assert get_main_zodiac(2025) == "蛇"
    assert not is_main_zodiac(2025, "马")
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平特一肖", "2.0", "1")
    settings.add_item(plan.id, "平特一肖带主肖", "5.0", "3")
    intake = OrderIntakeService(session_factory)
    saved = intake.parse_and_save("平马各80", region="澳门", source="test", zodiac_year=2026)
    assert saved.success and saved.order is not None
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        ("平特一肖带主肖", "马", Decimal("80.00"))
    ]
    draw = _create_draw(
        session_factory,
        regular_numbers=["13", "04", "07", "09", "11", "12"],
        special_number="17",
        issue_number="PINGTE-MAIN-2026",
    )

    service = SettlementService(session_factory)
    item = service.commit_order_settlement(saved.order.id, draw.id).results[0]

    assert item.normalized_bet_type == PINGTE_MAIN_ZODIAC
    assert item.is_main_zodiac is True
    assert item.is_winner is True
    assert item.matched_numbers == ("13",)
    assert item.odds == Decimal("5.0")
    assert item.odds_key_used == "平特一肖带主肖"
    assert item.payout_amount == Decimal("400.00")
    assert item.rebate_key_used == "平特一肖带主肖"
    record = service.get_settlement_record_by_order_id(saved.order.id)
    assert record is not None
    assert record.result_snapshot["items"][0]["odds_key_used"] == "平特一肖带主肖"
    assert record.result_snapshot["items"][0]["missing_odds"] is False
    assert record.result_snapshot["items"][0]["settlement_ready"] is True


def test_pingte_v2_main_and_regular_hits_use_their_own_odds_and_rebate_keys(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平特一肖", "2.0", "1")
    settings.add_item(plan.id, "平特一肖带主肖", "5.0", "3")
    order = _create_order(
        session_factory,
        items=[
            OrderItemCreate(bet_type="平特一肖带主肖", selection="马", amount="80"),
            OrderItemCreate(bet_type="平特一肖", selection="龙", amount="80"),
        ],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["13", "03", "04", "07", "09", "11"],
        special_number="12",
        issue_number="PINGTE-MIXED-ODDS",
    )

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert [item.is_winner for item in preview.results] == [True, True]
    assert [item.odds_key_used for item in preview.results] == ["平特一肖带主肖", "平特一肖"]
    assert [item.rebate_key_used for item in preview.results] == ["平特一肖带主肖", "平特一肖"]
    assert [item.payout_amount for item in preview.results] == [Decimal("400.00"), Decimal("160.00")]
    assert preview.total_payout_amount == Decimal("560.00")
    assert preview.total_rebate_amount == Decimal("3.20")


def test_pingte_main_zodiac_does_not_fall_back_to_regular_pingte_odds(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平特一肖", "2.0", "1")
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="平特一肖带主肖", selection="马", amount="80")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["13", "04", "07", "09", "11", "12"],
        special_number="17",
        issue_number="PINGTE-MAIN-NO-ODDS",
    )

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.is_winner is True
    assert item.odds is None
    assert item.payout_amount == Decimal("0.00")
    assert item.odds_key_used is None
    assert "缺少主肖专用赔率配置" in item.payout_note
    assert item.missing_odds is True
    assert item.settlement_ready is False
    assert item.odds_key_candidates == ("平特一肖带主肖", "平特一肖主肖", "平肖主肖")


@pytest.mark.parametrize(
    ("bet_type", "selection", "regular_numbers", "special_number", "is_main", "is_winner"),
    [
        ("平特一肖", "龙", ["03", "04", "07", "09", "11", "12"], "17", False, True),
        ("平特一肖", "龙", ["02", "04", "07", "09", "11", "12"], "17", False, False),
        ("平特一肖带主肖", "马", ["13", "04", "07", "09", "11", "12"], "17", True, True),
        ("平特一肖带主肖", "马", ["03", "04", "07", "09", "11", "12"], "17", True, False),
    ],
)
def test_pingte_v2_missing_odds_blocks_formal_settlement_for_hits_and_misses(
    session_factory,
    bet_type: str,
    selection: str,
    regular_numbers: list[str],
    special_number: str,
    is_main: bool,
    is_winner: bool,
) -> None:
    if is_main:
        settings = SettingsService(session_factory)
        plan = settings.ensure_default_plan()
        settings.add_item(plan.id, "平特一肖", "2.0", "1")
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type=bet_type, selection=selection, amount="80")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=regular_numbers,
        special_number=special_number,
        issue_number=f"PINGTE-MISSING-{bet_type}-{is_winner}",
    )
    service = SettlementService(session_factory)

    preview = service.preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is is_winner
    assert item.missing_odds is True
    assert item.settlement_ready is False
    assert item.odds is None
    assert "当前结果仅供核对，不能正式结算" in item.payout_note
    assert preview.settlement_ready is False
    assert preview.blocking_reasons
    if is_main:
        assert item.odds_key_candidates == ("平特一肖带主肖", "平特一肖主肖", "平肖主肖")
        assert "主肖专用赔率" in item.blocking_reason
    else:
        assert item.odds_key_candidates == ("平特一肖", "平肖", "生肖")
        assert "平特一肖赔率" in item.blocking_reason

    with pytest.raises(SettlementDataError, match="订单 .*赔率配置不完整"):
        service.commit_order_settlement(order.id, draw.id)

    assert service.get_settlement_record_by_order_id(order.id) is None
    assert OrderService(session_factory).get_order(order.id).status == "active"


def test_pingte_mixed_order_blocks_when_main_odds_are_missing(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平特一肖", "2.0", "1")
    order = _create_order(
        session_factory,
        items=[
            OrderItemCreate(bet_type="平特一肖", selection="龙", amount="80"),
            OrderItemCreate(bet_type="平特一肖带主肖", selection="马", amount="80"),
        ],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["03", "13", "04", "07", "09", "11"],
        special_number="12",
        issue_number="PINGTE-MIXED-MISSING-MAIN",
    )
    service = SettlementService(session_factory)

    preview = service.preview_order(order.id, draw.id)
    regular, main = preview.results
    assert regular.missing_odds is False
    assert regular.odds_key_used == "平特一肖"
    assert main.missing_odds is True
    assert main.odds_key_used is None
    assert preview.settlement_ready is False

    with pytest.raises(SettlementDataError, match="马.*主肖"):
        service.commit_order_settlement(order.id, draw.id)

    assert service.get_settlement_record_by_order_id(order.id) is None
    assert OrderService(session_factory).get_order(order.id).status == "active"


def test_pingte_v2_uses_saved_order_zodiac_year(session_factory) -> None:
    order = _create_order(
        session_factory,
        zodiac_year=2025,
        items=[OrderItemCreate(bet_type="平特一肖带主肖", selection="蛇", amount="80")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["01", "02", "03", "04", "05", "06"],
        special_number="07",
        issue_number="PINGTE-MAIN-2025",
    )

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.zodiac_year == 2025
    assert item.is_main_zodiac is True
    assert item.is_winner is True
    assert item.matched_numbers == ("01",)


@pytest.mark.parametrize("ruleset_version", [FORTUNE_RULESET_2026_V1, "UNKNOWN_RULESET"])
def test_pingte_v1_and_unknown_rulesets_remain_blocked(session_factory, ruleset_version: str) -> None:
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="平特一肖", selection="龙", amount="80")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["03", "04", "07", "09", "11", "12"],
        special_number="17",
        issue_number=f"PINGTE-BLOCK-{ruleset_version}",
    )
    with session_factory() as session:
        persisted = session.scalars(select(Order).where(Order.id == order.id)).one()
        persisted.ruleset_version = ruleset_version
        session.commit()

    service = SettlementService(session_factory)
    support = service.check_order_support(order.id)
    assert support and all(not item.is_supported for item in support)
    with pytest.raises(SettlementDataError, match="规则版本不允许正式结算"):
        service.commit_order_settlement(order.id, draw.id)
    assert service.get_settlement_record_by_order_id(order.id) is None


def test_pingte_v2_requires_saved_zodiac_year_for_formal_settlement(session_factory) -> None:
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="平特一肖", selection="龙", amount="80")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["03", "04", "07", "09", "11", "12"],
        special_number="17",
        issue_number="PINGTE-NO-YEAR",
    )
    with session_factory() as session:
        persisted = session.scalars(select(Order).where(Order.id == order.id)).one()
        persisted.zodiac_year = None
        session.commit()

    service = SettlementService(session_factory)
    assert service.check_order_support(order.id)[0].is_supported is False
    with pytest.raises(SettlementDataError, match="需要订单保存的生肖年份"):
        service.commit_order_settlement(order.id, draw.id)


def test_pingte_mapper_rejects_duplicate_zodiac_and_preserves_number_and_special_zodiac_regressions(session_factory) -> None:
    intake = OrderIntakeService(session_factory)
    duplicate = intake.preview_raw_text("平特一肖 龙羊龙各80", region="澳门", zodiac_year=2026)
    number = intake.preview_raw_text("鼠各数130", region="澳门", zodiac_year=2026)
    special = intake.preview_raw_text("香港特码：蛇 包80", region="香港", zodiac_year=2026)

    assert not duplicate.can_save
    assert any("平特一肖生肖重复：龙" in error for error in duplicate.errors)
    assert [(item.bet_type, item.selection, item.amount) for item in number.order_items] == [
        ("特码", "07", Decimal("130.00")),
        ("特码", "19", Decimal("130.00")),
        ("特码", "31", Decimal("130.00")),
        ("特码", "43", Decimal("130.00")),
    ]
    assert special.can_save
    assert [(item.bet_type, item.selection, item.amount) for item in special.order_items] == [
        ("特码生肖", "蛇", Decimal("80.00"))
    ]
