from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from domain.play_rules import FORTUNE_RULESET_2026_V1, FORTUNE_RULESET_2026_V2
from models import Order
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_parser import parse_lines
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from services.settlement_support_service import SettlementSupportService
from settlement.exceptions import SettlementDataError


@dataclass(frozen=True, slots=True)
class GoldenOrder:
    name: str
    text: str
    region: str
    expected_items: tuple[tuple[str, str, Decimal], ...]
    regular_numbers: tuple[str, ...]
    special_number: str
    odds: tuple[tuple[str, str, str], ...]
    winners: tuple[bool, ...]
    odds_keys: tuple[str | None, ...]
    rebate_keys: tuple[str | None, ...]
    matcher_ids: tuple[str, ...]
    total_amount: Decimal
    total_payout: Decimal


GOLDEN_ORDERS = (
    GoldenOrder(
        "special-duplicates",
        "特码49、49，各10",
        "澳门",
        (("特码", "49", Decimal("10")), ("特码", "49", Decimal("10"))),
        ("01", "02", "03", "04", "05", "06"),
        "49",
        (("特码", "2", "1"),),
        (True, True),
        ("特码", "特码"),
        ("特码", "特码"),
        ("match_special_number", "match_special_number"),
        Decimal("20"),
        Decimal("40"),
    ),
    GoldenOrder(
        "regular-duplicates",
        "平码22、22，各10",
        "澳门",
        (("平码", "22", Decimal("10")), ("平码", "22", Decimal("10"))),
        ("01", "02", "03", "04", "05", "22"),
        "49",
        (("平码", "2", "1"),),
        (True, True),
        ("平码", "平码"),
        ("平码", "平码"),
        ("match_regular_number", "match_regular_number"),
        Decimal("20"),
        Decimal("40"),
    ),
    GoldenOrder(
        "pingte-zodiacs",
        "平特一肖 龙-羊-猴，各80",
        "澳门",
        (
            ("平特一肖", "龙", Decimal("80")),
            ("平特一肖", "羊", Decimal("80")),
            ("平特一肖", "猴", Decimal("80")),
        ),
        ("24", "08", "03", "14", "32", "49"),
        "17",
        (("平特一肖", "2", "1"),),
        (True, True, False),
        ("平特一肖", "平特一肖", None),
        ("平特一肖", "平特一肖", "平特一肖"),
        ("pingte_zodiac_v2", "pingte_zodiac_v2", "pingte_zodiac_v2"),
        Decimal("240"),
        Decimal("320"),
    ),
    GoldenOrder(
        "main-zodiac",
        "平马各80",
        "澳门",
        (("平特一肖带主肖", "马", Decimal("80")),),
        ("13", "04", "07", "09", "11", "12"),
        "17",
        (("平特一肖带主肖", "5", "3"),),
        (True,),
        ("平特一肖带主肖",),
        ("平特一肖带主肖",),
        ("pingte_zodiac_v2",),
        Decimal("80"),
        Decimal("400"),
    ),
    GoldenOrder(
        "flat-tails",
        "平尾 0尾、4尾、7尾 各100",
        "澳门",
        (
            ("平特0尾", "0", Decimal("100")),
            ("平尾", "4", Decimal("100")),
            ("平尾", "7", Decimal("100")),
        ),
        ("10", "24", "18", "04", "02", "09"),
        "17",
        (("平特0尾", "5", "3"), ("平尾", "2", "1")),
        (True, True, True),
        ("平特0尾", "平尾", "平尾"),
        ("平特0尾", "平尾", "平尾"),
        ("flat_tail_v2", "flat_tail_v2", "flat_tail_v2"),
        Decimal("300"),
        Decimal("900"),
    ),
    GoldenOrder(
        "lianxiao",
        "连肖 龙羊虎 各100",
        "澳门",
        (("连肖", "虎,龙,羊", Decimal("100")),),
        ("24", "08", "03", "14", "32", "49"),
        "17",
        (("连肖", "2", "1"),),
        (True,),
        ("连肖",),
        ("连肖",),
        ("lianxiao_zodiac_v2",),
        Decimal("100"),
        Decimal("200"),
    ),
    GoldenOrder(
        "ten-non-hit",
        "6 18 31 43 22 10 03 15 01 13 十不中 4000",
        "澳门",
        (("N不中", "01,03,06,10,13,15,18,22,31,43", Decimal("4000")),),
        ("02", "04", "07", "09", "11", "12"),
        "18",
        (("十不中", "5", "1"),),
        (True,),
        ("十不中",),
        ("十不中",),
        ("non_hit_number_v2",),
        Decimal("4000"),
        Decimal("20000"),
    ),
    GoldenOrder(
        "two-in-two",
        "二中二 (01-02)-(03-08) 各10",
        "澳门",
        (("二中二", "(01-02)", Decimal("10")), ("二中二", "(03-08)", Decimal("10"))),
        ("01", "02", "03", "04", "05", "06"),
        "08",
        (("二中二", "2", "1"),),
        (True, False),
        ("二中二", None),
        ("二中二", "二中二"),
        ("match_two_in_two", "match_two_in_two"),
        Decimal("20"),
        Decimal("20"),
    ),
    GoldenOrder(
        "three-in-three",
        "三中三 (01-02-03)-(04-05-08) 各10",
        "澳门",
        (
            ("三中三", "(01-02-03)", Decimal("10")),
            ("三中三", "(04-05-08)", Decimal("10")),
        ),
        ("01", "02", "03", "04", "05", "06"),
        "08",
        (("三中三", "2", "1"),),
        (True, False),
        ("三中三", None),
        ("三中三", "三中三"),
        ("match_three_in_three", "match_three_in_three"),
        Decimal("20"),
        Decimal("20"),
    ),
    GoldenOrder(
        "three-in-two-tiers",
        "三中二 (01-02-08)-(03-04-05) 各10",
        "澳门",
        (
            ("三中二", "(01-02-08)", Decimal("10")),
            ("三中二", "(03-04-05)", Decimal("10")),
        ),
        ("01", "02", "03", "04", "05", "06"),
        "08",
        (("三中二中2", "2", "0"), ("三中二中3", "5", "0"), ("三中二", "99", "1")),
        (True, True),
        ("三中二中2", "三中二中3"),
        ("三中二", "三中二"),
        ("three_in_two_v2", "three_in_two_v2"),
        Decimal("20"),
        Decimal("70"),
    ),
    GoldenOrder(
        "special-zodiac",
        "香港特码：蛇 包80",
        "香港",
        (("特码生肖", "蛇", Decimal("80")),),
        ("01", "03", "04", "05", "06", "07"),
        "02",
        (("特码生肖", "2", "1"),),
        (True,),
        ("特码生肖",),
        ("特码生肖",),
        ("match_zodiac",),
        Decimal("80"),
        Decimal("160"),
    ),
)


