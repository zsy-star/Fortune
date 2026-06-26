"""订单导入预览弹窗：第一阶段只解析预览，不保存订单。"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
from services.settings_service import SettingsService
from ui.app_events import app_events


class OrderImportDialog(QDialog):
    """订单导入预览对话框。

    本阶段不提供确认导入/保存按钮，所有结果仅用于人工检查。
    """

    def __init__(
        self,
        parent=None,
        import_service: OrderImportService | None = None,
        settings_service: SettingsService | None = None,
    ):
        super().__init__(parent)
        self._import_service = import_service or OrderImportService()
        session_factory = getattr(getattr(self._import_service, "_order_intake_service", None), "_session_factory", None)
        self._settings_service = settings_service or (
            SettingsService(session_factory) if session_factory is not None else SettingsService()
        )
        self._source_skipped_count = 0
        self._preview = OrderImportPreview()
        self._import_completed = False
        self._last_import_time: datetime | None = None
        self._last_import_context: tuple[str, str, str] | None = None
        self._channel_manually_changed = False

        self.setWindowTitle("订单导入预览")
        self.resize(1080, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("订单导入预览")
        title.setObjectName("dialogTitle")
        hint = QLabel(
            "导入前会先预览；确认导入后仅保存解析成功行。申报人和渠道会写入成功导入订单；"
            "失败行不会保存申报人/渠道。本功能不结算、不计算赔付、不改余额。"
        )
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
        self._reload_declarers()
        self._update_import_button()

    def _build_file_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("请选择 .txt / .csv / .xlsx 文件")
        self._btn_select_file = QPushButton("选择文件")
        self._btn_select_file.clicked.connect(self._on_select_file)
        self._btn_download_template = QPushButton("下载导入模板")
        self._btn_download_template.clicked.connect(self._on_download_template)
        row.addWidget(QLabel("文件"))
        row.addWidget(self._path_edit, stretch=1)
        row.addWidget(self._btn_select_file)
        row.addWidget(self._btn_download_template)
        return row

    def _build_option_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._region_combo = QComboBox()
        self._region_combo.addItem("自动识别", None)
        self._region_combo.addItem("澳门", "澳门")
        self._region_combo.addItem("香港", "香港")
        self._encoding_combo = QComboBox()
        self._encoding_combo.addItems(["UTF-8", "GBK"])
        self._chk_history_duplicate = QCheckBox("检查历史重复订单")
        self._chk_history_duplicate.setChecked(True)
        self._chk_history_duplicate.setToolTip("只读查询历史订单原文、地区和申报人，发现疑似重复时在预览中提示。")
        self._chk_history_duplicate.toggled.connect(lambda _checked: self._refresh_preview_if_ready())
        self._chk_skip_history_duplicate = QCheckBox("导入时跳过历史疑似重复行")
        self._chk_skip_history_duplicate.setChecked(True)
        self._chk_skip_history_duplicate.setToolTip("确认导入时跳过已标记为历史疑似重复的成功行；取消勾选则允许导入。")
        self._chk_skip_history_duplicate.toggled.connect(lambda _checked: self._fill_preview(self._preview))
        self._declarer_combo = QComboBox()
        self._declarer_combo.setMinimumWidth(140)
        self._declarer_combo.currentIndexChanged.connect(self._on_declarer_changed)
        self._plan_label = QLabel("配置方案：未绑定配置方案")
        self._channel_combo = QComboBox()
        self._channel_combo.addItems(["导入", "TXT导入", "CSV导入", "XLSX导入", "手工整理导入"])
        self._channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        row.addWidget(QLabel("地区默认值"))
        row.addWidget(self._region_combo)
        row.addWidget(QLabel("编码"))
        row.addWidget(self._encoding_combo)
        row.addWidget(self._chk_history_duplicate)
        row.addWidget(self._chk_skip_history_duplicate)
        row.addWidget(QLabel("申报人"))
        row.addWidget(self._declarer_combo)
        row.addWidget(self._plan_label)
        row.addWidget(QLabel("渠道"))
        row.addWidget(self._channel_combo)
        row.addStretch(1)
        return row

    def _reload_declarers(self) -> None:
        self._declarer_combo.blockSignals(True)
        self._declarer_combo.clear()
        self._declarer_combo.addItem("未设置申报人", None)
        try:
            declarers = self._settings_service.list_declarers()
        except Exception:
            declarers = []
            self._plan_label.setText("配置方案：配置读取失败")
            if hasattr(self, "_stats_label"):
                self._stats_label.setText("申报人配置读取失败，已降级为未设置；当前不会写数据库")
        else:
            self._plan_label.setText("配置方案：未绑定配置方案")
        for declarer in declarers:
            self._declarer_combo.addItem(declarer.name, (declarer.name, declarer.plan_name))
        self._declarer_combo.blockSignals(False)
        self._on_declarer_changed(self._declarer_combo.currentIndex())

    def _on_declarer_changed(self, _index: int) -> None:
        data = self._declarer_combo.currentData()
        if isinstance(data, tuple) and len(data) >= 2:
            self._plan_label.setText(f"配置方案：{data[1] or '未绑定配置方案'}")
        elif self._plan_label.text() != "配置方案：配置读取失败":
            self._plan_label.setText("配置方案：未绑定配置方案")
        self._refresh_preview_if_ready()

    def _on_channel_changed(self, _index: int) -> None:
        self._channel_manually_changed = True

    def _selected_customer_name(self) -> str | None:
        data = self._declarer_combo.currentData()
        if isinstance(data, tuple) and data:
            return str(data[0]).strip() or None
        return None

    def _selected_config_plan_name(self) -> str | None:
        data = self._declarer_combo.currentData()
        if isinstance(data, tuple) and len(data) >= 2:
            return str(data[1]).strip() or None
        return None

    def _selected_channel(self) -> str:
        return self._channel_combo.currentText().strip() or "导入"

    def _refresh_preview_if_ready(self) -> None:
        if not hasattr(self, "_raw_text") or self._import_completed:
            return
        if self._raw_text.toPlainText().strip():
            self._on_preview()

    def _suggest_channel_from_suffix(self, suffix: str) -> None:
        if self._channel_manually_changed:
            return
        mapping = {".txt": "TXT导入", ".csv": "CSV导入", ".xlsx": "XLSX导入"}
        suggestion = mapping.get(suffix)
        if not suggestion:
            return
        index = self._channel_combo.findText(suggestion)
        if index >= 0:
            self._channel_combo.blockSignals(True)
            self._channel_combo.setCurrentIndex(index)
            self._channel_combo.blockSignals(False)

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
            "订单文件 (*.txt *.csv *.xlsx);;Text Files (*.txt);;CSV Files (*.csv);;Excel Files (*.xlsx);;All Files (*)",
        )
        if not path:
            self._stats_label.setText("已取消选择文件；当前不会写数据库")
            return
        self.load_file(path)

    def _on_download_template(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "下载导入模板",
            "订单导入模板.xlsx",
            "Excel Files (*.xlsx);;CSV Files (*.csv);;Text Files (*.txt);;All Files (*)",
        )
        if not path:
            self._stats_label.setText("已取消生成导入模板")
            return

        target = Path(path)
        file_type = self._template_type_from_selection(target, selected_filter)
        if target.suffix.lower() not in {".txt", ".csv", ".xlsx"}:
            target = target.with_suffix(f".{file_type}")

        try:
            self._import_service.create_template(target, file_type=file_type)
        except Exception as exc:
            self._stats_label.setText(f"生成导入模板失败：{exc}")
            QMessageBox.warning(self, "下载导入模板", f"生成导入模板失败：{exc}")
            return

        self._stats_label.setText(f"已生成导入模板：{target}")
        QMessageBox.information(self, "下载导入模板", f"导入模板已保存：{target}")

    def _template_type_from_selection(self, path: Path, selected_filter: str) -> str:
        suffix = path.suffix.lower().lstrip(".")
        if suffix in {"txt", "csv", "xlsx"}:
            return suffix
        if "CSV" in selected_filter:
            return "csv"
        if "Text" in selected_filter:
            return "txt"
        return "xlsx"

    def load_file(self, path: str) -> None:
        suffix = Path(path).suffix.lower()
        if suffix not in {".txt", ".csv", ".xlsx"}:
            message = "当前仅支持 txt/csv/xlsx"
            self._path_edit.setText(path)
            self._raw_text.clear()
            self._table.setRowCount(0)
            self._preview = OrderImportPreview()
            self._import_completed = False
            self._last_import_time = None
            self._last_import_context = None
            self._update_import_button()
            self._stats_label.setText(f"{message}；当前不会写数据库")
            QMessageBox.warning(self, "订单导入预览", message)
            return

        encoding = "gbk" if self._encoding_combo.currentText().lower() == "gbk" else "utf-8"
        result = self._import_service.read_file(path, encoding=encoding)
        self._path_edit.setText(path)
        self._suggest_channel_from_suffix(suffix)
        if result.error:
            self._raw_text.clear()
            self._source_skipped_count = 0
            self._preview = OrderImportPreview()
            self._import_completed = False
            self._last_import_time = None
            self._last_import_context = None
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
        self._last_import_context = None
        self._preview = self._import_service.preview_text(
            self._raw_text.toPlainText(),
            region_mode=self._region_combo.currentData(),
            history_duplicate_check=self._chk_history_duplicate.isChecked(),
            customer_name=self._selected_customer_name(),
        )
        # 文件读取阶段的空行也要体现在统计里；用户编辑后的空行以 preview_text 结果为准。
        if self._source_skipped_count and self._raw_text.toPlainText().strip():
            self._preview = OrderImportPreview(
                rows=self._preview.rows,
                skipped_count=max(self._preview.skipped_count, self._source_skipped_count),
                history_duplicate_check_enabled=self._preview.history_duplicate_check_enabled,
                history_duplicate_error=self._preview.history_duplicate_error,
            )
        self._fill_preview(self._preview)

    def _fill_preview(self, preview: OrderImportPreview) -> None:
        self._table.setRowCount(len(preview.rows))
        for row_index, row in enumerate(preview.rows):
            self._fill_row(row_index, row)
        self._update_stats(preview)

    def _fill_row(self, row_index: int, row: OrderImportPreviewRow) -> None:
        import_status = row.import_status
        if (
            not self._import_completed
            and row.success
            and row.history_duplicate_warning
            and self._chk_skip_history_duplicate.isChecked()
        ):
            import_status = "待跳过，疑似历史重复"
        values = [
            str(row.line_number),
            row.raw_text,
            row.region,
            "成功" if row.success else "失败",
            row.bet_type_summary,
            f"{row.amount_total:.2f}" if row.success else "0.00",
            str(row.item_count),
            self._row_error_text(row),
            import_status,
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
            if column == 8 and import_status == "已导入":
                item.setForeground(Qt.GlobalColor.darkGreen)
            if column == 8 and ("失败" in import_status or "跳过" in import_status):
                item.setForeground(Qt.GlobalColor.red)
            self._table.setItem(row_index, column, item)

    def _update_stats(self, preview: OrderImportPreview) -> None:
        history_text = ""
        if preview.history_duplicate_error:
            history_text = f"    {preview.history_duplicate_error}"
        elif preview.history_duplicate_check_enabled:
            history_text = f"    历史疑似重复：{preview.history_duplicate_count}"
        self._stats_label.setText(
            f"总行数：{preview.total_count}    "
            f"解析成功：{preview.success_count}    "
            f"解析失败：{preview.failure_count}    "
            f"跳过空行：{preview.skipped_count}    "
            f"当前不会写数据库{history_text}"
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
        parts = [part for part in (row.error, row.duplicate_warning, row.history_duplicate_warning) if part]
        return "；".join(parts)

    def _row_issue_text(self, row: OrderImportPreviewRow) -> str:
        parts = [
            part
            for part in (row.error, row.duplicate_warning, row.history_duplicate_warning, row.import_error)
            if part
        ]
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
            f"历史疑似重复行数：{self._preview.history_duplicate_count}\n"
            f"导入时跳过历史疑似重复行：{'是' if self._chk_skip_history_duplicate.isChecked() else '否'}\n\n"
            "只会导入解析成功行，失败行不会导入。\n"
            f"申报人：{self._selected_customer_name() or '未设置申报人'}\n"
            f"渠道：{self._selected_channel()}\n"
            f"配置方案：{self._selected_config_plan_name() or '未绑定配置方案'}\n"
            "导入会写入订单和操作日志，但不会结算、不会计算赔付或余额。"
        )
        if self._has_duplicate_rows():
            confirm_text += "\n\n当前预览中存在疑似重复行，请确认是否继续导入。"
        if self._preview.history_duplicate_count:
            confirm_text += "\n\n当前预览中存在历史疑似重复行，请核对后继续。"
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
            customer_name = self._selected_customer_name()
            channel = self._selected_channel()
            config_plan_name = self._selected_config_plan_name()
            result = self._import_service.confirm_import(
                self._preview,
                file_path=self._path_edit.text(),
                customer_name=customer_name,
                channel=channel,
                config_plan_name=config_plan_name,
                skip_history_duplicates=self._chk_skip_history_duplicate.isChecked(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "订单导入", f"导入失败：{exc}")
            self._stats_label.setText(f"导入失败：{exc}")
            return

        self._preview = result.preview
        self._import_completed = True
        self._last_import_time = datetime.now()
        self._last_import_context = (
            customer_name or "未设置申报人",
            channel,
            config_plan_name or "未绑定配置方案",
        )
        self._fill_preview(self._preview)
        self._stats_label.setText(
            f"本次应导入：{result.attempted_count}    "
            f"成功导入：{result.imported_count}    "
            f"保存失败：{result.save_failed_count}    "
            f"跳过失败解析行：{result.skipped_parse_failed_count}    "
            f"跳过历史重复：{result.skipped_history_duplicate_count}    "
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
        skipped_history_duplicate = sum(1 for row in self._preview.rows if row.import_status == "已跳过，疑似历史重复")
        region_text = self._region_combo.currentText()
        import_time = self._last_import_time or datetime.now()
        customer_name, channel, config_plan_name = self._report_context()
        lines = [
            "订单导入结果报告",
            f"文件路径：{self._path_edit.text() or '未选择文件'}",
            f"文件名：{Path(self._path_edit.text()).name if self._path_edit.text() else '未选择文件'}",
            f"导入时间：{import_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"地区选择：{region_text}",
            f"申报人：{customer_name}",
            f"渠道：{channel}",
            f"配置方案：{config_plan_name}",
            f"总行数：{self._preview.total_count}",
            f"跳过空行数：{self._preview.skipped_count}",
            f"解析成功数：{self._preview.success_count}",
            f"解析失败数：{self._preview.failure_count}",
            f"本次应导入数：{attempted_count}",
            f"成功导入数：{imported_count}",
            f"保存失败数：{save_failed_count}",
            f"跳过解析失败行数：{skipped_parse_failed}",
            f"历史重复检测：{'已启用' if self._preview.history_duplicate_check_enabled else '未启用'}",
            f"历史疑似重复行数：{self._preview.history_duplicate_count}",
            f"跳过历史重复行数：{skipped_history_duplicate}",
            "",
            "每行明细",
            "行号\t原始文本\t解析状态\t导入状态\t地区\t申报人\t渠道\t配置方案\t投注类型\t金额\t条目数\t历史重复提示\t历史订单\t是否跳过\t错误原因\t订单ID",
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
                        customer_name,
                        channel,
                        config_plan_name,
                        row.bet_type_summary,
                        f"{row.amount_total:.2f}" if row.success else "0.00",
                        str(row.item_count),
                        row.history_duplicate_warning,
                        row.history_duplicate_order_no or str(row.history_duplicate_order_id or ""),
                        "是" if row.import_status == "已跳过，疑似历史重复" else "否",
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
            customer_name, channel, config_plan_name = self._report_context()
            writer.writerow(
                [
                    "行号",
                    "原始文本",
                    "解析状态",
                    "导入状态",
                    "地区",
                    "申报人",
                    "渠道",
                    "配置方案",
                    "投注类型",
                    "金额",
                    "条目数",
                    "历史重复提示",
                    "历史订单",
                    "是否跳过",
                    "错误原因",
                ]
            )
            for row in self._preview.rows:
                writer.writerow(
                    [
                        row.line_number,
                        row.raw_text,
                        "成功" if row.success else "失败",
                        row.import_status,
                        row.region,
                        customer_name,
                        channel,
                        config_plan_name,
                        row.bet_type_summary,
                        f"{row.amount_total:.2f}" if row.success else "0.00",
                        row.item_count,
                        row.history_duplicate_warning,
                        row.history_duplicate_order_no or str(row.history_duplicate_order_id or ""),
                        "是" if row.import_status == "已跳过，疑似历史重复" else "否",
                        self._row_issue_text(row),
                    ]
                )

    def _report_context(self) -> tuple[str, str, str]:
        if self._last_import_context is not None:
            return self._last_import_context
        return (
            self._selected_customer_name() or "未设置申报人",
            self._selected_channel(),
            self._selected_config_plan_name() or "未绑定配置方案",
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
