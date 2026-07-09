from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from ui.main_window import MainWindow
from ui.pages.lianxiao_order_page import LianxiaoOrderPage
from ui.pages.order_analysis_page import OrderAnalysisPage
from ui.pages.special_order_page import SpecialOrderPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def nav_texts(window: MainWindow) -> set[str]:
    return {button.text() for button in window.findChildren(QPushButton)}


def test_main_window_creates_with_complete_top_navigation() -> None:
    app()
    window = MainWindow()
    try:
        assert window.windowTitle()
        assert window.width() >= 1280
        assert {
            "数据总览",
            "订单分析",
            "特码调单",
            "今日开奖",
            "订单详情",
            "结算历史",
            "开奖记录",
            "辅助工具",
            "操作日志",
            "号码大全",
            "我要录单",
            "设置",
        }.issubset(nav_texts(window))
        assert "background-color: #223142" in window.styleSheet()
        assert "background-color: #f5b041" in window.styleSheet()
        assert "background: #F5F7FA" in window.styleSheet()
        assert "QTableWidget" in window.styleSheet()
        assert "QHeaderView::section" in window.styleSheet()
    finally:
        window.close()
        window.deleteLater()


def test_main_window_navigation_switches_page_and_active_state() -> None:
    app()
    window = MainWindow()
    try:
        window._on_nav_clicked(1)

        active_button = window._nav_group.button(1)
        inactive_button = window._nav_group.button(0)
        assert isinstance(window._stack.currentWidget(), OrderAnalysisPage)
        assert window._active_nav_id == 1
        assert active_button.isChecked()
        assert active_button.property("active") is True
        assert inactive_button.property("active") is False
    finally:
        window.close()
        window.deleteLater()


def test_main_window_adjust_navigation_keeps_refresh_hooks() -> None:
    app()
    window = MainWindow()
    special_calls = {"count": 0}
    lianxiao_calls = {"count": 0}

    def special_refresh_spy() -> None:
        special_calls["count"] += 1

    def lianxiao_refresh_spy() -> None:
        lianxiao_calls["count"] += 1

    try:
        special_page = window._stack.widget(2)
        lianxiao_page = window._stack.widget(3)
        special_page.refresh_data = special_refresh_spy  # type: ignore[method-assign]
        lianxiao_page.refresh_data = lianxiao_refresh_spy  # type: ignore[method-assign]

        window._on_nav_clicked(2)
        assert isinstance(window._stack.currentWidget(), SpecialOrderPage)
        assert special_calls["count"] == 1
        assert window._nav_group.button(2).property("active") is True

        window._on_adjust_page_selected(3)
        assert isinstance(window._stack.currentWidget(), LianxiaoOrderPage)
        assert lianxiao_calls["count"] == 1
        assert window._nav_group.button(2).property("active") is True
    finally:
        window.close()
        window.deleteLater()


def test_main_window_record_order_button_opens_record_window() -> None:
    app()
    instances: list[object] = []

    class FakeSignal:
        def connect(self, _slot) -> None:
            pass

    class FakeRecordOrderWindow:
        def __init__(self) -> None:
            self.destroyed = FakeSignal()
            self.show_called = False
            self.raise_called = False
            self.activate_called = False
            instances.append(self)

        def show(self) -> None:
            self.show_called = True

        def raise_(self) -> None:
            self.raise_called = True

        def activateWindow(self) -> None:
            self.activate_called = True

    with patch("ui.main_window.RecordOrderWindow", FakeRecordOrderWindow):
        window = MainWindow()
        try:
            button = window.findChild(QPushButton, "navActionButton")
            assert button is not None

            button.click()

            assert len(instances) == 1
            assert instances[0].show_called
            assert instances[0].raise_called
            assert instances[0].activate_called
        finally:
            window.close()
            window.deleteLater()


def test_main_window_settings_button_opens_dialog_without_switching_page() -> None:
    app()
    with patch("ui.main_window.SettingsDialog") as dialog_class:
        dialog_class.return_value.exec.return_value = QDialog.DialogCode.Accepted
        window = MainWindow()
        try:
            before_index = window._stack.currentIndex()

            window._btn_settings.click()

            dialog_class.assert_called_once_with(parent=window)
            dialog_class.return_value.exec.assert_called_once()
            assert window._stack.currentIndex() == before_index
        finally:
            window.close()
            window.deleteLater()