def _configure_odds(session_factory, configs: tuple[tuple[str, str, str], ...]) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    for bet_type, odds, rebate in configs:
        settings.add_item(plan.id, bet_type, odds, rebate)


def _create_draw(session_factory, case: GoldenOrder):
    return DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region=case.region,
            issue_number=f"V2-E2E-{case.name}",
            draw_date=date(2026, 7, 15),
            regular_numbers=list(case.regular_numbers),
            special_number=case.special_number,
            source="v2-e2e",
        )
    )


@pytest.mark.parametrize("case", GOLDEN_ORDERS, ids=lambda case: case.name)
def test_golden_orders_cover_parse_save_support_commit_snapshot_and_detail(
    session_factory,
    case: GoldenOrder,
) -> None:
    parsed = parse_lines(case.text)
    assert parsed and all(result.success for result in parsed)
    assert sum((Decimal(result.total) for result in parsed), Decimal("0")) == case.total_amount

    intake = OrderIntakeService(session_factory)
    intake_preview = intake.preview_raw_text(case.text, region=case.region, zodiac_year=2026)
    assert intake_preview.can_save, intake_preview.errors
    assert intake_preview.total_amount == case.total_amount
    assert [(item.bet_type, item.selection, item.amount) for item in intake_preview.order_items] == list(
        case.expected_items
    )
    assert all(
        item.settlement_support_status == "supported"
        for item in intake_preview.items
        if item.is_valid
    )

    saved = intake.save_preview(intake_preview)
    assert saved.success and saved.order is not None
    assert saved.order.total_amount == case.total_amount
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None
    assert detail.status == "active"
    assert detail.ruleset_version == FORTUNE_RULESET_2026_V2
    assert [(item.bet_type, item.selection, item.amount) for item in detail.items] == list(
        case.expected_items
    )
    support = SettlementSupportService().check_order_items(
        detail.items,
        ruleset_version=detail.ruleset_version,
        zodiac_year=detail.zodiac_year,
        require_zodiac_year=True,
    )
    assert support and all(result.is_supported for result in support)

    _configure_odds(session_factory, case.odds)
    draw = _create_draw(session_factory, case)
    settlement = SettlementService(session_factory)
    preview = settlement.preview_order(detail.id, draw.id)
    assert preview.settlement_ready is True
    assert tuple(item.is_winner for item in preview.results) == case.winners
    assert tuple(item.odds_key_used for item in preview.results) == case.odds_keys
    assert tuple(item.rebate_key_used for item in preview.results) == case.rebate_keys
    assert preview.total_bet_amount == case.total_amount
    assert preview.total_payout_amount == case.total_payout

    committed = settlement.commit_order_settlement(detail.id, draw.id)
    assert committed.order_status_before == "active"
    assert committed.order_status_after == "settled"
    assert committed.total_bet_amount == case.total_amount
    assert committed.total_payout_amount == case.total_payout
    assert tuple(item.matcher_id for item in committed.results) == case.matcher_ids

    record = settlement.get_settlement_record_by_order_id(detail.id)
    assert record is not None
    assert record.order_status == "settled"
    assert record.total_amount == case.total_amount
    snapshot = record.result_snapshot
    assert snapshot["order"]["ruleset_version"] == FORTUNE_RULESET_2026_V2
    assert len(snapshot["items"]) == len(case.expected_items)
    assert [item["matcher_id"] for item in snapshot["items"]] == list(case.matcher_ids)
    assert [item["odds_key_used"] for item in snapshot["items"]] == list(case.odds_keys)
    assert [item["rebate_key_used"] for item in snapshot["items"]] == list(case.rebate_keys)
    assert all(item["ruleset_version"] == FORTUNE_RULESET_2026_V2 for item in snapshot["items"])
    assert all("reason" in item and "odds_key_candidates" in item for item in snapshot["items"])

    settled_detail = OrderService(session_factory).get_order(detail.id)
    assert settled_detail is not None and settled_detail.status == "settled"
    assert [(item.bet_type, item.selection, item.amount) for item in settled_detail.items] == list(
        case.expected_items
    )
    with pytest.raises(SettlementDataError, match="不能重复结算"):
        settlement.commit_order_settlement(detail.id, draw.id)


