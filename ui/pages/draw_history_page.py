"""开奖历史页面：读取本地开奖库，支持筛选、分页和后台同步。"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models import LotteryDraw
from schemas.draw_schema import LotteryDrawCreate
from services.draw_service import DrawService
from services.draw_sync_service import DrawSyncResult
from ui.workers import DrawSyncTask

REGION_LOTTERY_TYPE = {"澳门": 2, "香港": 1}
PAGE_SIZE = 20


class DrawHistoryPage(QWidget):
    def __init__(self, parent=None, draw_service: DrawService | None = None):
        super().__init__(parent)
        self._draw_service = draw_service or DrawService()
        self._sync_task: DrawSyncTask | None = None
        self._page = 1
        self._total = 0
        self._row_draw_ids: list[int] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        root.addLayout(self._build_filter_bar())
        root.addLayout(self._build_action_bar())
        root.addWidget(self._build_table(), stretch=1)
        root.addLayout(self._build_pager())
        root.addWidget(self._build_status_panel())

        self._apply_stylesheet()
        self.reload_data()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload_data()

    def _build_filter_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("地区:"))
        self._cmb_region = QComboBox()
        self._cmb_region.addItems(["全部", "澳门", "香港"])
        row.addWidget(self._cmb_region)

        row.addWidget(QLabel("期号:"))
        self._issue_edit = QLineEdit()
        self._issue_edit.setPlaceholderText("输入期号关键字")
        self._issue_edit.setMinimumWidth(120)
        row.addWidget(self._issue_edit)

        row.addWidget(QLabel("开始日期:"))
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        self._start_date.setSpecialValueText("不限")
        self._start_date.setMinimumDate(QDate(2000, 1, 1))
        self._start_date.setDate(self._start_date.minimumDate())
        row.addWidget(self._start_date)

        row.addWidget(QLabel("结束日期:"))
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date.setSpecialValueText("不限")
        self._end_date.setMinimumDate(QDate(2000, 1, 1))
        self._end_date.setDate(self._end_date.minimumDate())
        row.addWidget(self._end_date)

        btn_query = QPushButton("查询")
        btn_reset = QPushButton("重置")
        btn_query.clicked.connect(self._on_query)
        btn_reset.clicked.connect(self._on_reset)
        row.addWidget(btn_query)
        row.addWidget(btn_reset)
        row.addStretch(1)
        return row

    def _build_action_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_sync_latest = QPushButton("获取最新数据")
        self._btn_sync_history = QPushButton("同步历史数据")
        self._btn_manual_add = QPushButton("手工新增开奖")
        self._btn_manual_edit = QPushButton("修正选中开奖")
        self._btn_sync_latest.setObjectName("fetchButton")
        self._btn_sync_history.setObjectName("fetchButton")
        self._btn_manual_add.setObjectName("fetchButton")
        self._btn_manual_edit.setObjectName("fetchButton")
        self._btn_sync_latest.clicked.connect(self._sync_latest)
        self._btn_sync_history.clicked.connect(self._open_history_sync_dialog)
        self._btn_manual_add.clicked.connect(self._on_manual_add_draw)
        self._btn_manual_edit.clicked.connect(self._on_manual_edit_draw)
        self._btn_manual_edit.setEnabled(False)
        row.addWidget(self._btn_sync_latest)
        row.addWidget(self._btn_sync_history)
        row.addWidget(self._btn_manual_add)
        row.addWidget(self._btn_manual_edit)
        return row

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["地区", "期号", "开奖日期", "普通号码", "特码", "来源", "状态", "更新时间"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
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

    def _build_status_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("detailPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        self._status_label = QLabel("本页面打开时只读取本地数据库，不自动联网。")
        layout.addWidget(self._status_label)
        return panel

    def reload_data(self) -> None:
        region, issue, start_date, end_date = self._filters()
        self._total = self._draw_service.count_draws(
            region=region,
            issue_number=issue,
            start_date=start_date,
            end_date=end_date,
        )
        offset = (self._page - 1) * PAGE_SIZE
        rows = self._draw_service.list_draws(
            region=region,
            issue_number=issue,
            start_date=start_date,
            end_date=end_date,
            limit=PAGE_SIZE,
            offset=offset,
        )
        self._fill_table(rows)
        self._update_pager()

    def _filters(self) -> tuple[str | None, str | None, date | None, date | None]:
        region_text = self._cmb_region.currentText()
        region = None if region_text == "全部" else region_text
        issue = self._issue_edit.text().strip() or None
        start_date = self._qdate_or_none(self._start_date.date())
        end_date = self._qdate_or_none(self._end_date.date())
        return region, issue, start_date, end_date

    def _qdate_or_none(self, value: QDate) -> date | None:
        if value == self._start_date.minimumDate():
            return None
        return date(value.year(), value.month(), value.day())

    def _fill_table(self, rows: list[LotteryDraw]) -> None:
        self._row_draw_ids = []
        self._table.setRowCount(len(rows))
        for row_idx, draw in enumerate(rows):
            self._row_draw_ids.append(draw.id)
            values = [
                draw.region,
                draw.issue_number,
                draw.draw_date.isoformat(),
                "  ".join(draw.regular_numbers),
                draw.special_number,
                draw.source or "-",
                draw.status,
                draw.updated_at.strftime("%Y-%m-%d %H:%M:%S") if draw.updated_at else "-",
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 4:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(Qt.GlobalColor.yellow)
                self._table.setItem(row_idx, col_idx, item)
        if not rows:
            self._status_label.setText("暂无开奖数据")
        else:
            self._status_label.setText(f"已加载 {len(rows)} 条记录")

        self._on_selection_changed()

    def _update_pager(self) -> None:
        total_pages = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page > total_pages:
            self._page = total_pages
        self._lbl_page.setText(f"第 {self._page} / {total_pages} 页    总记录数：{self._total}")
        self._btn_prev.setEnabled(self._page > 1)
        self._btn_next.setEnabled(self._page < total_pages)

    def _on_query(self) -> None:
        self._page = 1
        self.reload_data()

    def _on_reset(self) -> None:
        self._cmb_region.setCurrentIndex(0)
        self._issue_edit.clear()
        self._start_date.setDate(self._start_date.minimumDate())
        self._end_date.setDate(self._end_date.minimumDate())
        self._page = 1
        self.reload_data()

    def _prev_page(self) -> None:
        if self._page > 1:
            self._page -= 1
            self.reload_data()

    def _next_page(self) -> None:
        total_pages = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page < total_pages:
            self._page += 1
            self.reload_data()

    def _sync_latest(self) -> None:
        region = self._cmb_region.currentText()
        if region == "全部":
            region = "澳门"
        self._start_sync(mode="latest", region=region, year=date.today().year)

    def _open_history_sync_dialog(self) -> None:
        dialog = _HistorySyncDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        region, year, pages, page_size = dialog.values()
        self._start_sync(mode="history", region=region, year=year, pages=pages, page_size=page_size)

    def _start_sync(
        self,
        *,
        mode: str,
        region: str,
        year: int,
        pages: int = 1,
        page_size: int = PAGE_SIZE,
    ) -> bool:
        if self._sync_task and self._sync_task.is_active():
            self._status_label.setText("已有同步任务正在执行，请稍候。")
            return False

        self._set_sync_enabled(False)
        self._status_label.setText("正在同步开奖数据...")
        self._sync_task = DrawSyncTask(
            mode=mode,
            lottery_type=REGION_LOTTERY_TYPE[region],
            year=year,
            pages=pages,
            page_size=page_size,
            parent=self,
        )
        self._sync_task.progress.connect(self._on_sync_progress)
        self._sync_task.succeeded.connect(self._on_sync_success)
        self._sync_task.failed.connect(self._on_sync_failed)
        self._sync_task.finished.connect(lambda: self._set_sync_enabled(True))
        self._sync_task.start()
        return True

    @Slot(str)
    def _on_sync_progress(self, message: str) -> None:
        self._status_label.setText(message)

    def _on_sync_success(self, result: DrawSyncResult) -> None:
        self.reload_data()
        if result.skipped and not result.created and not result.updated and not result.failed:
            self._status_label.setText("没有新数据，当前已经是最新一期。")
            return
        self._status_label.setText(
            f"同步完成：新增{result.created}条，更新{result.updated}条，"
            f"跳过{result.skipped}条，失败{result.failed}条。"
        )

    def _on_sync_failed(self, message: str) -> None:
        self._status_label.setText(f"同步失败：{self._friendly_error(message)}")

    def _on_selection_changed(self) -> None:
        self._btn_manual_edit.setEnabled(self._selected_draw_id() is not None)

    def _selected_draw_id(self) -> int | None:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            return None
        row = rows[0].row()
        if row < 0 or row >= len(self._row_draw_ids):
            return None
        return self._row_draw_ids[row]

    def _on_manual_add_draw(self) -> None:
        dialog = _ManualDrawDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            draw = self._draw_service.create_draw(dialog.to_draw_create(source="manual_ui"))
        except Exception as exc:
            self._show_manual_error("手工新增开奖记录失败", exc)
            return
        self.reload_data()
        self._status_label.setText(f"已手工新增开奖记录：{draw.region} 第{draw.issue_number}期")
        QMessageBox.information(self, "开奖记录", "手工新增开奖记录已保存。")

    def _on_manual_edit_draw(self) -> None:
        draw_id = self._selected_draw_id()
        if draw_id is None:
            self._status_label.setText("请先选择一条开奖记录后再修正。")
            QMessageBox.warning(self, "开奖记录", "请先选择一条开奖记录。")
            return
        draw = self._draw_service.get_draw_by_id(draw_id)
        if draw is None:
            self._status_label.setText("选中的开奖记录已不存在，请刷新后重试。")
            QMessageBox.warning(self, "开奖记录", "选中的开奖记录已不存在。")
            return
        dialog = _ManualDrawDialog(self, draw)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            updated = self._draw_service.update_draw(draw_id, dialog.to_draw_create(source="manual_ui"))
        except Exception as exc:
            self._show_manual_error("修正开奖记录失败", exc)
            return
        self.reload_data()
        self._status_label.setText(f"已修正开奖记录：{updated.region} 第{updated.issue_number}期")
        QMessageBox.information(self, "开奖记录", "开奖记录修正已保存。")

    def _show_manual_error(self, title: str, exc: Exception) -> None:
        message = str(exc) or exc.__class__.__name__
        self._status_label.setText(f"{title}：{message}")
        QMessageBox.warning(self, "开奖记录", f"{title}：{message}")

    def _set_sync_enabled(self, enabled: bool) -> None:
        self._btn_sync_latest.setEnabled(enabled)
        self._btn_sync_history.setEnabled(enabled)

    def _friendly_error(self, message: str) -> str:
        lower = message.lower()
        if "timed out" in lower or "timeout" in lower:
            return "网络超时，请稍后重试。"
        if "forbidden" in lower or "403" in lower:
            return "数据源拒绝访问。"
        if "rate limited" in lower or "429" in lower:
            return "请求过于频繁，请稍后再试。"
        if "server error" in lower or "500" in lower:
            return "数据源服务器异常。"
        if "response" in lower or "json" in lower:
            return "网站响应格式发生变化。"
        return message

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
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
            QComboBox, QLineEdit, QDateEdit, QSpinBox {
                padding: 4px 8px;
                border: 1px solid #bdc3c7;
                font-size: 12px;
            }
            QPushButton#fetchButton, QPushButton {
                padding: 6px 12px;
                border: 1px solid #bdc3c7;
                background: #ffffff;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #ebf5fb;
            }
            QPushButton:disabled {
                color: #95a5a6;
            }
            QFrame#detailPanel {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                min-height: 40px;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
            """
        )


