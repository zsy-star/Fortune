"""连肖调单页面：第一阶段只读汇总工作台。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.order_service import OrderService

LIANXIAO_BET_TYPES = {"连肖", "多生肖", "复试连肖"}
TABLE_HEADERS = ["生肖组", "下注数", "盈亏"]


@dataclass(frozen=True, slots=True)
class LianxiaoSummary:
    group: str
    amount: Decimal


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


class LianxiaoOrderPage(QWidget):
    """连肖调单页面。

    第一阶段只读汇总已有连肖类订单明细，不保存调整、不写数据库、不计算赔付。
    布局恢复为传统连肖工作台：左侧总表 + 右侧四个并排连肖列表。
    """

    def __init__(self, parent=None, order_service: OrderService | None = None):
        super().__init__(parent)
        self._order_service = order_service or OrderService()
        self._summaries: list[LianxiaoSummary] = []
        self._tables: list[QTableWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(2)

        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), stretch=7)
        root.addWidget(self._build_stats_panel())
        root.addWidget(self._build_action_panel())

        self._output = QPlainTextEdit()
        self._output.setObjectName("adjustOutput")
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("连肖调单操作提示会显示在这里。")
        root.addWidget(self._output, stretch=3)

        self._apply_stylesheet()
        self.reload_data()

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("topFilter")
        row = QHBoxLayout(frame)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(6)
        row.addStretch(1)

        self._region_group = QButtonGroup(self)
        specs = [("全部", None, True), ("只看澳门", "澳门", False), ("只看香港", "香港", False)]
        for idx, (label, value, checked) in enumerate(specs):
            rb = QRadioButton(label)
            rb.setProperty("region", value)
            rb.setChecked(checked)
            rb.toggled.connect(lambda toggled=False: self.reload_data() if toggled else None)
            self._region_group.addButton(rb, idx)
            row.addWidget(rb)

        row.addStretch(1)
        return frame

    def _build_body(self) -> QWidget:
        panel = QWidget()
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)

        self._summary_table = self._create_table("lianxiaoSummaryTable")
        self._summary_table.setMinimumWidth(280)
        row.addWidget(self._summary_table, stretch=23)

        right = QWidget()
        right_row = QHBoxLayout(right)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(3)
        for index in range(4):
            table = self._create_table(f"lianxiaoListTable{index + 1}")
            self._tables.append(table)
            right_row.addWidget(table, stretch=1)
        row.addWidget(right, stretch=77)
        return panel

    def _create_table(self, object_name: str) -> QTableWidget:
        table = QTableWidget(0, 3)
        table.setObjectName(object_name)
        table.setHorizontalHeaderLabels(TABLE_HEADERS)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(24)
        return table

    def _build_stats_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)

        self._lbl_lianxiao_total = QLabel()
        self._lbl_max_profit = QLabel()
        self._lbl_max_loss = QLabel()
        self._lbl_eat_total = QLabel()
        self._lbl_adjustment_total = QLabel()
        self._lbl_adjusted_max_profit = QLabel()
        self._lbl_adjusted_max_loss = QLabel()

        self._original_stats_bar = self._stats_row(
            "原连肖数据",
            self._lbl_lianxiao_total,
            self._lbl_max_profit,
            self._lbl_max_loss,
        )
        self._adjusted_stats_bar = self._stats_row(
            "调整后数据",
            self._lbl_eat_total,
            self._lbl_adjustment_total,
            self._lbl_adjusted_max_profit,
            self._lbl_adjusted_max_loss,
        )
        col.addWidget(self._original_stats_bar)
        col.addWidget(self._adjusted_stats_bar)
        return panel

    def _stats_row(self, title: str, *labels: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statsPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("statsTitle")
        row.addWidget(title_label)
        for label in labels:
            label.setObjectName("statsValue")
            row.addWidget(self._separator())
            row.addWidget(label, stretch=1)
        return frame

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setObjectName("statsSeparator")
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        return line

    def _build_action_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("actionPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        actions = [
            ("打印连肖调整", self._on_print_adjustment),
            ("清空输出框", self._on_clear_output),
            ("重置调整", self._on_reset_adjustment),
        ]
        for text, handler in actions:
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button, stretch=1)
            if text == "打印连肖调整":
                self._btn_print = button
            elif text == "清空输出框":
                self._btn_clear_output = button
            elif text == "重置调整":
                self._btn_reset = button
        return frame

    def reload_data(self) -> None:
        self._summaries = self._load_lianxiao_summary()
        self._fill_tables()
        self._update_stats()
        if self._summaries:
            self._append_output(f"已加载连肖汇总：{len(self._summaries)} 组。")
        else:
            self._append_output("暂无数据：当前筛选条件下没有连肖订单明细。")
        self._append_output("当前仅展示只读汇总，不保存订单调整。")

    def _selected_region(self) -> str | None:
        button = self._region_group.checkedButton()
        return button.property("region") if button is not None else None

    def _load_lianxiao_summary(self) -> list[LianxiaoSummary]:
        grouped: dict[str, Decimal] = {}
        offset = 0
        while True:
            orders = self._order_service.list_orders(
                region=self._selected_region(),
                limit=200,
                offset=offset,
            )
            if not orders:
                break
            for order in orders:
                detail = self._order_service.get_order(order.id)
                if detail is None:
                    continue
                for item in detail.items:
                    if item.bet_type not in LIANXIAO_BET_TYPES:
                        continue
                    group = item.selection.strip() or "未命名组合"
                    grouped[group] = grouped.get(group, Decimal("0")) + Decimal(item.amount)
            if len(orders) < 200:
                break
            offset += 200
        return [
            LianxiaoSummary(group=group, amount=amount)
            for group, amount in sorted(grouped.items(), key=lambda row: (-row[1], row[0]))
        ]

    def _fill_tables(self) -> None:
        self._fill_table(self._summary_table, self._summaries, show_empty=True)
        for table in self._tables:
            self._fill_table(table, [], show_empty=False)

        if not self._summaries:
            return

        chunk_count = len(self._tables)
        chunk_size = max(1, (len(self._summaries) + chunk_count - 1) // chunk_count)
        for index, table in enumerate(self._tables):
            start = index * chunk_size
            end = start + chunk_size
            self._fill_table(table, self._summaries[start:end], show_empty=False)

    def _fill_table(
        self,
        table: QTableWidget,
        rows: list[LianxiaoSummary],
        *,
        show_empty: bool,
    ) -> None:
        if not rows and show_empty:
            table.setRowCount(1)
            values = ["暂无数据", "0.00", "0.00"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(0, column, item)
            return

        table.setRowCount(len(rows))
        for row, summary in enumerate(rows):
            values = [summary.group, _money(summary.amount), "0.00"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                alignment = (
                    Qt.AlignmentFlag.AlignCenter
                    if column
                    else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                item.setTextAlignment(alignment)
                table.setItem(row, column, item)

    def _update_stats(self) -> None:
        total = sum((summary.amount for summary in self._summaries), Decimal("0"))
        zero = Decimal("0")
        self._lbl_lianxiao_total.setText(f"连肖总额：{_money(total)}")
        self._lbl_max_profit.setText(f"最大盈利：{_money(zero)}")
        self._lbl_max_loss.setText(f"最大亏损：{_money(zero)}")
        self._lbl_eat_total.setText(f"吃单总额：{_money(total)}")
        self._lbl_adjustment_total.setText(f"调整总额：{_money(zero)}")
        self._lbl_adjusted_max_profit.setText(f"最大盈利：{_money(zero)}")
        self._lbl_adjusted_max_loss.setText(f"最大亏损：{_money(zero)}")

    def _append_output(self, message: str) -> None:
        current = self._output.toPlainText().strip()
        self._output.setPlainText(f"{current}\n{message}".strip())

    def _on_print_adjustment(self) -> None:
        self._append_output("打印功能第一阶段不直接调用打印机；请先复制或导出当前汇总后打印。")

    def _on_clear_output(self) -> None:
        self._output.clear()

    def _on_reset_adjustment(self) -> None:
        self._append_output("已重置当前页面临时调整；数据库订单未被修改。")

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #ffffff;
                color: #263238;
                font-size: 12px;
            }
            QFrame#topFilter {
                border: none;
                background: #ffffff;
                min-height: 24px;
                max-height: 26px;
            }
            QTableWidget {
                border: 1px solid #9fb4b8;
                gridline-color: #d5dfe1;
                alternate-background-color: #f7fafb;
                selection-background-color: #d8eef2;
                selection-color: #1e2e32;
            }
            QHeaderView::section {
                background: #dff2f3;
                padding: 1px 3px;
                border: 1px solid #9fb4b8;
                font-weight: 600;
                min-height: 22px;
                max-height: 24px;
            }
            QFrame#statsPanel {
                border: 1px solid #8f9da1;
                background: #ffffff;
                min-height: 23px;
                max-height: 25px;
            }
            QLabel#statsTitle {
                color: #c0392b;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
                min-width: 90px;
            }
            QLabel#statsValue {
                qproperty-alignment: AlignCenter;
            }
            QFrame#statsSeparator {
                color: #2c3e50;
                max-width: 1px;
            }
            QFrame#actionPanel QPushButton {
                padding: 2px 8px;
                border: 1px solid #b8c7ca;
                border-left: none;
                background: #ffffff;
                min-height: 26px;
                max-height: 30px;
            }
            QFrame#actionPanel QPushButton:first-child {
                border-left: 1px solid #b8c7ca;
            }
            QPushButton:hover {
                background: #e8f7f8;
                border-color: #5fbac2;
            }
            QPlainTextEdit#adjustOutput {
                border: 1px solid #b8c7ca;
                background: #ffffff;
                font-family: Consolas, "Microsoft YaHei", monospace;
            }
            """
        )
