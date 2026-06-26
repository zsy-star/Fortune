"""订单导入预览弹窗：第一阶段只解析预览，不保存订单。"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from schemas.order_import_schema import OrderImportPreview, OrderImportPreviewRow
from services.order_import_service import OrderImportService
from ui.app_events import app_events


class OrderImportDialog(QDialog):
    """订单导入预览对话框。

    本阶段不提供确认导入/保存按钮，所有结果仅用于人工检查。
    """

    def __init__(
        self,
        parent=None,
        import_service: OrderImportService | None = None,
    ):
        super().__init__(parent)
        self._import_service = import_service or OrderImportService()
        self._source_skipped_count = 0
        self._preview = OrderImportPreview()
        self._import_completed = False
        self._last_import_time: datetime | None = None

        self.setWindowTitle("订单导入预览")
        self.resize(1080, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("订单导入预览")
        title.setObjectName("dialogTitle")
        hint = QLabel("当前仅解析预览，不写数据库，不保存订单；导入保存后续阶段开放。")
        hint.setObjectName("safeHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)
        root.addLayout(self._build_file_row())
        root.addLayout(self._build_option_row())

        self._raw_text = QPlainTextEdit()
        self._raw_text.setPlaceholderText("文件内容会显示在这里，可编辑后点击“重新解析”。")
        self._raw_text.setMinimumHeight(110)
        root.addWidget(self._raw_text)

        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels(
            ["行号", "原始文本", "地区", "解析状态", "投注类型", "金额", "条目数", "错误原因", "导入结果", "保存错误"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table, stretch=1)

        self._stats_label = QLabel("总行数：0    解析成功：0    解析失败：0    跳过空行：0    当前不会写数据库")
        self._stats_label.setObjectName("safeHint")
        root.addWidget(self._stats_label)
        root.addLayout(self._build_bottom_row())
        self._apply_stylesheet()
        self._update_import_button()

    def _build_file_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("请选择 .txt 或 .csv 文件")
        self._btn_select_file = QPushButton("选择文件")
        self._btn_select_file.clicked.connect(self._on_select_file)
        row.addWidget(QLabel("文件"))
        row.addWidget(self._path_edit, stretch=1)
        row.addWidget(self._btn_select_file)
        return row

    def _build_option_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._region_combo = QComboBox()
        self._region_combo.addItem("自动识别", None)
        self._region_combo.addItem("澳门", "澳门")
        self._region_combo.addItem("香港", "香港")
        self._encoding_combo = QComboBox()
        self._encoding_combo.addItems(["UTF-8", "GBK"])
        row.addWidget(QLabel("地区默认值"))
        row.addWidget(self._region_combo)
        row.addWidget(QLabel("编码"))
        row.addWidget(self._encoding_combo)
        row.addStretch(1)
        return row

    def _build_bottom_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_preview = QPushButton("重新解析")
        self._btn_confirm_import = QPushButton("确认导入成功行")
        self._btn_copy_errors = QPushButton("复制错误报告")
        self._btn_copy_result = QPushButton("复制导入结果")
        self._btn_export_result = QPushButton("导出导入结果")
        self._btn_close = QPushButton("关闭")
        self._btn_preview.clicked.connect(self._on_preview)
        self._btn_confirm_import.clicked.connect(self._on_confirm_import)
        self._btn_copy_errors.clicked.connect(self._on_copy_error_report)
        self._btn_copy_result.clicked.connect(self._on_copy_import_result)
        self._btn_export_result.clicked.connect(self._on_export_import_result)
        self._btn_close.clicked.connect(self.reject)
        row.addWidget(self._btn_preview)
        row.addWidget(self._btn_confirm_import)
        row.addWidget(self._btn_copy_errors)
        row.addWidget(self._btn_copy_result)
        row.addWidget(self._btn_export_result)
        row.addWidget(self._btn_close)
        return row

    def _on_select_file(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "选择订单导入文件",
            "",
            "订单文本 (*.txt *.csv);;Text Files (*.txt);;CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            self._stats_label.setText("已取消选择文件；当前不会写数据库")
            return
        self.load_file(path)

    def load_file(self, path: str) -> None:
        suffix = Path(path).suffix.lower()
        if suffix not in {".txt", ".csv"}:
            message = "当前仅支持 txt/csv，xlsx 后续开放"
            self._path_edit.setText(path)
            self._raw_text.clear()
            self._table.setRowCount(0)
            self._preview = OrderImportPreview()
            self._import_completed = False
            self._last_import_time = None
            self._update_import_button()
            self._stats_label.setText(f"{message}；当前不会写数据库")
            QMessageBox.warning(self, "订单导入预览", message)
            return

        encoding = "gbk" if self._encoding_combo.currentText().lower() == "gbk" else "utf-8"
        result = self._import_service.read_file(path, encoding=encoding)
        self._path_edit.setText(path)
        if result.error:
            self._raw_text.clear()
            self._source_skipped_count = 0
            self._preview = OrderImportPreview()
            self._import_completed = False
            self._last_import_time = None
            self._fill_preview(self._preview)
            self._stats_label.setText(f"{result.error}；当前不会写数据库")
            QMessageBox.warning(self, "订单导入预览", result.error)
            return

        self._source_skipped_count = result.skipped_count
        self._raw_text.setPlainText("\n".join(result.lines))
        self._on_preview()

    def _on_preview(self) -> None:
        self._import_completed = False
        self._last_import_time = None
        self._preview = self._import_service.preview_text(
            self._raw_text.toPlainText(),
            region_mode=self._region_combo.currentData(),
        )
        # 文件读取阶段的空行也要体现在统计里；用户编辑后的空行以 preview_text 结果为准。
        if self._source_skipped_count and self._raw_text.toPlainText().strip():
            self._preview = OrderImportPreview(
                rows=self._preview.rows,
                skipped_count=max(self._preview.skipped_count, self._source_skipped_count),
            )
        self._fill_preview(self._preview)

    def _fill_preview(self, preview: OrderImportPreview) -> None:
        self._table.setRowCount(len(preview.rows))
        for row_index, row in enumerate(preview.rows):
            self._fill_row(row_index, row)
        self._update_stats(preview)

    def _fill_row(self, row_index: int, row: OrderImportPreviewRow) -> None:
        values = [
            str(row.line_number),
            row.raw_text,
            row.region,
            "成功" if row.success else "失败",
            row.bet_type_summary,
            f"{row.amount_total:.2f}" if row.success else "0.00",
            str(row.item_count),
            self._row_error_text(row),
            row.import_status,
            row.import_error,
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                if column in (1, 7)
                else Qt.AlignmentFlag.AlignCenter
            )
            if column == 3:
                item.setForeground(Qt.GlobalColor.darkGreen if row.success else Qt.GlobalColor.red)
            if column == 8 and row.import_status == "已导入":
                item.setForeground(Qt.GlobalColor.darkGreen)
            if column == 8 and "失败" in row.import_status:
                item.setForeground(Qt.GlobalColor.red)
            self._table.setItem(row_index, column, item)

    def _update_stats(self, preview: OrderImportPreview) -> None:
        self._stats_label.setText(
            f"总行数：{preview.total_count}    "
            f"解析成功：{preview.success_count}    "
            f"解析失败：{preview.failure_count}    "
            f"跳过空行：{preview.skipped_count}    "
            "当前不会写数据库"
        )
        self._update_import_button()

    def _update_import_button(self) -> None:
        if not hasattr(self, "_btn_confirm_import"):
            return
        self._btn_confirm_import.setEnabled(
            not self._import_completed and self._preview.success_count > 0
        )
        if self._import_completed:
            self._btn_confirm_import.setToolTip("本次导入已完成；请重新解析或重新选择文件后再次导入")
        elif self._preview.success_count <= 0:
            self._btn_confirm_import.setToolTip("没有解析成功行，不能导入")
        else:
            self._btn_confirm_import.setToolTip("只导入解析成功行；失败行不会导入")

    def _row_error_text(self, row: OrderImportPreviewRow) -> str:
        parts = [part for part in (row.error, row.duplicate_warning) if part]
        return "；".join(parts)

    def _row_issue_text(self, row: OrderImportPreviewRow) -> str:
        parts = [part for part in (row.error, row.duplicate_warning, row.import_error) if part]
        return "；".join(parts)

    def _has_duplicate_rows(self) -> bool:
        return any(row.duplicate_warning for row in self._preview.rows)

    def _on_confirm_import(self) -> None:
        if self._preview.success_count <= 0:
            self._stats_label.setText("没有解析成功行，不能导入")
            self._update_import_button()
            return

        confirm_text = (
            "确认导入当前预览中的成功行？\n\n"
            f"总行数：{self._preview.total_count}\n"
            f"解析成功行数：{self._preview.success_count}\n"
            f"解析失败行数：{self._preview.failure_count}\n"
            f"跳过空行数：{self._preview.skipped_count}\n\n"
            "只会导入解析成功行，失败行不会导入。\n"
            "导入会写入订单和操作日志，但不会结算、不会计算赔付或余额。"
        )
        if self._has_duplicate_rows():
            confirm_text += "\n\n当前预览中存在疑似重复行，请确认是否继续导入。"
        choice = QMessageBox.question(
            self,
            "确认导入成功行",
            confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            self._stats_label.setText("已取消确认导入；未写数据库")
            return

        try:
            result = self._import_service.confirm_import(
                self._preview,
                file_path=self._path_edit.text(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "订单导入", f"导入失败：{exc}")
            self._stats_label.setText(f"导入失败：{exc}")
            return

        self._preview = result.preview
        self._import_completed = True
        self._last_import_time = datetime.now()
        self._fill_preview(self._preview)
        self._stats_label.setText(
            f"本次应导入：{result.attempted_count}    "
            f"成功导入：{result.imported_count}    "
            f"保存失败：{result.save_failed_count}    "
            f"跳过失败解析行：{result.skipped_parse_failed_count}    "
            f"跳过空行：{self._preview.skipped_count}"
        )
        self._update_import_button()
        if result.imported_count > 0:
            app_events.orders_changed.emit()
        if result.log_id is not None:
            app_events.logs_changed.emit()
        if result.imported_count and result.save_failed_count:
            QMessageBox.information(self, "订单导入", "导入部分成功，请查看预览表中的导入结果。")
        elif result.imported_count:
            QMessageBox.information(self, "订单导入", f"成功导入 {result.imported_count} 条订单。")
        elif result.save_failed_count:
            QMessageBox.warning(self, "订单导入", "解析成功行均保存失败，请查看保存错误。")

    def _on_copy_error_report(self) -> None:
        QApplication.clipboard().setText(self._build_error_report())
        self._stats_label.setText("已复制错误报告；当前不会写数据库")

    def _on_copy_import_result(self) -> None:
        report = self._build_import_result_report()
        if report == "当前暂无导入结果":
            self._stats_label.setText("当前暂无导入结果")
            return
        QApplication.clipboard().setText(report)
        self._stats_label.setText("已复制导入结果报告到剪贴板")

    def _on_export_import_result(self) -> None:
        report = self._build_import_result_report()
        if report == "当前暂无导入结果":
            self._stats_label.setText("当前暂无导入结果")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出导入结果",
            "订单导入结果报告.txt",
            "Text Files (*.txt);;CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            self._stats_label.setText("已取消导出导入结果")
            return
        try:
            if Path(path).suffix.lower() == ".csv" or "CSV" in selected_filter:
                self._write_result_csv(path)
            else:
                Path(path).write_text(report, encoding="utf-8")
        except OSError as exc:
            self._stats_label.setText(f"导出导入结果失败：{exc}")
            return
        self._stats_label.setText(f"已导出导入结果：{path}")

    def _build_error_report(self) -> str:
        failed_rows = [row for row in self._preview.rows if not row.success]
        if not failed_rows:
            return "当前没有解析失败行"
        lines = ["订单导入预览错误报告", "行号\t原始文本\t错误原因"]
        for row in failed_rows:
            lines.append(f"{row.line_number}\t{row.raw_text}\t{self._row_error_text(row) or '解析失败'}")
        return "\n".join(lines)

    def _build_import_result_report(self) -> str:
        if not self._preview.rows:
            return "当前暂无导入结果"
        imported_count = sum(1 for row in self._preview.rows if row.import_status == "已导入")
        save_failed_count = sum(1 for row in self._preview.rows if row.import_status == "导入失败")
        skipped_parse_failed = sum(1 for row in self._preview.rows if not row.success)
        attempted_count = sum(1 for row in self._preview.rows if row.success)
        region_text = self._region_combo.currentText()
        import_time = self._last_import_time or datetime.now()
        lines = [
            "订单导入结果报告",
            f"文件路径：{self._path_edit.text() or '未选择文件'}",
            f"文件名：{Path(self._path_edit.text()).name if self._path_edit.text() else '未选择文件'}",
            f"导入时间：{import_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"地区选择：{region_text}",
            f"总行数：{self._preview.total_count}",
            f"跳过空行数：{self._preview.skipped_count}",
            f"解析成功数：{self._preview.success_count}",
            f"解析失败数：{self._preview.failure_count}",
            f"本次应导入数：{attempted_count}",
            f"成功导入数：{imported_count}",
            f"保存失败数：{save_failed_count}",
            f"跳过解析失败行数：{skipped_parse_failed}",
            "",
            "每行明细",
            "行号\t原始文本\t解析状态\t导入状态\t地区\t投注类型\t金额\t条目数\t错误原因\t订单ID",
        ]
        for row in self._preview.rows:
            lines.append(
                "\t".join(
                    [
                        str(row.line_number),
                        row.raw_text,
                        "成功" if row.success else "失败",
                        row.import_status,
                        row.region,
                        row.bet_type_summary,
                        f"{row.amount_total:.2f}" if row.success else "0.00",
                        str(row.item_count),
                        self._row_issue_text(row),
                        str(row.order_id or ""),
                    ]
                )
            )
        lines.extend(
            [
                "",
                "安全说明",
                "本报告仅用于核对",
                "失败行未导入",
                "本次未执行结算",
                "本次未计算赔付、余额、返水",
            ]
        )
        return "\n".join(lines)

    def _write_result_csv(self, path: str) -> None:
        with open(path, "w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["行号", "原始文本", "解析状态", "导入状态", "地区", "投注类型", "金额", "条目数", "错误原因"])
            for row in self._preview.rows:
                writer.writerow(
                    [
                        row.line_number,
                        row.raw_text,
                        "成功" if row.success else "失败",
                        row.import_status,
                        row.region,
                        row.bet_type_summary,
                        f"{row.amount_total:.2f}" if row.success else "0.00",
                        row.item_count,
                        self._row_issue_text(row),
                    ]
                )

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QLabel#dialogTitle {
                font-size: 16px;
                font-weight: 700;
                color: #244357;
            }
            QLabel#safeHint {
                color: #6c7a80;
            }
            QLineEdit, QComboBox, QPlainTextEdit {
                border: 1px solid #b8c7ca;
                background: #ffffff;
                min-height: 24px;
            }
            QPushButton {
                min-height: 26px;
                padding: 2px 10px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #e8f7f8;
                border-color: #5fbac2;
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
            """
        )
