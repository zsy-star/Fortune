from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from ui.windows.split_order_window import SplitOrderWindow


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_window() -> SplitOrderWindow:
    app()
    return SplitOrderWindow()


def test_split_order_window_creates() -> None:
    window = make_window()
    try:
        assert window.windowTitle() == "拆单助手 V0.1"
        assert window._btn_split.isEnabled()
        assert window._btn_style.isEnabled()
        assert window._btn_save.isEnabled()
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


def test_split_order_window_does_not_reference_order_database_services() -> None:
    import inspect

    source = inspect.getsource(SplitOrderWindow)
    assert "OrderIntakeService" not in source
    assert "OrderService" not in source
    assert "Session" not in source
    assert "sqlite" not in source.lower()
    assert "fortune.db" not in source.lower()
