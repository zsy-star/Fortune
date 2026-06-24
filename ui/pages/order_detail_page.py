"""订单详情页面：从数据库读取订单与明细。"""

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
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from schemas.order_schema import OrderDetailResult, OrderSummary
from services.draw_service import DrawService
from services.excel_export_service import ExcelExportService
from services.log_service import LogService
from services.order_service import OrderService
from services.settlement_service import SettlementService
from ui.dialogs.settlement_preview_dialog import SettlementPreviewDialog

PAGE_SIZE = 20
VOIDABLE_ORDER_STATUSES = {"active", "pending"}
ORDER_STATUS_SETTLED = "settled"
ORDER_STATUS_VOIDED = "voided"


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


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


class OrderDetailPage(QWidget):
    def __init__(
        self,
        parent=None,
        order_service: OrderService | None = None,
        log_service: LogService | None = None,
        draw_service: DrawService | None = None,
        settlement_service: SettlementService | None = None,
        excel_export_service: ExcelExportService | None = None,
    ):
        super().__init__(parent)
        self._order_service = order_service or OrderService()
        session_factory = self._order_service._session_factory
        self._log_service = log_service or LogService(session_factory)
        self._draw_service = draw_service or DrawService(session_factory)
        self._settlement_service = settlement_service or SettlementService(session_factory)
        self._excel_export_service = excel_export_service or ExcelExportService(session_factory)
        self._page = 1
        self._total = 0
        self._selected_order_id: int | None = None
        self._logged_order_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        root.addLayout(self._build_toolbar())
        root.addLayout(self._build_filter_row())
        root.addWidget(self._build_order_table(), stretch=3)
        root.addLayout(self._build_pager())
        root.addWidget(self._build_detail_panel(), stretch=3)
        root.addWidget(self._build_status_panel())

        self._apply_stylesheet()
        self.reload_data()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload_data()

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        hint = QLabel(
            "批量处理、导入订单和正式兑奖暂未开放；这些功能需要权限、余额和赔付规则支持。"
            "当前测试版请使用查询、Excel 导出、结算预览、作废。"
        )
        hint.setObjectName("scopeHint")
        hint.setWordWrap(True)
        row.addWidget(hint)
        row.addStretch(1)
        return row

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._cmb_region = QComboBox()
        self._cmb_region.addItems(["全部", "澳门", "香港"])
        self._edit_order_no = QLineEdit()
        self._edit_order_no.setPlaceholderText("订单号关键词")
        self._edit_customer = QLineEdit()
        self._edit_customer.setPlaceholderText("客户名称")
        self._edit_channel = QLineEdit()
        self._edit_channel.setPlaceholderText("渠道")
        self._cmb_status = QComboBox()
        self._cmb_status.addItems(["全部", "active", "pending", "settled", "voided", "cancelled"])
        self._start_date = self._make_date_edit()
        self._end_date = self._make_date_edit()

        for label, widget in (
            ("地区", self._cmb_region),
            ("订单号", self._edit_order_no),
            ("客户", self._edit_customer),
            ("渠道", self._edit_channel),
            ("状态", self._cmb_status),
            ("开始", self._start_date),
            ("结束", self._end_date),
        ):
            row.addWidget(QLabel(label))
            row.addWidget(widget)

        btn_query = QPushButton("查询")
        btn_reset = QPushButton("重置")
        btn_refresh = QPushButton("刷新")
        self._btn_export_excel = QPushButton("导出 Excel")
        btn_query.clicked.connect(self._on_query)
        btn_reset.clicked.connect(self._on_reset)
        btn_refresh.clicked.connect(self.reload_data)
        self._btn_export_excel.clicked.connect(self._on_export_excel)
        row.addWidget(btn_query)
        row.addWidget(btn_reset)
        row.addWidget(btn_refresh)
        row.addWidget(self._btn_export_excel)
        return row

    def _make_date_edit(self) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        edit.setSpecialValueText("不限")
        edit.setMinimumDate(QDate(2000, 1, 1))
        edit.setDate(edit.minimumDate())
        return edit

    def _build_order_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(["订单号", "创建时间", "地区", "客户名称", "渠道", "总金额", "状态", "来源"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(lambda _item: self._on_selection_changed())
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
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

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._detail_info = QLabel("请选择订单")
        self._detail_info.setWordWrap(True)
        self._raw_text = QPlainTextEdit()
        self._raw_text.setReadOnly(True)
        self._raw_text.setPlaceholderText("原始文本")
        self._raw_text.setMaximumHeight(90)

        self._item_table = QTableWidget(0, 5)
        self._item_table.setHorizontalHeaderLabels(["投注类型", "投注内容", "金额", "赔率", "备注"])
        self._item_table.verticalHeader().setVisible(False)
        self._item_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._item_table.horizontalHeader().setStretchLastSection(True)

        preview_row = QHBoxLayout()
        self._btn_preview = QPushButton("结算预览")
        self._btn_preview.setEnabled(False)
        self._btn_preview.clicked.connect(self._on_settlement_preview)
        self._btn_void = QPushButton("作废订单")
        self._btn_void.setEnabled(False)
        self._btn_void.clicked.connect(self._on_void_order)
        preview_row.addWidget(self._btn_preview)
        preview_row.addWidget(self._btn_void)
        preview_row.addStretch(1)

        self._prize_hint = QLabel(
            "结算预览：只读查看当前订单在指定期开奖结果下的命中情况。"
            "正式确认结算：在预览窗口二次确认后保存结算记录并写入操作日志。"
            "赔付、盈亏和余额功能暂未开放。"
        )
        self._prize_hint.setObjectName("prizeHint")

        layout.addWidget(self._detail_info)
        layout.addWidget(self._raw_text)
        layout.addWidget(self._item_table, stretch=1)
        layout.addLayout(preview_row)
        layout.addWidget(self._prize_hint)
        return panel

    def _build_status_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("resultPanel")
        layout = QHBoxLayout(frame)
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)
        return frame

    def reload_data(self) -> None:
        if not self._validate_dates():
            return
        region, order_no, customer, channel, status, start_dt, end_dt = self._filters()
        self._total = self._order_service.count_orders(
            region=region,
            order_no=order_no,
            customer_name=customer,
            channel=channel,
            status=status,
            start_date=start_dt,
            end_date=end_dt,
        )
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page > max_page:
            self._page = max_page
        rows = self._order_service.list_orders(
            region=region,
            order_no=order_no,
            customer_name=customer,
            channel=channel,
            status=status,
            start_date=start_dt,
            end_date=end_dt,
            limit=PAGE_SIZE,
            offset=(self._page - 1) * PAGE_SIZE,
        )
        self._fill_table(rows)
        self._update_pager()

    def _filters(self):
        region = None if self._cmb_region.currentText() == "全部" else self._cmb_region.currentText()
        status = None if self._cmb_status.currentText() == "全部" else self._cmb_status.currentText()
        return (
            region,
            self._edit_order_no.text().strip() or None,
            self._edit_customer.text().strip() or None,
            self._edit_channel.text().strip() or None,
            status,
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
            self._status_label.setText("开始日期不能晚于结束日期")
            return False
        return True

    def _fill_table(self, rows: list[OrderSummary]) -> None:
        self._table.setRowCount(len(rows))
        self._row_order_ids: list[int] = []
        for row_idx, order in enumerate(rows):
            self._row_order_ids.append(order.id)
            values = [
                order.order_no,
                order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                order.region,
                _dash(order.customer_name),
                _dash(order.channel),
                _money(order.total_amount),
                order.status,
                _dash(order.source),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_idx, col_idx, item)
        if not rows:
            self._status_label.setText("暂无订单数据。订单保存功能接入后，订单会显示在这里。")
            self._clear_detail()
        else:
            self._status_label.setText(f"已加载 {len(rows)} 条订单")

    def _update_pager(self) -> None:
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._lbl_page.setText(f"第 {self._page} / {max_page} 页    总记录数：{self._total}")
        self._btn_prev.setEnabled(self._page > 1)
        self._btn_next.setEnabled(self._page < max_page)

    def _on_query(self) -> None:
        self._page = 1
        self.reload_data()

    def _on_reset(self) -> None:
        self._cmb_region.setCurrentIndex(0)
        self._cmb_status.setCurrentIndex(0)
        self._edit_order_no.clear()
        self._edit_customer.clear()
        self._edit_channel.clear()
        self._start_date.setDate(self._start_date.minimumDate())
        self._end_date.setDate(self._end_date.minimumDate())
        self._page = 1
        self.reload_data()

    def _on_export_excel(self) -> None:
        if not self._validate_dates():
            return
        output_dir = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not output_dir:
            self._status_label.setText("已取消导出")
            return

        region, order_no, _customer, _channel, status, start_dt, end_dt = self._filters()
        try:
            result = self._excel_export_service.export_orders(
                region=region,
                status=status,
                start_date=start_dt,
                end_date=end_dt,
                keyword=order_no,
                include_voided=False,
                output_dir=output_dir,
            )
        except Exception as exc:
            QMessageBox.warning(self, "导出 Excel", f"导出失败：{exc}")
            self._status_label.setText(f"导出失败：{exc}")
            return

        QMessageBox.information(self, "导出 Excel", _export_success_message(result))
        self._status_label.setText(f"导出成功：{result.file_name}")

    def _prev_page(self) -> None:
        if self._page > 1:
            self._page -= 1
            self.reload_data()

    def _next_page(self) -> None:
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page < max_page:
            self._page += 1
            self.reload_data()

    def _on_selection_changed(self) -> None:
        selected = self._table.selectionModel().selectedRows()
        if not selected:
            self._clear_detail()
            return
        row = selected[0].row()
        if row >= len(self._row_order_ids):
            self._clear_detail()
            return
        self._load_detail(self._row_order_ids[row])

    def _load_detail(self, order_id: int) -> None:
        detail = self._order_service.get_order(order_id)
        if detail is None:
            self._status_label.setText("订单不存在或已被删除，列表已刷新。")
            self.reload_data()
            return
        self._selected_order_id = order_id
        self._render_detail(detail)
        if self._logged_order_id != order_id:
            self._logged_order_id = order_id
            try:
                self._log_service.create_log(
                    module="订单详情",
                    action="查看订单",
                    description=f"查看订单 {detail.order_no}",
                    related_type="order",
                    related_id=order_id,
                )
            except Exception:
                self._status_label.setText("订单已显示，但查看日志写入失败。")

    def _render_detail(self, detail: OrderDetailResult) -> None:
        self._btn_preview.setEnabled(True)
        self._btn_void.setEnabled(detail.status in VOIDABLE_ORDER_STATUSES)
        self._detail_info.setText(
            "订单号：{no}    客户：{customer}    渠道：{channel}    地区：{region}    "
            "来源：{source}    创建：{created}    更新：{updated}    状态：{status}    总金额：{total}".format(
                no=detail.order_no,
                customer=_dash(detail.customer_name),
                channel=_dash(detail.channel),
                region=detail.region,
                source=_dash(detail.source),
                created=detail.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                updated=detail.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                status=detail.status,
                total=_money(detail.total_amount),
            )
        )
        self._raw_text.setPlainText(detail.raw_text)
        self._item_table.setRowCount(len(detail.items))
        for row_idx, item in enumerate(detail.items):
            values = [
                item.bet_type,
                item.selection,
                _money(item.amount),
                _dash(item.odds),
                _dash(item.note),
            ]
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._item_table.setItem(row_idx, col_idx, cell)

    def _clear_detail(self) -> None:
        self._selected_order_id = None
        self._detail_info.setText("请选择订单")
        self._raw_text.clear()
        self._item_table.setRowCount(0)
        self._btn_preview.setEnabled(False)
        self._btn_void.setEnabled(False)

    def _on_settlement_preview(self) -> None:
        if self._selected_order_id is None:
            self._status_label.setText("请先选择订单")
            return
        dialog = SettlementPreviewDialog(
            self._selected_order_id,
            parent=self,
            order_service=self._order_service,
            draw_service=self._draw_service,
            settlement_service=self._settlement_service,
        )
        if not dialog.is_valid():
            QMessageBox.warning(self, "结算预览", "订单不存在或已被删除。")
            return
        dialog.exec()
        if dialog.settlement_committed():
            self.reload_data()
            if self._selected_order_id is not None:
                self._load_detail(self._selected_order_id)

    def _on_void_order(self) -> None:
        if self._selected_order_id is None:
            self._status_label.setText("请先选择订单")
            QMessageBox.warning(self, "作废订单", "请先选择订单")
            return

        detail = self._order_service.get_order(self._selected_order_id)
        if detail is None:
            self._status_label.setText("订单不存在或已被删除，列表已刷新。")
            self.reload_data()
            return
        if detail.status == ORDER_STATUS_SETTLED:
            QMessageBox.warning(self, "作废订单", "已结算订单不能作废")
            self._btn_void.setEnabled(False)
            return
        if detail.status == ORDER_STATUS_VOIDED:
            QMessageBox.warning(self, "作废订单", "该订单已作废，不能重复作废")
            self._btn_void.setEnabled(False)
            return
        if detail.status not in VOIDABLE_ORDER_STATUSES:
            QMessageBox.warning(self, "作废订单", f"当前状态不能作废：{detail.status}")
            self._btn_void.setEnabled(False)
            return

        reason, ok = QInputDialog.getMultiLineText(
            self,
            "作废订单",
            "请输入作废原因",
        )
        if not ok:
            self._status_label.setText("已取消作废订单")
            return
        reason = reason.strip()
        if not reason:
            QMessageBox.warning(self, "作废订单", "请输入作废原因")
            return

        confirm_text = (
            f"订单ID / 订单号：{detail.id} / {detail.order_no}\n"
            f"当前状态：{detail.status}\n"
            f"投注总额：{_money(detail.total_amount)}\n"
            f"作废原因：{reason}\n\n"
            "作废后订单不会被删除，但会从有效统计中排除。\n"
            "该操作会写入操作日志。\n\n"
            "确认作废该订单？"
        )
        choice = QMessageBox.question(
            self,
            "确认作废订单",
            confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            self._status_label.setText("已取消作废订单")
            return

        try:
            result = self._order_service.void_order(detail.id, reason, operator="system")
        except Exception as exc:
            QMessageBox.warning(self, "作废订单", f"订单作废失败：{exc}")
            self._status_label.setText(f"订单作废失败：{exc}")
            self._render_detail(detail)
            return

        message = (
            "订单作废成功\n"
            f"订单ID：{result.order_id}\n"
            f"订单号：{result.order_no}\n"
            f"作废原因：{result.reason}\n"
            f"操作日志ID：{result.operation_log_id}"
        )
        QMessageBox.information(self, "作废订单", message)
        self._status_label.setText(f"订单作废成功：{result.order_no}")
        self.reload_data()
        self._load_detail(result.order_id)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QPushButton#toolBtn {
                padding: 4px 8px;
                border: none;
                color: #95a5a6;
                font-size: 12px;
            }
            QLineEdit, QComboBox, QDateEdit {
                padding: 5px 8px;
                border: 1px solid #bdc3c7;
                font-size: 12px;
            }
            QPushButton {
                padding: 5px 10px;
                border: 1px solid #bdc3c7;
                background: #ffffff;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #ebf5fb;
            }
            QTableWidget {
                border: 1px solid #bdc3c7;
                font-size: 12px;
                gridline-color: #d5d8dc;
            }
            QHeaderView::section {
                background-color: #d6eaf8;
                padding: 6px 4px;
                border: 1px solid #aed6f1;
                font-weight: 600;
            }
            QPlainTextEdit {
                border: 1px solid #bdc3c7;
                font-size: 12px;
            }
            QFrame#resultPanel {
                border: 1px solid #bdc3c7;
                background: #ffffff;
                min-height: 40px;
            }
            QLabel#prizeHint {
                color: #7f8c8d;
                font-size: 12px;
            }
            QLabel#scopeHint {
                color: #7f8c8d;
                font-size: 12px;
                padding: 2px 0;
            }
            """
        )
