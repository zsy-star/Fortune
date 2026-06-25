from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QMessageBox

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.log_service import LogService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from ui.app_events import app_events
from ui.pages.operation_log_page import OperationLogPage
from ui.pages.order_analysis_page import OrderAnalysisPage
from ui.pages.order_detail_page import OrderDetailPage
from ui.pages.overview_page import OverviewPage
from ui.pages.settlement_ledger_page import SettlementLedgerPage
from ui.main_window import MainWindow
from ui.windows.record_order_window import RecordOrderWindow


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(service: OrderService, index: int):
    return service.create_order(
        OrderCreate(
            customer_name="林林",
            channel="微信",
            region="澳门",
            raw_text=f"01/10 #{index}",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )


def test_record_save_event_refreshes_open_order_and_log_pages(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    log_service = LogService(session_factory)
    overview = OverviewPage(order_service=order_service)
    analysis = OrderAnalysisPage(order_service=order_service)
    detail = OrderDetailPage(order_service=order_service, log_service=log_service)
    logs = OperationLogPage(log_service=log_service)
    window = RecordOrderWindow(
        order_intake_service=OrderIntakeService(session_factory),
        settings_service=SettingsService(session_factory),
    )
    orders_spy = QSignalSpy(app_events.orders_changed)
    logs_spy = QSignalSpy(app_events.logs_changed)

    assert overview._lbl_total_orders.text() == "订单总数: 0"
    assert detail._table.rowCount() == 0
    assert logs._total == 0

    window._input_text.setPlainText("01/10")
    window._do_parse()
    with (
        patch(
            "ui.windows.record_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch("ui.windows.record_order_window.QMessageBox.information"),
    ):
        window._on_save_order()

    assert orders_spy.count() == 1
    assert logs_spy.count() == 1
    assert overview._lbl_total_orders.text() == "订单总数: 1"
    assert analysis._snapshots["all"].summary.total_order_count == 1
    assert detail._table.rowCount() == 1
    assert logs._total == 1
    assert overview._btn_refresh.isEnabled()
    assert analysis._btn_refresh.isEnabled()
    assert detail._btn_refresh.isEnabled()


def test_order_detail_event_refresh_preserves_filters_search_and_page(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    for index in range(21):
        create_order(service, index)
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))
    page._cmb_region.setCurrentText("澳门")
    page._cmb_declarer.setCurrentText("林林")
    page._cmb_status.setCurrentText("active")
    page._edit_channel.setText("微信")
    page._edit_order_no.setText("ORD")
    page._on_query()
    page._next_page()
    assert page._page == 2

    app_events.orders_changed.emit()

    assert page._page == 2
    assert page._cmb_region.currentText() == "澳门"
    assert page._cmb_declarer.currentText() == "林林"
    assert page._cmb_status.currentText() == "active"
    assert page._edit_channel.text() == "微信"
    assert page._edit_order_no.text() == "ORD"
    assert page._table.rowCount() == 1


def test_order_detail_auto_refresh_failure_is_safe(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )
    with patch.object(page, "reload_data", side_effect=RuntimeError("refresh boom")):
        app_events.orders_changed.emit()

    assert "自动刷新失败" in page._status_label.text()
    assert "refresh boom" in page._status_label.text()


def test_log_and_settlement_pages_subscribe_to_change_events(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    logs = OperationLogPage(log_service=LogService(session_factory))
    ledger = SettlementLedgerPage(
        order_service=order_service,
        settlement_service=SettlementService(session_factory),
    )

    with (
        patch.object(logs, "reload_data", wraps=logs.reload_data) as reload_logs,
        patch.object(ledger, "reload_data", wraps=ledger.reload_data) as reload_settlements,
    ):
        app_events.logs_changed.emit()
        app_events.settlements_changed.emit()

    reload_logs.assert_called_once_with()
    reload_settlements.assert_called_once_with()


def test_database_restore_event_reloads_main_window_pages(monkeypatch) -> None:
    app()
    window = MainWindow()
    calls: list[str] = []
    try:
        for index in range(window._stack.count()):
            page = window._stack.widget(index)
            if callable(getattr(page, "reload_data", None)):
                monkeypatch.setattr(
                    page,
                    "reload_data",
                    lambda page=page: calls.append(type(page).__name__),
                )

        app_events.app_data_reloaded.emit()

        assert "OverviewPage" in calls
        assert "OrderAnalysisPage" in calls
        assert "OrderDetailPage" in calls
        assert "DrawHistoryPage" in calls
        assert "OperationLogPage" in calls
        assert "SettlementLedgerPage" in calls
    finally:
        window.close()
        window.deleteLater()


def test_page_event_handlers_report_unexpected_refresh_failures(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    overview = OverviewPage(order_service=order_service)
    analysis = OrderAnalysisPage(order_service=order_service)
    logs = OperationLogPage(log_service=LogService(session_factory))
    ledger = SettlementLedgerPage(
        order_service=order_service,
        settlement_service=SettlementService(session_factory),
    )

    with patch.object(overview, "reload_data", side_effect=RuntimeError("overview boom")):
        overview._on_orders_changed()
    with patch.object(analysis, "reload_data", side_effect=RuntimeError("analysis boom")):
        analysis._on_orders_changed()
    with patch.object(logs, "reload_data", side_effect=RuntimeError("logs boom")):
        logs._on_logs_changed()
    with patch.object(ledger, "reload_data", side_effect=RuntimeError("ledger boom")):
        ledger._on_settlements_changed()

    assert "overview boom" in overview._lbl_total_orders.text()
    assert "analysis boom" in analysis._report_view.toPlainText()
    assert "logs boom" in logs._lbl_total.text()
    assert "ledger boom" in ledger._lbl_total.text()
