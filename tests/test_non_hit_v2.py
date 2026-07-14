from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from domain.play_rules import (
    FORTUNE_RULESET_2026_V1,
    FORTUNE_RULESET_2026_V2,
    DrawScope,
    DuplicatePolicy,
    SelectionUnit,
    SettlementAvailability,
    get_play_rule,
)
from models import Order
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_parser import parse_order
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from services.settlement_support_service import SettlementSupportService
from settlement.bet_normalizer import BetTypeNormalizer
from settlement.exceptions import InvalidSelectionError, SettlementDataError


TEN_NON_HIT_SELECTION = "01,03,06,10,13,15,18,22,31,43"
TEN_NON_HIT_TEXT = "6 18 31 43 22 10 03 15 01 13 十不中 4000"


def _create_order(session_factory, *, amount: str = "4000"):
    return OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text=TEN_NON_HIT_TEXT,
            source="test",
            items=[
                OrderItemCreate(
                    bet_type="N不中",
                    selection=TEN_NON_HIT_SELECTION,
                    amount=amount,
                )
            ],
        )
    )


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


@pytest.mark.parametrize(
    ("regular_numbers", "special_number", "expected_winner", "expected_hits"),
    [
        (["02", "04", "07", "09", "11", "12"], "18", True, ()),
        (["02", "04", "07", "09", "11", "18"], "49", False, ("18",)),
        (["02", "04", "07", "09", "11", "12"], "49", True, ()),
    ],
)
def test_non_hit_v2_golden_regular_six_scenarios(
    session_factory,
    regular_numbers: list[str],
    special_number: str,
    expected_winner: bool,
    expected_hits: tuple[str, ...],
) -> None:
    order = _create_order(session_factory)
    draw = _create_draw(
        session_factory,
        regular_numbers=regular_numbers,
        special_number=special_number,
        issue_number=f"NH-{special_number}-{regular_numbers[-1]}",
    )

    item = SettlementService(session_factory).preview_order(order.id, draw.id).results[0]

    assert item.is_supported is True
    assert item.is_winner is expected_winner
    assert item.normalized_bet_type == "non_hit_number"
    assert item.selected_numbers == tuple(TEN_NON_HIT_SELECTION.split(","))
    assert item.regular_numbers == tuple(regular_numbers)
    assert item.special_number == special_number
    assert item.hit_regular_numbers == expected_hits
    assert item.hit_numbers == expected_hits
    assert special_number not in item.hit_regular_numbers
    assert "前6个平码" in item.reason
    assert "特别号不参与N不中判断" in item.reason
    assert "全部开奖号码" not in item.reason
    assert item.matcher_id == "non_hit_number_v2"
    assert item.matcher_version == "2.0"
    assert item.draw_scope == DrawScope.REGULAR_SIX.value
    assert item.selection_unit == SelectionUnit.NUMBER_GROUP.value


@pytest.mark.parametrize(
    ("bet_type", "count"),
    [
        ("5不中", 5),
        ("五不中", 5),
        ("27不中", 27),
        ("二十七不中", 27),
    ],
)
def test_non_hit_v2_accepts_five_through_twenty_seven(bet_type: str, count: int) -> None:
    selection = ",".join(f"{number:02d}" for number in range(1, count + 1))

    normalized = BetTypeNormalizer().normalize(bet_type, selection)

    assert normalized.normalized_bet_type == "non_hit_number"
    assert normalized.selection.split(",") == selection.split(",")


@pytest.mark.parametrize(("bet_type", "count"), [("4不中", 4), ("28不中", 28)])
def test_non_hit_v2_rejects_out_of_range_counts(bet_type: str, count: int) -> None:
    selection = ",".join(str(number) for number in range(1, count + 1))

    with pytest.raises(InvalidSelectionError, match="5-27"):
        BetTypeNormalizer().normalize(bet_type, selection)


@pytest.mark.parametrize(
    ("selection", "message"),
    [
        ("01,02,03,04,05,06,07,08,09", "实际9个"),
        ("01,02,03,04,05,06,07,08,09,10,11", "实际11个"),
        ("01,02,03,04,05,06,07,08,09,09", "号码重复"),
        ("00,01,02,03,04,05,06,07,08,09", "01-49"),
        ("01,02,03,04,05,06,07,08,09,50", "01-49"),
    ],
)
def test_ten_non_hit_v2_strict_selection_validation(selection: str, message: str) -> None:
    with pytest.raises(InvalidSelectionError, match=message):
        BetTypeNormalizer().normalize("十不中", selection)


