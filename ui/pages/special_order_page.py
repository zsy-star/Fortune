"""特码调单页面：汇总调整并保存调单快照记录。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.color_rules import get_wave_color
from domain.number_rules import normalize_number
from domain.zodiac_rules import get_zodiac
from schemas.adjustment_record_schema import AdjustmentRecordCreate
from services.adjustment_record_service import AdjustmentRecordService
from services.order_service import OrderService
from ui.app_events import app_events
from ui.dialogs.adjustment_record_dialog import AdjustmentRecordDialog

SPECIAL_BET_TYPES = {"特码", "号码", "单号投注", "纯数字"}
WAVE_TEXT_COLORS = {
    "红波": "#e74c3c",
    "蓝波": "#2e86de",
    "绿波": "#27ae60",
}


@dataclass(frozen=True, slots=True)
class NumberSummary:
    number: str
    amount: Decimal
    row_id: int


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _decimal_from_text(text: str) -> Decimal:
    stripped = text.strip()
    if not stripped:
        return Decimal("0")
    try:
        value = Decimal(stripped)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    if not value.is_finite():
        return Decimal("0")
    return value


class SpecialOrderPage(QWidget):
    """特码调单主页面。

    当前只读取现有订单做汇总，并可保存调单快照记录；不修改原订单、不自动兑奖。
    """

    def __init__(
        self,
        parent=None,
        order_service: OrderService | None = None,
        adjustment_record_service: AdjustmentRecordService | None = None,
    ):
        super().__init__(parent)
        self._order_service = order_service or OrderService()
        session_factory = getattr(self._order_service, "_session_factory", None)
        self._adjustment_record_service = adjustment_record_service or (
            AdjustmentRecordService(session_factory) if session_factory is not None else AdjustmentRecordService()
        )
        self._number_rows: dict[str, NumberSummary] = {}
        self._number_labels: dict[str, QLabel] = {}
        self._original_edits: dict[str, QLineEdit] = {}
        self._adjust_edits: dict[str, QLineEdit] = {}
        self._total_edits: dict[str, QLineEdit] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        body = QHBoxLayout()
        body.setSpacing(4)
        body.addWidget(self._build_summary_table(), stretch=2)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(self._build_header())
        right.addWidget(self._build_number_grid(), stretch=7)
        body.addLayout(right, stretch=8)
        root.addLayout(body, stretch=8)

        root.addWidget(self._build_stats_panel())
        root.addWidget(self._build_action_panel())
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("操作提示和临时调整结果会显示在这里。")
        root.addWidget(self._output, stretch=2)

        self._apply_stylesheet()
        self.reload_data()

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("topFilter")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 4, 8, 4)
        row.addWidget(QLabel("特码调单（保存调单记录，不修改订单、不自动结算）"))
        row.addStretch(1)
        self._region_group = QButtonGroup(self)
        specs = [("全部", None, True), ("只看澳门", "澳门", False), ("只看香港", "香港", False)]
        for idx, (label, value, checked) in enumerate(specs):
            rb = QRadioButton(label)
            rb.setChecked(checked)
            rb.setProperty("region", value)
            rb.toggled.connect(lambda checked=False: self.reload_data() if checked else None)
            self._region_group.addButton(rb, idx)
            row.addWidget(rb)
        return frame

    def _build_summary_table(self) -> QTableWidget:
        self._summary_table = QTableWidget(49, 4)
        self._summary_table.setObjectName("specialSummaryTable")
        self._summary_table.setHorizontalHeaderLabels(["号码", "下注数", "盈亏", "ID"])
        self._summary_table.verticalHeader().setVisible(False)
        self._summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._summary_table.setAlternatingRowColors(True)
        self._summary_table.setMinimumWidth(250)
        self._summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._summary_table.verticalHeader().setDefaultSectionSize(22)
        return self._summary_table

    def _build_number_grid(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("numberGrid")
        grid = QGridLayout(frame)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)

        columns = 4
        rows_per_column = 13
        headers = ("号码", "原金额", "调整", "总计")
        for column in range(columns):
            base = column * 4
            for offset, text in enumerate(headers):
                header = QLabel(text)
                header.setObjectName("gridHeader")
                header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(header, 0, base + offset)

        for number in range(1, 50):
            display = f"{number:02d}"
            column = (number - 1) // rows_per_column
            row = (number - 1) % rows_per_column + 1
            base = column * 4

            number_label = QLabel(self._number_label_text(display))
            number_label.setObjectName("numberBadge")
            number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            number_label.setStyleSheet(f"color: {self._wave_text_color(display)}; font-weight: 700;")
            original = QLineEdit("0.00")
            original.setReadOnly(True)
            original.setAlignment(Qt.AlignmentFlag.AlignCenter)
            adjust = QLineEdit("")
            adjust.setAlignment(Qt.AlignmentFlag.AlignCenter)
            total = QLineEdit("0.00")
            total.setReadOnly(True)
            total.setAlignment(Qt.AlignmentFlag.AlignCenter)
            adjust.textChanged.connect(lambda _text="", n=display: self._update_number_total(n))

            grid.addWidget(number_label, row, base)
            grid.addWidget(original, row, base + 1)
            grid.addWidget(adjust, row, base + 2)
            grid.addWidget(total, row, base + 3)
            self._number_labels[display] = number_label
            self._original_edits[display] = original
            self._adjust_edits[display] = adjust
            self._total_edits[display] = total
        return frame

    def _build_stats_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        self._lbl_original_total = QLabel()
        self._lbl_adjusted_total = QLabel()
        self._lbl_adjustment_total = QLabel()
        self._lbl_special_total = QLabel()
        self._lbl_max_profit = QLabel()
        self._lbl_max_loss = QLabel()
        self._lbl_profit_count = QLabel()
        self._lbl_loss_count = QLabel()
        col.addWidget(
            self._stats_row(
                "原特码数据",
                self._lbl_special_total,
                self._lbl_max_profit,
                self._lbl_max_loss,
                self._lbl_profit_count,
                self._lbl_loss_count,
            )
        )
        col.addWidget(
            self._stats_row(
                "调整后数据",
                self._lbl_adjusted_total,
                self._lbl_adjustment_total,
                QLabel(""),
                QLabel(""),
                QLabel(""),
            )
        )
        return panel

    def _stats_row(self, title: str, *labels: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statsPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 3, 8, 3)
        title_label = QLabel(title)
        title_label.setObjectName("statsTitle")
        row.addWidget(title_label)
        for label in labels:
            row.addWidget(label)
            row.addStretch(1)
        return frame

    def _build_action_panel(self) -> QFrame:
        frame = QFrame()
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        actions = [
            ("保存本次调整", self._on_save_adjustment),
            ("调整成为 10 的倍数", self._on_round_to_tens),
            ("清空当前调整", self._on_clear_adjustments),
            ("清空输出框", self._on_clear_output),
            ("复制当前汇总", self._on_copy_summary),
            ("导出当前汇总", self._on_export_summary),
            ("重置所有数据", self._on_reset_all_data),
            ("特码兑奖", self._on_special_settlement),
        ]
        for text, handler in actions:
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
            if text == "保存本次调整":
                self._btn_save_adjustment = button
                button.setToolTip("保存本次页面调整为调单快照记录；不修改原订单、不自动兑奖、不写余额。")
            elif text == "复制当前汇总":
                self._btn_copy_summary = button
                button.setToolTip("复制当前特码调单汇总文本，不修改订单。")
            elif text == "导出当前汇总":
                self._btn_export_summary = button
                button.setToolTip("导出当前特码调单汇总文本，不修改订单。")
            elif text == "重置所有数据":
                self._btn_reset_all = button
                button.setEnabled(False)
                button.setToolTip("高风险维护入口：清空或重置数据需要权限、审计和恢复策略，当前不开放。")
                button.setStatusTip("不会清空订单、调单记录或数据库。")
            elif text == "特码兑奖":
                self._btn_special_settlement = button
                button.setEnabled(False)
                button.setToolTip("真实兑奖入账不属于当前产品范围；请使用订单详情查看结算预览、正式结算记录和中奖金额快照。")
                button.setStatusTip("特码调单页只保存调单快照，不执行付款、不写余额。")
        row.addStretch(1)
        self._btn_open_extension = QPushButton("打开拓展")
        self._btn_open_extension.clicked.connect(self._on_open_extension)
        self._btn_open_extension.setEnabled(False)
        self._btn_open_extension.setToolTip("拓展调单规则尚未确认，当前不开放额外调单扩展。")
        self._btn_open_extension.setStatusTip("不会打开新页面或执行额外业务。")
        row.addWidget(self._btn_open_extension)
        self._btn_adjust_records = QPushButton("调整记录")
        self._btn_adjust_records.clicked.connect(self._on_adjust_records)
        self._btn_adjust_records.setToolTip("查看已保存的特码调单快照记录；不提供删除、恢复或重新应用。")
        row.addWidget(self._btn_adjust_records)
        return frame

    def reload_data(self) -> None:
        self._number_rows = self._load_number_summary()
        self._fill_summary_table()
        self._fill_number_grid()
        self._update_stats()
        active_count = sum(1 for summary in self._number_rows.values() if summary.amount > 0)
        if active_count:
            self._append_output(f"已加载特码汇总：{active_count} 个号码。")
        else:
            self._append_output("暂无数据：当前筛选条件下没有可汇总的特码订单明细。")

    def _selected_region(self) -> str | None:
        button = self._region_group.checkedButton()
        return button.property("region") if button is not None else None

    def _load_number_summary(self) -> dict[str, NumberSummary]:
        amounts = {f"{number:02d}": Decimal("0") for number in range(1, 50)}
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
                    if item.bet_type not in SPECIAL_BET_TYPES:
                        continue
                    for token in item.selection.replace("，", ",").replace("、", ",").split(","):
                        token = token.strip()
                        if not token:
                            continue
                        try:
                            number = normalize_number(token)
                        except Exception:
                            continue
                        amounts[number] += Decimal(item.amount)
            if len(orders) < 200:
                break
            offset += 200
        return {
            number: NumberSummary(number=number, amount=amount, row_id=index)
            for index, (number, amount) in enumerate(amounts.items(), start=1)
        }

    def _fill_summary_table(self) -> None:
        rows = [self._number_rows[f"{number:02d}"] for number in range(1, 50)]
        self._summary_table.setRowCount(len(rows))
        for row, summary in enumerate(rows):
            values = [summary.number, _money(summary.amount), "0.00", str(summary.row_id)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 0:
                    item.setForeground(QColor(self._wave_text_color(summary.number)))
                    item.setToolTip(f"{summary.number} / {self._number_zodiac(summary.number)} / {get_wave_color(summary.number)}")
                self._summary_table.setItem(row, column, item)

    def _fill_number_grid(self) -> None:
        for number in range(1, 50):
            key = f"{number:02d}"
            amount = self._number_rows.get(key, NumberSummary(key, Decimal("0"), number)).amount
            self._original_edits[key].setText(_money(amount))
            if not self._adjust_edits[key].text().strip():
                self._total_edits[key].setText(_money(amount))
            else:
                self._update_number_total(key)

    def _update_number_total(self, number: str) -> None:
        original = _decimal_from_text(self._original_edits[number].text())
        adjustment = _decimal_from_text(self._adjust_edits[number].text())
        self._total_edits[number].setText(_money(original + adjustment))
        self._update_stats()

    def _update_stats(self) -> None:
        original_total = sum(_decimal_from_text(edit.text()) for edit in self._original_edits.values())
        adjustment_total = sum(_decimal_from_text(edit.text()) for edit in self._adjust_edits.values())
        adjusted_total = original_total + adjustment_total
        totals = [_decimal_from_text(edit.text()) for edit in self._total_edits.values()]
        non_zero = [value for value in totals if value != 0]
        max_value = max(non_zero) if non_zero else Decimal("0")
        min_value = min(non_zero) if non_zero else Decimal("0")
        profit_count = sum(1 for value in totals if value > 0)
        loss_count = sum(1 for value in totals if value < 0)
        self._lbl_original_total.setText(f"原特码数据：{_money(original_total)}")
        self._lbl_adjusted_total.setText(f"调整后数据：{_money(adjusted_total)}")
        self._lbl_adjustment_total.setText(f"调整金额：{_money(adjustment_total)}")
        self._lbl_special_total.setText(f"特码总额：{_money(original_total)}")
        self._lbl_max_profit.setText(f"最大盈利：{_money(max_value)}")
        self._lbl_max_loss.setText(f"最大亏损：{_money(min_value)}")
        self._lbl_profit_count.setText(f"盈利数量：{profit_count}")
        self._lbl_loss_count.setText(f"亏损数量：{loss_count}")

    def _append_output(self, message: str) -> None:
        current = self._output.toPlainText().strip()
        self._output.setPlainText(f"{current}\n{message}".strip())

    def _selected_region_label(self) -> str:
        return self._selected_region() or "全部"

    def _build_export_text(self) -> str:
        lines = [
            "特码调单汇总",
            f"当前筛选区域：{self._selected_region_label()}",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "左侧号码汇总表",
            "号码\t下注数\t盈亏\tID",
        ]
        for row in range(self._summary_table.rowCount()):
            values = [
                self._summary_table.item(row, column).text()
                if self._summary_table.item(row, column) is not None
                else ""
                for column in range(4)
            ]
            lines.append("\t".join(values))

        lines.extend(["", "右侧 01-49 调整区", "号码\t原金额\t调整\t总计"])
        for number in range(1, 50):
            key = f"{number:02d}"
            lines.append(
                "\t".join(
                    [
                        key,
                        self._original_edits[key].text().strip() or "0.00",
                        self._adjust_edits[key].text().strip() or "0.00",
                        self._total_edits[key].text().strip() or "0.00",
                    ]
                )
            )

        lines.extend(
            [
                "",
                "原特码数据统计",
                self._lbl_special_total.text(),
                self._lbl_max_profit.text(),
                self._lbl_max_loss.text(),
                self._lbl_profit_count.text(),
                self._lbl_loss_count.text(),
                "",
                "调整后数据统计",
                self._lbl_adjusted_total.text(),
                self._lbl_adjustment_total.text(),
                "",
                "安全说明",
                "保存调整仅写入调单记录",
                "不修改订单",
                "不自动结算或兑奖",
                "未计算真实赔付",
                "不写余额",
            ]
        )
        return "\n".join(lines)

    def _on_copy_summary(self) -> None:
        QApplication.clipboard().setText(self._build_export_text())
        self._append_output("已复制特码调单汇总到剪贴板。")

    def _on_export_summary(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出特码调单汇总",
            "特码调单汇总.txt",
            "Text Files (*.txt);;CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            self._append_output("已取消导出。")
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(self._build_export_text())
        except OSError as exc:
            self._append_output(f"导出特码调单汇总失败：{exc}")
            return
        self._append_output(f"已导出特码调单汇总：{path}")

    def _on_save_adjustment(self) -> None:
        payload = self._build_adjustment_payload()
        if payload is None:
            self._append_output("当前没有调整内容，无需保存。")
            return

        message = (
            "确认保存本次特码调单记录？\n\n"
            f"地区：{payload.region}\n"
            f"调整号码数量：{payload.item_count}\n"
            f"原金额合计：{payload.original_total}\n"
            f"调整金额合计：{payload.adjustment_total}\n"
            f"调整后合计：{payload.after_total}\n\n"
            "保存为调单快照记录，不修改订单，不自动结算或兑奖，不写余额。"
        )
        choice = QMessageBox.question(
            self,
            "保存本次调整",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            self._append_output("已取消保存本次调整。")
            return

        try:
            result = self._adjustment_record_service.create_record(payload)
        except Exception as exc:
            QMessageBox.warning(self, "保存本次调整", f"保存失败：{exc}")
            self._append_output(f"保存本次调整失败：{exc}")
            return
        app_events.logs_changed.emit()
        self._append_output(
            f"已保存特码调单记录 ID：{result.record.id}；"
            f"操作日志 ID：{result.operation_log_id}。当前调整未清空，订单未被修改，未自动兑奖。"
        )

    def _on_round_to_tens(self) -> None:
        changed = 0
        for number, original_edit in self._original_edits.items():
            original = _decimal_from_text(original_edit.text())
            target = (original / Decimal("10")).to_integral_value(rounding=ROUND_CEILING) * Decimal("10")
            adjustment = target - original
            self._adjust_edits[number].setText("" if adjustment == 0 else _money(adjustment))
            changed += 1 if adjustment else 0
        self._append_output(f"已将页面内临时总计调整到 10 的倍数：{changed} 个号码产生调整。")

    def _on_clear_adjustments(self) -> None:
        for edit in self._adjust_edits.values():
            edit.clear()
        self._append_output("已清空当前页面临时调整。")

    def _on_clear_output(self) -> None:
        self._output.clear()

    def _on_reset_all_data(self) -> None:
        self._append_output(
            "重置所有数据未开放：该操作涉及清空订单、调单记录或数据库，"
            "需要权限、审计和恢复策略；本次未执行任何写入。"
        )

    def _on_special_settlement(self) -> None:
        self._append_output(
            "特码调单页不执行兑奖：当前仅支持查看调单汇总和保存调单快照；"
            "请在订单详情中使用结算预览和正式结算记录，不计算赔付金额，不写余额。"
        )

    def _on_open_extension(self) -> None:
        self._append_output("拓展调单规则尚未确认，当前不开放额外调单扩展，未打开新页面。")

    def _on_adjust_records(self) -> None:
        dialog = AdjustmentRecordDialog(
            self,
            default_type="special",
            service=self._adjustment_record_service,
        )
        dialog.exec()
        self._append_output("已关闭特码调整记录窗口。")

    def _build_adjustment_payload(self) -> AdjustmentRecordCreate | None:
        details: list[dict[str, str]] = []
        non_zero_details: list[dict[str, str]] = []
        original_total = Decimal("0")
        adjustment_total = Decimal("0")
        after_total = Decimal("0")
        positive_count = 0
        negative_count = 0
        for number in range(1, 50):
            key = f"{number:02d}"
            original = _decimal_from_text(self._original_edits[key].text())
            adjustment = _decimal_from_text(self._adjust_edits[key].text())
            after = original + adjustment
            original_total += original
            adjustment_total += adjustment
            after_total += after
            detail = {
                "number": key,
                "original_amount": _money(original),
                "adjustment_amount": _money(adjustment),
                "after_amount": _money(after),
            }
            details.append(detail)
            if adjustment > 0:
                positive_count += 1
                non_zero_details.append(detail)
            elif adjustment < 0:
                negative_count += 1
                non_zero_details.append(detail)

        if not non_zero_details:
            return None

        return AdjustmentRecordCreate(
            adjustment_type="special",
            region=self._selected_region_label(),
            source_filter={"region": self._selected_region_label()},
            original_total=_money(original_total),
            adjustment_total=_money(adjustment_total),
            after_total=_money(after_total),
            item_count=len(non_zero_details),
            positive_count=positive_count,
            negative_count=negative_count,
            record_snapshot={
                "all_numbers": details,
                "adjusted_numbers": non_zero_details,
            },
            summary_snapshot={
                "original_stats": {
                    "special_total": self._lbl_special_total.text(),
                    "max_profit": self._lbl_max_profit.text(),
                    "max_loss": self._lbl_max_loss.text(),
                    "profit_count": self._lbl_profit_count.text(),
                    "loss_count": self._lbl_loss_count.text(),
                },
                "adjusted_stats": {
                    "adjusted_total": self._lbl_adjusted_total.text(),
                    "adjustment_total": self._lbl_adjustment_total.text(),
                },
            },
            note="特码调单保存，仅记录调整快照，不修改订单、不自动结算。",
        )

    def _number_zodiac(self, number: str) -> str:
        try:
            return get_zodiac(number, year=2026)
        except Exception:
            return ""

    def _number_label_text(self, number: str) -> str:
        zodiac = self._number_zodiac(number)
        return f"{zodiac}{number}" if zodiac else number

    def _wave_text_color(self, number: str) -> str:
        try:
            return WAVE_TEXT_COLORS.get(get_wave_color(number), "#263238")
        except Exception:
            return "#263238"

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #ffffff; color: #263238; font-size: 12px; }
            QFrame#topFilter, QFrame#statsPanel, QFrame#numberGrid {
                border: 1px solid #c5d2d6;
                background: #fbfefe;
            }
            QLabel#gridHeader {
                background: #f3fafa;
                border-bottom: 1px solid #c5d2d6;
                font-weight: 600;
                color: #2c3e50;
                min-height: 20px;
            }
            QLabel#numberBadge {
                min-width: 36px;
            }
            QLabel#statsTitle {
                color: #c0392b;
                font-weight: 700;
                min-width: 80px;
            }
            QTableWidget {
                border: 1px solid #aebfc2;
                gridline-color: #d5dfe1;
                alternate-background-color: #f7fafb;
            }
            QHeaderView::section {
                background: #dff2f3;
                padding: 4px;
                border: 1px solid #afc9cc;
                font-weight: 600;
            }
            QLineEdit {
                min-height: 22px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QLineEdit:read-only { background: #f6f8f8; color: #50636a; }
            QPushButton {
                padding: 5px 12px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QPushButton:hover { background: #e8f7f8; border-color: #5fbac2; }
            QPlainTextEdit { border: 1px solid #b8c7ca; background: #ffffff; }
            """
        )