@pytest.mark.parametrize("case", GOLDEN_ORDERS, ids=lambda case: case.name)
def test_golden_orders_missing_odds_cannot_commit(session_factory, case: GoldenOrder) -> None:
    intake = OrderIntakeService(session_factory)
    saved = intake.parse_and_save(
        case.text,
        region=case.region,
        source="v2-e2e-missing-odds",
        zodiac_year=2026,
    )
    assert saved.success and saved.order is not None
    draw = _create_draw(session_factory, case)
    settlement = SettlementService(session_factory)

    preview = settlement.preview_order(saved.order.id, draw.id)
    assert preview.settlement_ready is False
    assert any(item.missing_odds for item in preview.results)
    with pytest.raises(SettlementDataError, match="赔率配置不完整"):
        settlement.commit_order_settlement(saved.order.id, draw.id)
    assert settlement.get_settlement_record_by_order_id(saved.order.id) is None
    detail = OrderService(session_factory).get_order(saved.order.id)
    assert detail is not None and detail.status == "active"


SPECIAL_PROPERTY_CASES = (
    ("龙", "special_zodiac", "特码生肖", "match_zodiac"),
    ("蓝波", "special_color", "特码波色", "match_color"),
    ("蓝单", "special_half_wave", "特码半波", "match_half_color"),
    ("小", "special_size", "特码大小", "match_size"),
    ("单", "special_parity", "特码单双", "match_parity"),
    ("尾3", "special_tail", "特码尾数", "match_tail"),
    ("0头", "special_head", "特码头数", "match_head"),
    ("合单", "special_sum_parity", "特码合数单双", "match_sum_parity"),
    ("合小", "special_sum_size", "特码合数大小", "match_sum_size"),
    ("金", "special_element", "特码五行", "match_element"),
)


