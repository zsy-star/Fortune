from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from sqlalchemy import func, select

from models import Order
from services.log_service import LogService
from services.order_import_service import OrderImportService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from ui.app_events import app_events
from ui.dialogs.order_import_dialog import OrderImportDialog
from ui.pages.order_detail_page import OrderDetailPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def count_orders(session_factory) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count(Order.id))) or 0)


def count_import_logs(session_factory) -> int:
    return LogService(session_factory).count_logs(action="order/import")


def test_order_import_service_txt_reads_non_empty_lines() -> None:
    service = OrderImportService()

    result = service.extract_txt_lines("\n01各10\n  \n02各5\n")

    assert result.lines == ["01各10", "02各5"]
    assert result.skipped_count == 2


def test_order_import_service_csv_with_header_reads_text_column() -> None:
    service = OrderImportService()

    result = service.extract_csv_lines("name,订单内容\n甲,01各10\n乙,无效文本\n")

    assert result.lines == ["01各10", "无效文本"]


def test_order_import_service_csv_without_header_uses_first_column() -> None:
    service = OrderImportService()

    result = service.extract_csv_lines("01各10,备注\n02各5,备注\n")

    assert result.lines == ["01各10", "02各5"]


def test_order_import_service_rejects_unsupported_file_type(tmp_path) -> None:
    service = OrderImportService()
    path = tmp_path / "orders.xlsx"
    path.write_text("01各10", encoding="utf-8")

    result = service.read_file(path)

    assert result.lines == []
    assert "当前仅支持 txt/csv" in result.error


def test_order_import_service_preview_success_and_failure_rows() -> None:
    service = OrderImportService()

    preview = service.preview_lines(["01各10", "明显无效"], region_mode="澳门")

    assert preview.total_count == 2
    assert preview.success_count == 1
    assert preview.failure_count == 1
    assert preview.rows[0].success is True
    assert preview.rows[0].region == "澳门"
    assert preview.rows[0].bet_type_summary == "纯数字"
    assert preview.rows[0].amount_total == 10
    assert preview.rows[0].item_count == 1
    assert preview.rows[1].success is False
    assert preview.rows[1].error


def test_order_import_dialog_initializes_with_confirm_button_disabled() -> None:
    app()
    dialog = OrderImportDialog(import_service=OrderImportService())

    assert dialog.windowTitle() == "订单导入预览"
    assert dialog._btn_select_file.text() == "选择文件"
    assert dialog._btn_preview.text() == "重新解析"
    assert dialog._btn_confirm_import.text() == "确认导入成功行"
    assert not dialog._btn_confirm_import.isEnabled()
    assert dialog._btn_copy_errors.text() == "复制错误报告"
    assert dialog._btn_close.text() == "关闭"
    assert "当前不会写数据库" in dialog._stats_label.text()


def test_order_import_dialog_loads_txt_and_updates_preview_table(tmp_path) -> None:
    app()
    path = tmp_path / "orders.txt"
    path.write_text("01各10\n\n明显无效\n", encoding="utf-8")
    dialog = OrderImportDialog(import_service=OrderImportService())

    dialog.load_file(str(path))

    assert dialog._path_edit.text() == str(path)
    assert dialog._table.rowCount() == 2
    assert dialog._table.item(0, 3).text() == "成功"
    assert dialog._table.item(1, 3).text() == "失败"
    assert dialog._table.item(1, 7).text()
    assert "总行数：2" in dialog._stats_label.text()
    assert "解析成功：1" in dialog._stats_label.text()
    assert "解析失败：1" in dialog._stats_label.text()
    assert "跳过空行：1" in dialog._stats_label.text()
    assert dialog._btn_confirm_import.isEnabled()


def test_order_import_dialog_loads_csv_header_and_no_header(tmp_path) -> None:
    app()
    dialog = OrderImportDialog(import_service=OrderImportService())
    header_path = tmp_path / "orders_header.csv"
    header_path.write_text("备注,order_text\nA,01各10\n", encoding="utf-8")
    no_header_path = tmp_path / "orders_no_header.csv"
    no_header_path.write_text("02各5,备注\n", encoding="utf-8")

    dialog.load_file(str(header_path))
    assert dialog._raw_text.toPlainText() == "01各10"
    assert dialog._table.item(0, 3).text() == "成功"

    dialog.load_file(str(no_header_path))
    assert dialog._raw_text.toPlainText() == "02各5"
    assert dialog._table.item(0, 3).text() == "成功"


