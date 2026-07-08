from __future__ import annotations

from decimal import Decimal

from domain.zodiac_config import get_default_zodiac_year, get_zodiac_number_map
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.adjustment_summary_service import AdjustmentSummaryService, normalize_lianxiao_group
from services.order_service import OrderService


def create_order(
    service: OrderService,
    *,
    region: str = "澳门",
    bet_type: str = "特码",
    selection: str = "01",
    amount: str = "10",
    zodiac_year: int | None = None,
):
    return service.create_order(
        OrderCreate(
            customer_name="调单测试",
            channel="pytest",
            region=region,
            raw_text=f"{bet_type} {selection} {amount}",
            source="test",
            zodiac_year=zodiac_year,
            items=[OrderItemCreate(bet_type=bet_type, selection=selection, amount=amount)],
        )
    )


def test_tema_number_summary_expands_direct_numbers(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, selection="01", amount="100")
    create_order(order_service, selection="25-37-49各20", amount="20")

    summary = AdjustmentSummaryService(session_factory).summarize_tema(region="澳门")
    by_number = {row.number: row for row in summary.rows}

    assert by_number["01"].original_amount == Decimal("100.00")
    assert by_number["25"].original_amount == Decimal("20.00")
    assert by_number["37"].original_amount == Decimal("20.00")
    assert by_number["49"].original_amount == Decimal("20.00")
    assert summary.original_total == Decimal("160.00")


def test_tema_zodiac_summary_expands_zodiacs(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, selection="马", amount="50")
    create_order(order_service, selection="羊马各10", amount="10")

    service = AdjustmentSummaryService(session_factory)
    summary = service.summarize_tema(region="澳门")
    by_number = {row.number: row for row in summary.rows}
    zodiac_map = get_zodiac_number_map(get_default_zodiac_year())

    for number in zodiac_map["马"]:
        assert by_number[number].original_amount == Decimal("60.00")
    for number in zodiac_map["羊"]:
        assert by_number[number].original_amount == Decimal("10.00")


def test_tema_adjustment_input() -> None:
    adjustments = AdjustmentSummaryService().parse_tema_adjustments("12=100\n25=50")

    assert adjustments == {"12": Decimal("100.00"), "25": Decimal("50.00")}


def test_lianxiao_regular_group_summary(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, bet_type="连肖", selection="狗羊猴", amount="200")
    create_order(order_service, bet_type="连肖", selection="龙羊猴鸡", amount="50")

    rows = AdjustmentSummaryService(session_factory).summarize_lianxiao(region="澳门").rows
    by_group = {row.group: row for row in rows}

    assert by_group[normalize_lianxiao_group("狗羊猴")].original_amount == Decimal("200.00")
    assert by_group[normalize_lianxiao_group("龙羊猴鸡")].original_amount == Decimal("50.00")


def test_lianxiao_fuxuan_expands_combinations(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, bet_type="连肖复选", selection="兔狗虎蛇龙 复4", amount="10")

    rows = AdjustmentSummaryService(session_factory).summarize_lianxiao(region="澳门").rows
    groups = {row.group for row in rows}

    assert len(groups) == 5
    assert normalize_lianxiao_group("兔狗虎蛇") in groups
    assert normalize_lianxiao_group("兔狗虎龙") in groups
    assert normalize_lianxiao_group("兔狗蛇龙") in groups
    assert normalize_lianxiao_group("兔虎蛇龙") in groups
    assert normalize_lianxiao_group("狗虎蛇龙") in groups
    assert all(row.original_amount == Decimal("10.00") for row in rows)


def test_lianxiao_group_normalize_uses_fixed_zodiac_order() -> None:
    assert normalize_lianxiao_group("狗羊猴") == normalize_lianxiao_group("羊狗猴")


def test_lianxiao_adjustment_input() -> None:
    service = AdjustmentSummaryService()
    adjustments = service.parse_lianxiao_adjustments("狗羊猴=100\n龙羊猴鸡=50")

    assert adjustments[normalize_lianxiao_group("狗羊猴")] == Decimal("100.00")
    assert adjustments[normalize_lianxiao_group("龙羊猴鸡")] == Decimal("50.00")