def _create_special_property_order(session_factory, selection: str):
    return OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text=f"特码 {selection} 各10",
            source="v2-e2e-special-property",
            zodiac_year=2026,
            items=[OrderItemCreate(bet_type="特码", selection=selection, amount="10")],
        )
    )


@pytest.mark.parametrize(
    ("selection", "normalized_type", "odds_key", "matcher_id"),
    SPECIAL_PROPERTY_CASES,
)
def test_supported_special_properties_use_special_only_matcher_and_specific_keys(
    session_factory,
    selection: str,
    normalized_type: str,
    odds_key: str,
    matcher_id: str,
) -> None:
    order = _create_special_property_order(session_factory, selection)
    _configure_odds(session_factory, ((odds_key, "2", "1"),))
    case = GoldenOrder(
        f"property-{normalized_type}",
        "unused",
        "澳门",
        (),
        ("01", "02", "04", "05", "06", "07"),
        "03",
        (),
        (),
        (),
        (),
        (),
        Decimal("0"),
        Decimal("0"),
    )
    draw = _create_draw(session_factory, case)
    settlement = SettlementService(session_factory)

    item = settlement.commit_order_settlement(order.id, draw.id).results[0]

    assert item.normalized_bet_type == normalized_type
    assert item.is_winner is True
    assert item.odds_key_used == odds_key
    assert item.rebate_key_used == odds_key
    assert item.payout_amount == Decimal("20")
    assert item.matcher_id == matcher_id
    record = settlement.get_settlement_record_by_order_id(order.id)
    assert record is not None
    audit = record.result_snapshot["items"][0]
    assert audit["ruleset_version"] == FORTUNE_RULESET_2026_V2
    assert audit["matcher_id"] == matcher_id
    assert audit["odds_key_used"] == odds_key
    assert audit["rebate_key_used"] == odds_key
    assert audit["draw_special_number"] == "03"


@pytest.mark.parametrize(
    ("selection", "_normalized_type", "odds_key", "_matcher_id"),
    SPECIAL_PROPERTY_CASES,
)
def test_supported_special_properties_missing_specific_odds_are_not_ready(
    session_factory,
    selection: str,
    _normalized_type: str,
    odds_key: str,
    _matcher_id: str,
) -> None:
    order = _create_special_property_order(session_factory, selection)
    case = GoldenOrder(
        f"property-missing-{odds_key}",
        "unused",
        "澳门",
        (),
        ("01", "02", "04", "05", "06", "07"),
        "03",
        (),
        (),
        (),
        (),
        (),
        Decimal("0"),
        Decimal("0"),
    )
    draw = _create_draw(session_factory, case)
    settlement = SettlementService(session_factory)

    preview = settlement.preview_order(order.id, draw.id)
    item = preview.results[0]
    assert item.missing_odds is True
    assert item.settlement_ready is False
    assert odds_key in item.odds_key_candidates
    with pytest.raises(SettlementDataError, match="赔率配置不完整"):
        settlement.commit_order_settlement(order.id, draw.id)
    assert settlement.get_settlement_record_by_order_id(order.id) is None
    detail = OrderService(session_factory).get_order(order.id)
    assert detail is not None and detail.status == "active"


