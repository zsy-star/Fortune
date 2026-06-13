"""数据总览页面。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ui.matplotlib_setup import ensure_matplotlib_configured

ensure_matplotlib_configured()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.order_service import OrderService


@dataclass(frozen=True)
class OverviewSnapshot:
    """某一筛选条件下的真实展示数据。"""

    bet_types: tuple[str, ...]
    amounts: tuple[float, ...]
    total_order_count: int
    today_order_count: int
    total_amount: Decimal
    today_amount: Decimal
    macau_order_count: int
    hong_kong_order_count: int
    pending_order_count: int
    settled_order_count: int
    recent_orders: tuple[str, ...]
    error_message: str | None = None


_EMPTY_SNAPSHOT = OverviewSnapshot(
    bet_types=(),
    amounts=(),
    total_order_count=0,
    today_order_count=0,
    total_amount=Decimal("0"),
    today_amount=Decimal("0"),
    macau_order_count=0,
    hong_kong_order_count=0,
    pending_order_count=0,
    settled_order_count=0,
    recent_orders=(),
)


class _ChartCanvas(FigureCanvas):
    def __init__(self, width: float = 5, height: float = 3.6, parent=None):
        self.figure = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.figure.set_facecolor("#ffffff")


class OverviewPage(QWidget):
    def __init__(self, parent=None, order_service: OrderService | None = None):
        super().__init__(parent)
        self._order_service = order_service or OrderService()
        self._snapshots = {"all": _EMPTY_SNAPSHOT, "macau": _EMPTY_SNAPSHOT, "hk": _EMPTY_SNAPSHOT}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(12)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_charts_row(), stretch=3)
        root.addLayout(self._build_bottom_row(), stretch=2)

        self._apply_stylesheet()
        self.reload_data()

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

        self._filter_group.button(0).setChecked(True)
        self._filter_group.idClicked.connect(self._on_filter_changed)

        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.setObjectName("refreshButton")
        self._btn_refresh.clicked.connect(self.reload_data)
        row.addWidget(self._btn_refresh)
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
        self._lbl_total_orders = QLabel()
        self._lbl_today_orders = QLabel()
        self._lbl_total_amount = QLabel()
        self._lbl_today_amount = QLabel()
        self._lbl_macau_orders = QLabel()
        self._lbl_hk_orders = QLabel()
        self._lbl_pending_orders = QLabel()
        self._lbl_settled_orders = QLabel()
        for lbl in (
            self._lbl_total_orders,
            self._lbl_today_orders,
            self._lbl_total_amount,
            self._lbl_today_amount,
            self._lbl_macau_orders,
            self._lbl_hk_orders,
            self._lbl_pending_orders,
            self._lbl_settled_orders,
        ):
            lbl.setObjectName("statLabel")
            stats.addWidget(lbl)
        stats.addStretch(1)

        stats_wrap = QWidget()
        stats_wrap.setLayout(stats)
        stats_wrap.setMinimumWidth(200)

        self._recent_orders_view = QTextEdit()
        self._recent_orders_view.setReadOnly(True)
        self._recent_orders_view.setObjectName("recentOrders")
        self._recent_orders_view.setFrameShape(QFrame.Shape.Box)

        row.addWidget(stats_wrap, stretch=0)
        row.addWidget(self._recent_orders_view, stretch=1)
        return row

    def _filter_key(self, button_id: int) -> str:
        return ("all", "macau", "hk")[button_id]

    def _on_filter_changed(self, button_id: int) -> None:
        key = self._filter_key(button_id)
        data = self._snapshots[key]
        self._refresh_summary(data)
        self._refresh_bar_chart(data)
        self._refresh_pie_chart(data)
        self._refresh_recent_orders(data)

    def reload_data(self) -> None:
        try:
            self._snapshots = {
                "all": self._load_snapshot(region=None),
                "macau": self._load_snapshot(region="澳门"),
                "hk": self._load_snapshot(region="香港"),
            }
        except Exception as exc:
            message = f"读取数据总览失败：{exc}"
            error_snapshot = OverviewSnapshot(
                bet_types=(),
                amounts=(),
                total_order_count=0,
                today_order_count=0,
                total_amount=Decimal("0"),
                today_amount=Decimal("0"),
                macau_order_count=0,
                hong_kong_order_count=0,
                pending_order_count=0,
                settled_order_count=0,
                recent_orders=(),
                error_message=message,
            )
            self._snapshots = {"all": error_snapshot, "macau": error_snapshot, "hk": error_snapshot}

        checked_id = self._filter_group.checkedId()
        self._on_filter_changed(checked_id if checked_id in (0, 1, 2) else 0)

    def _load_snapshot(self, *, region: str | None) -> OverviewSnapshot:
        summary = self._order_service.get_dashboard_summary(region=region, recent_limit=8)
        recent_lines = tuple(
            f"{order.created_at:%Y-%m-%d %H:%M}  {order.order_no}  "
            f"{order.region}  {order.total_amount:.2f}  {order.status}"
            for order in summary.recent_orders
        )
        return OverviewSnapshot(
            bet_types=tuple(item[0] for item in summary.amount_by_bet_type),
            amounts=tuple(float(item[1]) for item in summary.amount_by_bet_type),
            total_order_count=summary.total_order_count,
            today_order_count=summary.today_order_count,
            total_amount=summary.total_amount,
            today_amount=summary.today_amount,
            macau_order_count=summary.macau_order_count,
            hong_kong_order_count=summary.hong_kong_order_count,
            pending_order_count=summary.pending_order_count,
            settled_order_count=summary.settled_order_count,
            recent_orders=recent_lines,
        )

    def _refresh_summary(self, data: OverviewSnapshot) -> None:
        self._lbl_total_orders.setText(f"订单总数: {data.total_order_count}")
        self._lbl_today_orders.setText(f"今日订单数: {data.today_order_count}")
        self._lbl_total_amount.setText(f"总投注金额: {data.total_amount:.2f}")
        self._lbl_today_amount.setText(f"今日投注金额: {data.today_amount:.2f}")
        self._lbl_macau_orders.setText(f"澳门订单数: {data.macau_order_count}")
        self._lbl_hk_orders.setText(f"香港订单数: {data.hong_kong_order_count}")
        self._lbl_pending_orders.setText(f"待处理订单数: {data.pending_order_count}")
        self._lbl_settled_orders.setText(f"已结算订单数: {data.settled_order_count}")

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

    def _refresh_recent_orders(self, data: OverviewSnapshot) -> None:
        if data.error_message:
            self._recent_orders_view.setPlainText(data.error_message)
            return
        if not data.recent_orders:
            self._recent_orders_view.setPlainText("最近订单：暂无订单数据")
            return
        self._recent_orders_view.setPlainText("最近订单：\n" + "\n".join(data.recent_orders))

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QRadioButton {
                font-size: 13px;
                spacing: 6px;
            }
            QPushButton#refreshButton {
                padding: 4px 12px;
                font-size: 12px;
            }
            QLabel#statLabel {
                color: #5dade2;
                font-size: 14px;
                font-weight: 500;
            }
            QTextEdit#recentOrders {
                border: 2px solid #3498db;
                background-color: #ffffff;
                font-size: 13px;
                padding: 8px;
            }
            """
        )
