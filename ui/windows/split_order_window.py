"""拆单助手弹窗。"""

from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dataclasses import replace

from schemas.order_import_schema import OrderImportPreview
from services.order_import_service import OrderImportService
from services.settings_service import SettingsService
from ui.app_events import app_events

SPLIT_ORDER_SCOPE_MESSAGE = (
    "拆单助手用于文本整理和辅助录单：可预览拆分结果并确认保存成功行。"
    "保存会写入订单和操作日志，但不会结算、不会计算赔付或余额。"
)
_SPLIT_PATTERN = re.compile(r"[，、；;,]+")


class SplitOrderWindow(QMainWindow):
    """拆单助手：文本整理 + 订单预览保存。"""

    def __init__(
        self,
        parent=None,
        *,
        import_service: OrderImportService | None = None,
        settings_service: SettingsService | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("拆单助手")
        self.resize(980, 760)
        self.setMinimumSize(820, 640)
        self._import_service = import_service or OrderImportService()
        session_factory = getattr(getattr(self._import_service, "_order_intake_service", None), "_session_factory", None)
        self._settings_service = settings_service or (
            SettingsService(session_factory) if session_factory is not None else SettingsService()
        )

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._result_lines: list[str] = []
        self._numbered = False
        self._preview = OrderImportPreview()
        self._import_completed = False
        self._filling_preview_table = False

        self._scope_hint = QLabel(SPLIT_ORDER_SCOPE_MESSAGE)
        self._scope_hint.setObjectName("scopeHint")
        self._scope_hint.setWordWrap(True)
        root.addWidget(self._scope_hint)

        self._input_text = QPlainTextEdit()
        self._input_text.setPlaceholderText("粘贴需要整理的文本；会按逗号、顿号、分号拆成多行")
        self._input_text.setMinimumHeight(100)
        root.addWidget(self._input_text)

        recognize_box = QGroupBox("识别结果")
        recognize_layout = QVBoxLayout(recognize_box)
        self._recognize_text = QPlainTextEdit()
        self._recognize_text.setReadOnly(True)
        self._recognize_text.setMinimumHeight(72)
        self._recognize_text.setPlainText(
            "等待拆分。可先整理文本并预览订单；确认保存时只保存勾选的解析成功行。"
        )
        recognize_layout.addWidget(self._recognize_text)
        root.addWidget(recognize_box)

        root.addLayout(self._build_config_row())
        root.addLayout(self._build_action_row())

        result_box = QGroupBox("拆分结果区域")
        result_layout = QVBoxLayout(result_box)
        self._result_text = QPlainTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setMinimumHeight(140)
        result_layout.addWidget(self._result_text)
        root.addWidget(result_box, stretch=1)

        preview_box = QGroupBox("订单预览")
        preview_layout = QVBoxLayout(preview_box)
        self._preview_table = QTableWidget(0, 10)
        self._preview_table.setHorizontalHeaderLabels(
            ["是否保存", "行号", "拆分文本", "地区", "解析状态", "投注类型", "金额", "条目数", "保存状态", "错误原因"]
        )
        self._preview_table.verticalHeader().setVisible(False)
        self._preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._preview_table.itemChanged.connect(self._on_preview_item_changed)
        preview_layout.addWidget(self._preview_table)
        root.addWidget(preview_box, stretch=2)

        self._btn_save = QPushButton("保存拆分结果到文件")
        self._btn_save.setObjectName("saveButton")
        self._btn_save.clicked.connect(self._on_save_results)
        root.addWidget(self._btn_save)

        self._apply_stylesheet()
        self._reload_declarers()
        self._update_confirm_button()

    def _build_config_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        row.addWidget(QLabel("单个号码最大金额："))
        self._edit_max_amount = QLineEdit("20")
        self._edit_max_amount.setFixedWidth(80)
        self._edit_max_amount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._edit_max_amount)

        row.addSpacing(16)

        self._region_group = QButtonGroup(self)
        region_specs = [
            ("自动识别", 0, True),
            ("澳门", 1, False),
            ("香港", 2, False),
        ]
        for text, idx, checked in region_specs:
            rb = QRadioButton(text)
            rb.setChecked(checked)
            self._region_group.addButton(rb, idx)
            row.addWidget(rb)

        row.addSpacing(12)
        row.addWidget(QLabel("申报人："))
        self._declarer_combo = QComboBox()
        self._declarer_combo.setMinimumWidth(130)
        self._declarer_combo.currentIndexChanged.connect(self._on_declarer_changed)
        row.addWidget(self._declarer_combo)
        self._plan_label = QLabel("配置方案：未绑定配置方案")
        row.addWidget(self._plan_label)

        row.addWidget(QLabel("渠道："))
        self._channel_combo = QComboBox()
        self._channel_combo.addItems(["拆单助手", "手工整理", "文本拆单"])
        self._channel_combo.setCurrentText("拆单助手")
        row.addWidget(self._channel_combo)

        row.addStretch(1)
        return row

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._btn_split = QPushButton("开始拆分")
        self._btn_style = QPushButton("调整拆分结果样式")
        self._btn_copy = QPushButton("复制结果")
        self._btn_preview_orders = QPushButton("预览订单")
        self._btn_confirm_save = QPushButton("确认保存成功行")
        btn_clear = QPushButton("清空输入")

        self._btn_split.clicked.connect(self._on_start_split)
        self._btn_style.clicked.connect(self._on_toggle_numbered_style)
        self._btn_copy.clicked.connect(self._on_copy_results)
        self._btn_preview_orders.clicked.connect(self._on_preview_orders)
        self._btn_confirm_save.clicked.connect(self._on_confirm_save)
        btn_clear.clicked.connect(self._on_clear_input)

        for btn in (self._btn_split, self._btn_style, self._btn_copy, self._btn_preview_orders, self._btn_confirm_save, btn_clear):
            btn.setObjectName("actionButton")
            row.addWidget(btn, stretch=1)

        return row

    def _on_start_split(self) -> None:
        raw = self._input_text.toPlainText()
        if not raw.strip():
            self._set_status("请输入需要拆分的内容")
            QMessageBox.warning(self, "拆单助手", "请输入需要拆分的内容")
            return
        self._result_lines = self._split_text(raw)
        self._numbered = False
        self._render_results()
        self._set_status(f"拆分完成：共 {len(self._result_lines)} 行。未写入订单数据库。")
        self._reset_preview()

    def _split_text(self, raw: str) -> list[str]:
        lines: list[str] = []
        for source_line in raw.splitlines():
            stripped_line = source_line.strip()
            if not stripped_line:
                continue
            for part in _SPLIT_PATTERN.split(stripped_line):
                cleaned = re.sub(r"\s+", " ", part.strip())
                if cleaned:
                    lines.append(cleaned)
        return lines

    def _render_results(self) -> None:
        if self._numbered:
            text = "\n".join(f"{index}. {line}" for index, line in enumerate(self._result_lines, start=1))
        else:
            text = "\n".join(self._result_lines)
        self._result_text.setPlainText(text)

    def _set_status(self, message: str) -> None:
        self._recognize_text.setPlainText(message)

    def _on_toggle_numbered_style(self) -> None:
        if not self._result_lines:
            self._set_status("没有可调整样式的拆分结果")
            QMessageBox.information(self, "拆单助手", "没有可调整样式的拆分结果")
            return
        self._numbered = not self._numbered
        self._render_results()
        self._set_status("已添加行号样式" if self._numbered else "已取消行号样式")

    def _on_clear_input(self) -> None:
        self._input_text.clear()
        self._recognize_text.clear()
        self._result_text.clear()
        self._result_lines = []
        self._numbered = False
        self._reset_preview()

    def _on_save_results(self) -> None:
        text = self._result_text.toPlainText().strip()
        if not text:
            self._set_status("没有可保存的拆分结果")
            QMessageBox.warning(self, "拆单助手", "没有可保存的拆分结果")
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "保存拆分结果",
            "split_order_result.txt",
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if not path:
            self._set_status("已取消保存")
            return
        try:
            Path(path).write_text(text + "\n", encoding="utf-8")
        except Exception as exc:
            self._set_status(f"保存失败：{exc}")
            QMessageBox.warning(self, "拆单助手", f"保存失败：{exc}")
            return
        self._set_status(f"保存成功：{path}")
        QMessageBox.information(self, "拆单助手", f"保存成功：{path}")

    def _on_copy_results(self) -> None:
        text = self._result_text.toPlainText().strip()
        if not text:
            self._set_status("没有可复制的拆分结果")
            QMessageBox.warning(self, "拆单助手", "没有可复制的拆分结果")
            return
        QApplication.clipboard().setText(text)
        self._set_status("拆分结果已复制到剪贴板")
        QMessageBox.information(self, "拆单助手", "拆分结果已复制到剪贴板")

    def _reload_declarers(self) -> None:
        self._declarer_combo.blockSignals(True)
        self._declarer_combo.clear()
        self._declarer_combo.addItem("未设置申报人", None)
        try:
            declarers = self._settings_service.list_declarers()
        except Exception:
            declarers = []
            self._plan_label.setText("配置方案：配置读取失败")
            self._set_status("申报人配置读取失败，已降级为未设置申报人")
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
        return self._channel_combo.currentText().strip() or "拆单助手"

    def _selected_region_mode(self) -> str | None:
        checked = self._region_group.checkedId()
        if checked == 1:
            return "澳门"
        if checked == 2:
            return "香港"
        return None

    def _preview_source_lines(self) -> list[str]:
        if self._result_lines:
            return list(self._result_lines)
        raw = self._input_text.toPlainText()
        if not raw.strip():
            return []
        self._result_lines = self._split_text(raw)
        self._numbered = False
        self._render_results()
        return list(self._result_lines)

    def _on_preview_orders(self) -> None:
        lines = self._preview_source_lines()
        if not lines:
            self._set_status("没有可预览的拆分结果")
            QMessageBox.warning(self, "拆单助手", "请先输入或拆分订单文本")
            return
        try:
            self._preview = self._import_service.preview_lines(
                lines,
                region_mode=self._selected_region_mode(),
                customer_name=self._selected_customer_name(),
            )
        except Exception as exc:
            self._set_status(f"预览失败：{exc}")
            QMessageBox.warning(self, "拆单助手", f"预览失败：{exc}")
            return
        self._import_completed = False
        self._fill_preview_table(self._preview)
        self._update_preview_stats()
        self._update_confirm_button()

    def _fill_preview_table(self, preview: OrderImportPreview) -> None:
        self._filling_preview_table = True
        try:
            self._preview_table.setRowCount(len(preview.rows))
            for row_index, row in enumerate(preview.rows):
                checked_item = QTableWidgetItem("")
                checked_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if row.success:
                    checked_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    checked_item.setCheckState(
                        Qt.CheckState.Checked if row.selected_for_import else Qt.CheckState.Unchecked
                    )
                else:
                    checked_item.setFlags(Qt.ItemFlag.ItemIsSelectable)
                    checked_item.setCheckState(Qt.CheckState.Unchecked)
                self._preview_table.setItem(row_index, 0, checked_item)

                values = [
                    str(row.line_number),
                    row.raw_text,
                    row.region,
                    "成功" if row.success else "失败",
                    row.bet_type_summary,
                    f"{row.amount_total:.2f}",
                    str(row.item_count),
                    row.import_status,
                    self._row_error_text(row),
                ]
                for column, value in enumerate(values, start=1):
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if column != 2 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self._preview_table.setItem(row_index, column, item)
        finally:
            self._filling_preview_table = False

    def _row_error_text(self, row) -> str:
        return "；".join(part for part in (row.error, row.import_error, row.duplicate_warning) if part)

    def _on_preview_item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling_preview_table or item.column() != 0:
            return
        self._sync_preview_selection_from_table()
        self._update_preview_stats()
        self._update_confirm_button()

    def _sync_preview_selection_from_table(self) -> None:
        rows = []
        for index, row in enumerate(self._preview.rows):
            item = self._preview_table.item(index, 0)
            selected = bool(row.success and item is not None and item.checkState() == Qt.CheckState.Checked)
            rows.append(replace(row, selected_for_import=selected))
        self._preview = replace(self._preview, rows=rows)

    def _selected_success_count(self) -> int:
        return sum(1 for row in self._preview.rows if row.success and row.selected_for_import and row.import_status != "已导入")

    def _update_preview_stats(self) -> None:
        self._set_status(
            f"预览完成：总行数 {self._preview.total_count}，"
            f"成功 {self._preview.success_count}，失败 {self._preview.failure_count}，"
            f"已勾选保存 {self._selected_success_count()}。"
        )

    def _update_confirm_button(self) -> None:
        self._btn_confirm_save.setEnabled(not self._import_completed and self._selected_success_count() > 0)

    def _reset_preview(self) -> None:
        self._preview = OrderImportPreview()
        self._import_completed = False
        if hasattr(self, "_preview_table"):
            self._preview_table.setRowCount(0)
        if hasattr(self, "_btn_confirm_save"):
            self._update_confirm_button()

    def _on_confirm_save(self) -> None:
        if self._import_completed:
            self._set_status("本次拆单保存已完成；请重新预览订单后再次保存")
            self._update_confirm_button()
            return
        self._sync_preview_selection_from_table()
        selected_count = self._selected_success_count()
        if selected_count <= 0:
            self._set_status("没有勾选可保存的成功行")
            self._update_confirm_button()
            return
        confirm_text = (
            "确认保存拆单助手预览中的勾选成功行？\n\n"
            f"总行数：{self._preview.total_count}\n"
            f"解析成功数：{self._preview.success_count}\n"
            f"解析失败数：{self._preview.failure_count}\n"
            f"将保存行数：{selected_count}\n"
            f"申报人：{self._selected_customer_name() or '未设置申报人'}\n"
            f"渠道：{self._selected_channel()}\n"
            f"配置方案：{self._selected_config_plan_name() or '未绑定配置方案'}\n\n"
            "只保存勾选成功行，失败行不会保存；本功能不会结算、不会计算赔付或余额。"
        )
        choice = QMessageBox.question(
            self,
            "确认保存成功行",
            confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            self._set_status("已取消确认保存；未写数据库")
            return
        try:
            result = self._import_service.confirm_import(
                self._preview,
                file_path="拆单助手",
                channel=self._selected_channel(),
                customer_name=self._selected_customer_name(),
                config_plan_name=self._selected_config_plan_name(),
                source="split_order",
                skip_history_duplicates=False,
                log_action="split_order/save",
                log_label="拆单保存",
                related_type="split_order",
            )
        except Exception as exc:
            self._set_status(f"保存失败：{exc}")
            QMessageBox.warning(self, "拆单助手", f"保存失败：{exc}")
            return

        self._preview = result.preview
        self._import_completed = True
        self._fill_preview_table(self._preview)
        self._set_status(
            f"保存完成：尝试 {result.attempted_count}，成功 {result.imported_count}，"
            f"保存失败 {result.save_failed_count}，跳过失败解析行 {result.skipped_parse_failed_count}，"
            f"跳过未勾选 {result.skipped_unselected_count}。"
        )
        self._update_confirm_button()
        if result.imported_count > 0:
            app_events.orders_changed.emit()
        if result.log_id is not None:
            app_events.logs_changed.emit()
        if result.imported_count and result.save_failed_count:
            QMessageBox.information(self, "拆单助手", "保存部分成功，请查看预览表中的保存状态。")
        elif result.imported_count:
            QMessageBox.information(self, "拆单助手", f"成功保存 {result.imported_count} 条订单。")
        elif result.save_failed_count:
            QMessageBox.warning(self, "拆单助手", "勾选成功行均保存失败，请查看错误原因。")

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f0f0f0;
            }
            QPlainTextEdit, QLineEdit, QComboBox {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                font-size: 13px;
                padding: 6px;
            }
            QGroupBox {
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                margin-top: 10px;
                padding-top: 12px;
                background: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton#actionButton {
                padding: 8px 12px;
                background: #ecf0f1;
                border: 1px solid #bdc3c7;
                font-size: 13px;
            }
            QPushButton#actionButton:hover {
                background: #dfe6e9;
            }
            QPushButton#actionButton:disabled {
                color: #95a5a6;
                background: #f4f6f7;
            }
            QPushButton#saveButton {
                padding: 10px;
                background: #ecf0f1;
                border: 1px solid #95a5a6;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#saveButton:hover {
                background: #dfe6e9;
            }
            QLabel#scopeHint {
                color: #7f8c8d;
                font-size: 13px;
                padding: 8px;
                border: 1px solid #d5d8dc;
                background: #f8f9fa;
            }
            QRadioButton, QLabel {
                font-size: 13px;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #bdc3c7;
                gridline-color: #d5d8dc;
                font-size: 12px;
            }
            QHeaderView::section {
                background: #ecf0f1;
                border: 1px solid #bdc3c7;
                padding: 4px;
                font-weight: 600;
            }
            """
        )