def test_order_import_dialog_unsupported_type_shows_error(tmp_path) -> None:
    app()
    dialog = OrderImportDialog(import_service=OrderImportService())
    path = tmp_path / "orders.xlsx"
    path.write_text("01各10", encoding="utf-8")

    with patch("ui.dialogs.order_import_dialog.QMessageBox.warning") as warning:
        dialog.load_file(str(path))

    assert warning.called
    assert "当前仅支持 txt/csv" in dialog._stats_label.text()
    assert dialog._table.rowCount() == 0


def test_order_import_dialog_copy_error_report_handles_errors_and_no_errors(tmp_path) -> None:
    app()
    dialog = OrderImportDialog(import_service=OrderImportService())
    path = tmp_path / "orders.txt"
    path.write_text("01各10\n明显无效\n", encoding="utf-8")
    dialog.load_file(str(path))

    dialog._btn_copy_errors.click()
    assert "明显无效" in QApplication.clipboard().text()
    assert "已复制错误报告" in dialog._stats_label.text()

    dialog._raw_text.setPlainText("01各10")
    dialog._on_preview()
    dialog._btn_copy_errors.click()
    assert QApplication.clipboard().text() == "当前没有解析失败行"


def test_order_import_preview_does_not_write_database(session_factory, tmp_path) -> None:
    app()
    before = count_orders(session_factory)
    dialog = OrderImportDialog(import_service=OrderImportService())
    path = tmp_path / "orders.txt"
    path.write_text("01各10\n02各5\n", encoding="utf-8")

    dialog.load_file(str(path))
    dialog._on_preview()
    dialog._btn_copy_errors.click()

    assert count_orders(session_factory) == before


