from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QItemSelectionModel
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
    assert page._table.item(0, 7).text() == "张三"
    assert page._table.item(0, 4).text() == "30.00"

    page._table.selectRow(0)
    page._on_selection_changed()
    assert result.order_no in page._detail_info.text()
    assert page._item_table.rowCount() == 2
    assert page._item_table.item(0, 2).text() == "10.00"
    assert LogService(session_factory).count_logs(module="订单详情", action="查看订单") == 1


def test_order_detail_business_layout_and_core_entries(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )

    headers = [page._table.horizontalHeaderItem(index).text() for index in range(page._table.columnCount())]
    assert headers == [
        "订单信息",
        "复式类型",
        "计算方式",
        "金额",
        "订单总额",
        "是否自定义",
        "订单序号",
        "申报人",
        "中奖情况",
        "中奖金额",
        "备注",
    ]
    assert page._btn_query.isEnabled()
    assert page._btn_refresh.isEnabled()
    assert page._btn_export_excel.isEnabled()
    assert not page._btn_preview.isEnabled()
    assert not page._btn_void.isEnabled()


def test_order_detail_unavailable_actions_are_explicitly_disabled(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )

    buttons = [
        page._btn_clear_orders,
        page._btn_import_orders,
        page._btn_filter_prize,
        page._btn_combined_prize,
        page._btn_reset_draw,
        page._btn_expand_prize,
    ]
    assert all(not button.isEnabled() for button in buttons)
    assert all("暂未开放" in button.toolTip() for button in buttons)
    assert not page._cmb_bet_type.isEnabled()
    assert not page._cmb_winning.isEnabled()


def test_order_detail_selected_and_current_totals(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, customer="甲")
    create_order(service, customer="乙")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))

    assert page._lbl_current_total.text() == "当前订单总额：60.00"
    page._table.selectRow(0)
    selection = page._table.selectionModel()
    selection.select(
        page._table.model().index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )

    assert page._lbl_selected_total.text() == "选中总额：60.00"
    assert page._lbl_order_state.text() == "订单状态：未结算"


def test_order_detail_draw_area_has_empty_placeholders(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )

    for region in ("澳门", "香港"):
        placeholder = page._draw_widgets[region]["placeholder"]
        assert placeholder.text() == "暂无开奖数据"


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
