from __future__ import annotations

import inspect
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from schemas.excel_export_schema import ExcelExportResult
from services.log_service import LogService
from services.order_service import OrderService
from ui.pages.operation_log_page import OperationLogPage
from ui.pages.order_detail_page import OrderDetailPage
from ui.pages.settlement_ledger_page import SettlementLedgerPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


class FakeExcelExportService:
    def __init__(self, result: ExcelExportResult | None = None, error: Exception | None = None):
        self.result = result or ExcelExportResult(
            export_path=Path("unused") / "export.xlsx",
            file_name="export.xlsx",
            report_type="test",
            row_count=3,
            created_at=datetime(2026, 6, 14, 10, 0, 0),
            size_bytes=2048,
            filters={},
        )
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def _record(self, method: str, kwargs: dict) -> ExcelExportResult:
        self.calls.append((method, kwargs))
        if self.error is not None:
            raise self.error
        return self.result

    def export_orders(self, **kwargs) -> ExcelExportResult:
        return self._record("export_orders", kwargs)

    def export_settlement_ledger(self, **kwargs) -> ExcelExportResult:
        return self._record("export_settlement_ledger", kwargs)

    def export_operation_logs(self, **kwargs) -> ExcelExportResult:
        return self._record("export_operation_logs", kwargs)


def make_result(tmp_path, file_name: str = "report.xlsx") -> ExcelExportResult:
    return ExcelExportResult(
        export_path=tmp_path / file_name,
        file_name=file_name,
        report_type="test",
        row_count=5,
        created_at=datetime(2026, 6, 14, 10, 0, 0),
        size_bytes=4096,
        filters={},
    )


def test_export_buttons_exist_on_target_pages(session_factory) -> None:
    app()
    fake = FakeExcelExportService()

    order_page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        excel_export_service=fake,
    )
    ledger_page = SettlementLedgerPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        excel_export_service=fake,
    )
    log_page = OperationLogPage(
        log_service=LogService(session_factory),
        excel_export_service=fake,
    )

    assert order_page._btn_export_excel.text() == "导出 Excel"
    assert ledger_page._btn_export_excel.text() == "导出 Excel"
    assert log_page._btn_export_excel.text() == "导出 Excel"


def test_cancel_directory_selection_does_not_call_export_service(session_factory, tmp_path) -> None:
    app()
    fake = FakeExcelExportService(make_result(tmp_path))
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        excel_export_service=fake,
    )

    with patch("ui.pages.order_detail_page.QFileDialog.getExistingDirectory", return_value=""):
        page._on_export_excel()

    assert fake.calls == []
    assert list(tmp_path.glob("*.xlsx")) == []


def test_order_export_button_calls_export_orders(session_factory, tmp_path) -> None:
    app()
    fake = FakeExcelExportService(make_result(tmp_path, "orders.xlsx"))
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        excel_export_service=fake,
    )
    page._edit_order_no.setText("ORD-001")
    page._cmb_status.setCurrentText("pending")
    page._cmb_region.setCurrentText("澳门")

    with (
        patch("ui.pages.order_detail_page.QFileDialog.getExistingDirectory", return_value=str(tmp_path)),
        patch("ui.pages.order_detail_page.QMessageBox.information") as info,
    ):
        page._on_export_excel()

    assert fake.calls == [
        (
            "export_orders",
            {
                "region": "澳门",
                "status": "pending",
                "start_date": None,
                "end_date": None,
                "keyword": "ORD-001",
                "include_voided": False,
                "output_dir": str(tmp_path),
            },
        )
    ]
    info.assert_called_once()
    assert "导出成功" in info.call_args.args[2]
    assert "orders.xlsx" in info.call_args.args[2]
    assert "行数：5" in info.call_args.args[2]


def test_settlement_ledger_export_button_calls_export_settlement_ledger(session_factory, tmp_path) -> None:
    app()
    fake = FakeExcelExportService(make_result(tmp_path, "ledger.xlsx"))
    page = SettlementLedgerPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        excel_export_service=fake,
    )
    page._keyword.setText("1001")
    page._cmb_region.setCurrentText("香港")

    with (
        patch("ui.pages.settlement_ledger_page.QFileDialog.getExistingDirectory", return_value=str(tmp_path)),
        patch("ui.pages.settlement_ledger_page.QMessageBox.information") as info,
    ):
        page._on_export_excel()

    assert fake.calls == [
        (
            "export_settlement_ledger",
            {
                "region": "香港",
                "keyword": "1001",
                "start_date": None,
                "end_date": None,
                "output_dir": str(tmp_path),
            },
        )
    ]
    info.assert_called_once()
    assert "导出成功" in info.call_args.args[2]


def test_operation_log_export_button_calls_export_operation_logs(session_factory, tmp_path) -> None:
    app()
    fake = FakeExcelExportService(make_result(tmp_path, "logs.xlsx"))
    page = OperationLogPage(
        log_service=LogService(session_factory),
        excel_export_service=fake,
    )
    page._module.setText("order")
    page._action.setText("void")
    page._operator.setText("system")
    page._related_type.setText("order")
    page._keyword.setText("success")

    with (
        patch("ui.pages.operation_log_page.QFileDialog.getExistingDirectory", return_value=str(tmp_path)),
        patch("ui.pages.operation_log_page.QMessageBox.information") as info,
    ):
        page._on_export_excel()

    assert fake.calls == [
        (
            "export_operation_logs",
            {
                "module": "order",
                "action": "void",
                "operator": "system",
                "related_type": "order",
                "keyword": "success",
                "start_date": None,
                "end_date": None,
                "output_dir": str(tmp_path),
            },
        )
    ]
    info.assert_called_once()
    assert "导出成功" in info.call_args.args[2]


def test_export_failure_shows_warning_without_crashing(session_factory, tmp_path) -> None:
    app()
    fake = FakeExcelExportService(make_result(tmp_path), RuntimeError("disk full"))
    page = OperationLogPage(
        log_service=LogService(session_factory),
        excel_export_service=fake,
    )

    with (
        patch("ui.pages.operation_log_page.QFileDialog.getExistingDirectory", return_value=str(tmp_path)),
        patch("ui.pages.operation_log_page.QMessageBox.warning") as warning,
    ):
        page._on_export_excel()

    warning.assert_called_once()
    assert "导出失败" in warning.call_args.args[2]
    assert "disk full" in warning.call_args.args[2]
    assert fake.calls[0][0] == "export_operation_logs"


def test_excel_export_ui_uses_export_service_only() -> None:
    for page_class in (OrderDetailPage, SettlementLedgerPage, OperationLogPage):
        source = inspect.getsource(page_class)
        assert "ExcelExportService" in source
        assert "openpyxl" not in source
        assert "Workbook" not in source
        assert "Repository" not in source
        assert "sqlite" not in source.lower()
        assert "data/fortune.db" not in source
