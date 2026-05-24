"""数据总览页面。"""

from __future__ import annotations

from dataclasses import dataclass

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 盈利率分析条目（示例均为「可观」）
_PROFIT_ITEMS = [f"{n}不中的盈利率为: 可观" for n in range(16, 25)]


@dataclass(frozen=True)
class OverviewSnapshot:
    """某一筛选条件下的展示数据。"""

    bet_types: tuple[str, ...]
    amounts: tuple[float, ...]
    total_all: float
    total_macau: float
    total_hk: float


# 示例数据（后续接订单服务）
_DATA_ALL = OverviewSnapshot(
    bet_types=("特码",),
    amounts=(300.0,),
    total_all=300.0,
    total_macau=300.0,
    total_hk=0.0,
)
_DATA_MACAU = _DATA_ALL
_DATA_HK = OverviewSnapshot(
    bet_types=(),
    amounts=(),
    total_all=0.0,
    total_macau=0.0,
    total_hk=0.0,
)


class _ChartCanvas(FigureCanvas):
    def __init__(self, width: float = 5, height: float = 3.6, parent=None):
        self.figure = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.figure.set_facecolor("#ffffff")


class OverviewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshots = {
            "all": _DATA_ALL,
            "macau": _DATA_MACAU,
            "hk": _DATA_HK,
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(12)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_charts_row(), stretch=3)
        root.addLayout(self._build_bottom_row(), stretch=2)

        self._apply_stylesheet()
        self._on_filter_changed(1)

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)

        self._filter_group = QButtonGroup(self)
        specs = [
            ("全部订单", 0, "all"),
            ("只看澳门", 1, "macau"),
            ("只看香港", 2, "hk"),
        ]
        for text, idx, _key in specs:
            rb = QRadioButton(text)
            self._filter_group.addButton(rb, idx)
            row.addWidget(rb)

        self._filter_group.button(1).setChecked(True)
        self._filter_group.idClicked.connect(self._on_filter_changed)

        row.addStretch(1)
        return row

    def _build_charts_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        self._bar_canvas = _ChartCanvas(5.2, 3.8, self)
        self._pie_canvas = _ChartCanvas(4.8, 3.8, self)

        row.addWidget(self._bar_canvas, stretch=1)
        row.addWidget(self._pie_canvas, stretch=1)
        return row

    def _build_bottom_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        stats = QVBoxLayout()
        stats.setSpacing(6)
        self._lbl_total_all = QLabel()
        self._lbl_total_macau = QLabel()
        self._lbl_total_hk = QLabel()
        for lbl in (self._lbl_total_all, self._lbl_total_macau, self._lbl_total_hk):
            lbl.setObjectName("statLabel")
            stats.addWidget(lbl)
        stats.addStretch(1)

        stats_wrap = QWidget()
        stats_wrap.setLayout(stats)
        stats_wrap.setMinimumWidth(200)

        self._profit_view = QTextEdit()
        self._profit_view.setReadOnly(True)
        self._profit_view.setObjectName("profitAnalysis")
        self._profit_view.setFrameShape(QFrame.Shape.Box)

        row.addWidget(stats_wrap, stretch=0)
        row.addWidget(self._profit_view, stretch=1)
        return row

    def _filter_key(self, button_id: int) -> str:
        return ("all", "macau", "hk")[button_id]

    def _on_filter_changed(self, button_id: int) -> None:
        key = self._filter_key(button_id)
        data = self._snapshots[key]
        self._refresh_summary(data)
        self._refresh_bar_chart(data)
        self._refresh_pie_chart(data)
        self._refresh_profit_analysis()

    def _refresh_summary(self, data: OverviewSnapshot) -> None:
        self._lbl_total_all.setText(f"全部总金额: {data.total_all:.1f}")
        self._lbl_total_macau.setText(f"澳门单总额: {data.total_macau:.1f}")
        self._lbl_total_hk.setText(f"香港单总额: {data.total_hk:.1f}")

    def _refresh_bar_chart(self, data: OverviewSnapshot) -> None:
        fig = self._bar_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        if data.bet_types and data.amounts:
            y_pos = range(len(data.bet_types))
            bars = ax.barh(
                list(y_pos),
                list(data.amounts),
                color="#3498db",
                height=0.5,
            )
            ax.set_yticks(list(y_pos))
            ax.set_yticklabels(list(data.bet_types))
            max_val = max(data.amounts)
            x_max = max(300.0, max_val * 1.15)
            ax.set_xlim(0, x_max)
            for bar, val in zip(bars, data.amounts):
                ax.text(
                    bar.get_width() + x_max * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}",
                    va="center",
                    fontsize=9,
                )
        else:
            ax.set_xlim(0, 300)
            ax.set_ylim(0, 1)
            ax.text(
                0.5,
                0.5,
                "暂无数据",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color="#95a5a6",
            )

        ax.set_title("各投注类型的总金额", fontsize=11, pad=10)
        ax.set_xlabel("总金额", fontsize=9)
        ax.set_ylabel("投注类型", fontsize=9)
        ax.grid(axis="x", linestyle="--", alpha=0.35)
        fig.tight_layout()
        self._bar_canvas.draw()

    def _refresh_pie_chart(self, data: OverviewSnapshot) -> None:
        fig = self._pie_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        if data.bet_types and data.amounts:
            total = sum(data.amounts)
            if total > 0:
                labels = [
                    f"{name}\n{amt / total * 100:.2f}%"
                    for name, amt in zip(data.bet_types, data.amounts)
                ]
                ax.pie(
                    data.amounts,
                    labels=labels,
                    colors=["#3498db"] * len(data.amounts),
                    startangle=90,
                    textprops={"fontsize": 9},
                )
            else:
                ax.text(
                    0.5,
                    0.5,
                    "暂无数据",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    color="#95a5a6",
                )
        else:
            ax.text(
                0.5,
                0.5,
                "暂无数据",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color="#95a5a6",
            )

        ax.set_title("各投注类型的占比", fontsize=11, pad=10)
        fig.tight_layout()
        self._pie_canvas.draw()

    def _refresh_profit_analysis(self) -> None:
        lines = [
            "<p><b>当前赔率和反水设置的盈利情况分析 "
            "(非单批次订单计算, 仅做参考):</b></p>",
            '<p>'
            '<span style="color:#e74c3c;">低于0%: 亏损</span>&nbsp;&nbsp;'
            '<span style="color:#e67e22;">0~3%: 微利</span>&nbsp;&nbsp;'
            '<span style="color:#27ae60;">3%~6%: 还不错</span>&nbsp;&nbsp;'
            '<span style="color:#1e8449;">大于6%: 可观</span>'
            "</p>",
        ]
        for item in _PROFIT_ITEMS:
            lines.append(f'<p style="color:#1e8449;margin:2px 0;">{item}</p>')
        lines.append(
            '<p style="color:#7f8c8d;margin-top:8px;">'
            "(后续添加更多类型的盈利计算, 敬请期待)"
            "</p>"
        )
        self._profit_view.setHtml("\n".join(lines))

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QRadioButton {
                font-size: 13px;
                spacing: 6px;
            }
            QLabel#statLabel {
                color: #5dade2;
                font-size: 14px;
                font-weight: 500;
            }
            QTextEdit#profitAnalysis {
                border: 2px solid #3498db;
                background-color: #ffffff;
                font-size: 13px;
                padding: 8px;
            }
            """
        )
