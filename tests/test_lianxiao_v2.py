from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from domain.play_rules import FORTUNE_RULESET_2026_V1
from domain.zodiac_config import get_zodiac_number_map
from models import Order
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from settlement.bet_normalizer import LIANXIAO_ZODIAC
from settlement.exceptions import SettlementDataError


def _numbers_for_zodiacs(year: int, zodiacs: list[str]) -> list[str]:
    mapping = get_zodiac_number_map(year)
    used: dict[str, int] = {}
    numbers: list[str] = []
    for zodiac in zodiacs:
        index = used.get(zodiac, 0)
        used[zodiac] = index + 1
        numbers.append(str(mapping[zodiac][index]).zfill(2))
    return numbers


def _create_draw_for_zodiacs(
    session_factory,
    *,
    year: int = 2026,
    regular_zodiacs: list[str],
    special_zodiac: str,
    issue_number: str,
):
    return DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number=issue_number,
            draw_date=date(2026, 7, 15),
            regular_numbers=_numbers_for_zodiacs(year, regular_zodiacs),
            special_number=_numbers_for_zodiacs(year, [special_zodiac])[0],
            source="test",
        )
    )


def _create_order(
    session_factory,
    *,
    selection: str,
    amount: str = "100",
    zodiac_year: int = 2026,
):
    return OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="连肖 V2 测试",
            source="test",
            zodiac_year=zodiac_year,
            items=[OrderItemCreate(bet_type="连肖", selection=selection, amount=amount)],
        )
    )


def _configure_lianxiao_odds(session_factory, odds: str = "2", rebate: str = "1") -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "连肖", odds, rebate)


def test_lianxiao_v2_group_save_commit_and_snapshot(session_factory) -> None:
    _configure_lianxiao_odds(session_factory)
    intake = OrderIntakeService(session_factory)

    saved = intake.parse_and_save(
        "连肖 龙羊虎 各100",
        region="澳门",
        source="test",
        zodiac_year=2026,
    )

    assert saved.success and saved.order is not None
    assert saved.order.total_amount == Decimal("100.00")
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        ("连肖", "虎,龙,羊", Decimal("100.00"))
    ]
    draw = _create_draw_for_zodiacs(
        session_factory,
        regular_zodiacs=["羊", "猪", "龙", "蛇", "猪", "马"],
        special_zodiac="虎",
        issue_number="LIANXIAO-GOLDEN",
    )

    result = SettlementService(session_factory).commit_order_settlement(saved.order.id, draw.id)

    assert result.total_bet_amount == Decimal("100.00")
    assert result.win_count == 1
    assert result.lose_count == 0
    assert result.total_payout_amount == Decimal("200.00")
    item = result.results[0]
    assert item.normalized_bet_type == LIANXIAO_ZODIAC
    assert item.is_winner is True
    assert item.missing_zodiacs == ()
    assert item.odds_key_used == "连肖"
    record = SettlementService(session_factory).get_settlement_record_by_order_id(saved.order.id)
    assert record is not None
    snapshot = record.result_snapshot
    assert snapshot["lianxiao"]["drawn_zodiacs"] == ["羊", "猪", "龙", "蛇", "猪", "马", "虎"]
    assert snapshot["lianxiao"]["hit_group_count"] == 1
    assert snapshot["lianxiao"]["hit_stake_amount"] == "100.00"
    assert snapshot["lianxiao"]["item_results"][0]["missing_zodiacs"] == []
    item_snapshot = snapshot["items"][0]
    assert item_snapshot["matcher_id"] == "lianxiao_zodiac_v2"
    assert item_snapshot["matcher_version"] == "2.0"
    assert item_snapshot["draw_scope"] == "all_seven"
    assert item_snapshot["selection_unit"] == "zodiac_group"
    assert item_snapshot["duplicate_policy"] == "forbid_within_group"


def test_lianxiao_v2_loses_when_any_selected_zodiac_is_missing(session_factory) -> None:
    _configure_lianxiao_odds(session_factory)
    order = _create_order(session_factory, selection="龙,羊,猴")
    draw = _create_draw_for_zodiacs(
        session_factory,
        regular_zodiacs=["羊", "猪", "龙", "蛇", "猪", "马"],
        special_zodiac="虎",
        issue_number="LIANXIAO-MISSING",
    )

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.is_winner is False
    assert item.missing_zodiacs == ("猴",)
    assert item.payout_amount == Decimal("0.00")
    assert "缺少生肖：猴" in item.reason


def test_lianxiao_v2_repeated_draw_zodiac_pays_the_group_once(session_factory) -> None:
    _configure_lianxiao_odds(session_factory)
    order = _create_order(session_factory, selection="猪,龙")
    draw = _create_draw_for_zodiacs(
        session_factory,
        regular_zodiacs=["猪", "猪", "龙", "蛇", "马", "虎"],
        special_zodiac="羊",
        issue_number="LIANXIAO-REPEATED",
    )

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.results[0].is_winner is True
    assert len(result.results[0].matched_numbers) == 3
    assert result.total_bet_amount == Decimal("100.00")
    assert result.total_payout_amount == Decimal("200.00")


