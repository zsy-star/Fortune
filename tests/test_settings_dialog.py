from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from services.settings_service import SettingsService
from ui.app_events import app_events
from ui.dialogs.settings_dialog import SettingsDialog
from ui.main_window import MainWindow


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_dialog(session_factory) -> SettingsDialog:
    return SettingsDialog(settings_service=SettingsService(session_factory))


def test_settings_dialog_has_three_required_tabs(session_factory) -> None:
    app()
    dialog = make_dialog(session_factory)

    assert dialog.windowTitle() == "配置"
    assert dialog._tabs.count() == 3
    assert [dialog._tabs.tabText(index) for index in range(3)] == [
        "赔率/返水",
        "申报人",
        "导入/导出秘钥",
    ]


def test_dialog_adds_plan_item_and_saves_edited_values(session_factory) -> None:
    app()
    service = SettingsService(session_factory)
    dialog = SettingsDialog(settings_service=service)

    with patch(
        "ui.dialogs.settings_dialog.QInputDialog.getText",
        return_value=("47倍4水", True),
    ):
        dialog._on_add_plan()
    assert dialog._current_plan().name == "47倍4水"

    dialog._bet_type_input.setText("特码")
    dialog._odds_input.setText("47")
    dialog._rebate_input.setText("4")
    dialog._on_add_item()
    assert dialog._rate_table.rowCount() == 1

    dialog._rate_table.item(0, 1).setText("48")
    dialog._rate_table.item(0, 2).setText("3.5")
    with patch("ui.dialogs.settings_dialog.QMessageBox.information"):
        dialog._on_save_items()

    persisted = next(plan for plan in SettingsService(session_factory).list_plans() if plan.name == "47倍4水")
    assert str(persisted.items[0].odds) == "48.0000"
    assert str(persisted.items[0].rebate) == "3.50"


def test_dialog_adds_declarer_and_binds_plan(session_factory) -> None:
    app()
    service = SettingsService(session_factory)
    default = service.ensure_default_plan()
    custom = service.create_plan("46倍6水")
    dialog = SettingsDialog(settings_service=service)
    settings_spy = QSignalSpy(app_events.settings_changed)
    logs_spy = QSignalSpy(app_events.logs_changed)

    dialog._declarer_name_input.setText("林林")
    dialog._on_add_declarer()
    assert dialog._declarer_table.rowCount() == 1
    assert service.list_declarers()[0].plan_id == default.id
    assert settings_spy.count() == 1
    assert logs_spy.count() == 1

    plan_combo = dialog._declarer_table.cellWidget(0, 1)
    plan_combo.setCurrentIndex(plan_combo.findData(custom.id))
    assert SettingsService(session_factory).list_declarers()[0].plan_id == custom.id
    assert settings_spy.count() == 2
    assert logs_spy.count() == 2


def test_dialog_secret_mask_toggle_save_and_reload(session_factory) -> None:
    app()
    service = SettingsService(session_factory)
    dialog = SettingsDialog(settings_service=service)
    assert dialog._import_key_input.echoMode() == QLineEdit.EchoMode.Password
    assert dialog._export_key_input.echoMode() == QLineEdit.EchoMode.Password

    dialog._show_import_key.setChecked(True)
    dialog._show_export_key.setChecked(True)
    assert dialog._import_key_input.echoMode() == QLineEdit.EchoMode.Normal
    assert dialog._export_key_input.echoMode() == QLineEdit.EchoMode.Normal
    dialog._show_import_key.setChecked(False)
    dialog._show_export_key.setChecked(False)
    assert dialog._import_key_input.echoMode() == QLineEdit.EchoMode.Password
    assert dialog._export_key_input.echoMode() == QLineEdit.EchoMode.Password

    dialog._import_key_input.setText("import-key")
    dialog._export_key_input.setText("export-key")
    with patch("ui.dialogs.settings_dialog.QMessageBox.information"):
        dialog._on_save_keys()

    reopened = SettingsDialog(settings_service=SettingsService(session_factory))
    assert reopened._import_key_input.text() == "import-key"
    assert reopened._export_key_input.text() == "export-key"
    assert reopened._import_key_input.echoMode() == QLineEdit.EchoMode.Password
    assert reopened._export_key_input.echoMode() == QLineEdit.EchoMode.Password


def test_main_window_has_right_settings_button_and_opens_dialog() -> None:
    app()
    with patch("ui.main_window.SettingsDialog") as dialog_class:
        dialog_class.return_value.exec.return_value = QDialog.DialogCode.Accepted
        window = MainWindow()

        assert window._btn_settings.text() == "设置"
        assert window._btn_settings.objectName() == "settingsButton"
        assert window._btn_settings.isEnabled()
        before_index = window._stack.currentIndex()
        window._btn_settings.click()

    dialog_class.assert_called_once_with(parent=window)
    dialog_class.return_value.exec.assert_called_once()
    assert window._stack.currentIndex() == before_index
