"""主窗口：顶部导航 + 中部堆叠页面。"""

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
from ui.pages import (
    DrawHistoryPage,
    NumberCatalogPage,
    OperationLogPage,
    OrderAnalysisPage,
    OrderDetailPage,
    OverviewPage,
    SpecialOrderPage,
    TodayDrawPage,
    ToolsPage,
)
from ui.windows import RecordOrderWindow


class MainWindow(QMainWindow):
    """顶部横向导航，中部 QStackedWidget 切换页面。"""

    _RECORD_ORDER_LABEL = "我要录单"

    _NAV_SPECS: list[tuple[str, type[QWidget]]] = [
        ("数据总览", OverviewPage),
        ("订单分析", OrderAnalysisPage),
        ("特码调单", SpecialOrderPage),
        ("今日开奖", TodayDrawPage),
        ("订单详情", OrderDetailPage),
        ("开奖历史", DrawHistoryPage),
        ("辅助工具", ToolsPage),
        ("操作日志", OperationLogPage),
        ("号码大全", NumberCatalogPage),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 760)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("topNavBar")
        nav_layout = QHBoxLayout(top_bar)
        nav_layout.setContentsMargins(16, 10, 16, 10)
        nav_layout.setSpacing(8)

        self._stack = QStackedWidget()
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._record_order_window: RecordOrderWindow | None = None

        for idx, (text, page_cls) in enumerate(self._NAV_SPECS):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setObjectName("navButton")
            self._nav_group.addButton(btn, idx)
            nav_layout.addWidget(btn)
            self._stack.addWidget(page_cls())

        record_btn = QPushButton(self._RECORD_ORDER_LABEL)
        record_btn.setObjectName("navActionButton")
        record_btn.clicked.connect(self._open_record_order_window)
        nav_layout.addWidget(record_btn)

        nav_layout.addStretch(1)

        self._nav_group.idClicked.connect(self._stack.setCurrentIndex)

        root.addWidget(top_bar)
        root.addWidget(self._stack, stretch=1)

        first = self._nav_group.button(0)
        if first:
            first.setChecked(True)
        self._stack.setCurrentIndex(0)

        self._apply_stylesheet()

    def _open_record_order_window(self) -> None:
        """打开录单弹窗（已打开则置前）。"""
        if self._record_order_window is None:
            self._record_order_window = RecordOrderWindow(self)
            self._record_order_window.destroyed.connect(self._on_record_order_window_destroyed)
        self._record_order_window.show()
        self._record_order_window.raise_()
        self._record_order_window.activateWindow()

    def _on_record_order_window_destroyed(self) -> None:
        self._record_order_window = None

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget#topNavBar {
                background-color: #2c3e50;
                border-bottom: 1px solid #1f2d3a;
            }
            QPushButton#navButton {
                color: #ecf0f1;
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 8px 14px;
                font-size: 13px;
            }
            QPushButton#navButton:hover {
                background-color: #34495e;
            }
            QPushButton#navButton:checked {
                background-color: #3498db;
                color: #ffffff;
            }
            QPushButton#navActionButton {
                color: #f1c40f;
                background-color: transparent;
                border: 1px solid #f39c12;
                border-radius: 4px;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#navActionButton:hover {
                background-color: #34495e;
            }
            QLabel#pageTitle {
                font-size: 22px;
                font-weight: 600;
                color: #2c3e50;
            }
            QLabel#pageHint {
                font-size: 14px;
                color: #7f8c8d;
                margin-top: 8px;
            }
            """
        )