def test_lianxiao_v2_special_and_regular_numbers_both_participate(session_factory) -> None:
    _configure_lianxiao_odds(session_factory)
    special_last = _create_order(session_factory, selection="虎,羊")
    regular_only = _create_order(session_factory, selection="龙,羊")
    special_draw = _create_draw_for_zodiacs(
        session_factory,
        regular_zodiacs=["羊", "猪", "龙", "蛇", "猪", "马"],
        special_zodiac="虎",
        issue_number="LIANXIAO-SPECIAL-LAST",
    )
    regular_draw = _create_draw_for_zodiacs(
        session_factory,
        regular_zodiacs=["羊", "猪", "龙", "蛇", "猪", "马"],
        special_zodiac="虎",
        issue_number="LIANXIAO-REGULAR-ONLY",
    )
    service = SettlementService(session_factory)

    special_item = service.preview_order(special_last.id, special_draw.id).results[0]
    regular_item = service.preview_order(regular_only.id, regular_draw.id).results[0]

    assert special_item.is_winner is True
    assert regular_item.is_winner is True
    assert "虎" not in regular_item.selected_zodiacs


def test_lianxiao_v2_rejects_duplicate_zodiac_and_uses_saved_year(session_factory) -> None:
    intake = OrderIntakeService(session_factory)
    duplicate = intake.preview_raw_text("连肖 龙羊龙 各100", region="澳门", zodiac_year=2026)
    order = _create_order(session_factory, selection="蛇,龙", zodiac_year=2025)
    draw = _create_draw_for_zodiacs(
        session_factory,
        year=2025,
        regular_zodiacs=["龙", "鼠", "牛", "虎", "兔", "马"],
        special_zodiac="蛇",
        issue_number="LIANXIAO-SAVED-YEAR",
    )

    assert not duplicate.can_save
    assert any("连肖生肖重复：龙" in error for error in duplicate.errors)
    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]
    assert item.zodiac_year == 2025
    assert item.is_winner is True


@pytest.mark.parametrize(
    ("selection", "regular_zodiacs", "special_zodiac", "is_winner"),
    [
        ("龙,羊", ["羊", "猪", "龙", "蛇", "猪", "马"], "虎", True),
        ("龙,猴", ["羊", "猪", "龙", "蛇", "猪", "马"], "虎", False),
    ],
)
def test_lianxiao_v2_missing_odds_blocks_hit_and_miss(
    session_factory,
    selection: str,
    regular_zodiacs: list[str],
    special_zodiac: str,
    is_winner: bool,
) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平特一肖", "2", "1")
    order = _create_order(session_factory, selection=selection)
    draw = _create_draw_for_zodiacs(
        session_factory,
        regular_zodiacs=regular_zodiacs,
        special_zodiac=special_zodiac,
        issue_number=f"LIANXIAO-NO-ODDS-{is_winner}",
    )
    service = SettlementService(session_factory)

    preview = service.preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is is_winner
    assert item.missing_odds is True
    assert item.settlement_ready is False
    assert item.odds_key_candidates == ("连肖",)
    assert item.odds_key_used is None
    assert preview.settlement_ready is False
    with pytest.raises(SettlementDataError, match="订单 .*连肖"):
        service.commit_order_settlement(order.id, draw.id)
    assert service.get_settlement_record_by_order_id(order.id) is None
    assert OrderService(session_factory).get_order(order.id).status == "active"


@pytest.mark.parametrize("ruleset_version", [FORTUNE_RULESET_2026_V1, "UNKNOWN_RULESET"])
def test_lianxiao_v1_and_unknown_rulesets_remain_blocked(session_factory, ruleset_version: str) -> None:
    order = _create_order(session_factory, selection="龙,羊")
    draw = _create_draw_for_zodiacs(
        session_factory,
        regular_zodiacs=["羊", "猪", "龙", "蛇", "猪", "马"],
        special_zodiac="虎",
        issue_number=f"LIANXIAO-BLOCK-{ruleset_version}",
    )
    with session_factory() as session:
        persisted = session.scalars(select(Order).where(Order.id == order.id)).one()
        persisted.ruleset_version = ruleset_version
        session.commit()

    service = SettlementService(session_factory)
    assert service.check_order_support(order.id)[0].is_supported is False
    with pytest.raises(SettlementDataError, match="规则版本不允许正式结算"):
        service.commit_order_settlement(order.id, draw.id)
    assert service.get_settlement_record_by_order_id(order.id) is None


def test_lianxiao_fuxuan_remains_blocked(session_factory) -> None:
    order = OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="连肖复选 V2 门禁",
            source="test",
            items=[
                OrderItemCreate(
                    bet_type="连肖复选",
                    selection="兔,狗,虎,蛇,龙",
                    amount="100",
                    note="复选类型=复4",
                )
            ],
        )
    )
    draw = _create_draw_for_zodiacs(
        session_factory,
        regular_zodiacs=["羊", "猪", "龙", "蛇", "猪", "马"],
        special_zodiac="虎",
        issue_number="LIANXIAO-FUXUAN-BLOCK",
    )
    service = SettlementService(session_factory)

    assert service.check_order_support(order.id)[0].is_supported is False
    with pytest.raises(SettlementDataError, match="存在暂不支持玩法"):
        service.commit_order_settlement(order.id, draw.id)
    assert service.get_settlement_record_by_order_id(order.id) is None
