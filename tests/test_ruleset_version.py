from __future__ import annotations

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
from schemas.order_intake_schema import IntakeMetadata, IntakeTableRow
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_import_service import OrderImportService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService


def test_order_create_defaults_to_v2_and_rejects_non_v2_new_orders() -> None:
    item = OrderItemCreate(bet_type="特码", selection="01", amount="10")

    order = OrderCreate(region="澳门", raw_text="01各10", source="manual", items=[item])

    assert order.ruleset_version == FORTUNE_RULESET_2026_V2
    with pytest.raises(ValueError, match="新订单只能使用规则版本"):
        OrderCreate(
            region="澳门",
            raw_text="01各10",
            source="manual",
            items=[item],
            ruleset_version=FORTUNE_RULESET_2026_V1,
        )
    with pytest.raises(ValueError, match="新订单只能使用规则版本"):
        OrderCreate(
            region="澳门",
            raw_text="01各10",
            source="manual",
            items=[item],
            ruleset_version="UNKNOWN_RULESET",
        )


def test_direct_order_service_persists_v2(session_factory) -> None:
    result = OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="01各10",
            source="manual",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )

    assert result.ruleset_version == FORTUNE_RULESET_2026_V2
    with session_factory() as session:
        order = session.get(Order, result.id)
        assert order is not None
        assert order.ruleset_version == FORTUNE_RULESET_2026_V2


def test_intelligent_intake_and_custom_table_save_v2(session_factory) -> None:
    service = OrderIntakeService(session_factory)
    recognized = service.parse_and_save(
        "01各10",
        region="澳门",
        source="record_window",
    )
    custom_preview = service.preview_table_rows(
        [
            IntakeTableRow(
                row_number=1,
                region="澳门",
                bet_type="特码",
                selection="02",
                total_amount="20",
                per_item_amount="20",
            )
        ],
        IntakeMetadata(
            region="澳门",
            source="record_window_adjusted",
            raw_text="custom row",
        ),
    )
    custom = service.save_preview(custom_preview)

    assert recognized.success and recognized.order is not None
    assert custom.success and custom.order is not None
    assert recognized.order.ruleset_version == FORTUNE_RULESET_2026_V2
    assert custom.order.ruleset_version == FORTUNE_RULESET_2026_V2
    with session_factory() as session:
        versions = session.scalars(select(Order.ruleset_version).order_by(Order.id)).all()
    assert versions == [FORTUNE_RULESET_2026_V2, FORTUNE_RULESET_2026_V2]


def test_file_import_save_v2(session_factory) -> None:
    intake = OrderIntakeService(session_factory)
    service = OrderImportService(order_intake_service=intake)
    preview = service.preview_lines(["03各10"], region_mode="澳门")

    result = service.confirm_import(preview, file_path="trial.txt")

    assert result.imported_count == 1
    order_id = result.preview.rows[0].order_id
    assert order_id is not None
    detail = OrderService(session_factory).get_order(order_id)
    assert detail is not None
    assert detail.ruleset_version == FORTUNE_RULESET_2026_V2


def test_play_rule_metadata_describes_safe_and_blocked_v2_plays() -> None:
    special = get_play_rule("特码")
    pingte = get_play_rule("平特一肖")
    pingte_main = get_play_rule("平特一肖带主肖")
    ping_tail = get_play_rule("平尾")
    zero_tail = get_play_rule("平特0尾")
    non_hit_alias = get_play_rule("十不中")

    assert special is not None
    assert special.draw_scope is DrawScope.SPECIAL_ONLY
    assert special.selection_unit is SelectionUnit.NUMBER
    assert special.duplicate_policy is DuplicatePolicy.REPEAT_AS_INDEPENDENT_STAKES
    assert special.availability is SettlementAvailability.SUPPORTED
    assert special.matcher_id == "match_special_number"
    assert pingte is not None
    assert pingte.availability is SettlementAvailability.SUPPORTED
    assert pingte.draw_scope is DrawScope.ALL_SEVEN
    assert pingte.selection_unit is SelectionUnit.ZODIAC
    assert pingte.duplicate_policy is DuplicatePolicy.FORBID_WITHIN_GROUP
    assert pingte.matcher_id == "pingte_zodiac_v2"
    assert pingte.matcher_version == "2.0"
    assert pingte_main is not None
    assert pingte_main.availability is SettlementAvailability.SUPPORTED
    assert pingte_main.matcher_id == "pingte_zodiac_v2"
    assert pingte_main.matcher_version == "2.0"
    assert ping_tail is not None
    assert ping_tail.availability is SettlementAvailability.SUPPORTED
    assert ping_tail.draw_scope is DrawScope.ALL_SEVEN
    assert ping_tail.selection_unit is SelectionUnit.TAIL
    assert ping_tail.duplicate_policy is DuplicatePolicy.FORBID_WITHIN_GROUP
    assert ping_tail.matcher_id == "flat_tail_v2"
    assert ping_tail.matcher_version == "2.0"
    assert zero_tail is not None
    assert zero_tail.availability is SettlementAvailability.SUPPORTED
    assert zero_tail.normalized_type == "ping_tail"
    assert zero_tail.odds_keys == ("平特0尾", "平尾0尾", "0尾")
    assert non_hit_alias is get_play_rule("N不中")
    assert non_hit_alias is not None
    assert non_hit_alias.availability is SettlementAvailability.SUPPORTED
    assert non_hit_alias.draw_scope is DrawScope.REGULAR_SIX
    assert non_hit_alias.matcher_id == "non_hit_number_v2"
    assert non_hit_alias.matcher_version == "2.0"


@pytest.mark.parametrize(
    "bet_type",
    [
        "连肖",
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
def test_unsafe_v2_plays_remain_saveable_for_accounting(session_factory, bet_type: str) -> None:
    result = OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text=f"{bet_type} trial accounting order",
            source="test",
            items=[OrderItemCreate(bet_type=bet_type, selection="01,02,03", amount="10")],
        )
    )

    detail = OrderService(session_factory).get_order(result.id)
    assert detail is not None
    assert detail.items[0].bet_type == bet_type
    assert detail.ruleset_version == FORTUNE_RULESET_2026_V2
