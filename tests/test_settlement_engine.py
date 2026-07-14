from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from models import Order
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from services.settlement_service import SettlementService
from settlement.bet_normalizer import BetTypeNormalizer
from settlement.exceptions import InvalidDrawError, InvalidSelectionError, SettlementDataError, UnsupportedBetTypeError
from settlement.matchers import (
    match_color,
    match_element,
    match_half_color,
    match_head,
    match_parity,
    match_size,
    match_special_number,
    match_sum_parity,
    match_sum_size,
    match_tail,
    match_zodiac,
)
from settlement.settlement_engine import SettlementEngine


@dataclass
class DrawLike:
    region: str = "澳门"
    issue_number: str = "162"
    draw_date: date = date(2026, 6, 11)
    regular_numbers: list[str] | None = None
    special_number: str = "01"

    def __post_init__(self) -> None:
        if self.regular_numbers is None:
            self.regular_numbers = ["02", "03", "04", "05", "06", "07"]


@dataclass
class ItemLike:
    id: int
    bet_type: str
    selection: str
    amount: Decimal = Decimal("10.00")


@dataclass
class OrderLike:
    id: int = 1
    order_no: str = "ORD-TEST"
    region: str = "澳门"
    items: list[ItemLike] | None = None

    def __post_init__(self) -> None:
        if self.items is None:
            self.items = []


def test_bet_type_normalizer_aliases_and_unknown() -> None:
    normalizer = BetTypeNormalizer()

    assert normalizer.normalize("特号", "1").normalized_bet_type == "special_number"
    assert normalizer.normalize("特码", "马").normalized_bet_type == "special_zodiac"
    assert normalizer.normalize("波色", "红波").normalized_bet_type == "special_color"

    with pytest.raises(UnsupportedBetTypeError):
        normalizer.normalize("未知玩法", "01")

    assert normalizer.normalize("连肖", "马蛇").normalized_bet_type == "special_zodiac_group"
    assert normalizer.normalize("连肖", "马蛇").selection == "蛇,马"

    assert normalizer.normalize("十不中", "6/18/31/43/22/10/03/15/01/13").selection == (
        "01,03,06,10,13,15,18,22,31,43"
    )
    with pytest.raises(InvalidSelectionError, match="实际9个"):
        normalizer.normalize("十不中", "01,02,03,04,05,06,07,08,09")
    with pytest.raises(InvalidSelectionError, match="号码重复"):
        normalizer.normalize("十不中", "01,02,03,04,05,06,07,08,09,09")


def test_special_number_matchers() -> None:
    assert match_special_number("01", "1")[0] is True
    assert match_special_number("01", "02")[0] is False
    assert match_special_number("1", "01")[0] is True

    with pytest.raises(Exception):
        match_special_number("50", "01")


def test_zodiac_rules_use_domain_mapping() -> None:
    assert match_zodiac("马", "01", year=2026)[0] is True
    assert match_zodiac("蛇", "01", year=2026)[0] is False
    assert match_zodiac("蛇", "01", year=2025)[0] is True
    assert match_zodiac("马", "01", year=2025)[0] is False


def test_settlement_engine_uses_configured_zodiac_year() -> None:
    order = OrderLike(items=[ItemLike(1, "特码生肖", "蛇")])
    draw = DrawLike(special_number="01")

    preview_2026 = SettlementEngine(zodiac_year=2026).evaluate_order(order, draw)
    preview_2025 = SettlementEngine(zodiac_year=2025).evaluate_order(order, draw)

    assert preview_2026.results[0].is_winner is False
    assert preview_2026.results[0].draw_special_zodiac == "马"
    assert preview_2025.results[0].is_winner is True
    assert preview_2025.results[0].draw_special_zodiac == "蛇"


def test_hong_kong_special_zodiac_package_checks_only_special_number_zodiac() -> None:
    preview = OrderIntakeService().preview_raw_text("香港特码：蛇 包80")
    assert preview.can_save
    assert len(preview.order_items) == 1
    item = preview.order_items[0]
    assert (item.bet_type, item.selection, item.amount) == ("特码生肖", "蛇", Decimal("80"))

    engine = SettlementEngine(zodiac_year=2026)

    regular_has_snake = engine.evaluate_item(
        item,
        DrawLike(
            region="香港",
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="08",
        ),
    )
    assert regular_has_snake.normalized_bet_type == "special_zodiac"
    assert regular_has_snake.is_winner is False
    assert regular_has_snake.matched_number is None

    only_special_is_snake = engine.evaluate_item(
        item,
        DrawLike(
            region="香港",
            regular_numbers=["01", "03", "04", "05", "06", "07"],
            special_number="02",
        ),
    )
    assert only_special_is_snake.normalized_bet_type == "special_zodiac"
    assert only_special_is_snake.is_winner is True
    assert only_special_is_snake.matched_number == "02"


