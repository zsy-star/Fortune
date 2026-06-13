"""Read-only settlement ledger page."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
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
from schemas.order_schema import OrderSummary
from services.excel_export_service import ExcelExportService
from services.log_service import LogService
from services.order_service import OrderService

PAGE_SIZE = 20


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _dash(value: object | None) -> str:
    return str(value) if value not in (None, "") else "-"


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


class SettlementLedgerPage(QWidget):
    def __init__(
        self,
        parent=None,
        order_service: OrderService | None = None,
        log_service: LogService | None = None,
        excel_export_service: ExcelExportService | None = None,
    ):
        super().__init__(parent)
        self._order_service = order_service or OrderService()
        self._log_service = log_service or LogService()
        self._excel_export_service = excel_export_service or ExcelExportService(self._order_service._session_factory)
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

        self._cmb_region = QComboBox()
        self._cmb_region.addItems(["全部", "澳门", "香港"])
        self._keyword = QLineEdit()
        self._keyword.setPlaceholderText("订单号 / 订单ID")
        self._start_date = self._make_date_edit()
        self._end_date = self._make_date_edit()

        for label, widget in (
            ("地区", self._cmb_region),
            ("订单", self._keyword),
            ("结算开始", self._start_date),
            ("结算结束", self._end_date),
        ):
            row.addWidget(QLabel(label))
            row.addWidget(widget)
        row.addStretch(1)
        return row

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for text, handler in (
            ("查询", self._on_query),
            ("重置", self._on_reset),
            ("刷新", self.reload_data),
            ("导出 Excel", self._on_export_excel),
        ):
            btn = QPushButton(text)
            if text == "导出 Excel":
                self._btn_export_excel = btn
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch(1)
        return row

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._lbl_total = QLabel()
        self._lbl_displayed = QLabel()
        self._lbl_readonly = QLabel("只读流水：本页面不修改订单状态，不触发重新结算。")
        self._lbl_readonly.setObjectName("hintLabel")
        row.addWidget(self._lbl_total)
        row.addWidget(self._lbl_readonly)
        row.addStretch(1)
        row.addWidget(self._lbl_displayed)
        return row

    def _build_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setObjectName("ledgerSeparator")
        line.setFixedHeight(2)
        return line

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 11)
        self._table.setHorizontalHeaderLabels(
            [
                "订单ID",
                "订单号",
                "客户",
                "地区",
                "状态",
                "投注总额",
                "结算时间",
                "开奖期号（暂未记录）",
                "最近操作日志",
                "创建时间",
                "更新时间",
            ]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        for col in (0, 2, 3, 4, 5, 6, 7, 9, 10):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
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
        region, keyword, start_dt, end_dt = self._filters()
        try:
            self._total = self._order_service.count_settlement_ledger(
                region=region,
                keyword=keyword,
                start_date=start_dt,
                end_date=end_dt,
            )
            max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
            if self._page > max_page:
                self._page = max_page
            rows = self._order_service.list_settlement_ledger(
                region=region,
                keyword=keyword,
                start_date=start_dt,
                end_date=end_dt,
                limit=PAGE_SIZE,
                offset=(self._page - 1) * PAGE_SIZE,
            )
        except Exception as exc:
            self._table.setRowCount(0)
            self._lbl_total.setText(f"结算流水加载失败：{exc}")
            self._lbl_displayed.setText("已显示0条记录")
            self._update_pager()
            return

        self._fill_table(rows)
        self._update_summary(len(rows))
        self._update_pager()

    def _filters(self):
        region = None if self._cmb_region.currentText() == "全部" else self._cmb_region.currentText()
        return (
            region,
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

    def _fill_table(self, rows: list[OrderSummary]) -> None:
        self._table.setRowCount(len(rows))
        for row_idx, order in enumerate(rows):
            log = self._latest_settlement_log(order)
            settlement_time = log.created_at if log else order.updated_at
            log_text = log.description if log else "-"
            shown_log = log_text if len(log_text) <= 80 else log_text[:77] + "..."
            values = [
                str(order.id),
                order.order_no,
                _dash(order.customer_name),
                order.region,
                order.status,
                _money(order.total_amount),
                settlement_time.strftime("%Y-%m-%d %H:%M:%S"),
                "-",
                shown_log,
                order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                order.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                alignment = Qt.AlignmentFlag.AlignLeft if col_idx == 8 else Qt.AlignmentFlag.AlignCenter
                item.setTextAlignment(alignment)
                if col_idx == 8:
                    item.setToolTip(log_text)
                self._table.setItem(row_idx, col_idx, item)

    def _latest_settlement_log(self, order: OrderSummary) -> OperationLogResult | None:
        logs = self._log_service.list_logs(
            module="settlement",
            action="commit",
            related_type="order",
            keyword=order.order_no,
            limit=1,
        )
        return logs[0] if logs else None

    def _update_summary(self, displayed_count: int) -> None:
        if self._total == 0:
            self._lbl_total.setText("暂无结算记录")
        else:
            self._lbl_total.setText(f"共有{self._total}条结算记录")
        self._lbl_displayed.setText(f"已显示{displayed_count}条记录")

    def _update_pager(self) -> None:
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._lbl_page.setText(f"第 {self._page} / {max_page} 页   总记录数：{self._total}")
        self._btn_prev.setEnabled(self._page > 1)
        self._btn_next.setEnabled(self._page < max_page)

    def _on_query(self) -> None:
        self._page = 1
        self.reload_data()

    def _on_reset(self) -> None:
        self._cmb_region.setCurrentIndex(0)
        self._keyword.clear()
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

        region, keyword, start_dt, end_dt = self._filters()
        try:
            result = self._excel_export_service.export_settlement_ledger(
                region=region,
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

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QPushButton {
                color: #1a5276;
                border: 1px solid #bdc3c7;
                padding: 5px 10px;
                font-size: 13px;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #ebf5fb;
            }
            QFrame#ledgerSeparator {
                background-color: #27ae60;
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
                background-color: #eafaf1;
                padding: 6px 4px;
                border: 1px solid #bdc3c7;
                font-weight: 600;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
            QLabel#hintLabel {
                color: #7f8c8d;
            }
            QLineEdit, QComboBox, QDateEdit {
                padding: 4px 6px;
                border: 1px solid #bdc3c7;
                border-radius: 2px;
                background: #ffffff;
                font-size: 13px;
            }
            """
        )
