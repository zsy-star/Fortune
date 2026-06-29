from __future__ import annotations

import os
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from sqlalchemy import func, select

from models import OperationLog, Order, SettlementRecord
from schemas.order_import_schema import OrderImportConfirmResult, OrderImportPreview
from services.order_import_service import OrderImportService
from services.order_intake_service import OrderIntakeService
from ui.app_events import app_events
from ui.windows.split_order_window import SplitOrderWindow


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


class FakeSettingsService:
    def list_declarers(self):
        return []


class DeclarerSettingsService:
    def list_declarers(self):
        class Declarer:
            name = "林林"
            plan_name = "默认方案"

        return [Declarer()]


def make_window(**kwargs) -> SplitOrderWindow:
    app()
    kwargs.setdefault("settings_service", FakeSettingsService())
    return SplitOrderWindow(**kwargs)


def count_orders(session_factory) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count(Order.id))) or 0)


def count_settlements(session_factory) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count(SettlementRecord.id))) or 0)


def test_split_order_window_creates() -> None:
    window = make_window()
    try:
        assert window.windowTitle() == "拆单助手 V0.1"
        assert window._btn_split.isEnabled()
        assert window._btn_style.isEnabled()
        assert window._btn_save.isEnabled()
        assert window._btn_preview_orders.text() == "预览订单"
        assert window._btn_confirm_save.text() == "确认保存成功行"
        assert not window._btn_confirm_save.isEnabled()
        assert [button.text() for button in window._region_group.buttons()] == ["自动识别", "澳门", "香港"]
        assert window._declarer_combo.itemText(0) == "未设置申报人"
        assert window._channel_combo.currentText() == "拆单助手"
    finally:
        window.close()
        window.deleteLater()


def test_split_order_window_declarer_combo_initializes_with_plan() -> None:
    window = make_window(settings_service=DeclarerSettingsService())
    try:
        assert window._declarer_combo.count() == 2
        window._declarer_combo.setCurrentText("林林")
        assert window._selected_customer_name() == "林林"
        assert window._selected_config_plan_name() == "默认方案"
        assert "默认方案" in window._plan_label.text()
    finally:
        window.close()
        window.deleteLater()


def test_empty_input_split_shows_prompt() -> None:
    window = make_window()
    try:
        with patch("ui.windows.split_order_window.QMessageBox.warning") as warning:
            window._on_start_split()
        warning.assert_called_once()
        assert "请输入需要拆分的内容" in window._recognize_text.toPlainText()
    finally:
        window.close()
        window.deleteLater()


def test_split_removes_empty_lines_and_extra_spaces() -> None:
    window = make_window()
    try:
        window._input_text.setPlainText("  兔   各 10  \n\n  马 各 5  ")
        window._on_start_split()
        assert window._result_text.toPlainText() == "兔 各 10\n马 各 5"
    finally:
        window.close()
        window.deleteLater()


def test_chinese_delimiters_split_into_lines() -> None:
    window = make_window()
    try:
        window._input_text.setPlainText("兔各10，马各5、蛇各3；龙各2")
        window._on_start_split()
        assert window._result_text.toPlainText().splitlines() == ["兔各10", "马各5", "蛇各3", "龙各2"]
    finally:
        window.close()
        window.deleteLater()


def test_english_delimiters_split_into_lines() -> None:
    window = make_window()
    try:
        window._input_text.setPlainText("01/10,02/20;03/30")
        window._on_start_split()
        assert window._result_text.toPlainText().splitlines() == ["01/10", "02/20", "03/30"]
    finally:
        window.close()
        window.deleteLater()


def test_toggle_numbered_style_adds_and_removes_numbers() -> None:
    window = make_window()
    try:
        window._input_text.setPlainText("兔各10，马各5")
        window._on_start_split()
        window._on_toggle_numbered_style()
        assert window._result_text.toPlainText().splitlines() == ["1. 兔各10", "2. 马各5"]
        window._on_toggle_numbered_style()
        assert window._result_text.toPlainText().splitlines() == ["兔各10", "马各5"]
    finally:
        window.close()
        window.deleteLater()


