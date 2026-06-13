from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService
from ui.pages.order_analysis_page import OrderAnalysisPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(
    service: OrderService,
    *,
    customer: str,
    region: str,
    amount: str,
    status: str | None = None,
    items: list[OrderItemCreate] | None = None,
):
    order = service.create_order(
        OrderCreate(
            customer_name=customer,
            channel="微信",
            region=region,
            raw_text=f"{customer}{amount}",
            source="test",
            items=items or [OrderItemCreate(bet_type="特码", selection="1", amount=amount)],
        )
    )
    if status is not None:
        from models import Order

        with service._session_factory() as session:
            saved = session.get(Order, order.id)
            assert saved is not None
            saved.status = status
            session.commit()
    return order


def _table_rows(page: OrderAnalysisPage) -> list[tuple[str, str, str, str]]:
    rows = []
    for row in range(page._table.rowCount()):
        rows.append(tuple(page._table.item(row, col).text() for col in range(4)))
    return rows


def test_order_analysis_page_empty_database_shows_zero_state(session_factory) -> None:
    app()
    page = OrderAnalysisPage(order_service=OrderService(session_factory))

    rows = _table_rows(page)
    assert ("总计", "全部订单", "0", "0.00") in rows
    assert ("总计", "平均订单金额", "0", "0.00") in rows
    assert "暂无订单数据" in page._report_view.toPlainText()


def test_order_analysis_page_loads_real_region_status_bet_type_and_recent_orders(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    macau = create_order(
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
    hk = create_order(
        service,
        customer="香港客",
        region="香港",
        amount="20",
        status="settled",
        items=[OrderItemCreate(bet_type="包半波", selection="红单", amount="20")],
    )

    page = OrderAnalysisPage(order_service=service)
    rows = _table_rows(page)

    assert ("总计", "全部订单", "2", "50.00") in rows
    assert ("总计", "平均订单金额", "2", "25.00") in rows
    assert ("地区", "澳门", "1", "30.00") in rows
    assert ("地区", "香港", "1", "20.00") in rows
    assert ("状态", "active", "1", "30.00") in rows
    assert ("状态", "settled", "1", "20.00") in rows
    assert ("投注类型", "特码", "1", "30.00") in rows
    assert ("投注类型", "包半波", "1", "20.00") in rows
    report = page._report_view.toPlainText()
    assert macau.order_no in report
    assert hk.order_no in report


def test_order_analysis_page_refresh_reads_latest_database_state(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    page = OrderAnalysisPage(order_service=service)
    assert ("总计", "全部订单", "0", "0.00") in _table_rows(page)

    order = create_order(service, customer="刷新客", region="澳门", amount="10")
    page.reload_data()

    rows = _table_rows(page)
    assert ("总计", "全部订单", "1", "10.00") in rows
    assert ("地区", "澳门", "1", "10.00") in rows
    assert order.order_no in page._report_view.toPlainText()


def test_order_analysis_page_uses_service_only_not_database_or_web_clients() -> None:
    src = inspect.getsource(OrderAnalysisPage)
    assert "OrderService" in src
    assert "sqlalchemy" not in src.lower()
    assert "Session" not in src
    assert "OrderRepository" not in src
    assert "sqlite" not in src.lower()
    assert "fortune.db" not in src.lower()
    assert "49wz777" not in src.lower()
