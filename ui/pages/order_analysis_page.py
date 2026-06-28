"""订单分析工作台页面。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ui.matplotlib_setup import ensure_matplotlib_configured

ensure_matplotlib_configured()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.color_rules import get_wave_color
from domain.zodiac_rules import get_zodiac
from schemas.order_analysis_schema import (
    NumberAnalysisRow,
    OrderAnalysisWorkbench,
    ZodiacAmountRow,
    ZodiacFrequencyRow,
)
from services.order_analysis_service import OrderAnalysisService
from services.order_service import OrderService
from ui.app_events import app_events

_ZODIACS = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")
_ZERO_AMOUNT = Decimal("0")


@dataclass(frozen=True)
class AnalysisSnapshot:
    summary: OrderAnalysisWorkbench | None
    error_message: str | None = None


class _ChartCanvas(FigureCanvas):
    def __init__(self, width: float = 5.6, height: float = 2.25, parent=None):
        self.figure = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.figure.set_facecolor("#f5f7fa")


class OrderAnalysisPage(QWidget):
    def __init__(
        self,
        parent=None,
        analysis_service: OrderAnalysisService | None = None,
        order_service: OrderService | None = None,
    ):
        super().__init__(parent)
        if analysis_service is not None:
            self._analysis_service = analysis_service
        elif order_service is not None:
            self._analysis_service = OrderAnalysisService(order_service._session_factory)
        else:
            self._analysis_service = OrderAnalysisService()
        self._snapshots: dict[str, AnalysisSnapshot] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_body_row(), stretch=1)

        self._apply_stylesheet()
        app_events.orders_changed.connect(self._on_orders_changed)
        app_events.app_data_reloaded.connect(self._on_app_data_reloaded)
        self.reload_data()

    def _on_orders_changed(self) -> None:
        try:
            self.reload_data()
        except Exception as exc:
            self._report_view.setPlainText(f"订单数据已变更，但自动刷新失败：{exc}")

    def _on_app_data_reloaded(self) -> None:
        try:
            self.reload_data()
        except Exception as exc:
            self._report_view.setPlainText(f"应用数据已重载，但订单分析刷新失败：{exc}")

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)

        self._filter_group = QButtonGroup(self)
        for text, idx in (("全部订单", 0), ("只看澳门", 1), ("只看香港", 2)):
            radio = QRadioButton(text)
            radio.setObjectName("analysisFilter")
            self._filter_group.addButton(radio, idx)
            row.addWidget(radio)

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
        row.setSpacing(6)

        self._table = QTableWidget()
        self._table.setObjectName("numberStatsTable")
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["号码", "下注数", "盈亏", "ID"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setMinimumWidth(230)
        self._table.setMaximumWidth(260)
        self._table.verticalHeader().setDefaultSectionSize(21)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        right_frame = QFrame()
        right_frame.setObjectName("analysisRightPane")
        right = QVBoxLayout(right_frame)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)

        self._freq_canvas = _ChartCanvas(5.8, 2.25, self)
        self._bet_canvas = _ChartCanvas(5.8, 2.25, self)

        self._report_view = QPlainTextEdit()
        self._report_view.setReadOnly(True)
        self._report_view.setObjectName("analysisReport")
        self._report_view.setMinimumHeight(130)
        self._report_view.setMaximumHeight(190)

        right.addWidget(self._freq_canvas, stretch=3)
        right.addWidget(self._bet_canvas, stretch=3)
        right.addWidget(self._report_view, stretch=2)

        row.addWidget(self._table, stretch=0)
        row.addWidget(right_frame, stretch=1)
        return row

    def _filter_key(self, button_id: int) -> str:
        return ("all", "macau", "hongkong")[button_id]

    def _on_filter_changed(self, button_id: int) -> None:
        key = self._filter_key(button_id)
        snapshot = self._snapshots.get(key)
        if snapshot and snapshot.error_message:
            self._fill_number_table(self._empty_number_rows())
            self._refresh_frequency_chart(tuple(ZodiacFrequencyRow(zodiac, 0) for zodiac in _ZODIACS))
            self._refresh_amount_chart(tuple(ZodiacAmountRow(zodiac, _ZERO_AMOUNT) for zodiac in _ZODIACS))
            self._report_view.setPlainText(snapshot.error_message)
            return

        workbench = snapshot.summary if snapshot else None
        if workbench is None:
            self._fill_number_table(self._empty_number_rows())
            self._refresh_frequency_chart(tuple(ZodiacFrequencyRow(zodiac, 0) for zodiac in _ZODIACS))
            self._refresh_amount_chart(tuple(ZodiacAmountRow(zodiac, _ZERO_AMOUNT) for zodiac in _ZODIACS))
            self._report_view.setPlainText("订单分析报告（仅参考）：\n当前筛选条件下暂无订单数据。")
            return

        self._fill_number_table(workbench.number_rows)
        self._refresh_frequency_chart(workbench.lianxiao_frequency)
        self._refresh_amount_chart(workbench.pingte_zodiac_amounts)
        self._report_view.setPlainText(workbench.report_text)

    def reload_data(self) -> None:
        try:
            self._snapshots = {
                "all": AnalysisSnapshot(self._analysis_service.get_workbench(region=None)),
                "macau": AnalysisSnapshot(self._analysis_service.get_workbench(region="澳门")),
                "hongkong": AnalysisSnapshot(self._analysis_service.get_workbench(region="香港")),
            }
        except Exception as exc:
            error = AnalysisSnapshot(None, f"读取订单分析失败：{exc}")
            self._snapshots = {"all": error, "macau": error, "hongkong": error}

        checked_id = self._filter_group.checkedId()
        self._on_filter_changed(checked_id if checked_id in (0, 1, 2) else 0)

    def _empty_number_rows(self) -> tuple[NumberAnalysisRow, ...]:
        return tuple(
            NumberAnalysisRow(
                row_id=number,
                number=number,
                zodiac=get_zodiac(number),
                display=f"{get_zodiac(number)}{number:02d}",
                bet_amount=_ZERO_AMOUNT,
                profit_loss=None,
            )
            for number in range(1, 50)
        )

    def _fill_number_table(self, rows: tuple[NumberAnalysisRow, ...]) -> None:
        self._table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                row.display,
                f"{row.bet_amount:.2f}",
                "—" if row.profit_loss is None else f"{row.profit_loss:.2f}",
                str(row.row_id),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 0:
                    item.setForeground(self._number_color(row.number))
                elif col == 1 and row.bet_amount > 0:
                    item.setForeground(QColor("#c0392b"))
                else:
                    item.setForeground(QColor("#34495e"))
                self._table.setItem(row_idx, col, item)

    def _number_color(self, number: int) -> QColor:
        try:
            color = get_wave_color(number)
        except Exception:
            return QColor("#34495e")
        if color == "红波":
            return QColor("#c0392b")
        if color == "蓝波":
            return QColor("#2e6fbb")
        if color == "绿波":
            return QColor("#27864c")
        return QColor("#34495e")

    def _refresh_frequency_chart(self, rows: tuple[ZodiacFrequencyRow, ...]) -> None:
        labels = [row.zodiac for row in rows]
        values = [row.count for row in rows]
        self._draw_bar_chart(
            self._freq_canvas,
            title="连肖中生肖出现频率",
            ylabel="出现次数",
            labels=labels,
            values=values,
            color="#4f81bd",
            value_format="{:g}",
        )

    def _refresh_amount_chart(self, rows: tuple[ZodiacAmountRow, ...]) -> None:
        labels = [row.zodiac for row in rows]
        values = [float(row.amount) for row in rows]
        self._draw_bar_chart(
            self._bet_canvas,
            title="平特一肖投注情况",
            ylabel="金额",
            labels=labels,
            values=values,
            color="#54a24b",
            value_format="{:.0f}",
        )

    def _draw_bar_chart(
        self,
        canvas: _ChartCanvas,
        *,
        title: str,
        ylabel: str,
        labels: list[str],
        values: list[float | int],
        color: str,
        value_format: str,
    ) -> None:
        fig = canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#eef1f7")

        x = list(range(len(labels)))
        bars = ax.bar(x, values, color=color, width=0.56)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        max_value = max([float(value) for value in values], default=0.0)
        y_max = max(max_value * 1.18, 1.0)
        ax.set_ylim(0, y_max)
        for bar, value in zip(bars, values):
            label = value_format.format(float(value))
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                float(value) + y_max * 0.02,
                label,
                ha="center",
                va="bottom",
                fontsize=8,
                color="#333333",
            )
        ax.set_title(title, fontsize=10, pad=6)
        ax.set_xlabel("生肖", fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.grid(axis="y", linestyle="-", linewidth=0.5, alpha=0.4)
        fig.tight_layout(pad=1.0)
        canvas.draw()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QRadioButton#analysisFilter {
                font-size: 12px;
            }
            QPushButton#refreshButton {
                padding: 3px 10px;
                font-size: 12px;
            }
            QTableWidget#numberStatsTable {
                background-color: #ffffff;
                alternate-background-color: #f7f9fb;
                gridline-color: #d9dee5;
                border: 1px solid #aeb6bf;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #e8f0f2;
                padding: 3px 4px;
                border: 1px solid #aeb6bf;
                font-size: 12px;
                font-weight: 600;
            }
            QFrame#analysisRightPane {
                border: 0;
                background: transparent;
            }
            QPlainTextEdit#analysisReport {
                border: 1px solid #aeb6bf;
                background-color: #ffffff;
                font-size: 12px;
                padding: 5px;
            }
            """
        )
