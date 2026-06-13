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

from ui.widgets import NavHoverMenuButton

from ui.windows import RecordOrderWindow



# 堆叠页顺序（与下方 _NAV_STACK_MAP 对应）

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



# 顶部普通导航按钮 -> 堆叠页索引（「特码调单」悬停菜单单独处理）

_NAV_LABELS = [

    "数据总览",

    "订单分析",

    "今日开奖",

    "订单详情",

    "结算历史",

    "开奖历史",

    "辅助工具",

    "操作日志",

    "号码大全",

]

_NAV_STACK_MAP = [0, 1, 4, 5, 6, 7, 8, 9, 10]



_SPECIAL_ORDER_STACK = 2

_LIANXIAO_ORDER_STACK = 3





class MainWindow(QMainWindow):

    """顶部横向导航，中部 QStackedWidget 切换页面。"""



    _RECORD_ORDER_LABEL = "我要录单"



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

        self._adjust_nav: NavHoverMenuButton | None = None



        for page_cls in _STACK_PAGE_CLASSES:

            self._stack.addWidget(page_cls())



        nav_id = 0

        for label, stack_idx in zip(_NAV_LABELS, _NAV_STACK_MAP):

            if label == "今日开奖":

                self._add_adjust_nav(nav_layout, nav_id)

                nav_id += 1



            btn = QPushButton(label)

            btn.setCheckable(True)

            btn.setObjectName("navButton")

            self._nav_group.addButton(btn, nav_id)

            nav_layout.addWidget(btn)

            nav_id += 1



        record_btn = QPushButton(self._RECORD_ORDER_LABEL)

        record_btn.setObjectName("navActionButton")

        record_btn.clicked.connect(self._open_record_order_window)

        nav_layout.addWidget(record_btn)



        nav_layout.addStretch(1)



        self._nav_group.idClicked.connect(self._on_nav_clicked)



        root.addWidget(top_bar)

        root.addWidget(self._stack, stretch=1)



        first = self._nav_group.button(0)

        if first:

            first.setChecked(True)

        self._stack.setCurrentIndex(0)



        self._apply_stylesheet()



    def _add_adjust_nav(self, nav_layout: QHBoxLayout, nav_id: int) -> None:

        """在「订单分析」与「今日开奖」之间插入特码调单悬停菜单。"""

        self._adjust_nav = NavHoverMenuButton(

            "特码调单",

            [

                ("连码调单", _SPECIAL_ORDER_STACK),

                ("连肖调单", _LIANXIAO_ORDER_STACK),

            ],

            self,

        )

        self._adjust_nav.page_requested.connect(self._on_adjust_page_selected)

        self._nav_group.addButton(self._adjust_nav.main_button(), nav_id)

        nav_layout.addWidget(self._adjust_nav)



    def _on_nav_clicked(self, nav_id: int) -> None:
        mapping = {0: 0, 1: 1, 2: _SPECIAL_ORDER_STACK, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10}
        stack_idx = mapping.get(nav_id)
        if stack_idx is not None:
            self._stack.setCurrentIndex(stack_idx)



    def _on_adjust_page_selected(self, stack_idx: int) -> None:

        self._stack.setCurrentIndex(stack_idx)

        if self._adjust_nav:

            self._adjust_nav.main_button().setChecked(True)



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