def test_split_results_can_preview_orders_with_default_selection() -> None:
    window = make_window()
    try:
        window._input_text.setPlainText("01各10，明显无效，02各5")
        window._on_start_split()
        window._on_preview_orders()

        assert window._preview.total_count == 3
        assert window._preview.success_count == 2
        assert window._preview.failure_count == 1
        assert window._preview_table.rowCount() == 3
        assert window._preview_table.item(0, 0).checkState() == Qt.CheckState.Checked
        assert window._preview_table.item(1, 0).checkState() == Qt.CheckState.Unchecked
        assert not (window._preview_table.item(1, 0).flags() & Qt.ItemFlag.ItemIsEnabled)
        assert window._preview_table.item(0, 4).text() == "成功"
        assert window._preview_table.item(1, 4).text() == "失败"
        assert window._btn_confirm_save.isEnabled()
        assert "已勾选保存 2" in window._recognize_text.toPlainText()
    finally:
        window.close()
        window.deleteLater()


def test_success_row_can_be_unchecked_and_confirm_button_updates() -> None:
    window = make_window()
    try:
        window._input_text.setPlainText("01各10")
        window._on_start_split()
        window._on_preview_orders()
        window._preview_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)

        assert not window._btn_confirm_save.isEnabled()
        assert window._preview.rows[0].selected_for_import is False
        assert "已勾选保存 0" in window._recognize_text.toPlainText()
    finally:
        window.close()
        window.deleteLater()


def test_save_empty_result_shows_prompt() -> None:
    window = make_window()
    try:
        with patch("ui.windows.split_order_window.QMessageBox.warning") as warning:
            window._on_save_results()
        warning.assert_called_once()
        assert "没有可保存的拆分结果" in window._recognize_text.toPlainText()
    finally:
        window.close()
        window.deleteLater()


def test_save_result_writes_utf8_txt(tmp_path: Path) -> None:
    window = make_window()
    target = tmp_path / "split.txt"
    try:
        window._input_text.setPlainText("兔各10，马各5")
        window._on_start_split()
        with (
            patch("ui.windows.split_order_window.QFileDialog.getSaveFileName", return_value=(str(target), "")),
            patch("ui.windows.split_order_window.QMessageBox.information") as info,
        ):
            window._on_save_results()
        info.assert_called_once()
        assert target.read_text(encoding="utf-8") == "兔各10\n马各5\n"
    finally:
        window.close()
        window.deleteLater()


def test_copy_result_writes_clipboard() -> None:
    clipboard = app().clipboard()
    clipboard.clear()
    window = make_window()
    try:
        window._input_text.setPlainText("兔各10，马各5")
        window._on_start_split()
        with patch("ui.windows.split_order_window.QMessageBox.information") as info:
            window._on_copy_results()
        info.assert_called_once()
        assert clipboard.text() == "兔各10\n马各5"
    finally:
        window.close()
        window.deleteLater()


