from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService
from ui.pages.overview_page import OverviewPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(
    service: OrderService,
    *,
    customer: str,
    region: str,
    amount: str,
    items: list[OrderItemCreate] | None = None,
):
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel="微信",
            region=region,
            raw_text=f"{customer}{amount}",
            source="test",
            items=items or [OrderItemCreate(bet_type="特码", selection="1", amount=amount)],
        )
    )


def test_overview_page_empty_database_shows_zero_state(session_factory) -> None:
    app()
    page = OverviewPage(order_service=OrderService(session_factory))

    assert page._lbl_total_orders.text() == "订单总数: 0"
    assert page._lbl_today_orders.text() == "今日订单数: 0"
    assert page._lbl_total_amount.text() == "总投注金额: 0.00"
    assert page._lbl_today_amount.text() == "今日投注金额: 0.00"
    assert page._lbl_macau_orders.text() == "澳门订单数: 0"
    assert page._lbl_hk_orders.text() == "香港订单数: 0"
    assert "暂无订单数据" in page._recent_orders_view.toPlainText()


def test_overview_page_loads_real_order_statistics_and_recent_orders(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(
        service,
        customer="澳门客",
        region="澳门",
        amount="30",
        items=[
            OrderItemCreate(bet_type="特码", selection="1", amount="10"),
            OrderItemCreate(bet_type="特码", selection="2", amount="10"),
            OrderItemCreate(bet_type="特码", selection="3", amount="10"),
        ],
    )
    hk = create_order(service, customer="香港客", region="香港", amount="20")

    page = OverviewPage(order_service=service)

    assert page._lbl_total_orders.text() == "订单总数: 2"
    assert page._lbl_today_orders.text() == "今日订单数: 2"
    assert page._lbl_total_amount.text() == "总投注金额: 50.00"
    assert page._lbl_today_amount.text() == "今日投注金额: 50.00"
    assert page._lbl_macau_orders.text() == "澳门订单数: 1"
    assert page._lbl_hk_orders.text() == "香港订单数: 1"
    assert page._lbl_pending_orders.text() == "待处理订单数: 2"
    assert hk.order_no in page._recent_orders_view.toPlainText()
    assert "20.00" in page._recent_orders_view.toPlainText()
    assert page._snapshots["all"].amounts == (50.0,)


def test_overview_page_refresh_reads_latest_database_state(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    page = OverviewPage(order_service=service)
    assert page._lbl_total_orders.text() == "订单总数: 0"

    order = create_order(service, customer="刷新客", region="澳门", amount="10")
    page.reload_data()

    assert page._lbl_total_orders.text() == "订单总数: 1"
    assert page._lbl_total_amount.text() == "总投注金额: 10.00"
    assert order.order_no in page._recent_orders_view.toPlainText()


def test_overview_page_uses_service_only_not_database_or_web_clients() -> None:
    src = inspect.getsource(OverviewPage)
    assert "OrderService" in src
    assert "sqlalchemy" not in src.lower()
    assert "Session" not in src
    assert "OrderRepository" not in src
    assert "sqlite" not in src.lower()
    assert "fortune.db" not in src.lower()
    assert "49wz777" not in src.lower()
