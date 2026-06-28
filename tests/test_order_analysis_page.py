from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QRadioButton

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService
from ui.app_events import app_events
from ui.pages.order_analysis_page import OrderAnalysisPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(
    service: OrderService,
    *,
    region: str,
    items: list[OrderItemCreate] | None = None,
):
    return service.create_order(
        OrderCreate(
            customer_name="page-test",
            channel="test",
            region=region,
            raw_text="page analysis",
            source="test",
            items=items or [OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )


def _headers(page: OrderAnalysisPage) -> list[str]:
    return [page._table.horizontalHeaderItem(col).text() for col in range(page._table.columnCount())]


def _table_rows(page: OrderAnalysisPage) -> list[tuple[str, str, str, str]]:
    rows = []
    for row in range(page._table.rowCount()):
        rows.append(tuple(page._table.item(row, col).text() for col in range(4)))
    return rows


def test_order_analysis_page_creates_workbench_with_required_controls(session_factory) -> None:
    app()
    page = OrderAnalysisPage(order_service=OrderService(session_factory))

    assert page._table.rowCount() == 49
    assert _headers(page) == ["号码", "下注数", "盈亏", "ID"]
    radio_texts = [radio.text() for radio in page.findChildren(QRadioButton)]
    assert ["全部订单", "只看澳门", "只看香港"] == radio_texts
    assert page._freq_canvas.figure.axes[0].get_title() == "连肖中生肖出现频率"
    assert page._bet_canvas.figure.axes[0].get_title() == "平特一肖投注情况"
    assert "订单分析报告（仅参考）" in page._report_view.toPlainText()


def test_order_analysis_page_loads_number_table_charts_and_report(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(
        service,
        region="澳门",
        items=[
            OrderItemCreate(bet_type="特码", selection="01", amount="10"),
            OrderItemCreate(bet_type="连肖", selection="鼠,牛", amount="20"),
            OrderItemCreate(bet_type="平特一肖", selection="马", amount="30"),
        ],
    )

    page = OrderAnalysisPage(order_service=service)
    rows = _table_rows(page)
    report = page._report_view.toPlainText()

    assert ("马01", "10.00", "—", "1") in rows
    assert "订单数量：1" in report
    assert "明细数量：3" in report
    assert "总投注金额：60.00" in report
    assert "当前不计算赔付金额" in report


def test_order_analysis_page_region_filter_refreshes_all_sections(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, region="澳门", items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")])
    create_order(service, region="香港", items=[OrderItemCreate(bet_type="特码", selection="02", amount="20")])

    page = OrderAnalysisPage(order_service=service)
    page._filter_group.button(1).click()
    macau_rows = _table_rows(page)
    assert ("马01", "10.00", "—", "1") in macau_rows
    assert ("蛇02", "0.00", "—", "2") in macau_rows
    assert "当前筛选范围：澳门" in page._report_view.toPlainText()

    page._filter_group.button(2).click()
    hk_rows = _table_rows(page)
    assert ("马01", "0.00", "—", "1") in hk_rows
    assert ("蛇02", "20.00", "—", "2") in hk_rows
    assert "当前筛选范围：香港" in page._report_view.toPlainText()


def test_order_analysis_page_orders_changed_refreshes(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    page = OrderAnalysisPage(order_service=service)
    assert ("马01", "0.00", "—", "1") in _table_rows(page)

    create_order(service, region="澳门", items=[OrderItemCreate(bet_type="特码", selection="01", amount="15")])
    app_events.orders_changed.emit()

    assert ("马01", "15.00", "—", "1") in _table_rows(page)
    assert page._snapshots["all"].summary.total_order_count == 1


def test_order_analysis_page_uses_analysis_service_only_not_database_or_settlement_clients() -> None:
    src = inspect.getsource(OrderAnalysisPage)

    assert "OrderAnalysisService" in src
    assert "sqlalchemy" not in src.lower()
    assert "Session" not in src
    assert "OrderRepository" not in src
    assert "sqlite" not in src.lower()
    assert "fortune.db" not in src.lower()
    assert "SettlementService" not in src
    assert "void_order" not in src
    assert "create_order(" not in src
