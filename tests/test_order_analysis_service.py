from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from models import Order, OrderItem
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_analysis_service import OrderAnalysisService
from services.order_service import OrderService


def create_order(
    service: OrderService,
    *,
    region: str,
    amount: str = "10",
    items: list[OrderItemCreate] | None = None,
):
    return service.create_order(
        OrderCreate(
            customer_name="analysis-test",
            channel="test",
            region=region,
            raw_text=f"analysis {amount}",
            source="test",
            items=items or [OrderItemCreate(bet_type="特码", selection="01", amount=amount)],
        )
    )


def _amount_by_number(summary, number: int) -> Decimal:
    return summary.number_rows[number - 1].bet_amount


def _count_by_zodiac(rows) -> dict[str, int]:
    return {row.zodiac: row.count for row in rows}


def _amount_by_zodiac(rows) -> dict[str, Decimal]:
    return {row.zodiac: row.amount for row in rows}


def test_order_analysis_service_empty_database_keeps_full_zero_shape(session_factory) -> None:
    summary = OrderAnalysisService(session_factory).get_workbench()

    assert summary.order_count == 0
    assert summary.item_count == 0
    assert len(summary.number_rows) == 49
    assert all(row.bet_amount == Decimal("0") for row in summary.number_rows)
    assert len(summary.lianxiao_frequency) == 12
    assert len(summary.pingte_zodiac_amounts) == 12


def test_order_analysis_service_counts_number_amounts_and_filters_regions(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(
        order_service,
        region="澳门",
        items=[
            OrderItemCreate(bet_type="特码", selection="1", amount="10"),
            OrderItemCreate(bet_type="号码", selection="02,03", amount="7"),
        ],
    )
    create_order(order_service, region="香港", items=[OrderItemCreate(bet_type="特码", selection="02", amount="20")])

    service = OrderAnalysisService(session_factory)
    all_summary = service.get_workbench()
    macau_summary = service.get_workbench(region="macau")
    hk_summary = service.get_workbench(region="Hong Kong")

    assert _amount_by_number(all_summary, 1) == Decimal("10.00")
    assert _amount_by_number(all_summary, 2) == Decimal("27.00")
    assert _amount_by_number(all_summary, 3) == Decimal("7.00")
    assert macau_summary.order_count == 1
    assert _amount_by_number(macau_summary, 2) == Decimal("7.00")
    assert hk_summary.order_count == 1
    assert _amount_by_number(hk_summary, 2) == Decimal("20.00")


def test_order_analysis_service_counts_lianxiao_frequency_and_zodiac_amounts(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(
        order_service,
        region="澳门",
        items=[
            OrderItemCreate(bet_type="连肖", selection="鼠,牛,虎", amount="30"),
            OrderItemCreate(bet_type="平特一肖", selection="马", amount="11"),
            OrderItemCreate(bet_type="平特一肖", selection="羊,马", amount="13"),
        ],
    )

    summary = OrderAnalysisService(session_factory).get_workbench()
    lianxiao = _count_by_zodiac(summary.lianxiao_frequency)
    pingte = _amount_by_zodiac(summary.pingte_zodiac_amounts)

    assert lianxiao["鼠"] == 1
    assert lianxiao["牛"] == 1
    assert lianxiao["虎"] == 1
    assert pingte["马"] == Decimal("24.00")
    assert pingte["羊"] == Decimal("13.00")


def test_order_analysis_service_does_not_force_unclear_items_into_statistics(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(
        order_service,
        region="澳门",
        items=[
            OrderItemCreate(bet_type="包半波", selection="红单", amount="99"),
            OrderItemCreate(bet_type="特码", selection="红单", amount="10"),
        ],
    )

    summary = OrderAnalysisService(session_factory).get_workbench()

    assert all(row.bet_amount == Decimal("0") for row in summary.number_rows)
    assert all(row.count == 0 for row in summary.lianxiao_frequency)
    assert all(row.amount == Decimal("0") for row in summary.pingte_zodiac_amounts)


def test_order_analysis_report_contains_top_info_and_safety_notes(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(
        order_service,
        region="澳门",
        items=[
            OrderItemCreate(bet_type="特码", selection="01", amount="10"),
            OrderItemCreate(bet_type="连肖", selection="鼠,牛", amount="20"),
            OrderItemCreate(bet_type="平特一肖", selection="马", amount="30"),
        ],
    )

    report = OrderAnalysisService(session_factory).get_workbench(region="澳门").report_text

    assert "当前筛选范围：澳门" in report
    assert "订单数量：1" in report
    assert "明细数量：3" in report
    assert "总投注金额：60.00" in report
    assert "下注最多的号码 Top 5" in report
    assert "连肖出现最多的生肖 Top 5" in report
    assert "平特一肖投注金额 Top 5" in report
    assert "当前不计算赔付金额" in report
    assert "余额、返水、佣金" in report
    assert "盈亏字段暂不代表真实结算盈亏" in report


def test_order_analysis_service_does_not_write_database(session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, region="澳门", amount="10")
    with session_factory() as session:
        before = (
            session.scalar(select(func.count(Order.id))),
            session.scalar(select(func.count(OrderItem.id))),
        )

    OrderAnalysisService(session_factory).get_workbench()

    with session_factory() as session:
        after = (
            session.scalar(select(func.count(Order.id))),
            session.scalar(select(func.count(OrderItem.id))),
        )
    assert after == before
