from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.play_rules import FORTUNE_RULESET_2026_V1
from models import Order
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
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


def _create_order(session_factory, *, items: list[OrderItemCreate]):
    return OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="平尾 V2 测试",
            source="test",
            items=items,
        )
    )


def test_flat_tail_v2_mapper_saves_each_tail_and_preserves_zero(session_factory) -> None:
    intake = OrderIntakeService(session_factory)

    preview = intake.preview_raw_text("平尾 0尾、4尾、6尾 各100", region="澳门")
    saved = intake.parse_and_save("平尾 0尾、4尾、6尾 各100", region="澳门", source="test")

    assert preview.can_save
    assert preview.total_amount == Decimal("300.00")
    assert [(item.bet_type, item.selection, item.amount) for item in preview.order_items] == [
        ("平特0尾", "0", Decimal("100.00")),
        ("平尾", "4", Decimal("100.00")),
        ("平尾", "6", Decimal("100.00")),
    ]
    assert all(item.normalized_bet_type == "ping_tail" for item in preview.items)
    assert saved.success and saved.order is not None
    assert saved.order.total_amount == Decimal("300.00")
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == [
        ("平特0尾", "0", Decimal("100.00")),
        ("平尾", "4", Decimal("100.00")),
        ("平尾", "6", Decimal("100.00")),
    ]


def test_flat_tail_v2_rejects_duplicate_tail_input(session_factory) -> None:
    preview = OrderIntakeService(session_factory).preview_raw_text(
        "平尾 4尾、1尾、4尾 各100",
        region="澳门",
    )

    assert not preview.can_save
    assert any("重复" in error for error in preview.errors)


@pytest.mark.parametrize(
    ("selection", "regular_numbers", "special_number", "winner", "matched_numbers"),
    [
        ("4", ["24", "18", "03", "04", "02", "09"], "17", True, ("24", "04")),
        ("0", ["10", "20", "03", "04", "02", "09"], "17", True, ("10", "20")),
        ("7", ["02", "04", "08", "09", "11", "12"], "17", True, ("17",)),
        ("8", ["08", "04", "07", "09", "11", "12"], "17", True, ("08",)),
        ("6", ["02", "04", "08", "09", "11", "12"], "17", False, ()),
    ],
)
def test_flat_tail_v2_checks_all_seven_and_counts_each_tail_once(
    session_factory,
    selection: str,
    regular_numbers: list[str],
    special_number: str,
    winner: bool,
    matched_numbers: tuple[str, ...],
) -> None:
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="平尾", selection=selection, amount="100")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=regular_numbers,
        special_number=special_number,
        issue_number=f"FLAT-TAIL-MATCH-{selection}-{special_number}",
    )

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.normalized_bet_type == "ping_tail"
    assert item.is_winner is winner
    assert item.selected_tail == selection
    assert item.matched_numbers == matched_numbers
    assert len(item.draw_tails) == 7
    assert "全部7个开奖号" in item.reason
    if selection == "4":
        assert item.matched_tails == ("4",)
        assert len(item.matched_numbers) == 2


def test_flat_tail_v2_pays_each_selected_tail_independently_and_snapshots(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平特0尾", "5", "3")
    settings.add_item(plan.id, "平尾", "2", "1")
    order = _create_order(
        session_factory,
        items=[
            OrderItemCreate(bet_type="平特0尾", selection="0", amount="100"),
            OrderItemCreate(bet_type="平尾", selection="4", amount="100"),
            OrderItemCreate(bet_type="平尾", selection="6", amount="100"),
        ],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["10", "24", "18", "04", "02", "09"],
        special_number="17",
        issue_number="FLAT-TAIL-PAYOUT",
    )

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert [item.is_winner for item in result.results] == [True, True, False]
    assert [item.payout_amount for item in result.results] == [
        Decimal("500.00"),
        Decimal("200.00"),
        Decimal("0.00"),
    ]
    assert [item.odds_key_used for item in result.results] == ["平特0尾", "平尾", None]
    assert result.total_bet_amount == Decimal("300.00")
    assert result.total_payout_amount == Decimal("700.00")
    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    snapshot = record.result_snapshot["ping_tail"]
    assert snapshot["selected_tails"] == ["0", "4", "6"]
    assert snapshot["hit_tail_count"] == 2
    assert snapshot["hit_stake_amount"] == "200.00"
    assert snapshot["item_results"][0]["is_zero_tail"] is True
    assert snapshot["item_results"][0]["odds_key_used"] == "平特0尾"
    assert all(item["missing_odds"] is False for item in snapshot["item_results"])
    assert all(item["settlement_ready"] is True for item in snapshot["item_results"])
    first_item_snapshot = record.result_snapshot["items"][0]
    assert first_item_snapshot["matcher_id"] == "flat_tail_v2"
    assert first_item_snapshot["matcher_version"] == "2.0"
    assert first_item_snapshot["draw_scope"] == "all_seven"
    assert first_item_snapshot["selection_unit"] == "tail"
    assert first_item_snapshot["duplicate_policy"] == "forbid_within_group"


@pytest.mark.parametrize(
    ("selection", "regular_numbers", "special_number", "is_winner"),
    [
        ("4", ["24", "18", "03", "04", "02", "09"], "17", True),
        ("6", ["02", "04", "08", "09", "11", "12"], "17", False),
    ],
)
def test_flat_tail_v2_missing_regular_odds_blocks_hit_and_miss(
    session_factory,
    selection: str,
    regular_numbers: list[str],
    special_number: str,
    is_winner: bool,
) -> None:
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="平尾", selection=selection, amount="100")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=regular_numbers,
        special_number=special_number,
        issue_number=f"FLAT-TAIL-NO-ODDS-{selection}-{is_winner}",
    )
    service = SettlementService(session_factory)

    preview = service.preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is is_winner
    assert item.missing_odds is True
    assert item.settlement_ready is False
    assert item.odds_key_candidates == ("平尾",)
    assert preview.settlement_ready is False
    with pytest.raises(SettlementDataError, match="订单 .*平尾"):
        service.commit_order_settlement(order.id, draw.id)
    assert service.get_settlement_record_by_order_id(order.id) is None
    assert OrderService(session_factory).get_order(order.id).status == "active"