def test_zodiac_each_numbers_save_and_settle_as_special_numbers_not_pingte() -> None:
    preview = OrderIntakeService().preview_raw_text(
        "鼠各数130-31/75-43/75",
        region="香港",
        zodiac_year=2026,
    )

    assert preview.can_save and preview.total_amount == Decimal("670")
    assert [item.bet_type for item in preview.order_items] == ["特码"] * 6
    assert [item.selection for item in preview.order_items] == ["07", "19", "31", "43", "31", "43"]

    engine = SettlementEngine(zodiac_year=2026)
    results = [
        engine.evaluate_item(
            item,
            DrawLike(region="香港", special_number="31"),
        )
        for item in preview.order_items
    ]
    assert all(result.normalized_bet_type == "special_number" for result in results)
    assert [result.is_winner for result in results] == [False, False, True, False, True, False]


def test_color_half_wave_and_invalid_selection() -> None:
    assert match_color("红波", "01")[0] is True
    assert match_color("蓝波", "01")[0] is False
    assert match_half_color("红单", "01")[0] is True

    with pytest.raises(InvalidSelectionError):
        BetTypeNormalizer().normalize("特码波色", "紫波")


def test_size_parity_tail_head_sum_and_element_matchers() -> None:
    assert match_size("小", "24")[0] is True
    assert match_size("大", "25")[0] is True
    assert match_parity("单", "01")[0] is True
    assert match_tail("尾9", "49")[0] is True
    assert match_head("3头", "37")[0] is True
    assert match_sum_parity("合单", "10")[0] is True
    assert match_sum_size("合大", "27")[0] is True
    assert match_element("金", "03")[0] is True
    assert match_element("木", "03")[0] is False

    with pytest.raises(InvalidSelectionError):
        BetTypeNormalizer().normalize("特码大小", "中")


def test_order_preview_counts_supported_losing_and_unsupported() -> None:
    order = OrderLike(
        items=[
            ItemLike(1, "特码", "01"),
            ItemLike(2, "特码生肖", "蛇"),
            ItemLike(3, "连尾", "马蛇"),
        ]
    )
    preview = SettlementEngine().evaluate_order(order, DrawLike())

    assert preview.total_items == 3
    assert preview.supported_items == 2
    assert preview.unsupported_items == 1
    assert preview.winning_items == 1
    assert preview.losing_items == 1
    assert preview.results[2].is_supported is False
    assert preview.results[2].is_winner is None


def test_order_preview_rejects_region_empty_order_and_invalid_draw() -> None:
    engine = SettlementEngine()

    with pytest.raises(SettlementDataError):
        engine.evaluate_order(OrderLike(region="香港", items=[ItemLike(1, "特码", "01")]), DrawLike())

    with pytest.raises(SettlementDataError):
        engine.evaluate_order(OrderLike(items=[]), DrawLike())

    with pytest.raises(InvalidDrawError):
        engine.evaluate_order(
            OrderLike(items=[ItemLike(1, "特码", "01")]),
            DrawLike(regular_numbers=["01", "02", "03", "04", "05", "06"], special_number="06"),
        )


def test_settlement_service_preview_is_read_only_and_detached(session_factory) -> None:
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)

    order = order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text="settlement test",
            source="test",
            items=[
                OrderItemCreate(bet_type="特码", selection="01", amount="10"),
                OrderItemCreate(bet_type="特码", selection="02", amount="20"),
            ],
        )
    )
    draw = draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="162",
            draw_date=date(2026, 6, 11),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="01",
        )
    )

    service = SettlementService(session_factory)
    before = order_service.get_order(order.id)
    preview = service.preview_order(order.id, draw.id)
    after = order_service.get_order(order.id)

    assert preview.order_id == order.id
    assert preview.winning_items == 1
    assert preview.losing_items == 1
    assert preview.results[0].amount == Decimal("10.00")
    assert before.status == after.status == "active"
    assert before.total_amount == after.total_amount
    assert preview.results[0].reason


def test_settlement_service_by_issue_and_missing_data(session_factory) -> None:
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text="settlement issue test",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )
    draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="163",
            draw_date=date(2026, 6, 12),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="01",
        )
    )

    preview = SettlementService(session_factory).preview_order_by_issue(order.id, "澳门", "163")
    assert preview.issue_number == "163"

    with pytest.raises(SettlementDataError):
        SettlementService(session_factory).preview_order(999999, 999999)


def test_settlement_service_uses_order_zodiac_year(session_factory) -> None:
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text="zodiac year settlement",
            source="test",
            zodiac_year=2025,
            items=[OrderItemCreate(bet_type="特码", selection="蛇", amount="10")],
        )
    )
    draw = draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="164",
            draw_date=date(2026, 6, 13),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="01",
        )
    )

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.results[0].is_winner is True
    assert preview.results[0].draw_special_zodiac == "蛇"


def test_settlement_service_falls_back_for_legacy_order_without_zodiac_year(session_factory) -> None:
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text="legacy zodiac year settlement",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="马", amount="10")],
        )
    )
    with session_factory() as session:
        db_order = session.get(Order, order.id)
        db_order.zodiac_year = None
        session.commit()
    draw = draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="165",
            draw_date=date(2026, 6, 14),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="01",
        )
    )

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.results[0].is_winner is True
    assert any("订单未记录生肖年份" in warning for warning in result.warnings)
