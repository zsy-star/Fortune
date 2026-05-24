"""订单详情页面。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.pages.today_draw_page import BallInfo, _MACAU_DRAW

_TABLE_COLUMNS = [
    "区域",
    "投注类型",
    "订单信息",
    "筛选类型",
    "计算方式",
    "金额",
    "订单总额",
    "是否自定义",
    "申报人",
    "中奖情况",
    "中奖金额",
]

_SAMPLE_ORDERS = [
    ("澳门", "特码", "1", "NaN", "各数", "200.0", "200.0", "标准", "定总", "未中奖", ""),
    ("澳门", "特码", "12", "NaN", "各数", "100.0", "100.0", "标准", "定总", "未中奖", ""),
]

_BALL_COLORS = {
    "blue": "#5b6dfb",
    "green": "#008b7d",
    "orange": "#ff7043",
}


class OrderDetailPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        root.addLayout(self._build_toolbar())
        root.addWidget(self._build_order_table(), stretch=3)
        root.addLayout(self._build_summary_row())
        root.addLayout(self._build_filter_row())
        root.addWidget(self._build_prize_tabs(), stretch=0)
        root.addLayout(self._build_result_panels(), stretch=2)

        self._apply_stylesheet()

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        for text in (
            "清空订单",
            "删除过滤订单",
            "导出订单",
            "导入订单",
            "过滤兑奖",
            "综合兑奖",
        ):
            btn = QPushButton(text)
            btn.setObjectName("toolBtn")
            row.addWidget(btn)

        btn_reset = QPushButton("重置开奖")
        btn_reset.setObjectName("resetDrawBtn")
        row.addWidget(btn_reset)

        row.addSpacing(12)
        row.addWidget(QLabel("扩大兑奖框"))
        cmb = QComboBox()
        cmb.addItems(["47倍4水", "46倍4水", "45倍4水"])
        cmb.setMinimumWidth(100)
        row.addWidget(cmb)

        row.addStretch(1)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索订单中的关键字")
        self._search_edit.setObjectName("searchEdit")
        self._search_edit.setMinimumWidth(220)

        btn_search = QPushButton("搜索")
        btn_search.setObjectName("searchBtn")

        row.addWidget(self._search_edit)
        row.addWidget(btn_search)
        return row

    def _build_order_table(self) -> QTableWidget:
        table = QTableWidget(len(_SAMPLE_ORDERS), len(_TABLE_COLUMNS))
        table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        table.verticalHeader().setVisible(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        for row_idx, row_data in enumerate(_SAMPLE_ORDERS):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row_idx, col_idx, item)

        return table

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("当前订单总额：300.0"))
        row.addSpacing(24)
        row.addWidget(QLabel("选择总额："))
        row.addSpacing(24)

        status = QLabel('订单状态：<span style="color:#27ae60;font-weight:600;">正常</span>')
        status.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(status)
        row.addStretch(1)
        return row

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        for items in (
            ["全部区域", "澳门", "香港"],
            ["不限投注类型", "特码", "平特一肖"],
            ["不限中奖", "未中奖", "已中奖"],
            ["不限申报人", "定总", "个人微信"],
        ):
            cmb = QComboBox()
            cmb.addItems(items)
            cmb.setMinimumWidth(160)
            row.addWidget(cmb, stretch=1)

        return row

    def _build_prize_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("prizeTabs")

        macau_tab = QWidget()
        macau_layout = QVBoxLayout(macau_tab)
        macau_layout.setContentsMargins(8, 12, 8, 8)
        macau_layout.addLayout(self._build_draw_balls_row(_MACAU_DRAW.balls))
        tabs.addTab(macau_tab, "澳门兑奖")

        hk_tab = QWidget()
        hk_layout = QVBoxLayout(hk_tab)
        hk_layout.setContentsMargins(8, 12, 8, 8)
        hk_layout.addWidget(
            QLabel("暂无香港开奖数据", alignment=Qt.AlignmentFlag.AlignCenter)
        )
        tabs.addTab(hk_tab, "香港兑奖")

        tabs.setCurrentIndex(0)
        return tabs

    def _build_draw_balls_row(self, balls: tuple[BallInfo, ...]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addStretch(1)

        for idx, ball in enumerate(balls):
            if idx == len(balls) - 1:
                row.addSpacing(24)
            row.addWidget(self._build_ball_cell(ball))

        row.addStretch(1)
        return row

    def _build_ball_cell(self, ball: BallInfo) -> QWidget:
        cell = QWidget()
        col = QVBoxLayout(cell)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        bg = _BALL_COLORS.get(ball.color, _BALL_COLORS["blue"])
        num_lbl = QLabel(ball.number)
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_lbl.setFixedSize(48, 48)
        num_lbl.setStyleSheet(
            f"background-color: {bg}; color: #ffffff; font-size: 18px; "
            "font-weight: 700; border-radius: 4px;"
        )

        zodiac_lbl = QLabel(ball.zodiac)
        zodiac_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zodiac_lbl.setFixedSize(48, 32)
        zodiac_lbl.setObjectName("zodiacCell")

        col.addWidget(num_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addWidget(zodiac_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        return cell

    def _build_result_panels(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        for title in ("澳门兑奖结果", "香港兑奖结果", "综合结果"):
            frame = QFrame()
            frame.setObjectName("resultPanel")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(8, 8, 8, 8)
            lbl = QLabel(title)
            lbl.setObjectName("panelTitle")
            layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignLeft)
            layout.addStretch(1)
            row.addWidget(frame, stretch=1)

        return row

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QPushButton#toolBtn {
                padding: 4px 8px;
                border: none;
                color: #2980b9;
                font-size: 12px;
            }
            QPushButton#toolBtn:hover {
                color: #1a5276;
                text-decoration: underline;
            }
            QPushButton#resetDrawBtn {
                padding: 4px 8px;
                border: none;
                color: #27ae60;
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit#searchEdit {
                padding: 6px 10px;
                border: 1px solid #aed6f1;
                background: #ebf5fb;
                font-size: 12px;
            }
            QPushButton#searchBtn {
                padding: 6px 14px;
                background: #d6eaf8;
                border: 1px solid #aed6f1;
                font-size: 12px;
            }
            QTableWidget {
                border: 1px solid #bdc3c7;
                font-size: 12px;
                gridline-color: #d5d8dc;
            }
            QHeaderView::section {
                background-color: #d6eaf8;
                padding: 6px 4px;
                border: 1px solid #aed6f1;
                font-weight: 600;
            }
            QComboBox {
                padding: 4px 8px;
                border: 1px solid #bdc3c7;
                font-size: 12px;
            }
            QTabWidget#prizeTabs::pane {
                border: 1px solid #bdc3c7;
                background: #ffffff;
            }
            QTabBar::tab {
                padding: 8px 16px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: #d6eaf8;
                border-bottom: 2px solid #3498db;
            }
            QLabel#zodiacCell {
                background: #ffffff;
                border: 1px solid #2c3e50;
                font-size: 14px;
            }
            QFrame#resultPanel {
                border: 1px solid #bdc3c7;
                background: #ffffff;
                min-height: 80px;
            }
            QLabel#panelTitle {
                font-size: 12px;
                color: #7f8c8d;
            }
            """
        )