def test_ten_non_hit_parser_and_save_keep_one_group_amount(session_factory) -> None:
    parsed = parse_order(TEN_NON_HIT_TEXT)

    assert parsed.success
    assert parsed.category == "N不中"
    assert parsed.numbers == (1, 3, 6, 10, 13, 15, 18, 22, 31, 43)
    assert parsed.amount == 4000
    assert parsed.total == 4000

    saved = OrderIntakeService(session_factory).parse_and_save(
        TEN_NON_HIT_TEXT,
        region="澳门",
        source="test",
    )
    assert saved.success and saved.order is not None
    assert saved.order.total_amount == Decimal("4000.00")
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None
    assert len(detail.items) == 1
    assert detail.items[0].bet_type == "N不中"
    assert detail.items[0].selection == TEN_NON_HIT_SELECTION
    assert detail.items[0].amount == Decimal("4000.00")


def test_non_hit_v2_support_metadata_and_formal_commit_snapshot(session_factory) -> None:
    rule = get_play_rule("十不中")
    assert rule is not None
    assert rule.availability is SettlementAvailability.SUPPORTED
    assert rule.draw_scope is DrawScope.REGULAR_SIX
    assert rule.selection_unit is SelectionUnit.NUMBER_GROUP
    assert rule.duplicate_policy is DuplicatePolicy.FORBID_WITHIN_GROUP
    assert rule.matcher_id == "non_hit_number_v2"
    assert rule.matcher_version == "2.0"

    support = SettlementSupportService().check_order_items(
        [
            type(
                "Item",
                (),
                {"bet_type": "N不中", "selection": TEN_NON_HIT_SELECTION, "note": None},
            )()
        ],
        ruleset_version=FORTUNE_RULESET_2026_V2,
    )
    assert len(support) == 1 and support[0].is_supported

    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "十不中", "5.0", "1")
    order = _create_order(session_factory)
    draw = _create_draw(
        session_factory,
        regular_numbers=["02", "04", "07", "09", "11", "12"],
        special_number="18",
        issue_number="NH-COMMIT",
    )

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.win_count == 1
    assert result.total_bet_amount == Decimal("4000.00")
    assert result.total_payout_amount == Decimal("20000.00")
    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    item = record.result_snapshot["items"][0]
    assert item["ruleset_version"] == FORTUNE_RULESET_2026_V2
    assert item["normalized_type"] == "non_hit_number"
    assert item["matcher_id"] == "non_hit_number_v2"
    assert item["matcher_version"] == "2.0"
    assert item["draw_scope"] == DrawScope.REGULAR_SIX.value
    assert item["selection_unit"] == SelectionUnit.NUMBER_GROUP.value
    assert item["odds_key_used"] == "十不中"
    assert item["rebate_key_used"] == "十不中"
    assert item["payout_tier"] is None
    assert item["selected_numbers"] == TEN_NON_HIT_SELECTION.split(",")
    assert item["regular_numbers"] == ["02", "04", "07", "09", "11", "12"]
    assert item["special_number"] == "18"
    assert item["hit_regular_numbers"] == []
    assert item["is_winner"] is True
    assert "特别号不参与N不中判断" in item["reason"]


@pytest.mark.parametrize("ruleset_version", [FORTUNE_RULESET_2026_V1, "UNKNOWN_RULESET"])
def test_non_hit_v1_and_unknown_rulesets_cannot_use_v2_matcher(
    session_factory,
    ruleset_version: str,
) -> None:
    order = _create_order(session_factory)
    draw = _create_draw(
        session_factory,
        regular_numbers=["02", "04", "07", "09", "11", "12"],
        special_number="18",
        issue_number=f"NH-BLOCK-{ruleset_version}",
    )
    with session_factory() as session:
        persisted = session.scalars(select(Order).where(Order.id == order.id)).one()
        persisted.ruleset_version = ruleset_version
        session.commit()

    support = SettlementService(session_factory).check_order_support(order.id)
    assert support and all(not item.is_supported for item in support)
    with pytest.raises(SettlementDataError, match="规则版本不允许正式结算"):
        SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    detail = OrderService(session_factory).get_order(order.id)
    assert detail is not None
    assert detail.status == "active"
    assert detail.ruleset_version == ruleset_version
    assert SettlementService(session_factory).get_settlement_record_by_order_id(order.id) is None

