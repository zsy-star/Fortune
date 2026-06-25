from __future__ import annotations

import inspect
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QMessageBox

from schemas.database_backup_schema import DatabaseBackupInfo, DatabaseRestoreResult
from ui.app_events import app_events
from ui.pages.tools_page import ToolsPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def backup_info(name: str = "fortune_backup_20260614_090000.db") -> DatabaseBackupInfo:
    return DatabaseBackupInfo(
        backup_path=Path("D:/tmp/backups") / name,
        backup_name=name,
        created_at=datetime(2026, 6, 14, 9, 0, 0),
        size_bytes=2048,
        reason="manual_ui",
    )


class FakeBackupService:
    def __init__(self, backups=None):
        self.backups = list(backups or [])
        self.create_backup = Mock(side_effect=self._create_backup)
        self.list_backups = Mock(side_effect=self._list_backups)
        self.restore_backup = Mock(side_effect=self._restore_backup)

    def _create_backup(self, reason=None):
        info = backup_info("fortune_backup_20260614_091000.db")
        object.__setattr__(info, "reason", reason)
        self.backups.insert(0, info)
        return info

    def _list_backups(self):
        return list(self.backups)

    def _restore_backup(self, backup, *, confirm=False):
        return DatabaseRestoreResult(
            restored_from=Path(backup),
            database_path=Path("D:/tmp/fortune_test.db"),
            pre_restore_backup_path=Path("D:/tmp/backups/fortune_before_restore_20260614_091500.db"),
            restored_at=datetime(2026, 6, 14, 9, 15, 0),
            size_bytes=4096,
            message="恢复已完成，建议重启软件后继续使用",
        )


def make_page(service: FakeBackupService) -> ToolsPage:
    return ToolsPage(backup_service=service)


def test_tools_page_backup_panel_empty_list_offscreen() -> None:
    app()
    service = FakeBackupService()
    page = make_page(service)

    assert page._backup_table.rowCount() == 0
    assert "暂无备份文件" in page._backup_status.text()
    assert service.list_backups.call_count == 1


def test_create_backup_calls_service_refreshes_list_and_shows_success() -> None:
    app()
    service = FakeBackupService()
    page = make_page(service)

    with patch("ui.pages.tools_page.QMessageBox.information") as info:
        page._on_create_backup()

    service.create_backup.assert_called_once_with(reason="manual_ui")
    assert service.list_backups.call_count == 2
    assert page._backup_table.rowCount() == 1
    assert page._backup_table.item(0, 0).text().startswith("fortune_backup_")
    assert "2.00 KB" in page._backup_table.item(0, 2).text()
    info.assert_called_once()
    assert "备份成功" in info.call_args.args[2]


def test_create_backup_failure_shows_friendly_error() -> None:
    app()
    service = FakeBackupService()
    service.create_backup.side_effect = RuntimeError("disk full")
    page = make_page(service)

    with patch("ui.pages.tools_page.QMessageBox.warning") as warning:
        page._on_create_backup()

    warning.assert_called_once()
    assert "备份失败" in warning.call_args.args[2]
    assert "disk full" in page._backup_status.text()


def test_restore_without_selection_warns_and_does_not_call_service() -> None:
    app()
    service = FakeBackupService([backup_info()])
    page = make_page(service)

    with patch("ui.pages.tools_page.QMessageBox.warning") as warning:
        page._on_restore_backup()

    warning.assert_called_once()
    assert "请先选择一个备份文件" in warning.call_args.args[2]
    service.restore_backup.assert_not_called()


def test_restore_cancel_confirmation_does_not_call_service() -> None:
    app()
    service = FakeBackupService([backup_info()])
    page = make_page(service)
    page._backup_table.selectRow(0)

    with patch(
        "ui.pages.tools_page.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    ) as question:
        page._on_restore_backup()

    question.assert_called_once()
    assert "恢复备份会覆盖当前数据库" in question.call_args.args[2]
    assert "恢复前系统会自动备份当前数据库" in question.call_args.args[2]
    assert "恢复成功后建议重启软件" in question.call_args.args[2]
    service.restore_backup.assert_not_called()
    assert "已取消恢复操作" in page._backup_status.text()


def test_restore_confirm_calls_service_with_confirm_true_and_shows_restart_hint() -> None:
    app()
    selected = backup_info()
    service = FakeBackupService([selected])
    page = make_page(service)
    page._backup_table.selectRow(0)
    app_data_spy = QSignalSpy(app_events.app_data_reloaded)

    with (
        patch(
            "ui.pages.tools_page.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as question,
        patch("ui.pages.tools_page.QMessageBox.information") as info,
    ):
        page._on_restore_backup()

    question.assert_called_once()
    service.restore_backup.assert_called_once_with(selected.backup_path, confirm=True)
    info.assert_called_once()
    assert app_data_spy.count() == 1
    assert "恢复成功，建议重启软件后继续使用" in info.call_args.args[2]
    assert "恢复前自动备份路径" in info.call_args.args[2]


def test_restore_failure_shows_error_without_crashing() -> None:
    app()
    service = FakeBackupService([backup_info()])
    service.restore_backup.side_effect = RuntimeError("locked")
    page = make_page(service)
    page._backup_table.selectRow(0)

    with (
        patch(
            "ui.pages.tools_page.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch("ui.pages.tools_page.QMessageBox.warning") as warning,
    ):
        page._on_restore_backup()

    warning.assert_called_once()
    assert "恢复失败" in warning.call_args.args[2]
    assert "locked" in page._backup_status.text()


def test_tools_page_has_no_delete_backup_button() -> None:
    app()
    page = make_page(FakeBackupService([backup_info()]))

    button_texts = [button.text() for button in page.findChildren(type(page._btn_create_backup))]
    assert all("删除" not in text for text in button_texts)
    assert all("清空" not in text for text in button_texts)


def test_backup_ui_uses_service_only() -> None:
    source = inspect.getsource(ToolsPage)

    for forbidden in ("Session", "Repository", "sqlite", "shutil", "data/fortune.db"):
        assert forbidden not in source
    assert "DatabaseBackupService" in source
    assert "restore_backup(" in source