BLOCKED_PLAYS = (
    ("连肖复选", "兔,狗,虎,蛇,龙", "复选类型=复4"),
    ("几中几复选", "01,02,03,04", "复选类型=复3"),
    ("二中特", "01,02", None),
    ("二中特复选", "01,02,03", "复选类型=复2"),
    ("特串", "01,02", None),
    ("四肖", "鼠,虎,龙,猴", None),
    ("包半波", "红单", None),
    ("连尾", "1尾,2尾", None),
    ("正码特", "01", None),
    ("胆拖", "01,02,03", None),
)


@pytest.mark.parametrize(("bet_type", "selection", "note"), BLOCKED_PLAYS)
def test_current_blocked_plays_cannot_bypass_gate(
    bet_type: str,
    selection: str,
    note: str | None,
) -> None:
    result = SettlementSupportService().check_item(bet_type, selection, note=note)

    assert result.is_supported is False
    assert result.status == "unsupported"


@pytest.mark.parametrize(
    ("bet_type", "selection", "note"),
    [case for case in BLOCKED_PLAYS if case[0] != "胆拖"],
)
def test_odds_configuration_does_not_bypass_formal_block(
    session_factory,
    bet_type: str,
    selection: str,
    note: str | None,
) -> None:
    order = OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text=f"{bet_type} {selection}",
            source="v2-e2e-blocked",
            zodiac_year=2026,
            items=[OrderItemCreate(bet_type=bet_type, selection=selection, amount="10", note=note)],
        )
    )
    _configure_odds(session_factory, ((bet_type, "99", "9"),))
    case = GoldenOrder(
        f"blocked-{bet_type}",
        "unused",
        "澳门",
        (),
        ("01", "02", "04", "05", "06", "07"),
        "03",
        (),
        (),
        (),
        (),
        (),
        Decimal("0"),
        Decimal("0"),
    )
    draw = _create_draw(session_factory, case)
    settlement = SettlementService(session_factory)

    with pytest.raises(SettlementDataError, match="暂不支持玩法"):
        settlement.commit_order_settlement(order.id, draw.id)
    assert settlement.get_settlement_record_by_order_id(order.id) is None


@pytest.mark.parametrize("ruleset_version", [FORTUNE_RULESET_2026_V1, "UNKNOWN_RULESET"])
def test_v1_and_unknown_rulesets_cannot_commit(
    session_factory,
    ruleset_version: str,
) -> None:
    order = OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="特码03各10",
            source="v2-e2e-ruleset-gate",
            items=[OrderItemCreate(bet_type="特码", selection="03", amount="10")],
        )
    )
    with session_factory() as session:
        stored = session.get(Order, order.id)
        assert stored is not None
        stored.ruleset_version = ruleset_version
        session.commit()
    _configure_odds(session_factory, (("特码", "2", "1"),))
    case = GoldenOrder(
        f"ruleset-{ruleset_version}",
        "unused",
        "澳门",
        (),
        ("01", "02", "04", "05", "06", "07"),
        "03",
        (),
        (),
        (),
        (),
        (),
        Decimal("0"),
        Decimal("0"),
    )
    draw = _create_draw(session_factory, case)
    settlement = SettlementService(session_factory)

    with pytest.raises(SettlementDataError, match="规则版本"):
        settlement.commit_order_settlement(order.id, draw.id)
    assert settlement.get_settlement_record_by_order_id(order.id) is None
    detail = OrderService(session_factory).get_order(order.id)
    assert detail is not None and detail.status == "active"
