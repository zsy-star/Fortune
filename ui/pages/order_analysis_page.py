"""订单分析页面。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from schemas.order_schema import OrderAnalysisGroup, OrderAnalysisSummary
from services.order_service import OrderService

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


@dataclass(frozen=True)
class AnalysisSnapshot:
    summary: OrderAnalysisSummary | None
    error_message: str | None = None


class _ChartCanvas(FigureCanvas):
    def __init__(self, width: float = 4.6, height: float = 2.4, parent=None):
        self.figure = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.figure.set_facecolor("#eef6fc")


class OrderAnalysisPage(QWidget):
    def __init__(self, parent=None, order_service: OrderService | None = None):
        super().__init__(parent)
        self._order_service = order_service or OrderService()
        self._snapshots: dict[str, AnalysisSnapshot] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_body_row(), stretch=1)

        self._apply_stylesheet()
        self.reload_data()

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)

        self._filter_group = QButtonGroup(self)
        for text, idx in (("全部订单", 0), ("只看澳门", 1), ("只看香港", 2)):
            rb = QRadioButton(text)
            self._filter_group.addButton(rb, idx)
            row.addWidget(rb)

        self._filter_group.button(0).setChecked(True)
        self._filter_group.idClicked.connect(self._on_filter_changed)

        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.setObjectName("refreshButton")
        self._btn_refresh.clicked.connect(self.reload_data)
        row.addWidget(self._btn_refresh)
        row.addStretch(1)
        return row

    def _build_body_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["维度", "分类", "订单数", "金额"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setMinimumWidth(300)
        self._table.setMaximumWidth(360)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

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
        snapshot = self._snapshots.get(key)
        summary = snapshot.summary if snapshot else None
        if snapshot and snapshot.error_message:
            self._fill_table([])
            self._refresh_trend_chart([])
            self._refresh_bet_type_chart([])
            self._report_view.setPlainText(snapshot.error_message)
            return
        if summary is None:
            self._fill_table([])
            self._refresh_trend_chart([])
            self._refresh_bet_type_chart([])
            self._report_view.setHtml(_REPORT_EMPTY_HTML)
            return

        self._fill_table(self._build_table_rows(summary))
        self._refresh_trend_chart(list(summary.recent_7_day_trend))
        self._refresh_bet_type_chart(list(summary.by_bet_type))
        self._refresh_report(summary)

    def reload_data(self) -> None:
        try:
            self._snapshots = {
                "all": AnalysisSnapshot(self._order_service.get_order_analysis_summary(region=None)),
                "macau": AnalysisSnapshot(self._order_service.get_order_analysis_summary(region="澳门")),
                "hk": AnalysisSnapshot(self._order_service.get_order_analysis_summary(region="香港")),
            }
        except Exception as exc:
            error = AnalysisSnapshot(None, f"读取订单分析失败：{exc}")
            self._snapshots = {"all": error, "macau": error, "hk": error}

        checked_id = self._filter_group.checkedId()
        self._on_filter_changed(checked_id if checked_id in (0, 1, 2) else 0)

    def _build_table_rows(self, summary: OrderAnalysisSummary) -> list[tuple[str, str, int, Decimal]]:
        rows: list[tuple[str, str, int, Decimal]] = [
            ("总计", "全部订单", summary.total_order_count, summary.total_amount),
            ("总计", "平均订单金额", summary.total_order_count, summary.average_order_amount),
        ]

        def add_groups(section: str, groups: tuple[OrderAnalysisGroup, ...]) -> None:
            for group in groups:
                rows.append((section, group.label, group.order_count, group.total_amount))

        add_groups("地区", summary.by_region)
        add_groups("状态", summary.by_status)
        add_groups("日期", summary.by_date)
        add_groups("投注类型", summary.by_bet_type)
        return rows

    def _fill_table(self, rows: list[tuple[str, str, int, Decimal]]) -> None:
        self._table.setRowCount(len(rows))
        for idx, (section, label, count, amount) in enumerate(rows):
            values = [section, label, str(count), f"{amount:.2f}"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if section == "总计":
                    item.setForeground(QColor("#2980b9"))
                self._table.setItem(idx, col, item)

    def _refresh_trend_chart(self, groups: list[OrderAnalysisGroup]) -> None:
        fig = self._freq_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#eef6fc")

        labels = [group.label[5:] for group in groups]
        values = [float(group.total_amount) for group in groups]
        x = list(range(len(labels)))
        if values and any(val > 0 for val in values):
            ax.plot(x, values, color="#3498db", marker="o", linewidth=1.5, markersize=5)
            ax.axhline(0, color="#95a5a6", linewidth=0.8)
            for xi, val in zip(x, values):
                ax.text(xi, val, f"{val:g}", ha="center", va="bottom", fontsize=8)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=8, rotation=25)
            y_max = max(values) * 1.2 if max(values) > 0 else 1
            ax.set_ylim(0, y_max)
        else:
            ax.set_xticks([])
            ax.set_ylim(0, 1)
            ax.text(0.5, 0.5, "暂无订单数据", ha="center", va="center", transform=ax.transAxes, color="#7f8c8d")
        ax.set_title("最近7天订单趋势", fontsize=10, pad=8)
        ax.set_ylabel("投注金额", fontsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        self._freq_canvas.draw()

    def _refresh_bet_type_chart(self, groups: list[OrderAnalysisGroup]) -> None:
        fig = self._bet_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#eef6fc")

        labels = [group.label for group in groups]
        values = [float(group.total_amount) for group in groups]
        if labels and values:
            x = list(range(len(labels)))
            bars = ax.bar(x, values, color="#27ae60", width=0.55)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=8, rotation=20)
            y_max = max(values) * 1.2 if max(values) > 0 else 1
            ax.set_ylim(0, y_max)
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, val, f"{val:g}", ha="center", va="bottom", fontsize=8)
        else:
            ax.set_ylim(0, 1)
            ax.text(0.5, 0.5, "暂无订单数据", ha="center", va="center", transform=ax.transAxes, color="#7f8c8d")

        ax.set_title("按投注类型统计金额", fontsize=10, pad=8)
        ax.set_ylabel("投注金额", fontsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        self._bet_canvas.draw()

    def _refresh_report(self, summary: OrderAnalysisSummary) -> None:
        if summary.total_order_count == 0:
            self._report_view.setHtml(_REPORT_EMPTY_HTML)
            return
        lines = [
            "<p><b>订单分析报告：</b></p>",
            f"<p>订单数：{summary.total_order_count}，投注金额：{summary.total_amount:.2f}，"
            f"平均订单金额：{summary.average_order_amount:.2f}</p>",
            "<p><b>最近订单：</b></p>",
        ]
        for order in summary.recent_orders:
            lines.append(
                f"<p>{order.created_at:%Y-%m-%d %H:%M} "
                f"{order.order_no} {order.region} {order.total_amount:.2f} {order.status}</p>"
            )
        self._report_view.setHtml("\n".join(lines))

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QRadioButton {
                font-size: 13px;
            }
            QPushButton#refreshButton {
                padding: 4px 12px;
                font-size: 12px;
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
