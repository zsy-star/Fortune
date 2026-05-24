"""开奖历史页面。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_ZODIAC = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")

_WAVE_COLORS = {
    "red": "#e74c3c",
    "blue": "#3498db",
    "green": "#27ae60",
}

_RED_NUMS = {1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46}
_BLUE_NUMS = {3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48}


@dataclass(frozen=True)
class HistoryDrawRow:
    period: str
    draw_date: str
    normals: tuple[int, int, int, int, int, int]
    special: int


def _wave_color(num: int) -> str:
    if num in _RED_NUMS:
        return "red"
    if num in _BLUE_NUMS:
        return "blue"
    return "green"


def _zodiac(num: int) -> str:
    return _ZODIAC[(num - 1) % 12]


_SAMPLE_HISTORY: tuple[HistoryDrawRow, ...] = (
    HistoryDrawRow("016", "2026-02-07", (5, 18, 29, 33, 42, 48), 9),
    HistoryDrawRow("015", "2026-01-31", (2, 11, 17, 26, 38, 44), 31),
    HistoryDrawRow("014", "2026-01-24", (7, 14, 21, 28, 35, 46), 3),
    HistoryDrawRow("013", "2026-01-17", (4, 12, 19, 27, 39, 45), 22),
    HistoryDrawRow("012", "2026-01-10", (1, 8, 16, 24, 32, 40), 47),
    HistoryDrawRow("011", "2026-01-03", (6, 13, 20, 30, 37, 43), 15),
)


class DrawHistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        root.addLayout(self._build_filter_bar())
        root.addWidget(self._build_table_header())
        root.addWidget(self._build_history_list(), stretch=1)
        root.addLayout(self._build_bottom_panels(), stretch=1)

        self._apply_stylesheet()

    def _build_filter_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        self._cmb_source = QComboBox()
        self._cmb_source.addItems(
            [
                "2026_hk_LotteryResult",
                "2026_macau_LotteryResult",
                "2025_hk_LotteryResult",
            ]
        )
        self._cmb_source.setMinimumWidth(200)
        row.addWidget(self._cmb_source)

        row.addWidget(QLabel("数据范围:"))
        self._range_group = QButtonGroup(self)
        for idx, text in enumerate(("不限", "近30期", "近90期")):
            rb = QRadioButton(text)
            if idx == 0:
                rb.setChecked(True)
            self._range_group.addButton(rb, idx)
            row.addWidget(rb)

        row.addSpacing(12)
        row.addWidget(QLabel("类型选择:"))
        self._type_group = QButtonGroup(self)
        for idx, text in enumerate(("不限", "特码", "平码", "特码波色")):
            rb = QRadioButton(text)
            if idx == 0:
                rb.setChecked(True)
            self._type_group.addButton(rb, idx)
            row.addWidget(rb)

        row.addStretch(1)

        btn_fetch = QPushButton("获取最新数据")
        btn_fetch.setObjectName("fetchButton")
        row.addWidget(btn_fetch)

        return row

    def _build_table_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("tableHeader")
        grid = QGridLayout(header)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(4)

        titles = ["期数", "平码1", "平码2", "平码3", "平码4", "平码5", "平码6", "特码"]
        widths = [120, 64, 64, 64, 64, 64, 64, 64]
        for col, (title, width) in enumerate(zip(titles, widths)):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(width)
            lbl.setObjectName("headerCell")
            grid.addWidget(lbl, 0, col)

        return header

    def _build_history_list(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)

        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(6)

        for draw in _SAMPLE_HISTORY:
            self._list_layout.addWidget(self._build_period_block(draw))

        self._list_layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _build_period_block(self, draw: HistoryDrawRow) -> QWidget:
        block = QFrame()
        block.setObjectName("periodBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel(f"▼  {draw.period}期(开奖时间:{draw.draw_date})")
        title.setObjectName("periodTitle")
        layout.addWidget(title)

        grid_wrap = QWidget()
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(120, 4, 8, 6)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)

        row_labels = ("号码", "生肖")
        numbers = list(draw.normals) + [draw.special]

        for row_idx, row_label in enumerate(row_labels):
            lbl = QLabel(row_label)
            lbl.setObjectName("rowTag")
            lbl.setFixedWidth(40)
            grid.addWidget(lbl, row_idx, 0, alignment=Qt.AlignmentFlag.AlignRight)

            for col_idx, num in enumerate(numbers):
                if row_idx == 0:
                    cell = self._make_number_cell(num)
                else:
                    cell = self._make_zodiac_cell(_zodiac(num))
                grid.addWidget(cell, row_idx, col_idx + 1)

        layout.addWidget(grid_wrap)
        return block

    def _make_number_cell(self, num: int) -> QLabel:
        color_key = _wave_color(num)
        bg = _WAVE_COLORS[color_key]
        lbl = QLabel(f"{num:02d}")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(60, 32)
        lbl.setStyleSheet(
            f"background-color: {bg}; color: #ffffff; font-weight: 700; "
            "font-size: 14px; border-radius: 2px;"
        )
        return lbl

    def _make_zodiac_cell(self, zodiac: str) -> QLabel:
        lbl = QLabel(zodiac)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(60, 28)
        lbl.setObjectName("zodiacCell")
        return lbl

    def _build_bottom_panels(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._panel_left = QFrame()
        self._panel_left.setObjectName("detailPanel")
        self._panel_left.setMinimumHeight(120)

        self._panel_right = QFrame()
        self._panel_right.setObjectName("detailPanel")
        self._panel_right.setMinimumHeight(120)

        row.addWidget(self._panel_left, stretch=1)
        row.addWidget(self._panel_right, stretch=1)
        return row

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QFrame#tableHeader {
                background-color: #d6eaf8;
                border: 1px solid #aed6f1;
            }
            QLabel#headerCell {
                font-weight: 600;
                font-size: 13px;
                color: #2c3e50;
            }
            QFrame#periodBlock {
                border: 1px solid #d5d8dc;
                background: #ffffff;
            }
            QLabel#periodTitle {
                background-color: #ecf0f1;
                padding: 6px 10px;
                font-size: 13px;
                color: #2c3e50;
                border-bottom: 1px solid #d5d8dc;
            }
            QLabel#rowTag {
                font-size: 12px;
                color: #7f8c8d;
            }
            QLabel#zodiacCell {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                font-size: 14px;
            }
            QFrame#detailPanel {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                min-height: 100px;
            }
            QPushButton#fetchButton {
                padding: 6px 14px;
                border: 1px solid #bdc3c7;
                background: #ffffff;
                font-size: 13px;
            }
            QPushButton#fetchButton:hover {
                background: #ebf5fb;
            }
            QComboBox, QRadioButton {
                font-size: 13px;
            }
            QScrollArea {
                border: 1px solid #bdc3c7;
                background: #ffffff;
            }
            """
        )