class _ManualDrawDialog(QDialog):
    def __init__(self, parent=None, draw: LotteryDraw | None = None):
        super().__init__(parent)
        self.setWindowTitle("修正开奖记录" if draw else "手工新增开奖记录")
        layout = QVBoxLayout(self)

        self._region = QComboBox()
        self._region.addItems(["澳门", "香港"])
        self._issue = QLineEdit()
        self._draw_date = QDateEdit()
        self._draw_date.setCalendarPopup(True)
        self._draw_date.setDisplayFormat("yyyy-MM-dd")
        self._draw_date.setMinimumDate(QDate(2000, 1, 1))
        self._draw_date.setDate(QDate.currentDate())
        self._regular_edits = [QLineEdit() for _ in range(6)]
        self._special = QLineEdit()

        for edit in [*self._regular_edits, self._special]:
            edit.setPlaceholderText("1-49")
            edit.setMaxLength(2)

        for label, widget in (
            ("地区", self._region),
            ("期号", self._issue),
            ("开奖日期", self._draw_date),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget, stretch=1)
            layout.addLayout(row)

        numbers_row = QHBoxLayout()
        numbers_row.addWidget(QLabel("正码"))
        for edit in self._regular_edits:
            numbers_row.addWidget(edit)
        layout.addLayout(numbers_row)

        special_row = QHBoxLayout()
        special_row.addWidget(QLabel("特码"))
        special_row.addWidget(self._special, stretch=1)
        layout.addLayout(special_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if draw is not None:
            self._load_draw(draw)

    def _load_draw(self, draw: LotteryDraw) -> None:
        self._region.setCurrentText(draw.region)
        self._issue.setText(draw.issue_number)
        self._draw_date.setDate(QDate(draw.draw_date.year, draw.draw_date.month, draw.draw_date.day))
        for edit, value in zip(self._regular_edits, draw.regular_numbers, strict=True):
            edit.setText(value)
        self._special.setText(draw.special_number)

    def to_draw_create(self, *, source: str = "manual_ui") -> LotteryDrawCreate:
        value = self._draw_date.date()
        return LotteryDrawCreate(
            region=self._region.currentText(),
            issue_number=self._issue.text(),
            draw_date=date(value.year(), value.month(), value.day()),
            regular_numbers=[edit.text().strip() for edit in self._regular_edits],
            special_number=self._special.text().strip(),
            source=source,
            status="confirmed",
        )


class _HistorySyncDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("同步历史数据")
        layout = QVBoxLayout(self)

        self._region = QComboBox()
        self._region.addItems(["澳门", "香港"])
        self._year = QSpinBox()
        self._year.setRange(2020, date.today().year)
        self._year.setValue(date.today().year)
        self._pages = QSpinBox()
        self._pages.setRange(1, 10)
        self._pages.setValue(1)
        self._page_size = QSpinBox()
        self._page_size.setRange(1, 50)
        self._page_size.setValue(20)

        for label, widget in (
            ("地区", self._region),
            ("年份", self._year),
            ("同步页数", self._pages),
            ("每页数量", self._page_size),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget, stretch=1)
            layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, int, int, int]:
        return (
            self._region.currentText(),
            self._year.value(),
            self._pages.value(),
            self._page_size.value(),
        )
