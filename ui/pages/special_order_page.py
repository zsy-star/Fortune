"""特码调单页面."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.color_rules import get_wave_color
from domain.zodiac_config import MAX_ZODIAC_YEAR, MIN_ZODIAC_YEAR, get_default_zodiac_year
from services.adjustment_record_service import AdjustmentRecordService
from services.adjustment_summary_service import AdjustmentSummaryService, TemaSummary, money
from services.order_service import OrderService
from services.risk_adjustment_service import RiskAdjustmentService
from ui.app_events import app_events
from ui.dialogs.adjustment_record_dialog import AdjustmentRecordDialog

WAVE_TEXT_COLORS = {"红波": "#d93636", "蓝波": "#1f66d1", "绿波": "#1f8f4d"}
NUMBER_BLOCKS = [
    ["49", *[f"{value:02d}" for value in range(1, 13)]],
    [f"{value:02d}" for value in range(13, 25)],
    [f"{value:02d}" for value in range(25, 37)],
    [f"{value:02d}" for value in range(37, 49)],
]
NUMBER_BLOCK_TITLES = ("49 / 01-12", "13-24", "25-36", "37-48")


class SpecialOrderPage(QWidget):
    """Workbench for special-number risk summary and manual adjustment."""

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
        self._summary: TemaSummary | None = None
        self._original_edits: dict[str, QLineEdit] = {}
        self._adjust_edits: dict[str, QLineEdit] = {}
        self._total_edits: dict[str, QLineEdit] = {}
        self._number_labels: dict[str, QLabel] = {}
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        root.addWidget(self._build_filter_bar())

        body = QHBoxLayout()
        body.setSpacing(4)
        body.addWidget(self._build_summary_table())

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)
        right.addWidget(self._build_number_grid(), stretch=0)
        right.addWidget(self._build_stats_panel())
        right.addWidget(self._build_adjust_panel())
        right.addWidget(self._build_action_panel())

        self._output = QPlainTextEdit()
        self._output.setObjectName("temaAdjustOutput")
        self._output.setPlaceholderText("调单结果、建议抛出金额和保存提示会显示在这里。")
        right.addWidget(self._output, stretch=1)
        body.addLayout(right, stretch=1)
        root.addLayout(body, stretch=1)
        root.addWidget(self._build_bottom_bar())

        self._apply_stylesheet()
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
        self._spin_zodiac_year.setObjectName("specialAdjustmentZodiacYearSpin")
        self._spin_zodiac_year.setRange(MIN_ZODIAC_YEAR, MAX_ZODIAC_YEAR)
        self._spin_zodiac_year.setValue(self._zodiac_year)
        self._spin_zodiac_year.valueChanged.connect(self._on_zodiac_year_changed)
        row.addWidget(self._spin_zodiac_year)
        return frame

    def _build_summary_table(self) -> QTableWidget:
        self._summary_table = QTableWidget(49, 4)
        self._summary_table.setObjectName("specialSummaryTable")
        self._summary_table.setHorizontalHeaderLabels(["号码", "下注数", "盈亏", "ID"])
        self._summary_table.setFixedWidth(276)
        self._summary_table.verticalHeader().setVisible(False)
        self._summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._summary_table.setAlternatingRowColors(True)
        self._summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._summary_table.setColumnWidth(0, 72)
        self._summary_table.setColumnWidth(1, 70)
        self._summary_table.setColumnWidth(2, 70)
        self._summary_table.setColumnWidth(3, 42)
        self._summary_table.verticalHeader().setDefaultSectionSize(20)
        return self._summary_table

    def _build_number_grid(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("numberGrid")
        grid = QGridLayout(frame)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(3)
        grid.setVerticalSpacing(2)
        headers = ("号码", "原金额", "调整", "总计")
        for block_index in range(4):
            base = block_index * 4
            group_label = QLabel(NUMBER_BLOCK_TITLES[block_index])
            group_label.setObjectName("numberGroupTitle")
            group_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(group_label, 0, base, 1, 4)
            for offset, text in enumerate(headers):
                label = QLabel(text)
                label.setObjectName("gridHeader")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(label, 1, base + offset)
            grid.setColumnMinimumWidth(base, 38)
            grid.setColumnMinimumWidth(base + 1, 64)
            grid.setColumnMinimumWidth(base + 2, 64)
            grid.setColumnMinimumWidth(base + 3, 64)

        for block_index, numbers in enumerate(NUMBER_BLOCKS):
            base = block_index * 4
            for row_index, number in enumerate(numbers, start=2):
                number_label = QLabel(number)
                number_label.setObjectName("numberBadge")
                number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                number_label.setFixedWidth(38)
                original = self._readonly_edit()
                adjust = QLineEdit()
                adjust.setObjectName(f"temaAdjust{number}")
                adjust.setAlignment(Qt.AlignmentFlag.AlignCenter)
                adjust.setFixedWidth(64)
                total = self._readonly_edit()
                adjust.editingFinished.connect(lambda n=number: self._on_adjust_edit_finished(n))
                grid.addWidget(number_label, row_index, base)
                grid.addWidget(original, row_index, base + 1)
                grid.addWidget(adjust, row_index, base + 2)
                grid.addWidget(total, row_index, base + 3)
                self._number_labels[number] = number_label
                self._original_edits[number] = original
                self._adjust_edits[number] = adjust
                self._total_edits[number] = total
        return frame

    def _readonly_edit(self) -> QLineEdit:
        edit = QLineEdit("0.00")
        edit.setReadOnly(True)
        edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit.setFixedWidth(64)
        return edit

    def _build_stats_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        self._lbl_original_total = QLabel()
        self._lbl_original_max_profit = QLabel()
        self._lbl_original_max_loss = QLabel()
        self._lbl_original_profit_count = QLabel()
        self._lbl_original_loss_count = QLabel()
        self._lbl_eat_total = QLabel()
        self._lbl_adjustment_total = QLabel()
        self._lbl_adjusted_max_profit = QLabel()
        self._lbl_adjusted_max_loss = QLabel()
        self._lbl_adjusted_profit_count = QLabel()
        self._lbl_adjusted_loss_count = QLabel()
        col.addWidget(
            self._stats_row(
                "原特码数据",
                self._lbl_original_total,
                self._lbl_original_max_profit,
                self._lbl_original_max_loss,
                self._lbl_original_profit_count,
                self._lbl_original_loss_count,
            )
        )
        col.addWidget(
            self._stats_row(
                "调整后数据",
                self._lbl_eat_total,
                self._lbl_adjustment_total,
                self._lbl_adjusted_max_profit,
                self._lbl_adjusted_max_loss,
                self._lbl_adjusted_profit_count,
                self._lbl_adjusted_loss_count,
            )
        )
        return panel

    def _stats_row(self, title: str, *labels: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statsPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 1, 8, 1)
        title_label = QLabel(title)
        title_label.setObjectName("statsTitle")
        row.addWidget(title_label)
        for label in labels:
            label.setObjectName("statsValue")
            row.addWidget(label, stretch=1)
        return frame

    def _build_adjust_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("adjustPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 3, 8, 3)
        row.addWidget(QLabel("最大亏损"))
        self._max_loss_edit = QLineEdit()
        self._max_loss_edit.setObjectName("temaMaxLossInput")
        self._max_loss_edit.setPlaceholderText("例如 1000")
        self._max_loss_edit.setFixedWidth(96)
        self._max_loss_edit.returnPressed.connect(self._on_generate_suggestion)
        row.addWidget(self._max_loss_edit)
        row.addWidget(QLabel("调整额"))
        self._adjustment_input = QLineEdit()
        self._adjustment_input.setObjectName("temaAdjustmentInput")
        self._adjustment_input.setPlaceholderText("12=100, 25=50, 37=200")
        self._adjustment_input.returnPressed.connect(self._on_apply_adjustment_input)
        row.addWidget(self._adjustment_input, stretch=3)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setObjectName("temaAdjustmentSlider")
        self._slider.setRange(0, 5000)
        self._slider.setSingleStep(10)
        self._slider.valueChanged.connect(lambda value: self._slider_value_label.setText(str(value)))
        row.addWidget(self._slider, stretch=2)
        self._slider_value_label = QLabel("0")
        self._slider_value_label.setObjectName("sliderValue")
        self._slider_value_label.setFixedWidth(42)
        row.addWidget(self._slider_value_label)
        return frame

    def _build_action_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("actionPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        actions = [
            ("保存本次调整", self._on_save_adjustment),
            ("调整为10的倍数", self._on_round_to_tens),
            ("清空当前调单", self._on_clear_adjustments),
            ("清空输出框", self._on_clear_output),
            ("重置所有数据", self._on_reset_all_data),
            ("结码总奖", self._on_special_settlement),
        ]
        for text, handler in actions:
            button = QPushButton(text)
            button.clicked.connect(handler)
            button.setMinimumWidth(92)
            row.addWidget(button)
            if text == "保存本次调整":
                self._btn_save_adjustment = button
            elif text == "调整为10的倍数":
                self._btn_round_to_tens = button
            elif text == "清空当前调单":
                self._btn_clear_adjustments = button
            elif text == "清空输出框":
                self._btn_clear_output = button
            elif text == "重置所有数据":
                self._btn_reset_all = button
            elif text == "结码总奖":
                self._btn_special_settlement = button
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
        row.addWidget(QLabel("输出输入框"))
        row.addStretch(1)
        row.addWidget(QLabel("调整类型：多个数字多加“，”字，此处“各”按赔率批量处理"))
        return frame

    def reload_data(self) -> None:
        self._summary_service.set_zodiac_year(self._selected_zodiac_year())
        self._risk_adjustment_service.set_zodiac_year(self._selected_zodiac_year())
        self._summary = self._summary_service.summarize_tema(
            region=self._selected_region(),
            adjustments=self._adjustments,
        )
        self._fill_summary_table()
        self._fill_number_grid()
        self._fill_stats()
        self._append_output(
            f"已加载{self._selected_region()}特码汇总："
            f"{sum(1 for row in self._summary.rows if row.original_amount > 0)} 个号码有下注。"
        )

    def _selected_region(self) -> str:
        button = self._region_group.checkedButton()
        return str(button.property("region")) if button is not None else "澳门"

    def _selected_zodiac_year(self) -> int:
        return int(self._spin_zodiac_year.value()) if hasattr(self, "_spin_zodiac_year") else self._zodiac_year

    def _on_zodiac_year_changed(self, year: int) -> None:
        self._zodiac_year = int(year)
        self.reload_data()

    def _fill_summary_table(self) -> None:
        if self._summary is None:
            return
        self._summary_table.setRowCount(len(self._summary.rows))
        for row_index, row in enumerate(self._summary.rows):
            values = [f"{row.zodiac}{row.number}", money(row.original_amount), money(row.profit_loss), str(row.row_id)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 0:
                    item.setForeground(QColor(self._number_color(row.number)))
                self._summary_table.setItem(row_index, column, item)

    def _fill_number_grid(self) -> None:
        if self._summary is None:
            return
        self._loading = True
        try:
            by_number = {row.number: row for row in self._summary.rows}
            for number, row in by_number.items():
                self._number_labels[number].setText(number)
                self._number_labels[number].setStyleSheet(f"color: {self._number_color(number)}; font-weight: 700;")
                self._original_edits[number].setText(money(row.original_amount))
                self._adjust_edits[number].setText("" if row.adjustment_amount == 0 else money(row.adjustment_amount))
                self._total_edits[number].setText(money(row.total_amount))
        finally:
            self._loading = False

    def _fill_stats(self) -> None:
        original = self._summary_service.summarize_tema(region=self._selected_region(), adjustments={})
        adjusted = self._summary
        if adjusted is None:
            return
        self._lbl_original_total.setText(f"特码总数：{money(original.original_total)}")
        self._lbl_original_max_profit.setText(f"最大盈利：{money(original.max_profit)}")
        self._lbl_original_max_loss.setText(f"最大亏损：{money(original.max_loss)}")
        self._lbl_original_profit_count.setText(f"盈利数量：{original.profit_count}")
        self._lbl_original_loss_count.setText(f"亏损数量：{original.loss_count}")
        self._lbl_eat_total.setText(f"吃单总数：{money(adjusted.after_total)}")
        self._lbl_adjustment_total.setText(f"调整总额：{money(adjusted.adjustment_total)}")
        self._lbl_adjusted_max_profit.setText(f"最大盈利：{money(adjusted.max_profit)}")
        self._lbl_adjusted_max_loss.setText(f"最大亏损：{money(adjusted.max_loss)}")
        self._lbl_adjusted_profit_count.setText(f"盈利数量：{adjusted.profit_count}")
        self._lbl_adjusted_loss_count.setText(f"亏损数量：{adjusted.loss_count}")

    def _on_adjust_edit_finished(self, number: str) -> None:
        if self._loading:
            return
        value = self._decimal_from_text(self._adjust_edits[number].text())
        if value == 0:
            self._adjustments.pop(number, None)
        else:
            self._adjustments[number] = value
        self.reload_data()

    def _on_apply_adjustment_input(self) -> None:
        try:
            parsed = self._summary_service.parse_tema_adjustments(self._adjustment_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "调整额", str(exc))
            return
        self._adjustments.update(parsed)
        self.reload_data()
        self._append_output("已应用调整输入：\n" + "\n".join(f"{key}={money(value)}" for key, value in sorted(parsed.items())))

    def _on_generate_suggestion(self) -> None:
        if self._summary is None:
            return
        try:
            suggestions = self._summary_service.suggest_tema_adjustments(self._summary.rows, self._max_loss_edit.text())
        except ValueError as exc:
            QMessageBox.warning(self, "最大亏损", str(exc))
            return
        self._adjustments.update(suggestions)
        self.reload_data()
        text = "\n".join(f"{number}={money(amount)}" for number, amount in sorted(suggestions.items()))
        self._output.setPlainText(text or "当前没有超过最大亏损的号码。")

    def _on_round_to_tens(self) -> None:
        self._adjustments = self._summary_service.round_adjustments_to_tens(self._adjustments)
        self.reload_data()
        self._append_output("已将当前调整金额处理为 10 的倍数。")

    def _on_clear_adjustments(self) -> None:
        self._adjustments.clear()
        self._adjustment_input.clear()
        self.reload_data()
        self._append_output("已清空当前调单，原始订单汇总保留。")

    def _on_clear_output(self) -> None:
        self._output.clear()

    def _on_reset_all_data(self) -> None:
        self._adjustments.clear()
        self._adjustment_input.clear()
        self.reload_data()
        self._append_output("已重新从订单数据计算原始汇总，并清空调整。")

    def _on_special_settlement(self) -> None:
        self._append_output("结码总奖入口已保留；本页面只做调单汇总和调整记录，不执行结算入账。")

    def _on_save_adjustment(self) -> None:
        if self._summary is None or not self._adjustments:
            self._append_output("当前没有调整内容，无需保存。")
            return
        try:
            result = self._risk_adjustment_service.apply_special_adjustments(
                self._adjustments,
                region=self._selected_region(),
                reason="特码调单",
            )
        except Exception as exc:
            QMessageBox.warning(self, "保存本次调整", f"保存失败：{exc}")
            self._append_output(f"保存失败：{exc}")
            return
        app_events.logs_changed.emit()
        self._append_output(
            "已保存本次特码调单抛出记录：\n"
            f"记录 ID：{result.record.id}\n"
            f"操作日志 ID：{result.operation_log_id}\n"
            f"地区：{result.record.region}\n"
            f"调整金额：{result.record.adjustment_total}\n"
            "历史订单和结算记录未被修改，可在“调整记录”中查看或撤销。"
        )

    def _on_adjust_records(self) -> None:
        dialog = AdjustmentRecordDialog(
            self,
            default_type="special_all",
            service=self._adjustment_record_service,
            risk_service=self._risk_adjustment_service,
        )
        dialog.exec()

    def _append_output(self, message: str) -> None:
        current = self._output.toPlainText().strip() if hasattr(self, "_output") else ""
        self._output.setPlainText(f"{current}\n{message}".strip())

    def _number_color(self, number: str) -> str:
        try:
            return WAVE_TEXT_COLORS.get(get_wave_color(number), "#263238")
        except Exception:
            return "#263238"

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
            QFrame#filterBar, QFrame#numberGrid, QFrame#statsPanel, QFrame#adjustPanel, QFrame#bottomBar {
                border: 1px solid #9fb4b8;
                background: #fbfefe;
            }
            QFrame#filterBar, QFrame#bottomBar {
                min-height: 24px;
                max-height: 28px;
            }
            QLabel#numberGroupTitle {
                background: #eef8f9;
                border: 1px solid #9fb4b8;
                color: #2c3e50;
                font-weight: 700;
                min-height: 18px;
                max-height: 20px;
            }
            QLabel#gridHeader {
                background: #dff2f3;
                border: 1px solid #9fb4b8;
                font-weight: 600;
                min-height: 20px;
                max-height: 22px;
            }
            QLabel#statsTitle {
                color: #c0392b;
                font-weight: 700;
                min-width: 86px;
            }
            QLabel#statsValue { qproperty-alignment: AlignCenter; }
            QTableWidget {
                border: 1px solid #9fb4b8;
                gridline-color: #d5dfe1;
                alternate-background-color: #f7fafb;
                selection-background-color: #d8eef2;
                selection-color: #1e2e32;
            }
            QHeaderView::section {
                background: #dff2f3;
                padding: 2px 3px;
                border: 1px solid #9fb4b8;
                font-weight: 600;
            }
            QLineEdit {
                min-height: 20px;
                max-height: 22px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QLineEdit:read-only { background: #f6f8f8; color: #50636a; }
            QPushButton {
                padding: 3px 10px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
                min-height: 24px;
                max-height: 28px;
            }
            QPushButton:hover { background: #e8f7f8; border-color: #5fbac2; }
            QPlainTextEdit {
                border: 1px solid #b8c7ca;
                background: #ffffff;
                font-family: Consolas, "Microsoft YaHei", monospace;
            }
            """
        )
