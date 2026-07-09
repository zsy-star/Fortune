"""Main application window with top navigation and stacked pages."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import APP_NAME
from ui.app_events import app_events
from ui.dialogs.settings_dialog import SettingsDialog
from ui.pages import (
    DrawHistoryPage,
    LianxiaoOrderPage,
    NumberCatalogPage,
    OperationLogPage,
    OrderAnalysisPage,
    OrderDetailPage,
    OverviewPage,
    SettlementLedgerPage,
    SpecialOrderPage,
    TodayDrawPage,
    ToolsPage,
)
from ui.theme import get_main_window_stylesheet
from ui.widgets import NavHoverMenuButton
from ui.windows import RecordOrderWindow

logger = logging.getLogger(__name__)

_STACK_PAGE_CLASSES = [
    OverviewPage,
    OrderAnalysisPage,
    SpecialOrderPage,
    LianxiaoOrderPage,
    TodayDrawPage,
    OrderDetailPage,
    SettlementLedgerPage,
    DrawHistoryPage,
    ToolsPage,
    OperationLogPage,
    NumberCatalogPage,
]

_NAV_LABELS = [
    "数据总览",
    "订单分析",
    "今日开奖",
    "订单详情",
    "结算历史",
    "开奖记录",
    "辅助工具",
    "操作日志",
    "号码大全",
]
_NAV_STACK_MAP = [0, 1, 4, 5, 6, 7, 8, 9, 10]

_SPECIAL_ORDER_STACK = 2
_LIANXIAO_ORDER_STACK = 3


class MainWindow(QMainWindow):
    """Top navigation with a central QStackedWidget."""

    _RECORD_ORDER_LABEL = "我要录单"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 760)

        central = QWidget()
        central.setObjectName("mainShell")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("topNavBar")
        nav_layout = QHBoxLayout(top_bar)
        nav_layout.setContentsMargins(12, 7, 12, 7)
        nav_layout.setSpacing(5)

        self._stack = QStackedWidget()
        self._stack.setObjectName("contentStack")
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._record_order_window: RecordOrderWindow | None = None
        self._settings_dialog: SettingsDialog | None = None
        self._adjust_nav: NavHoverMenuButton | None = None
        self._active_nav_id = 0

        for page_cls in _STACK_PAGE_CLASSES:
            self._stack.addWidget(page_cls())

        nav_id = 0
        for label, stack_idx in zip(_NAV_LABELS, _NAV_STACK_MAP):
            if label == "今日开奖":
                self._add_adjust_nav(nav_layout, nav_id)
                nav_id += 1

            btn = self._create_nav_button(label)
            self._nav_group.addButton(btn, nav_id)
            nav_layout.addWidget(btn)
            nav_id += 1

        record_btn = QPushButton(self._RECORD_ORDER_LABEL)
        record_btn.setObjectName("navActionButton")
        record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        record_btn.setMinimumHeight(30)
        record_btn.clicked.connect(self._open_record_order_window)
        nav_layout.addWidget(record_btn)

        nav_layout.addStretch(1)
        self._btn_settings = QPushButton("设置")
        self._btn_settings.setObjectName("settingsButton")
        self._btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_settings.setMinimumHeight(30)
        self._btn_settings.setToolTip("打开个人设置 / 配置中心")
        self._btn_settings.clicked.connect(self._open_settings_dialog)
        nav_layout.addWidget(self._btn_settings)

        self._nav_group.idClicked.connect(self._on_nav_clicked)

        root.addWidget(top_bar)
        root.addWidget(self._stack, stretch=1)

        self._set_active_nav_button(0)
        self._stack.setCurrentIndex(0)

        app_events.app_data_reloaded.connect(self._on_app_data_reloaded)
        self._apply_stylesheet()

    def _create_nav_button(self, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setObjectName("navButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(30)
        return btn

    def _add_adjust_nav(self, nav_layout: QHBoxLayout, nav_id: int) -> None:
        self._adjust_nav = NavHoverMenuButton(
            "特码调单",
            [("连肖调单", _LIANXIAO_ORDER_STACK)],
            self,
        )
        self._adjust_nav.page_requested.connect(self._on_adjust_page_selected)
        self._adjust_nav.main_button().setCursor(Qt.CursorShape.PointingHandCursor)
        self._adjust_nav.main_button().setMinimumHeight(30)
        self._adjust_nav.menu_button().setCursor(Qt.CursorShape.PointingHandCursor)
        self._adjust_nav.menu_button().setMinimumHeight(30)
        self._nav_group.addButton(self._adjust_nav.main_button(), nav_id)
        nav_layout.addWidget(self._adjust_nav)

    def _on_nav_clicked(self, nav_id: int) -> None:
        mapping = {0: 0, 1: 1, 2: _SPECIAL_ORDER_STACK, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10}
        stack_idx = mapping.get(nav_id)
        if stack_idx is not None:
            self._set_active_nav_button(nav_id)
            self._stack.setCurrentIndex(stack_idx)
            self._refresh_adjust_page_if_needed(stack_idx)

    def _on_adjust_page_selected(self, stack_idx: int) -> None:
        self._stack.setCurrentIndex(stack_idx)
        if self._adjust_nav:
            self._set_active_nav_button(self._nav_group.id(self._adjust_nav.main_button()))
        self._refresh_adjust_page_if_needed(stack_idx)

    def _set_active_nav_button(self, nav_id: int) -> None:
        self._active_nav_id = nav_id
        active_button = self._nav_group.button(nav_id)
        if active_button is not None:
            active_button.setChecked(True)
        for button in self._nav_group.buttons():
            button.setProperty("active", button is active_button)
            button.style().unpolish(button)
            button.style().polish(button)

    def _refresh_adjust_page_if_needed(self, stack_idx: int) -> None:
        if stack_idx not in {_SPECIAL_ORDER_STACK, _LIANXIAO_ORDER_STACK}:
            return
        page = self._stack.widget(stack_idx)
        refresh_data = getattr(page, "refresh_data", None)
        if not callable(refresh_data):
            return
        try:
            refresh_data()
        except Exception:
            logger.exception("Failed to refresh adjustment page %s on navigation", type(page).__name__)

    def _open_record_order_window(self) -> None:
        if self._record_order_window is None:
            self._record_order_window = RecordOrderWindow()
            self._record_order_window.destroyed.connect(self._on_record_order_window_destroyed)
        self._record_order_window.show()
        self._record_order_window.raise_()
        self._record_order_window.activateWindow()

    def _on_record_order_window_destroyed(self) -> None:
        self._record_order_window = None

    def _open_settings_dialog(self) -> None:
        self._settings_dialog = SettingsDialog(parent=self)
        try:
            self._settings_dialog.exec()
        finally:
            self._settings_dialog = None

    def _on_app_data_reloaded(self) -> None:
        for index in range(self._stack.count()):
            page = self._stack.widget(index)
            reload_data = getattr(page, "reload_data", None)
            if not callable(reload_data):
                continue
            try:
                reload_data()
            except Exception:
                logger.exception("Failed to reload %s after database restore", type(page).__name__)

        if self._record_order_window is not None:
            try:
                self._record_order_window.reload_declarers()
            except Exception:
                logger.exception("Failed to reload record-order settings after database restore")

        if self._settings_dialog is not None:
            try:
                self._settings_dialog.reload_data()
            except Exception:
                logger.exception("Failed to reload settings dialog after database restore")

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(get_main_window_stylesheet())