@pytest.mark.parametrize(
    ("regular_numbers", "special_number", "is_winner"),
    [
        (["10", "24", "18", "04", "02", "09"], "17", True),
        (["24", "18", "03", "04", "02", "09"], "17", False),
    ],
)
def test_flat_tail_v2_zero_tail_never_falls_back_to_regular_odds(
    session_factory,
    regular_numbers: list[str],
    special_number: str,
    is_winner: bool,
) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平尾", "2", "1")
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="平特0尾", selection="0", amount="100")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=regular_numbers,
        special_number=special_number,
        issue_number=f"FLAT-TAIL-ZERO-NO-ODDS-{is_winner}",
    )
    service = SettlementService(session_factory)

    preview = service.preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is is_winner
    assert item.is_zero_tail is True
    assert item.missing_odds is True
    assert item.odds_key_used is None
    assert item.odds_key_candidates == ("平特0尾", "平尾0尾", "0尾")
    assert "0尾专用赔率" in item.payout_note
    with pytest.raises(SettlementDataError, match="0尾.*已尝试赔率键"):
        service.commit_order_settlement(order.id, draw.id)
    assert service.get_settlement_record_by_order_id(order.id) is None
    assert OrderService(session_factory).get_order(order.id).status == "active"


def test_flat_tail_v2_mixed_order_blocks_when_zero_tail_odds_are_missing(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "平尾", "2", "1")
    order = _create_order(
        session_factory,
        items=[
            OrderItemCreate(bet_type="平尾", selection="4", amount="100"),
            OrderItemCreate(bet_type="平特0尾", selection="0", amount="100"),
        ],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["24", "10", "18", "04", "02", "09"],
        special_number="17",
        issue_number="FLAT-TAIL-MIXED-NO-ZERO",
    )
    service = SettlementService(session_factory)

    preview = service.preview_order(order.id, draw.id)
    regular, zero = preview.results
    assert regular.missing_odds is False
    assert regular.odds_key_used == "平尾"
    assert zero.missing_odds is True
    assert preview.settlement_ready is False
    with pytest.raises(SettlementDataError, match="平特0尾/0"):
        service.commit_order_settlement(order.id, draw.id)
    assert service.get_settlement_record_by_order_id(order.id) is None
    assert OrderService(session_factory).get_order(order.id).status == "active"


@pytest.mark.parametrize("ruleset_version", [FORTUNE_RULESET_2026_V1, "UNKNOWN_RULESET"])
def test_flat_tail_v1_and_unknown_rulesets_remain_blocked(session_factory, ruleset_version: str) -> None:
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="平尾", selection="4", amount="100")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["24", "18", "03", "04", "02", "09"],
        special_number="17",
        issue_number=f"FLAT-TAIL-BLOCK-{ruleset_version}",
    )
    with session_factory() as session:
        persisted = session.get(Order, order.id)
        assert persisted is not None
        persisted.ruleset_version = ruleset_version
        session.commit()

    service = SettlementService(session_factory)
    assert service.check_order_support(order.id)[0].is_supported is False
    with pytest.raises(SettlementDataError, match="规则版本不允许正式结算"):
        service.commit_order_settlement(order.id, draw.id)
    assert service.get_settlement_record_by_order_id(order.id) is None


def test_special_tail_remains_special_only(session_factory) -> None:
    order = _create_order(
        session_factory,
        items=[OrderItemCreate(bet_type="特码", selection="尾7", amount="100")],
    )
    draw = _create_draw(
        session_factory,
        regular_numbers=["07", "02", "04", "08", "09", "11"],
        special_number="18",
        issue_number="SPECIAL-TAIL-REGRESSION",
    )

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.normalized_bet_type == "special_tail"
    assert item.is_winner is False
    assert item.draw_special_number == "18"
