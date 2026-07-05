"""连肖调单页面：只读汇总并保存调单快照记录。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
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
from schemas.adjustment_record_schema import AdjustmentRecordCreate
from services.adjustment_record_service import AdjustmentRecordService
from services.order_service import OrderService
from services.risk_adjustment_service import LianxiaoRiskRow, RiskAdjustmentService
from ui.app_events import app_events
from ui.dialogs.adjustment_record_dialog import AdjustmentRecordDialog

LIANXIAO_BET_TYPES = {"连肖", "多生肖", "复试连肖"}
TABLE_HEADERS = ["生肖组", "下注数", "预计赔付", "原始风险", "已抛出", "调整后风险"]


@dataclass(frozen=True, slots=True)
class LianxiaoSummary:
    group: str
    amount: Decimal


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


class LianxiaoOrderPage(QWidget):
    """连肖调单页面。

    当前只读汇总已有连肖类订单明细，并可保存调单快照记录；不修改原订单、不自动兑奖。
    布局恢复为传统连肖工作台：左侧总表 + 右侧四个并排连肖列表。
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
        self._risk_adjustment_service = RiskAdjustmentService(session_factory) if session_factory is not None else RiskAdjustmentService()
        self._zodiac_year = get_default_zodiac_year()
        self._summaries: list[LianxiaoSummary] = []
        self._risk_rows: list[LianxiaoRiskRow] = []
        self._tables: list[QTableWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(2)

        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), stretch=7)
        root.addWidget(self._build_stats_panel())
        root.addWidget(self._build_throw_panel())
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
        row.addWidget(QLabel("生肖年份"))
        self._spin_zodiac_year = QSpinBox()
        self._spin_zodiac_year.setObjectName("lianxiaoAdjustmentZodiacYearSpin")
        self._spin_zodiac_year.setRange(MIN_ZODIAC_YEAR, MAX_ZODIAC_YEAR)
        self._spin_zodiac_year.setValue(self._zodiac_year)
        self._spin_zodiac_year.setToolTip("连肖调单按所选生肖年份的订单统计")
        self._spin_zodiac_year.valueChanged.connect(self._on_zodiac_year_changed)
        row.addWidget(self._spin_zodiac_year)

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
        table = QTableWidget(0, len(TABLE_HEADERS))
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

    def _build_throw_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("throwPanel")
        col = QVBoxLayout(frame)
        col.setContentsMargins(6, 3, 6, 3)
        top = QHBoxLayout()
        top.addWidget(QLabel("抛出原因"))
        self._throw_reason_edit = QLineEdit()
        self._throw_reason_edit.setPlaceholderText("应用抛出前必填")
        top.addWidget(self._throw_reason_edit, stretch=1)
        self._btn_apply_throw = QPushButton("应用连肖抛出")
        self._btn_apply_throw.clicked.connect(self._on_apply_throw)
        top.addWidget(self._btn_apply_throw)
        self._btn_copy_throw = QPushButton("复制抛出文本")
        self._btn_copy_throw.clicked.connect(self._on_copy_throw_text)
        top.addWidget(self._btn_copy_throw)
        col.addLayout(top)
        self._throw_input = QPlainTextEdit()
        self._throw_input.setPlaceholderText("抛出格式：龙羊猴=100、龙,羊,猴=100 或 龙-羊-猴=100；多条可换行。")
        self._throw_input.setMaximumHeight(64)
        col.addWidget(self._throw_input)
        return frame

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
            ("保存本次调整", self._on_save_adjustment),
            ("打印连肖调整", self._on_print_adjustment),
            ("复制当前汇总", self._on_copy_summary),
            ("导出当前汇总", self._on_export_summary),
            ("清空输出框", self._on_clear_output),
            ("重置调整", self._on_reset_adjustment),
            ("调整记录", self._on_adjust_records),
        ]
        for text, handler in actions:
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button, stretch=1)
            if text == "保存本次调整":
                self._btn_save_adjustment = button
                button.setToolTip("保存当前连肖汇总快照；不修改订单、不自动兑奖、不写余额。")
            elif text == "打印连肖调整":
                self._btn_print = button
                button.setToolTip("生成可复制/导出的打印文本；当前不调用真实打印机。")
            elif text == "复制当前汇总":
                self._btn_copy_summary = button
                button.setToolTip("复制当前连肖汇总文本，不修改订单。")
            elif text == "导出当前汇总":
                self._btn_export_summary = button
                button.setToolTip("导出当前连肖汇总文本，不修改订单。")
            elif text == "清空输出框":
                self._btn_clear_output = button
            elif text == "重置调整":
                self._btn_reset = button
                button.setToolTip("仅重置页面临时调整显示，不修改数据库订单。")
            elif text == "调整记录":
                self._btn_adjust_records = button
                button.setToolTip("查看已保存的连肖调单快照记录；不提供删除、恢复或重新应用。")
        return frame

    def reload_data(self) -> None:
        self._risk_adjustment_service.set_zodiac_year(self._selected_zodiac_year())
        self._summaries = self._load_lianxiao_summary()
        self._fill_tables()
        self._update_stats()
        if self._summaries:
            self._append_output(f"已加载连肖汇总：{len(self._summaries)} 组。")
        else:
            self._append_output("暂无数据：当前筛选条件下没有连肖订单明细。")
        self._append_output("当前展示只读汇总；保存本次调整仅记录调单快照，不修改订单。")

    def _selected_region(self) -> str | None:
        button = self._region_group.checkedButton()
        return button.property("region") if button is not None else None

    def _selected_zodiac_year(self) -> int:
        spin = getattr(self, "_spin_zodiac_year", None)
        return int(spin.value()) if spin is not None else self._zodiac_year

    def _on_zodiac_year_changed(self, year: int) -> None:
        self._zodiac_year = int(year)
        self.reload_data()

    def _load_lianxiao_summary(self) -> list[LianxiaoSummary]:
        self._risk_rows = self._risk_adjustment_service.build_lianxiao_risk_table(region=self._selected_region())
        return [
            LianxiaoSummary(group=row.zodiac_group, amount=row.raw_amount)
            for row in self._risk_rows
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
            values = ["暂无数据", "0.00", "0.00", "0.00", "0.00", "0.00"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(0, column, item)
            return

        table.setRowCount(len(rows))
        risk_by_group = {row.zodiac_group: row for row in self._risk_rows}
        for row, summary in enumerate(rows):
            risk = risk_by_group.get(summary.group)
            values = (
                [
                    summary.group,
                    _money(risk.raw_amount),
                    _money(risk.potential_payout_amount),
                    _money(risk.risk_amount),
                    _money(risk.thrown_amount),
                    _money(risk.adjusted_risk_amount),
                ]
                if risk is not None
                else [summary.group, _money(summary.amount), "0.00", "0.00", "0.00", "0.00"]
            )
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
        risks = [row.risk_amount for row in self._risk_rows]
        adjusted = [row.adjusted_risk_amount for row in self._risk_rows]
        thrown_total = sum((row.thrown_amount for row in self._risk_rows), Decimal("0"))
        max_risk = max(risks) if risks else Decimal("0")
        min_risk = min(risks) if risks else Decimal("0")
        adjusted_max = max(adjusted) if adjusted else Decimal("0")
        adjusted_min = min(adjusted) if adjusted else Decimal("0")
        self._lbl_lianxiao_total.setText(f"连肖总额：{_money(total)}")
        self._lbl_max_profit.setText(f"最高风险：{_money(max_risk)}")
        self._lbl_max_loss.setText(f"最低风险：{_money(min_risk)}")
        self._lbl_eat_total.setText(f"吃单总额：{_money(total)}")
        self._lbl_adjustment_total.setText(f"已抛出：{_money(thrown_total)}")
        self._lbl_adjusted_max_profit.setText(f"调整后最高风险：{_money(adjusted_max)}")
        self._lbl_adjusted_max_loss.setText(f"调整后最低风险：{_money(adjusted_min)}")

    def _append_output(self, message: str) -> None:
        current = self._output.toPlainText().strip()
        self._output.setPlainText(f"{current}\n{message}".strip())

    def _selected_region_label(self) -> str:
        return self._selected_region() or "全部"

    def _table_rows_text(self, table: QTableWidget) -> list[str]:
        rows: list[str] = []
        for row in range(table.rowCount()):
            values = [
                table.item(row, column).text() if table.item(row, column) is not None else ""
                for column in range(table.columnCount())
            ]
            rows.append("\t".join(values))
        return rows

    def _build_export_text(self) -> str:
        lines = [
            "连肖调单汇总",
            f"当前筛选区域：{self._selected_region_label()}",
            f"生肖年份：{self._selected_zodiac_year()}",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "左侧总表",
            "\t".join(TABLE_HEADERS),
        ]
        lines.extend(self._table_rows_text(self._summary_table))

        for index, table in enumerate(self._tables, start=1):
            lines.extend(["", f"第 {index} 列表", "\t".join(TABLE_HEADERS)])
            lines.extend(self._table_rows_text(table))

        lines.extend(
            [
                "",
                "原连肖数据统计",
                self._lbl_lianxiao_total.text(),
                self._lbl_max_profit.text(),
                self._lbl_max_loss.text(),
                "",
                "调整后数据统计",
                self._lbl_eat_total.text(),
                self._lbl_adjustment_total.text(),
                self._lbl_adjusted_max_profit.text(),
                self._lbl_adjusted_max_loss.text(),
                "",
                "安全说明",
                "保存调整仅写入调单记录",
                "不修改订单",
                "不自动结算或兑奖",
                "未计算真实赔付",
                "不写余额",
                "",
                "抛出输入",
                self._throw_input.toPlainText(),
            ]
        )
        return "\n".join(lines)

    def _on_print_adjustment(self) -> None:
        self._output.setPlainText(
            self._build_export_text()
            + "\n\n打印提示：当前只是生成可复制/导出的打印文本，未调用系统打印机；"
            "请使用“复制当前汇总”或“导出当前汇总”后打印。"
        )

    def _on_copy_summary(self) -> None:
        QApplication.clipboard().setText(self._build_export_text())
        self._append_output("已复制连肖调单汇总到剪贴板。")

    def _on_copy_throw_text(self) -> None:
        QApplication.clipboard().setText(self._throw_input.toPlainText())
        self._append_output("已复制连肖抛出文本到剪贴板。")

    def _on_apply_throw(self) -> None:
        try:
            entries = self._risk_adjustment_service.parse_lianxiao_throw_text(self._throw_input.toPlainText())
        except Exception as exc:
            QMessageBox.warning(self, "应用连肖抛出", str(exc))
            self._append_output(f"解析连肖抛出失败：{exc}")
            return
        reason = self._throw_reason_edit.text().strip()
        if not reason:
            QMessageBox.warning(self, "应用连肖抛出", "原因不能为空")
            self._append_output("应用连肖抛出失败：原因不能为空。")
            return
        total = sum((entry.amount for entry in entries), Decimal("0"))
        detail = "\n".join(f"{entry.zodiac_group}={_money(entry.amount)}" for entry in entries[:20])
        if len(entries) > 20:
            detail += f"\n... 共 {len(entries)} 条"
        choice = QMessageBox.question(
            self,
            "应用连肖抛出",
            (
                "确认保存连肖抛出记录？\n\n"
                f"地区：{self._selected_region_label()}\n"
                f"影响组合数量：{len(entries)}\n"
                f"总抛出金额：{_money(total)}\n"
                f"原因：{reason}\n\n"
                f"{detail}\n\n"
                "本操作只写调单记录和操作日志，不修改订单、不自动结算、不写余额。"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            self._append_output("已取消应用连肖抛出。")
            return
        try:
            result = self._risk_adjustment_service.apply_lianxiao_throw(
                entries,
                region=self._selected_region_label(),
                reason=reason,
            )
        except Exception as exc:
            QMessageBox.warning(self, "应用连肖抛出", f"保存失败：{exc}")
            self._append_output(f"应用连肖抛出失败：{exc}")
            return
        app_events.logs_changed.emit()
        self.reload_data()
        self._append_output(
            f"已保存连肖抛出记录 ID：{result.record.id}；操作日志 ID：{result.operation_log_id}。"
        )

    def _on_export_summary(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出连肖调单汇总",
            "连肖调单汇总.txt",
            "Text Files (*.txt);;CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            self._append_output("已取消导出。")
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(self._build_export_text())
        except OSError as exc:
            self._append_output(f"导出连肖调单汇总失败：{exc}")
            return
        self._append_output(f"已导出连肖调单汇总：{path}")

    def _on_clear_output(self) -> None:
        self._output.clear()

    def _on_reset_adjustment(self) -> None:
        self._append_output("已重置当前页面临时调整；数据库订单未被修改。")

    def _on_save_adjustment(self) -> None:
        payload = self._build_adjustment_payload()
        message = (
            "确认保存本次连肖调单记录？\n\n"
            f"地区：{payload.region}\n"
            f"连肖组数量：{payload.item_count}\n"
            f"连肖总额：{payload.original_total}\n\n"
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
            f"已保存连肖调单记录 ID：{result.record.id}；"
            f"操作日志 ID：{result.operation_log_id}。订单未被修改，未自动兑奖。"
        )

    def _on_adjust_records(self) -> None:
        dialog = AdjustmentRecordDialog(
            self,
            default_type="lianxiao_all",
            service=self._adjustment_record_service,
            risk_service=self._risk_adjustment_service,
        )
        dialog.exec()
        self.reload_data()
        self._append_output("已关闭连肖调整记录窗口。")

    def _table_rows_snapshot(self, table: QTableWidget) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in range(table.rowCount()):
            values = [
                table.item(row, column).text() if table.item(row, column) is not None else ""
                for column in range(table.columnCount())
            ]
            rows.append(
                {
                    "group": values[0] if len(values) > 0 else "",
                    "amount": values[1] if len(values) > 1 else "0.00",
                    "potential_payout_amount": values[2] if len(values) > 2 else "0.00",
                    "risk_amount": values[3] if len(values) > 3 else "0.00",
                    "thrown_amount": values[4] if len(values) > 4 else "0.00",
                    "adjusted_risk_amount": values[5] if len(values) > 5 else "0.00",
                }
            )
        return rows

    def _build_adjustment_payload(self) -> AdjustmentRecordCreate:
        total = sum((summary.amount for summary in self._summaries), Decimal("0"))
        return AdjustmentRecordCreate(
            adjustment_type="lianxiao",
            region=self._selected_region_label(),
            source_filter={"region": self._selected_region_label(), "zodiac_year": self._selected_zodiac_year()},
            original_total=_money(total),
            adjustment_total="0.00",
            after_total=_money(total),
            item_count=len(self._summaries),
            positive_count=0,
            negative_count=0,
            record_snapshot={
                "summary_table": self._table_rows_snapshot(self._summary_table),
                "right_tables": [
                    {
                        "table": index,
                        "rows": self._table_rows_snapshot(table),
                    }
                    for index, table in enumerate(self._tables, start=1)
                ],
                "temporary_adjustments": [],
            },
            summary_snapshot={
                "original_stats": {
                    "lianxiao_total": self._lbl_lianxiao_total.text(),
                    "max_profit": self._lbl_max_profit.text(),
                    "max_loss": self._lbl_max_loss.text(),
                },
                "adjusted_stats": {
                    "eat_total": self._lbl_eat_total.text(),
                    "adjustment_total": self._lbl_adjustment_total.text(),
                    "adjusted_max_profit": self._lbl_adjusted_max_profit.text(),
                    "adjusted_max_loss": self._lbl_adjusted_max_loss.text(),
                },
            },
            note="连肖调单保存，仅记录汇总快照，不修改订单、不自动结算。",
        )

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
            QFrame#throwPanel {
                border: 1px solid #8f9da1;
                background: #fbfefe;
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