def test_order_import_confirm_cancel_does_not_write_database(session_factory, tmp_path) -> None:
    app()
    service = OrderImportService(order_intake_service=OrderIntakeService(session_factory))
    dialog = OrderImportDialog(import_service=service)
    dialog._region_combo.setCurrentText("澳门")
    path = tmp_path / "orders.txt"
    path.write_text("01各10\n", encoding="utf-8")
    dialog.load_file(str(path))
    before = count_orders(session_factory)

    with patch(
        "ui.dialogs.order_import_dialog.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    ) as question:
        dialog._btn_confirm_import.click()

    assert question.called
    assert count_orders(session_factory) == before
    assert "已取消确认导入" in dialog._stats_label.text()


def test_order_import_confirm_saves_only_success_rows_and_writes_log(
    session_factory, tmp_path
) -> None:
    app()
    service = OrderImportService(order_intake_service=OrderIntakeService(session_factory))
    dialog = OrderImportDialog(import_service=service)
    dialog._region_combo.setCurrentText("澳门")
    path = tmp_path / "orders.txt"
    path.write_text("01各10\n\n明显无效\n02各5\n", encoding="utf-8")
    dialog.load_file(str(path))
    before = count_orders(session_factory)
    before_logs = count_import_logs(session_factory)
    events = {"orders": 0, "logs": 0}

    def on_orders():
        events["orders"] += 1

    def on_logs():
        events["logs"] += 1

    app_events.orders_changed.connect(on_orders)
    app_events.logs_changed.connect(on_logs)
    try:
        with patch(
            "ui.dialogs.order_import_dialog.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch("ui.dialogs.order_import_dialog.QMessageBox.information"):
            dialog._btn_confirm_import.click()
    finally:
        app_events.orders_changed.disconnect(on_orders)
        app_events.logs_changed.disconnect(on_logs)

    assert count_orders(session_factory) == before + 2
    assert count_import_logs(session_factory) == before_logs + 1
    assert dialog._table.item(0, 8).text() == "已导入"
    assert dialog._table.item(1, 8).text() == "未导入，解析失败"
    assert dialog._table.item(2, 8).text() == "已导入"
    assert "本次应导入：2" in dialog._stats_label.text()
    assert "成功导入：2" in dialog._stats_label.text()
    assert "保存失败：0" in dialog._stats_label.text()
    assert "跳过失败解析行：1" in dialog._stats_label.text()
    assert not dialog._btn_confirm_import.isEnabled()
    assert events == {"orders": 1, "logs": 1}

    logs = LogService(session_factory).list_logs(action="order/import")
    assert logs
    description = logs[0].description
    assert "total_rows=3" in description
    assert "parse_success=2" in description
    assert "parse_failed=1" in description
    assert "imported=2" in description
    assert "save_failed=0" in description
    assert "skipped_empty=1" in description


def test_order_import_confirm_all_success_and_prevents_duplicate_click(
    session_factory, tmp_path
) -> None:
    app()
    service = OrderImportService(order_intake_service=OrderIntakeService(session_factory))
    dialog = OrderImportDialog(import_service=service)
    dialog._region_combo.setCurrentText("澳门")
    path = tmp_path / "orders.txt"
    path.write_text("01各10\n02各5\n", encoding="utf-8")
    dialog.load_file(str(path))

    with patch(
        "ui.dialogs.order_import_dialog.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ), patch("ui.dialogs.order_import_dialog.QMessageBox.information"):
        dialog._btn_confirm_import.click()
        after_first = count_orders(session_factory)
        dialog._btn_confirm_import.click()

    assert count_orders(session_factory) == after_first
    assert "成功导入：2" in dialog._stats_label.text()
    assert not dialog._btn_confirm_import.isEnabled()


def test_order_import_reparse_resets_import_state(session_factory, tmp_path) -> None:
    app()
    service = OrderImportService(order_intake_service=OrderIntakeService(session_factory))
    dialog = OrderImportDialog(import_service=service)
    dialog._region_combo.setCurrentText("澳门")
    path = tmp_path / "orders.txt"
    path.write_text("01各10\n", encoding="utf-8")
    dialog.load_file(str(path))

    with patch(
        "ui.dialogs.order_import_dialog.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ), patch("ui.dialogs.order_import_dialog.QMessageBox.information"):
        dialog._btn_confirm_import.click()

    assert not dialog._btn_confirm_import.isEnabled()
    dialog._raw_text.setPlainText("02各5")
    dialog._on_preview()
    assert dialog._btn_confirm_import.isEnabled()
    assert dialog._table.item(0, 8).text() == "未导入"


def test_order_import_save_failure_is_shown_without_crashing() -> None:
    app()

    class BrokenIntake:
        _session_factory = None

        def preview_raw_text(self, *args, **kwargs):
            raise RuntimeError("模拟保存失败")

    class FakeLogService:
        def create_log(self, **kwargs):
            return SimpleNamespace(id=1)

    service = OrderImportService(order_intake_service=BrokenIntake(), log_service=FakeLogService())
    preview = service.preview_lines(["01各10"], region_mode="澳门")

    result = service.confirm_import(preview, file_path="orders.txt")

    assert result.imported_count == 0
    assert result.save_failed_count == 1
    assert result.preview.rows[0].import_status == "导入失败"
    assert "模拟保存失败" in result.preview.rows[0].import_error


def test_order_import_confirm_uses_order_intake_service_save_preview(
    session_factory, tmp_path
) -> None:
    app()
    intake = OrderIntakeService(session_factory)
    service = OrderImportService(order_intake_service=intake)
    dialog = OrderImportDialog(import_service=service)
    dialog._region_combo.setCurrentText("澳门")
    path = tmp_path / "orders.txt"
    path.write_text("01各10\n", encoding="utf-8")
    dialog.load_file(str(path))

    with patch.object(intake, "save_preview", wraps=intake.save_preview) as save_preview, patch(
        "ui.dialogs.order_import_dialog.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ), patch("ui.dialogs.order_import_dialog.QMessageBox.information"):
        dialog._btn_confirm_import.click()

    assert save_preview.called


def test_order_detail_import_button_opens_preview_dialog(session_factory) -> None:
    app()
    page = OrderDetailPage(order_service=OrderService(session_factory))

    assert page._btn_import_orders.isEnabled()
    assert page._btn_import_orders.text() == "导入订单"
    assert "预览" in page._btn_import_orders.toolTip()

    created = []

    class FakeDialog:
        def __init__(self, parent=None):
            created.append(parent)

        def exec(self):
            return 0

    with patch("ui.pages.order_detail_page.OrderImportDialog", FakeDialog):
        page._btn_import_orders.click()

    assert created == [page]
    assert "订单导入窗口已关闭" in page._status_label.text()
