"""连肖调单页面."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.zodiac_config import MAX_ZODIAC_YEAR, MIN_ZODIAC_YEAR, get_default_zodiac_year
from services.adjustment_record_service import AdjustmentRecordService
from services.adjustment_summary_service import AdjustmentSummaryService, LianxiaoSummary, money, normalize_lianxiao_group
from services.order_service import OrderService
from services.risk_adjustment_service import RiskAdjustmentService
from ui.app_events import app_events
from ui.dialogs.adjustment_record_dialog import AdjustmentRecordDialog

TABLE_HEADERS = ["生肖组", "持有", "盈亏"]


class LianxiaoOrderPage(QWidget):
    """Workbench for lianxiao group summary and adjustment output."""

    def __init__(
        self,
        parent=None,
        order_service: OrderService | None = None,
        adjustment_record_service: AdjustmentRecordService | None = None,
        risk_adjustment_service: RiskAdjustmentService | None = None,
    ):
        super().__init__(parent)
        self._order_service = order_service or OrderService()
        session_factory = getattr(self._order_service, "_session_factory", None)
        self._summary_service = AdjustmentSummaryService(session_factory) if session_factory else AdjustmentSummaryService()
        self._adjustment_record_service = adjustment_record_service or (
            AdjustmentRecordService(session_factory) if session_factory else AdjustmentRecordService()
        )
        self._risk_adjustment_service = risk_adjustment_service or (
            RiskAdjustmentService(session_factory) if session_factory else RiskAdjustmentService()
        )
        self._zodiac_year = get_default_zodiac_year()
        self._adjustments: dict[str, Decimal] = {}
        self._active_thrown_amounts: dict[str, Decimal] = {}
        self._summary: LianxiaoSummary | None = None
        self._tables: list[QTableWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_body(), stretch=7)
        root.addWidget(self._build_stats_panel())
        root.addWidget(self._build_adjust_input_bar())
        root.addWidget(self._build_action_panel())

        self._output = QPlainTextEdit()
        self._output.setObjectName("lianxiaoAdjustOutput")
        self._output.setPlaceholderText("连肖调整结果、打印文本和保存提示会显示在这里。")
        root.addWidget(self._output, stretch=3)
        root.addWidget(self._build_bottom_bar())

        self._apply_stylesheet()
        app_events.orders_changed.connect(self.refresh_data)
        self.reload_data()

    def _build_filter_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("filterBar")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 2, 8, 2)
        row.addStretch(1)
        self._region_group = QButtonGroup(self)
        for index, (label, region, checked) in enumerate((("只看澳门", "澳门", True), ("只看香港", "香港", False))):
            radio = QRadioButton(label)
            radio.setProperty("region", region)
            radio.setChecked(checked)
            radio.toggled.connect(lambda checked=False: self.reload_data() if checked else None)
            self._region_group.addButton(radio, index)
            row.addWidget(radio)
        row.addStretch(1)
        row.addWidget(QLabel("生肖年份"))
        self._spin_zodiac_year = QSpinBox()
        self._spin_zodiac_year.setObjectName("lianxiaoAdjustmentZodiacYearSpin")
        self._spin_zodiac_year.setRange(MIN_ZODIAC_YEAR, MAX_ZODIAC_YEAR)
        self._spin_zodiac_year.setValue(self._zodiac_year)
        self._spin_zodiac_year.valueChanged.connect(self._on_zodiac_year_changed)
        row.addWidget(self._spin_zodiac_year)
        return frame

    def _build_body(self) -> QWidget:
        panel = QWidget()
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._summary_table = self._create_table("lianxiaoSummaryTable")
        self._summary_table.setMinimumWidth(260)
        row.addWidget(self._summary_table, stretch=22)
        right = QWidget()
        right_row = QHBoxLayout(right)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(4)
        for index in range(5):
            table = self._create_table(f"lianxiaoListTable{index + 1}")
            self._tables.append(table)
            right_row.addWidget(table, stretch=1)
        row.addWidget(right, stretch=78)
        return panel

    def _create_table(self, object_name: str) -> QTableWidget:
        table = QTableWidget(0, len(TABLE_HEADERS))
        table.setObjectName(object_name)
        table.setHorizontalHeaderLabels(TABLE_HEADERS)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(24)
        return table

    def _build_stats_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        self._lbl_lianxiao_total = QLabel()
        self._lbl_original_max_profit = QLabel()
        self._lbl_original_max_loss = QLabel()
        self._lbl_eat_total = QLabel()
        self._lbl_adjustment_total = QLabel()
        self._lbl_adjusted_max_profit = QLabel()
        self._lbl_adjusted_max_loss = QLabel()
        col.addWidget(
            self._stats_row(
                "原连肖数据",
                self._lbl_lianxiao_total,
                self._lbl_original_max_profit,
                self._lbl_original_max_loss,
            )
        )
        col.addWidget(
            self._stats_row(
                "调整后数据",
                self._lbl_eat_total,
                self._lbl_adjustment_total,
                self._lbl_adjusted_max_profit,
                self._lbl_adjusted_max_loss,
            )
        )
        return panel

    def _stats_row(self, title: str, *labels: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statsPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 2, 8, 2)
        title_label = QLabel(title)
        title_label.setObjectName("statsTitle")
        row.addWidget(title_label)
        for label in labels:
            label.setObjectName("statsValue")
            row.addWidget(label, stretch=1)
        return frame

    def _build_adjust_input_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("adjustInputBar")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 4, 8, 4)
        row.addWidget(QLabel("调整输入"))
        self._adjustment_input = QLineEdit()
        self._adjustment_input.setObjectName("lianxiaoAdjustmentInput")
        self._adjustment_input.setPlaceholderText("狗羊猴=100, 龙羊猴鸡=50")
        self._adjustment_input.returnPressed.connect(self._on_apply_adjustment_input)
        row.addWidget(self._adjustment_input, stretch=1)
        return frame

    def _build_action_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("actionPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        actions = [
            ("打印连肖调整", self._on_print_adjustment),
            ("清空输出框", self._on_clear_output),
            ("重置调整", self._on_reset_adjustment),
        ]
        for text, handler in actions:
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
            if text == "打印连肖调整":
                self._btn_print = button
            elif text == "清空输出框":
                self._btn_clear_output = button
            elif text == "重置调整":
                self._btn_reset = button
        self._btn_save_adjustment = QPushButton("保存本次调整")
        self._btn_save_adjustment.clicked.connect(self._on_save_adjustment)
        row.addWidget(self._btn_save_adjustment)
        row.addStretch(1)
        self._btn_open_extension = QPushButton("打开扩展")
        self._btn_open_extension.clicked.connect(lambda: self._append_output("扩展调单入口已保留，规则确认后可继续接入。"))
        row.addWidget(self._btn_open_extension)
        self._btn_adjust_records = QPushButton("调整记录")
        self._btn_adjust_records.clicked.connect(self._on_adjust_records)
        row.addWidget(self._btn_adjust_records)
        return frame

    def _build_bottom_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("bottomBar")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 2, 8, 2)
        row.addWidget(QLabel("连肖必须有“连”字在其中，一组连肖之间不能有分隔符，组与组之间必须有分隔符。"))
        row.addStretch(1)
        return frame

    def reload_data(self) -> None:
        self._summary_service.set_zodiac_year(self._selected_zodiac_year())
        self._risk_adjustment_service.set_zodiac_year(self._selected_zodiac_year())
        self._active_thrown_amounts = {
            _page_group_key(group): amount
            for group, amount in self._risk_adjustment_service.get_active_lianxiao_throw_amounts(
                region=self._selected_region(),
            ).items()
        }
        self._summary = self._summary_service.summarize_lianxiao(
            region=self._selected_region(),
            adjustments=self._adjustments,
        )
        self._fill_tables()
        self._fill_stats()
        self._append_output(f"已加载{self._selected_region()}连肖汇总：{len(self._summary.rows)} 组。")

    def refresh_data(self) -> None:
        """Reload order summaries and active throws, clearing only temporary edits."""

        self._adjustments.clear()
        if hasattr(self, "_adjustment_input"):
            self._adjustment_input.clear()
        try:
            self.reload_data()
        except Exception as exc:
            self._append_output(f"调单页面刷新失败：{exc}")

    def _selected_region(self) -> str:
        button = self._region_group.checkedButton()
        return str(button.property("region")) if button is not None else "澳门"

    def _selected_zodiac_year(self) -> int:
        return int(self._spin_zodiac_year.value()) if hasattr(self, "_spin_zodiac_year") else self._zodiac_year

    def _on_zodiac_year_changed(self, year: int) -> None:
        self._zodiac_year = int(year)
        self.reload_data()

    def _fill_tables(self) -> None:
        if self._summary is None:
            return
        self._fill_table(self._summary_table, self._summary.rows, show_empty=True)
        for table in self._tables:
            self._fill_table(table, [], show_empty=False)
        if not self._summary.rows:
            return
        chunk_size = max(1, (len(self._summary.rows) + len(self._tables) - 1) // len(self._tables))
        for index, table in enumerate(self._tables):
            start = index * chunk_size
            self._fill_table(table, self._summary.rows[start : start + chunk_size], show_empty=False)

    def _fill_table(self, table: QTableWidget, rows, *, show_empty: bool) -> None:
        if not rows and show_empty:
            table.setRowCount(1)
            values = ["暂无数据", "0.00", "0.00"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(0, column, item)
            return
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            group_key = _page_group_key(row.group)
            thrown = self._active_thrown_amounts.get(group_key, Decimal("0"))
            current_adjustment = self._adjustments.get(row.group, Decimal("0"))
            holding = row.original_amount - thrown - current_adjustment
            values = [row.group, money(holding), money(-holding)]
            tooltip = (
                f"原金额：{money(row.original_amount)}\n"
                f"已抛出金额：{money(thrown)}\n"
                f"当前调整输入：{money(current_adjustment)}\n"
                f"调整后持有金额：{money(holding)}\n"
                f"active 抛出记录：{'有' if thrown else '无'}"
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if column else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(tooltip)
                table.setItem(row_index, column, item)

    def _fill_stats(self) -> None:
        original = self._summary_service.summarize_lianxiao(region=self._selected_region(), adjustments={})
        adjusted = self._summary
        if adjusted is None:
            return
        thrown_total = sum(self._active_thrown_amounts.values(), Decimal("0"))
        current_adjustment_total = sum(self._adjustments.values(), Decimal("0"))
        holding_total = original.original_total - thrown_total - current_adjustment_total
        self._lbl_lianxiao_total.setText(f"连肖总额：{money(original.original_total)}")
        self._lbl_original_max_profit.setText(f"最大盈利：{money(original.max_profit)}")
        self._lbl_original_max_loss.setText(f"最大亏损：{money(original.max_loss)}")
        self._lbl_eat_total.setText(f"持有总额：{money(holding_total)}")
        self._lbl_adjustment_total.setText(f"已抛/本次：{money(thrown_total)} / {money(current_adjustment_total)}")
        self._lbl_adjusted_max_profit.setText(f"最大盈利：{money(adjusted.max_profit)}")
        self._lbl_adjusted_max_loss.setText(f"最大亏损：{money(adjusted.max_loss)}")

    def _on_apply_adjustment_input(self) -> None:
        try:
            parsed = self._summary_service.parse_lianxiao_adjustments(self._adjustment_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "调整输入", str(exc))
            return
        self._adjustments.update(parsed)
        self.reload_data()
        self._append_output("已应用连肖调整输入：\n" + "\n".join(f"{key}={money(value)}" for key, value in sorted(parsed.items())))

    def _on_print_adjustment(self) -> None:
        self._output.setPlainText(self._build_print_text())

    def _build_print_text(self) -> str:
        if self._summary is None:
            return "暂无连肖调整数据。"
        lines = [
            "连肖调整",
            f"地区：{self._selected_region()}",
            f"生肖年份：{self._selected_zodiac_year()}",
            "",
            "生肖组\t原金额\t已抛\t当前调整\t调整后持有\t盈亏",
        ]
        for row in self._summary.rows:
            group_key = _page_group_key(row.group)
            thrown = self._active_thrown_amounts.get(group_key, Decimal("0"))
            current_adjustment = self._adjustments.get(row.group, Decimal("0"))
            holding = row.original_amount - thrown - current_adjustment
            lines.append(
                "\t".join(
                    [
                        row.group,
                        money(row.original_amount),
                        money(thrown),
                        money(current_adjustment),
                        money(holding),
                        money(-holding),
                    ]
                )
            )
        lines.extend(
            [
                "",
                self._lbl_lianxiao_total.text(),
                self._lbl_adjustment_total.text(),
                self._lbl_eat_total.text(),
            ]
        )
        return "\n".join(lines)

    def _on_clear_output(self) -> None:
        self._output.clear()

    def _on_reset_adjustment(self) -> None:
        self._adjustments.clear()
        self._adjustment_input.clear()
        self.reload_data()
        self._append_output("已清空调整金额，保留原始订单汇总。")

    def _on_save_adjustment(self) -> None:
        if self._summary is None or not self._adjustments:
            self._append_output("当前没有连肖调整内容，无需保存。")
            return
        try:
            result = self._risk_adjustment_service.apply_lianxiao_adjustments(
                self._adjustments,
                region=self._selected_region(),
                reason="连肖调单",
            )
        except Exception as exc:
            QMessageBox.warning(self, "保存本次调整", f"保存失败：{exc}")
            self._append_output(f"保存失败：{exc}")
            return
        saved_count = result.record.item_count
        saved_total = result.record.adjustment_total
        self._adjustments.clear()
        self._adjustment_input.clear()
        self.reload_data()
        app_events.logs_changed.emit()
        self._append_output(
            "已保存本次连肖调单抛出记录：\n"
            f"记录 ID：{result.record.id}\n"
            f"操作日志 ID：{result.operation_log_id}\n"
            f"地区：{result.record.region}\n"
            f"调整类型：{result.record.adjustment_type}\n"
            f"调整数：{saved_count}\n"
            f"总调整金额：{saved_total}\n"
            "历史订单和结算记录未被修改，可在“调整记录”中查看或撤销。"
        )

    def _on_adjust_records(self) -> None:
        dialog = AdjustmentRecordDialog(
            self,
            default_type="lianxiao_all",
            service=self._adjustment_record_service,
            risk_service=self._risk_adjustment_service,
        )
        dialog.exec()

    def _append_output(self, message: str) -> None:
        current = self._output.toPlainText().strip() if hasattr(self, "_output") else ""
        self._output.setPlainText(f"{current}\n{message}".strip())

    def _decimal_from_text(self, text: str) -> Decimal:
        try:
            value = Decimal(str(text).strip() or "0")
        except (InvalidOperation, ValueError):
            return Decimal("0")
        return value if value.is_finite() else Decimal("0")

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #ffffff; color: #263238; font-size: 12px; }
            QFrame#filterBar, QFrame#statsPanel, QFrame#adjustInputBar, QFrame#bottomBar {
                border: 1px solid #9fb4b8;
                background: #fbfefe;
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
                padding: 2px 4px;
                border: 1px solid #9fb4b8;
                font-weight: 600;
            }
            QLabel#statsTitle {
                color: #c0392b;
                font-weight: 700;
                min-width: 90px;
            }
            QLabel#statsValue { qproperty-alignment: AlignCenter; }
            QLineEdit {
                min-height: 23px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QPushButton {
                padding: 5px 10px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QPushButton:hover { background: #e8f7f8; border-color: #5fbac2; }
            QPlainTextEdit {
                border: 1px solid #b8c7ca;
                background: #ffffff;
                font-family: Consolas, "Microsoft YaHei", monospace;
            }
            """
        )


def _page_group_key(group: str) -> str:
    text = str(group)
    tokens = [token for token in text.split(",") if token] if "," in text else list(text)
    return normalize_lianxiao_group(tokens)
