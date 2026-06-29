"""Adjustment record history dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from schemas.adjustment_record_schema import AdjustmentRecordResult
from services.adjustment_record_service import AdjustmentRecordService

TYPE_LABELS = {
    "special": "特码",
    "lianxiao": "连肖",
}
LABEL_TYPES = {value: key for key, value in TYPE_LABELS.items()}


def _display(value: object | None) -> str:
    return str(value) if value not in (None, "", {}, []) else "—"


class AdjustmentRecordDialog(QDialog):
    """Read-only adjustment record browser."""

    def __init__(
        self,
        parent=None,
        *,
        default_type: str | None = None,
        service: AdjustmentRecordService | None = None,
    ):
        super().__init__(parent)
        self._service = service or AdjustmentRecordService()
        self._records: list[AdjustmentRecordResult] = []
        self._selected_record: AdjustmentRecordResult | None = None

        self.setWindowTitle("调整记录")
        self.resize(980, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("调整记录")
        title.setObjectName("dialogTitle")
        root.addWidget(title)
        root.addLayout(self._build_filter_row(default_type))
        root.addWidget(self._build_table(), stretch=4)

        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setPlaceholderText("选中一条调整记录后显示完整快照。")
        root.addWidget(self._detail, stretch=5)

        root.addLayout(self._build_button_row())
        self._apply_stylesheet()
        self.reload_data()

    def _build_filter_row(self, default_type: str | None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("类型"))
        self._type_filter = QComboBox()
        self._type_filter.addItem("全部", None)
        self._type_filter.addItem("特码", "special")
        self._type_filter.addItem("连肖", "lianxiao")
        if default_type in TYPE_LABELS:
            self._type_filter.setCurrentIndex(self._type_filter.findData(default_type))
        self._type_filter.currentIndexChanged.connect(lambda _index: self.reload_data())
        row.addWidget(self._type_filter)

        row.addWidget(QLabel("地区"))
        self._region_filter = QComboBox()
        self._region_filter.addItem("全部", None)
        self._region_filter.addItem("澳门", "澳门")
        self._region_filter.addItem("香港", "香港")
        self._region_filter.currentIndexChanged.connect(lambda _index: self.reload_data())
        row.addWidget(self._region_filter)

        row.addStretch(1)
        self._status_label = QLabel("")
        self._status_label.setObjectName("statusLabel")
        row.addWidget(self._status_label)
        return row

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            ["ID", "类型", "保存时间", "地区", "原金额合计", "调整金额合计", "调整后合计", "条目数", "备注"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        return self._table

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_copy = QPushButton("复制记录详情")
        self._btn_export = QPushButton("导出记录详情")
        self._btn_print = QPushButton("打印记录文本")
        self._btn_close = QPushButton("关闭")
        self._btn_copy.clicked.connect(self._on_copy_detail)
        self._btn_export.clicked.connect(self._on_export_detail)
        self._btn_print.clicked.connect(self._on_print_detail)
        self._btn_close.clicked.connect(self.accept)
        row.addWidget(self._btn_copy)
        row.addWidget(self._btn_export)
        row.addWidget(self._btn_print)
        row.addWidget(self._btn_close)
        return row

    def reload_data(self) -> None:
        adjustment_type = self._type_filter.currentData()
        region = self._region_filter.currentData()
        try:
            self._records = self._service.list_records(
                adjustment_type=adjustment_type,
                region=region,
                limit=200,
            )
        except Exception as exc:
            self._records = []
            self._status_label.setText(f"加载失败：{exc}")
        self._fill_table()
        if self._records:
            self._table.selectRow(0)
            self._status_label.setText(f"共 {len(self._records)} 条记录")
        else:
            self._selected_record = None
            self._detail.clear()
            self._status_label.setText("暂无调整记录")
        self._update_buttons()

    def _fill_table(self) -> None:
        self._table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            values = [
                str(record.id),
                TYPE_LABELS.get(record.adjustment_type, "未知类型"),
                record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                _display(record.region),
                _display(record.original_total),
                _display(record.adjustment_total),
                _display(record.after_total),
                _display(record.item_count),
                _display(record.note),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, column, item)

    def _on_selection_changed(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            self._selected_record = None
            self._detail.clear()
        else:
            self._selected_record = self._records[row]
            self._detail.setPlainText(self._service.format_record_text(self._selected_record))
        self._update_buttons()

    def _update_buttons(self) -> None:
        enabled = self._selected_record is not None
        self._btn_copy.setEnabled(enabled)
        self._btn_export.setEnabled(enabled)
        self._btn_print.setEnabled(enabled)

    def _current_text(self) -> str:
        return self._detail.toPlainText()

    def _on_copy_detail(self) -> None:
        if self._selected_record is None:
            self._status_label.setText("请先选择调整记录")
            return
        QApplication.clipboard().setText(self._current_text())
        self._status_label.setText("已复制记录详情")

    def _on_export_detail(self) -> None:
        if self._selected_record is None:
            self._status_label.setText("请先选择调整记录")
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出调整记录详情",
            f"调整记录-{self._selected_record.id}.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            self._status_label.setText("已取消导出")
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(self._current_text())
        except OSError as exc:
            QMessageBox.warning(self, "导出调整记录详情", f"导出失败：{exc}")
            self._status_label.setText(f"导出失败：{exc}")
            return
        self._status_label.setText(f"已导出记录详情：{path}")

    def _on_print_detail(self) -> None:
        if self._selected_record is None:
            self._status_label.setText("请先选择调整记录")
            return
        self._detail.setPlainText(
            self._current_text()
            + "\n\n打印提示：当前未调用真实打印机，请复制或导出后打印。"
        )
        self._status_label.setText("已生成打印文本，请复制或导出后打印")

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QLabel#dialogTitle {
                font-size: 18px;
                font-weight: 600;
                color: #2c3e50;
            }
            QLabel#statusLabel {
                color: #607d86;
            }
            QTableWidget {
                border: 1px solid #b8c7ca;
                gridline-color: #d5dfe1;
                alternate-background-color: #f7fafb;
            }
            QHeaderView::section {
                background: #dff2f3;
                padding: 4px;
                border: 1px solid #afc9cc;
                font-weight: 600;
            }
            QPlainTextEdit {
                border: 1px solid #b8c7ca;
                background: #ffffff;
                font-family: Consolas, "Microsoft YaHei", monospace;
            }
            QPushButton {
                padding: 5px 12px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #e8f7f8;
                border-color: #5fbac2;
            }
            """
        )