def test_confirm_save_cancel_does_not_write_database(session_factory) -> None:
    intake = OrderIntakeService(session_factory)
    import_service = OrderImportService(order_intake_service=intake)
    window = make_window(import_service=import_service)
    try:
        window._region_group.button(1).setChecked(True)
        window._input_text.setPlainText("01各10")
        window._on_start_split()
        window._on_preview_orders()
        with patch(
            "ui.windows.split_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ):
            window._on_confirm_save()

        assert count_orders(session_factory) == 0
        assert "已取消确认保存" in window._recognize_text.toPlainText()
        assert window._btn_confirm_save.isEnabled()
    finally:
        window.close()
        window.deleteLater()


def test_confirm_save_only_checked_success_rows_and_emits_events(session_factory) -> None:
    intake = OrderIntakeService(session_factory)
    import_service = OrderImportService(order_intake_service=intake)
    window = make_window(import_service=import_service, settings_service=DeclarerSettingsService())
    emitted = []
    app_events.orders_changed.connect(lambda: emitted.append("orders"))
    app_events.logs_changed.connect(lambda: emitted.append("logs"))
    try:
        window._region_group.button(1).setChecked(True)
        window._declarer_combo.setCurrentText("林林")
        window._channel_combo.setCurrentText("文本拆单")
        window._input_text.setPlainText("01各10，明显无效，02各5")
        window._on_start_split()
        window._on_preview_orders()
        window._preview_table.item(2, 0).setCheckState(Qt.CheckState.Unchecked)

        with patch(
            "ui.windows.split_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch("ui.windows.split_order_window.QMessageBox.information"):
            window._on_confirm_save()

        assert count_orders(session_factory) == 1
        assert count_settlements(session_factory) == 0
        assert emitted == ["orders", "logs"]
        assert window._preview_table.item(0, 8).text() == "已导入"
        assert window._preview_table.item(1, 8).text() == "未导入，解析失败"
        assert window._preview_table.item(2, 8).text() == "已跳过，未勾选"
        assert not window._btn_confirm_save.isEnabled()
        with session_factory() as session:
            order = session.scalars(select(Order)).one()
            assert order.customer_name == "林林"
            assert order.channel == "文本拆单"
            assert order.source == "split_order"
            log = session.scalars(
                select(OperationLog).where(OperationLog.action == "split_order/save")
            ).one()
            assert "declarer=林林" in log.description
            assert "channel=文本拆单" in log.description
            assert "config_plan=默认方案" in log.description
            assert "imported=1" in log.description
            assert "skipped_unselected=1" in log.description
        window._on_confirm_save()
        assert count_orders(session_factory) == 1
        assert "本次拆单保存已完成" in window._recognize_text.toPlainText()
        assert not window._btn_confirm_save.isEnabled()
    finally:
        window.close()
        window.deleteLater()


def test_save_failure_row_does_not_block_other_checked_rows(session_factory) -> None:
    class PartlyBrokenImportService(OrderImportService):
        def _save_row(self, row, **kwargs):
            if row.raw_text == "02各5":
                raise RuntimeError("模拟单行保存失败")
            return super()._save_row(row, **kwargs)

    intake = OrderIntakeService(session_factory)
    import_service = PartlyBrokenImportService(order_intake_service=intake)
    window = make_window(import_service=import_service)
    try:
        window._region_group.button(1).setChecked(True)
        window._input_text.setPlainText("01各10，02各5")
        window._on_start_split()
        window._on_preview_orders()

        with patch(
            "ui.windows.split_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch("ui.windows.split_order_window.QMessageBox.information"):
            window._on_confirm_save()

        assert count_orders(session_factory) == 1
        assert window._preview_table.item(0, 8).text() == "已导入"
        assert window._preview_table.item(1, 8).text() == "导入失败"
        assert "模拟单行保存失败" in window._preview_table.item(1, 9).text()
    finally:
        window.close()
        window.deleteLater()


def test_repreview_resets_saved_status_and_enables_confirm(session_factory) -> None:
    intake = OrderIntakeService(session_factory)
    import_service = OrderImportService(order_intake_service=intake)
    window = make_window(import_service=import_service)
    try:
        window._region_group.button(1).setChecked(True)
        window._input_text.setPlainText("01各10")
        window._on_start_split()
        window._on_preview_orders()
        with patch(
            "ui.windows.split_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch("ui.windows.split_order_window.QMessageBox.information"):
            window._on_confirm_save()

        assert not window._btn_confirm_save.isEnabled()
        window._input_text.setPlainText("02各5")
        window._on_start_split()
        window._on_preview_orders()

        assert window._preview_table.item(0, 8).text() == "未导入"
        assert window._btn_confirm_save.isEnabled()
    finally:
        window.close()
        window.deleteLater()


def test_clear_input_still_works() -> None:
    window = make_window()
    try:
        window._input_text.setPlainText("兔各10")
        window._on_start_split()
        window._on_clear_input()
        assert window._input_text.toPlainText() == ""
        assert window._result_text.toPlainText() == ""
        assert window._result_lines == []
    finally:
        window.close()
        window.deleteLater()


def test_split_order_window_uses_import_service_without_direct_orm_writes() -> None:
    import inspect

    source = inspect.getsource(SplitOrderWindow)
    assert "OrderImportService" in source
    assert "Order(" not in source
    assert "OrderItem(" not in source
    assert "Session" not in source
    assert "sqlite" not in source.lower()
    assert "fortune.db" not in source.lower()
