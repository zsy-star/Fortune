from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.log_service import LogService
from services.order_service import OrderService
from ui.pages.operation_log_page import OperationLogPage
from ui.pages.order_detail_page import OrderDetailPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(service: OrderService, *, customer: str = "张三", region: str = "澳门", channel: str = "微信"):
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel=channel,
            region=region,
            raw_text="1各10\n2各20",
            source="test",
            items=[
                OrderItemCreate(bet_type="特码", selection="1", amount="10"),
                OrderItemCreate(bet_type="特码", selection="2", amount="20"),
            ],
        )
    )


def test_order_detail_page_empty_state(session_factory) -> None:
    app()
    page = OrderDetailPage(order_service=OrderService(session_factory), log_service=LogService(session_factory))
    page.reload_data()
    assert page._table.rowCount() == 0
    assert "暂无订单数据" in page._status_label.text()
    assert all(not button.isEnabled() for button in page.findChildren(type(page._btn_prev)) if button.objectName() == "toolBtn")


def test_order_detail_page_loads_filters_and_details(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    result = create_order(service)
    create_order(service, customer="李四", region="香港", channel="现金")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))

    assert page._table.rowCount() == 2
    page._edit_customer.setText("张")
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 3).text() == "张三"
    assert page._table.item(0, 5).text() == "30.00"

    page._table.selectRow(0)
    page._on_selection_changed()
    assert result.order_no in page._detail_info.text()
    assert page._item_table.rowCount() == 2
    assert page._item_table.item(0, 2).text() == "10.00"
    assert LogService(session_factory).count_logs(module="订单详情", action="查看订单") == 1


def test_order_detail_page_pagination_state(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    for idx in range(21):
        create_order(service, customer=f"客户{idx}")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))
    assert page._table.rowCount() == 20
    assert not page._btn_prev.isEnabled()
    assert page._btn_next.isEnabled()
    page._next_page()
    assert page._table.rowCount() == 1


def test_operation_log_page_empty_state(session_factory) -> None:
    app()
    page = OperationLogPage(log_service=LogService(session_factory))
    assert page._table.rowCount() == 0
    assert page._lbl_total.text() == "暂无操作日志"


def test_operation_log_page_loads_filters_reset_and_paging(session_factory) -> None:
    app()
    service = LogService(session_factory)
    for idx in range(22):
        service.create_log(
            module="draw_sync" if idx % 2 == 0 else "order",
            action="success",
            description=f"同步日志 {idx}",
            related_type="draw",
            related_id=idx,
        )
    page = OperationLogPage(log_service=service)
    assert page._table.rowCount() == 20
    assert "17203" not in page._lbl_total.text()
    assert page._btn_next.isEnabled()
    page._module.setText("draw")
    page._on_query()
    assert page._total == 11
    page._keyword.setText("日志 2")
    page._on_query()
    assert page._total >= 1
    page._on_reset()
    assert page._total == 22
    assert page._table.item(0, 3).toolTip()


def test_operation_log_page_date_validation_and_clear_disabled(session_factory) -> None:
    app()
    page = OperationLogPage(log_service=LogService(session_factory))
    page._start_date.setDate(QDate(2026, 1, 2))
    page._end_date.setDate(QDate(2026, 1, 1))
    page.reload_data()
    assert "开始日期不能晚于结束日期" in page._lbl_total.text()
    page._on_clear_disabled()
    assert "暂未开放" in page._lbl_total.text()
