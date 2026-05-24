"""订单分析页面。"""

from __future__ import annotations

from dataclasses import dataclass

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_ZODIAC = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")
_NUMBER_COLORS = ("#c0392b", "#27ae60", "#2980b9", "#2c3e50")


@dataclass(frozen=True)
class NumberRow:
    label: str
    bet_count: int
    profit_loss: float
    number_color: str


def _zodiac_label(num: int) -> str:
    zodiac = _ZODIAC[(num - 1) % 12]
    return f"{zodiac}{num:02d}"


def _build_macau_rows() -> list[NumberRow]:
    """示例号码表（后续接订单统计服务）。"""
    specs: list[tuple[int, int, float]] = [
        (1, 200, -9112),
        (2, 0, 0),
        (3, 50, -320),
        (4, 80, 288),
        (5, 120, -1500),
        (6, 0, 0),
        (7, 30, -88),
        (8, 100, -2100),
        (9, 0, 0),
        (10, 60, 120),
        (11, 0, 0),
        (12, 100, -4500),
        (13, 40, -560),
        (14, 0, 0),
        (15, 90, 45),
        (16, 0, 0),
        (17, 25, -120),
        (18, 0, 0),
        (19, 70, -890),
        (20, 0, 0),
        (21, 110, -2300),
        (22, 0, 0),
        (23, 15, 30),
        (24, 0, 0),
        (25, 85, -670),
        (26, 0, 0),
        (27, 45, -200),
        (28, 0, 0),
        (29, 55, 95),
        (30, 0, 0),
        (31, 130, -1800),
        (32, 0, 0),
        (33, 20, -45),
        (34, 0, 0),
        (35, 75, -520),
        (36, 0, 0),
        (37, 95, -1100),
        (38, 0, 0),
        (39, 10, 15),
        (40, 0, 0),
        (41, 65, -380),
        (42, 0, 0),
        (43, 140, -3200),
        (44, 0, 0),
        (45, 35, -90),
        (46, 0, 0),
        (47, 50, 60),
        (48, 0, 0),
        (49, 180, -5600),
    ]
    rows: list[NumberRow] = []
    for num, bet, pl in specs:
        rows.append(
            NumberRow(
                label=_zodiac_label(num),
                bet_count=bet,
                profit_loss=pl,
                number_color=_NUMBER_COLORS[num % len(_NUMBER_COLORS)],
            )
        )
    return rows


_REPORT_HTML = """
<p><b>订单分析报告 (仅参考)：</b></p>
<p>[提示：分析结果基于当前订单以及赔率、胜率、返水设置情况得出。]</p>
<p>澳门特码<span style="color:#e74c3c;font-weight:600;">胜负差过大</span>，建议降低亏损较大的数字的押注数额。</p>
<p>建议澳门特码调整上报数据：
<span style="color:#e67e22;">01=190</span>, <span style="color:#e67e22;">12=90</span></p>
<p>香港特码检查：未知(可能没有特码数据)。</p>
<p>各类整订单占比检查：
<span style="background-color:#27ae60;color:#ffffff;padding:2px 8px;border-radius:3px;">健康</span></p>
<p style="color:#555;margin-top:10px;">
订单分析报告请参照数据概览页中盈利分析情况来调整订单数据。</p>
"""

_REPORT_EMPTY_HTML = """
<p><b>订单分析报告 (仅参考)：</b></p>
<p style="color:#7f8c8d;">当前筛选条件下暂无订单数据。</p>
"""


class _ChartCanvas(FigureCanvas):
    def __init__(self, width: float = 4.6, height: float = 2.4, parent=None):
        self.figure = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.figure.set_facecolor("#eef6fc")


class OrderAnalysisPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows_by_filter = {
            "all": _build_macau_rows(),
            "macau": _build_macau_rows(),
            "hk": [],
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_body_row(), stretch=1)

        self._apply_stylesheet()
        self._on_filter_changed(1)

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)

        self._filter_group = QButtonGroup(self)
        for text, idx in (("全部订单", 0), ("只看澳门", 1), ("只看香港", 2)):
            rb = QRadioButton(text)
            self._filter_group.addButton(rb, idx)
            row.addWidget(rb)

        self._filter_group.button(1).setChecked(True)
        self._filter_group.idClicked.connect(self._on_filter_changed)

        row.addStretch(1)
        return row

    def _build_body_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["号码", "下注数", "盈亏", "ID"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setMinimumWidth(300)
        self._table.setMaximumWidth(360)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        right = QVBoxLayout()
        right.setSpacing(6)

        self._freq_canvas = _ChartCanvas(4.8, 2.3, self)
        self._bet_canvas = _ChartCanvas(4.8, 2.3, self)

        self._report_view = QTextEdit()
        self._report_view.setReadOnly(True)
        self._report_view.setObjectName("analysisReport")
        self._report_view.setMinimumHeight(140)

        right.addWidget(self._freq_canvas, stretch=2)
        right.addWidget(self._bet_canvas, stretch=2)
        right.addWidget(self._report_view, stretch=2)

        row.addWidget(self._table, stretch=0)
        row.addLayout(right, stretch=1)
        return row

    def _filter_key(self, button_id: int) -> str:
        return ("all", "macau", "hk")[button_id]

    def _on_filter_changed(self, button_id: int) -> None:
        key = self._filter_key(button_id)
        rows = self._rows_by_filter[key]
        self._fill_table(rows)
        self._refresh_zodiac_chart(
            self._freq_canvas,
            "连肖中生肖出现频率",
            "出现次数",
            [0] * 12,
        )
        self._refresh_zodiac_chart(
            self._bet_canvas,
            "平特一肖押注情况",
            "金额",
            [0] * 12,
        )
        self._report_view.setHtml(_REPORT_HTML if rows else _REPORT_EMPTY_HTML)

    def _fill_table(self, rows: list[NumberRow]) -> None:
        self._table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            num_item = QTableWidgetItem(row.label)
            num_item.setForeground(QColor(row.number_color))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            bet_item = QTableWidgetItem(str(row.bet_count))
            bet_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            pl_item = QTableWidgetItem(str(row.profit_loss))
            pl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if row.profit_loss < 0:
                pl_item.setForeground(QColor("#c0392b"))
            elif row.profit_loss > 0:
                pl_item.setForeground(QColor("#3498db"))

            id_item = QTableWidgetItem(str(idx + 1))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self._table.setItem(idx, 0, num_item)
            self._table.setItem(idx, 1, bet_item)
            self._table.setItem(idx, 2, pl_item)
            self._table.setItem(idx, 3, id_item)

    def _refresh_zodiac_chart(
        self,
        canvas: _ChartCanvas,
        title: str,
        ylabel: str,
        values: list[float],
    ) -> None:
        fig = canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#eef6fc")

        x = list(range(len(_ZODIAC)))
        ax.plot(x, values, color="#3498db", marker="o", linewidth=1.5, markersize=5)
        ax.axhline(0, color="#95a5a6", linewidth=0.8)

        for xi, val in zip(x, values):
            ax.text(xi, val, f"{val:g}", ha="center", va="bottom", fontsize=8)

        ax.set_xticks(x)
        ax.set_xticklabels(list(_ZODIAC), fontsize=9)
        ax.set_ylim(-0.04, 0.04)
        ax.set_yticks([-0.04, -0.02, 0, 0.02, 0.04])
        ax.set_title(title, fontsize=10, pad=8)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        canvas.draw()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QRadioButton {
                font-size: 13px;
            }
            QTableWidget {
                background-color: #ffffff;
                gridline-color: #d5d8dc;
                border: 1px solid #bdc3c7;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #ecf0f1;
                padding: 6px 4px;
                border: 1px solid #bdc3c7;
                font-weight: 600;
            }
            QTextEdit#analysisReport {
                border: 1px solid #bdc3c7;
                background-color: #ffffff;
                font-size: 13px;
                padding: 8px;
            }
            """
        )
