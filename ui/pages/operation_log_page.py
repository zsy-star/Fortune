"""操作日志页面：从 OperationLog 表读取真实日志。"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from schemas.log_schema import OperationLogResult
from services.excel_export_service import ExcelExportService
from services.log_service import LogService

PAGE_SIZE = 20


def _dash(value: object | None) -> str:
    return str(value) if value not in (None, "") else "—"


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def _export_success_message(result) -> str:
    return (
        "导出成功\n"
        f"文件路径：{result.export_path}\n"
        f"行数：{result.row_count}\n"
        f"文件大小：{_format_size(result.size_bytes)}"
    )


class OperationLogPage(QWidget):
    def __init__(
        self,
        parent=None,
        log_service: LogService | None = None,
        excel_export_service: ExcelExportService | None = None,
    ):
        super().__init__(parent)
        self._log_service = log_service or LogService()
        self._excel_export_service = excel_export_service or ExcelExportService(self._log_service._session_factory)
        self._page = 1
        self._total = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_action_row())
        root.addLayout(self._build_summary_row())
        root.addWidget(self._build_separator())
        root.addWidget(self._build_table(), stretch=1)
        root.addLayout(self._build_pager())

        self._apply_stylesheet()
        self.reload_data()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload_data()

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._module = QLineEdit()
        self._module.setPlaceholderText("模块")
        self._action = QLineEdit()
        self._action.setPlaceholderText("操作")
        self._operator = QLineEdit()
        self._operator.setPlaceholderText("操作人")
        self._related_type = QLineEdit()
        self._related_type.setPlaceholderText("关联类型")
        self._keyword = QLineEdit()
        self._keyword.setPlaceholderText("描述关键词")
        self._start_date = self._make_date_edit()
        self._end_date = self._make_date_edit()

        for label, widget in (
            ("模块", self._module),
            ("操作", self._action),
            ("操作人", self._operator),
            ("关联", self._related_type),
            ("关键词", self._keyword),
            ("开始", self._start_date),
            ("结束", self._end_date),
        ):
            row.addWidget(QLabel(label))
            row.addWidget(widget)
        return row

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        specs = [
            ("今天", self._on_today, True),
            ("昨天", self._on_yesterday, True),
            ("最近三天", self._on_last_three_days, True),
            ("查询", self._on_query, True),
            ("重置", self._on_reset, True),
            ("刷新", self.reload_data, True),
            ("导出 Excel", self._on_export_excel, True),
            ("清空日志", self._on_clear_disabled, False),
        ]
        for text, handler, enabled in specs:
            btn = QPushButton(text)
            if text == "导出 Excel":
                self._btn_export_excel = btn
            btn.setObjectName("logActionLink")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(enabled)
            btn.clicked.connect(handler)
            if not enabled:
                btn.setToolTip("本阶段暂未开放")
            row.addWidget(btn)
        row.addStretch(1)
        return row

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._lbl_total = QLabel()
        self._lbl_displayed = QLabel()
        row.addWidget(self._lbl_total)
        row.addStretch(1)
        row.addWidget(self._lbl_displayed)
        return row

    def _build_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setObjectName("logSeparator")
        line.setFixedHeight(2)
        return line

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(["时间", "模块", "操作", "描述", "操作人", "关联类型", "关联ID"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        return self._table

    def _build_pager(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._btn_prev = QPushButton("上一页")
        self._btn_next = QPushButton("下一页")
        self._lbl_page = QLabel()
        self._btn_prev.clicked.connect(self._prev_page)
        self._btn_next.clicked.connect(self._next_page)
        row.addWidget(self._btn_prev)
        row.addWidget(self._btn_next)
        row.addWidget(self._lbl_page)
        row.addStretch(1)
        return row

    def _make_date_edit(self) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        edit.setSpecialValueText("不限")
        edit.setMinimumDate(QDate(2000, 1, 1))
        edit.setDate(edit.minimumDate())
        return edit

    def reload_data(self) -> None:
        if not self._validate_dates():
            return
        module, action, operator, related_type, keyword, start_dt, end_dt = self._filters()
        self._total = self._log_service.count_logs(
            module=module,
            action=action,
            operator=operator,
            related_type=related_type,
            keyword=keyword,
            start_date=start_dt,
            end_date=end_dt,
        )
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page > max_page:
            self._page = max_page
        logs = self._log_service.list_logs(
            module=module,
            action=action,
            operator=operator,
            related_type=related_type,
            keyword=keyword,
            start_date=start_dt,
            end_date=end_dt,
            limit=PAGE_SIZE,
            offset=(self._page - 1) * PAGE_SIZE,
        )
        self._fill_table(logs)
        self._update_summary(len(logs))
        self._update_pager()

    def _filters(self):
        return (
            self._module.text().strip() or None,
            self._action.text().strip() or None,
            self._operator.text().strip() or None,
            self._related_type.text().strip() or None,
            self._keyword.text().strip() or None,
            self._start_datetime(),
            self._end_datetime(),
        )

    def _date_or_none(self, edit: QDateEdit):
        value = edit.date()
        if value == edit.minimumDate():
            return None
        return value

    def _start_datetime(self) -> datetime | None:
        value = self._date_or_none(self._start_date)
        return datetime.combine(value.toPython(), time.min) if value else None

    def _end_datetime(self) -> datetime | None:
        value = self._date_or_none(self._end_date)
        return datetime.combine(value.toPython(), time.max) if value else None

    def _validate_dates(self) -> bool:
        start = self._date_or_none(self._start_date)
        end = self._date_or_none(self._end_date)
        if start and end and start > end:
            self._lbl_total.setText("开始日期不能晚于结束日期")
            return False
        return True

    def _fill_table(self, logs: list[OperationLogResult]) -> None:
        self._table.setRowCount(len(logs))
        for row_idx, log in enumerate(logs):
            description = log.description
            shown_description = description if len(description) <= 80 else description[:77] + "..."
            values = [
                log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                log.module,
                log.action,
                shown_description,
                _dash(log.operator),
                _dash(log.related_type),
                _dash(log.related_id),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col_idx != 3 else Qt.AlignmentFlag.AlignLeft)
                if col_idx == 3:
                    item.setToolTip(description)
                self._table.setItem(row_idx, col_idx, item)

    def _update_summary(self, displayed_count: int) -> None:
        if self._total == 0:
            self._lbl_total.setText("暂无操作日志")
        else:
            self._lbl_total.setText(f"共有{self._total}条操作记录")
        self._lbl_displayed.setText(f"已显示{displayed_count}条记录")

    def _update_pager(self) -> None:
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._lbl_page.setText(f"第 {self._page} / {max_page} 页    总记录数：{self._total}")
        self._btn_prev.setEnabled(self._page > 1)
        self._btn_next.setEnabled(self._page < max_page)

    def _set_day_range(self, day: datetime) -> None:
        self._start_date.setDate(QDate(day.year, day.month, day.day))
        self._end_date.setDate(QDate(day.year, day.month, day.day))
        self._page = 1
        self.reload_data()

    def _on_today(self) -> None:
        self._set_day_range(datetime.now())

    def _on_yesterday(self) -> None:
        self._set_day_range(datetime.now() - timedelta(days=1))

    def _on_last_three_days(self) -> None:
        end = datetime.now()
        start = end - timedelta(days=2)
        self._start_date.setDate(QDate(start.year, start.month, start.day))
        self._end_date.setDate(QDate(end.year, end.month, end.day))
        self._page = 1
        self.reload_data()

    def _on_query(self) -> None:
        self._page = 1
        self.reload_data()

    def _on_reset(self) -> None:
        for edit in (self._module, self._action, self._operator, self._related_type, self._keyword):
            edit.clear()
        self._start_date.setDate(self._start_date.minimumDate())
        self._end_date.setDate(self._end_date.minimumDate())
        self._page = 1
        self.reload_data()

    def _on_export_excel(self) -> None:
        if not self._validate_dates():
            return
        output_dir = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not output_dir:
            self._lbl_total.setText("已取消导出")
            return

        module, action, operator, related_type, keyword, start_dt, end_dt = self._filters()
        try:
            result = self._excel_export_service.export_operation_logs(
                module=module,
                action=action,
                operator=operator,
                related_type=related_type,
                keyword=keyword,
                start_date=start_dt,
                end_date=end_dt,
                output_dir=output_dir,
            )
        except Exception as exc:
            QMessageBox.warning(self, "导出 Excel", f"导出失败：{exc}")
            self._lbl_total.setText(f"导出失败：{exc}")
            return

        QMessageBox.information(self, "导出 Excel", _export_success_message(result))
        self._lbl_total.setText(f"导出成功：{result.file_name}")

    def _prev_page(self) -> None:
        if self._page > 1:
            self._page -= 1
            self.reload_data()

    def _next_page(self) -> None:
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page < max_page:
            self._page += 1
            self.reload_data()

    def _on_clear_disabled(self) -> None:
        self._lbl_total.setText("清空日志暂未开放")

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QPushButton#logActionLink, QPushButton {
                color: #1a5276;
                border: 1px solid #bdc3c7;
                padding: 5px 10px;
                font-size: 13px;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #ebf5fb;
            }
            QPushButton:disabled {
                color: #95a5a6;
            }
            QFrame#logSeparator {
                background-color: #3498db;
                border: none;
                max-height: 2px;
            }
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                gridline-color: #d5d8dc;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #ecf0f1;
                padding: 6px 4px;
                border: 1px solid #bdc3c7;
                font-weight: 600;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
            QLineEdit, QDateEdit {
                padding: 4px 6px;
                border: 1px solid #bdc3c7;
                border-radius: 2px;
                background: #ffffff;
                font-size: 13px;
            }
            """
        )
