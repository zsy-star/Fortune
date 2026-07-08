"""订单详情页面：紧凑业务表格、订单明细与本地开奖信息。"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from domain.color_rules import get_wave_color
from domain.zodiac_rules import get_zodiac
from schemas.order_schema import OrderDetailResult, OrderSummary
from schemas.settlement_schema import OrderSettlementPreview, SettlementLedgerResult
from services.draw_service import DrawService
from services.excel_export_service import ExcelExportService
from services.log_service import LogService
from services.maintenance_service import MaintenanceError, MaintenanceService
from services.order_service import OrderService
from services.settlement_service import SettlementService
from services.settings_service import SettingsService
from ui.dialogs.high_risk_confirm_dialog import HighRiskConfirmDialog
from ui.dialogs.order_import_dialog import OrderImportDialog
from ui.dialogs.settlement_preview_dialog import SettlementPreviewDialog
from ui.app_events import app_events

PAGE_SIZE = 20
VOIDABLE_ORDER_STATUSES = {"active", "pending"}
ORDER_STATUS_SETTLED = "settled"
ORDER_STATUS_VOIDED = "voided"
WAVE_COLORS = {"红波": "#e85d5d", "蓝波": "#4f78d8", "绿波": "#2d9d78"}
MALFORMED_SNAPSHOT_TEXT = "快照格式异常，无法完整展示"
LEGACY_NO_PAYOUT_TEXT = "旧记录无赔付数据"
LEGACY_NO_ODDS_TEXT = "旧记录无赔率数据"
LEGACY_NO_REBATE_TEXT = "旧记录无返水统计"
LEGACY_NO_NET_TEXT = "旧记录无统计结算金额"
WINNING_FILTER_OPTIONS = [
    ("不限中奖", None),
    ("未结算", "未结算"),
    ("已结算", "已结算"),
    ("命中", "命中"),
    ("未中", "未中"),
    ("部分命中", "部分命中"),
    ("含不支持", "含不支持"),
]


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _dash(value: object | None) -> str:
    return str(value) if value not in (None, "") else "—"


def _status_text(status: str) -> str:
    return {
        "active": "未结算",
        "pending": "未结算",
        "settled": "已结算",
        "voided": "已作废",
        "cancelled": "已取消",
    }.get(status, "不支持")


def _settlement_status(record: SettlementLedgerResult | None, order_status: str) -> str:
    if record is None:
        return _status_text(order_status)
    if record.unsupported_count > 0:
        return "含不支持"
    if record.hit_count > 0 and record.miss_count > 0:
        return "部分命中"
    if record.hit_count > 0:
        return "命中"
    if record.miss_count > 0:
        return "未中"
    return "已结算"


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
        settings_service: SettingsService | None = None,
        maintenance_service: MaintenanceService | None = None,
    ):
        super().__init__(parent)
        self._order_service = order_service or OrderService()
        session_factory = self._order_service._session_factory
        self._log_service = log_service or LogService(session_factory)
        self._draw_service = draw_service or DrawService(session_factory)
        self._settlement_service = settlement_service or SettlementService(session_factory)
        self._excel_export_service = excel_export_service or ExcelExportService(session_factory)
        self._settings_service = settings_service or SettingsService(session_factory)
        self._maintenance_service = maintenance_service or MaintenanceService(session_factory)
        self._page = 1
        self._total = 0
        self._selected_order_id: int | None = None
        self._logged_order_id: int | None = None
        self._row_order_ids: list[int] = []
        self._row_amounts: list[Decimal] = []
        self._row_statuses: list[str] = []
        self._settlement_records: dict[int, SettlementLedgerResult] = {}
        self._preview_snapshots: dict[int, dict[str, object]] = {}
        self._draw_widgets: dict[str, dict[str, object]] = {}
        self._result_expanded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_order_table(), stretch=5)
        root.addWidget(self._build_summary_bar())
        root.addWidget(self._build_filter_panel())

        self._context_tabs = QTabWidget()
        self._context_tabs.setObjectName("contextTabs")
        self._context_tabs.addTab(self._build_draw_section(), "开奖信息")
        self._context_tabs.addTab(self._build_detail_panel(), "所选订单详情")
        root.addWidget(self._context_tabs, stretch=3)
        self._result_section = self._build_result_section()
        root.addWidget(self._result_section, stretch=1)

        self._apply_stylesheet()
        app_events.orders_changed.connect(self._on_orders_changed)
        app_events.draws_changed.connect(self._on_draws_changed)
        app_events.settings_changed.connect(self._on_settings_changed)
        self.reload_data()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload_data()

    def _on_orders_changed(self) -> None:
        selected_order_id = self._selected_order_id
        try:
            self.reload_data()
            if selected_order_id is not None:
                self._load_detail(selected_order_id)
        except Exception as exc:
            self._status_label.setText(f"订单数据已变更，但自动刷新失败：{exc}")

    def _on_draws_changed(self) -> None:
        try:
            self._reload_draws()
        except Exception as exc:
            self._status_label.setText(f"开奖数据已变更，但自动刷新失败：{exc}")

    def _on_settings_changed(self) -> None:
        try:
            self._reload_declarer_filter_options()
        except Exception as exc:
            self._status_label.setText(f"设置数据已变更，但申报人筛选刷新失败：{exc}")

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbar")
        row = QHBoxLayout(frame)
        row.setContentsMargins(4, 3, 4, 3)
        row.setSpacing(4)

        self._btn_clear_orders = QPushButton("清空订单")
        self._btn_clear_orders.setObjectName("dangerAction")
        self._btn_clear_orders.setToolTip("高风险维护：执行前会自动备份，并要求原因、确认短语和二次确认。")
        self._btn_clear_orders.clicked.connect(self._on_clear_orders)
        self._btn_bulk_delete_orders = QPushButton("批量删除选中订单")
        self._btn_bulk_delete_orders.setObjectName("dangerAction")
        self._btn_bulk_delete_orders.setToolTip("高风险维护：只删除当前选中的订单及对应明细、结算快照。")
        self._btn_bulk_delete_orders.setEnabled(False)
        self._btn_bulk_delete_orders.clicked.connect(self._on_bulk_delete_orders)
        self._btn_export_excel = QPushButton("导出订单")
        self._btn_export_excel.setObjectName("primaryAction")
        self._btn_export_excel.setToolTip("按当前查询条件导出表格")
        self._btn_export_excel.clicked.connect(self._on_export_excel)
        self._btn_import_orders = QPushButton("导入订单")
        self._btn_import_orders.setObjectName("primaryAction")
        self._btn_import_orders.setToolTip("打开订单导入预览；确认导入后只保存解析成功行")
        self._btn_import_orders.clicked.connect(self._on_import_orders)
        self._btn_filter_prize = QPushButton("过滤结算结果")
        self._btn_filter_prize.setObjectName("primaryAction")
        self._btn_filter_prize.setToolTip("只读查看当前筛选结果的命中状态和快照中奖金额")
        self._btn_filter_prize.clicked.connect(self._on_filter_settlement_results)
        self._btn_combined_prize = QPushButton("综合结算摘要")
        self._btn_combined_prize.setObjectName("primaryAction")
        self._btn_combined_prize.setToolTip("只读汇总当前筛选结果，展示返水统计，不写余额、不计算佣金")
        self._btn_combined_prize.clicked.connect(self._on_combined_settlement_summary)
        self._btn_reset_draw = QPushButton("重置开奖")
        self._btn_reset_draw.setObjectName("dangerAction")
        self._btn_reset_draw.setToolTip("高风险维护：仅在无结算记录时允许重置开奖记录。")
        self._btn_reset_draw.clicked.connect(self._on_reset_draws)
        self._btn_expand_prize = QPushButton("扩大兑奖框")
        self._btn_expand_prize.setToolTip("扩大或收起底部结算摘要显示区域")
        self._btn_expand_prize.clicked.connect(self._on_toggle_result_panel_size)

        for button in (
            self._btn_clear_orders,
            self._btn_bulk_delete_orders,
            self._btn_export_excel,
            self._btn_import_orders,
            self._btn_filter_prize,
            self._btn_combined_prize,
            self._btn_reset_draw,
            self._btn_expand_prize,
        ):
            row.addWidget(button)

        self._cmb_toolbar_placeholder = QComboBox()
        self._cmb_toolbar_placeholder.addItem("选择业务操作", None)
        self._cmb_toolbar_placeholder.addItem("查看订单详情", "detail")
        self._cmb_toolbar_placeholder.addItem("结算预览", "preview")
        self._cmb_toolbar_placeholder.addItem("作废订单", "void")
        self._cmb_toolbar_placeholder.setToolTip("请选择已开放的订单操作；未选择订单时会给出提示")
        self._cmb_toolbar_placeholder.activated.connect(self._on_business_action_selected)
        row.addWidget(self._cmb_toolbar_placeholder)
        row.addStretch(1)

        self._edit_order_no = QLineEdit()
        self._edit_order_no.setObjectName("orderSearch")
        self._edit_order_no.setPlaceholderText("搜索订单号关键词")
        self._edit_order_no.setClearButtonEnabled(True)
        self._edit_order_no.returnPressed.connect(self._on_query)
        self._btn_query = QPushButton("搜索")
        self._btn_query.clicked.connect(self._on_query)
        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.clicked.connect(self.reload_data)
        row.addWidget(self._edit_order_no, stretch=1)
        row.addWidget(self._btn_query)
        row.addWidget(self._btn_refresh)
        return frame

    def _unavailable_button(self, text: str, reason: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("unavailableAction")
        button.setEnabled(False)
        button.setToolTip(f"{text}：当前功能未开放。{reason}")
        button.setStatusTip(reason)
        return button

    def _build_order_table(self) -> QTableWidget:
        headers = [
            "订单信息",
            "复式类型",
            "计算方式",
            "金额",
            "订单总额",
            "是否自定义",
            "订单序号",
            "申报人",
            "中奖情况",
            "中奖金额",
            "备注",
        ]
        self._table = QTableWidget(0, len(headers))
        self._table.setObjectName("orderBusinessTable")
        self._table.setHorizontalHeaderLabels(headers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(29)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(self._show_selected_detail)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(72)
        return self._table

    def _build_summary_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("summaryBar")
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 3, 8, 3)
        row.setSpacing(16)
        self._lbl_current_total = QLabel("当前订单总额：0.00")
        self._lbl_selected_total = QLabel("选中总额：0.00")
        self._lbl_order_state = QLabel("订单状态：未选择")
        self._status_label = QLabel("")
        self._status_label.setObjectName("operationStatus")
        self._btn_prev = QPushButton("上一页")
        self._btn_next = QPushButton("下一页")
        self._lbl_page = QLabel()
        self._btn_prev.clicked.connect(self._prev_page)
        self._btn_next.clicked.connect(self._next_page)

        row.addWidget(self._lbl_current_total)
        row.addWidget(self._lbl_selected_total)
        row.addWidget(self._lbl_order_state)
        row.addWidget(self._status_label, stretch=1)
        row.addWidget(self._btn_prev)
        row.addWidget(self._btn_next)
        row.addWidget(self._lbl_page)
        return frame

    def _build_filter_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("filterPanel")
        grid = QGridLayout(frame)
        grid.setContentsMargins(5, 4, 5, 4)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)

        self._cmb_region = QComboBox()
        self._cmb_region.addItems(["全部区域", "澳门", "香港"])
        self._cmb_bet_type = QComboBox()
        self._cmb_bet_type.addItem("不限投注类型", None)
        self._cmb_bet_type.setToolTip("投注类型来自历史订单明细")
        self._cmb_winning = QComboBox()
        for label, value in WINNING_FILTER_OPTIONS:
            self._cmb_winning.addItem(label, value)
        self._cmb_winning.setToolTip("基于订单状态和已有结算记录筛选，不重新计算结算")
        self._cmb_declarer = QComboBox()
        self._cmb_declarer.addItem("不限申报人", None)

        grid.addWidget(self._cmb_region, 0, 0)
        grid.addWidget(self._cmb_bet_type, 0, 1)
        grid.addWidget(self._cmb_winning, 0, 2)
        grid.addWidget(self._cmb_declarer, 0, 3)

        self._edit_channel = QLineEdit()
        self._edit_channel.setPlaceholderText("渠道")
        self._cmb_status = QComboBox()
        self._cmb_status.addItems(["不限状态", "active", "pending", "settled", "voided", "cancelled"])
        self._start_date = self._make_date_edit()
        self._end_date = self._make_date_edit()
        self._btn_reset = QPushButton("重置筛选")
        self._btn_reset.clicked.connect(self._on_reset)

        advanced = QHBoxLayout()
        advanced.setSpacing(5)
        for label, widget in (
            ("渠道", self._edit_channel),
            ("状态", self._cmb_status),
            ("开始", self._start_date),
            ("结束", self._end_date),
        ):
            advanced.addWidget(QLabel(label))
            advanced.addWidget(widget)
        advanced.addWidget(self._btn_reset)
        advanced.addStretch(1)
        grid.addLayout(advanced, 1, 0, 1, 4)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        return frame

    def _make_date_edit(self) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        edit.setSpecialValueText("不限")
        edit.setMinimumDate(QDate(2000, 1, 1))
        edit.setDate(edit.minimumDate())
        return edit

    def _build_draw_section(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 5, 4, 5)
        layout.setSpacing(4)
        hint = QLabel("读取本地数据库中的最新一期开奖；此区域不会自动联网或重置开奖。")
        hint.setObjectName("sectionHint")
        layout.addWidget(hint)
        regions = QHBoxLayout()
        regions.setSpacing(6)
        for region in ("澳门", "香港"):
            regions.addWidget(self._build_draw_panel(region), stretch=1)
        layout.addLayout(regions)
        return panel

    def _build_draw_panel(self, region: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("drawPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(3)
        title = QLabel(f"{region}开奖")
        title.setObjectName("drawTitle")
        placeholder = QLabel("暂无开奖数据")
        placeholder.setObjectName("drawPlaceholder")
        layout.addWidget(title)
        layout.addWidget(placeholder)

        balls_row = QHBoxLayout()
        balls_row.setSpacing(4)
        balls: list[tuple[QFrame, QLabel, QLabel]] = []
        for index in range(7):
            cell = QFrame()
            cell.setObjectName("drawBallCell")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(1)
            number = QLabel("--")
            number.setObjectName("specialDrawNumber" if index == 6 else "drawNumber")
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            number.setFixedHeight(30)
            zodiac = QLabel("")
            zodiac.setObjectName("drawZodiac")
            zodiac.setAlignment(Qt.AlignmentFlag.AlignCenter)
            zodiac.setFixedHeight(20)
            cell_layout.addWidget(number)
            cell_layout.addWidget(zodiac)
            balls_row.addWidget(cell, stretch=1)
            balls.append((cell, number, zodiac))
        layout.addLayout(balls_row)
        self._draw_widgets[region] = {"title": title, "placeholder": placeholder, "balls": balls}
        return frame

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 5, 4, 5)
        layout.setSpacing(4)

        detail_header = QHBoxLayout()
        self._detail_info = QLabel("请选择订单")
        self._detail_info.setWordWrap(True)
        self._btn_preview = QPushButton("结算预览")
        self._btn_preview.setEnabled(False)
        self._btn_preview.setToolTip("请选择未结算且未作废的订单后进行结算预览")
        self._btn_preview.clicked.connect(self._on_settlement_preview)
        self._btn_void = QPushButton("作废订单")
        self._btn_void.setEnabled(False)
        self._btn_void.setToolTip("请选择未结算且未作废的订单后作废；作废会二次确认并写操作日志")
        self._btn_void.clicked.connect(self._on_void_order)
        detail_header.addWidget(self._detail_info, stretch=1)
        detail_header.addWidget(self._btn_preview)
        detail_header.addWidget(self._btn_void)

        self._raw_text = QPlainTextEdit()
        self._raw_text.setReadOnly(True)
        self._raw_text.setPlaceholderText("原始订单文本")
        self._raw_text.setMaximumHeight(54)
        self._item_table = QTableWidget(0, 5)
        self._item_table.setHorizontalHeaderLabels(["投注类型", "投注内容", "金额", "赔率", "备注"])
        self._item_table.verticalHeader().setVisible(False)
        self._item_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._item_table.horizontalHeader().setStretchLastSection(True)

        layout.addLayout(detail_header)
        layout.addWidget(self._raw_text)
        layout.addWidget(self._item_table, stretch=1)
        return panel

    def _build_result_section(self) -> QWidget:
        panel = QWidget()
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        self._macau_result = self._result_box(row, "澳门兑奖结果")
        self._hong_kong_result = self._result_box(row, "香港兑奖结果")
        self._combined_result = self._result_box(row, "综合结果")
        self._clear_result_panels()
        return panel

    def _result_box(self, parent_layout: QHBoxLayout, title: str) -> QPlainTextEdit:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(5, 5, 5, 5)
        result = QPlainTextEdit()
        result.setReadOnly(True)
        result.setMaximumHeight(82)
        layout.addWidget(result)
        parent_layout.addWidget(group, stretch=1)
        return result

    def reload_data(self) -> None:
        if not self._validate_dates():
            return
        self._reload_bet_type_filter_options()
        self._reload_declarer_filter_options()
        region, order_no, bet_type, winning_status, declarer, channel, status, start_dt, end_dt = self._filters()
        self._total = self._order_service.count_orders(
            region=region,
            order_no=order_no,
            bet_type=bet_type,
            winning_status=winning_status,
            declarer_name=declarer,
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
            bet_type=bet_type,
            winning_status=winning_status,
            declarer_name=declarer,
            channel=channel,
            status=status,
            start_date=start_dt,
            end_date=end_dt,
            limit=PAGE_SIZE,
            offset=(self._page - 1) * PAGE_SIZE,
        )
        settlement_error = None
        try:
            self._settlement_records = self._settlement_service.get_settlement_records_by_order_ids(
                [order.id for order in rows]
            )
        except Exception as exc:
            self._settlement_records = {}
            settlement_error = str(exc)
        self._fill_table(rows)
        if settlement_error:
            self._status_label.setText(f"订单已加载，但结算摘要读取失败：{settlement_error}")
        self._update_pager()
        self._reload_draws()

    def _filters(self):
        region = None if self._cmb_region.currentIndex() == 0 else self._cmb_region.currentText()
        status = None if self._cmb_status.currentIndex() == 0 else self._cmb_status.currentText()
        return (
            region,
            self._edit_order_no.text().strip() or None,
            self._cmb_bet_type.currentData(),
            self._cmb_winning.currentData(),
            self._cmb_declarer.currentData(),
            self._edit_channel.text().strip() or None,
            status,
            self._start_datetime(),
            self._end_datetime(),
        )

    def _reload_bet_type_filter_options(self) -> None:
        selected_bet_type = self._cmb_bet_type.currentData()
        try:
            bet_types = self._order_service.list_bet_types()
        except Exception as exc:
            self._cmb_bet_type.setToolTip(f"投注类型读取失败：{exc}")
            return

        self._cmb_bet_type.blockSignals(True)
        self._cmb_bet_type.clear()
        self._cmb_bet_type.addItem("不限投注类型", None)
        for bet_type in bet_types:
            self._cmb_bet_type.addItem(bet_type, bet_type)
        selected_index = self._cmb_bet_type.findData(selected_bet_type)
        self._cmb_bet_type.setCurrentIndex(max(0, selected_index))
        self._cmb_bet_type.blockSignals(False)
        self._cmb_bet_type.setToolTip("投注类型来自历史订单明细")

    def _reload_declarer_filter_options(self) -> None:
        selected_name = self._cmb_declarer.currentData()
        names: list[str] = []
        errors: list[str] = []
        try:
            names.extend(declarer.name for declarer in self._settings_service.list_declarers())
        except Exception as exc:
            errors.append(f"设置中心：{exc}")
        try:
            names.extend(self._order_service.list_declarer_names())
        except Exception as exc:
            errors.append(f"历史订单：{exc}")

        unique_names = list(dict.fromkeys(name.strip() for name in names if name and name.strip()))
        self._cmb_declarer.blockSignals(True)
        self._cmb_declarer.clear()
        self._cmb_declarer.addItem("不限申报人", None)
        for name in unique_names:
            self._cmb_declarer.addItem(name, name)
        selected_index = self._cmb_declarer.findData(selected_name)
        self._cmb_declarer.setCurrentIndex(max(0, selected_index))
        self._cmb_declarer.blockSignals(False)
        if errors:
            self._cmb_declarer.setToolTip("申报人来源部分读取失败：" + "；".join(errors))
        else:
            self._cmb_declarer.setToolTip("申报人来自设置中心和历史订单")

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
        self._table.blockSignals(True)
        self._table.clearSelection()
        self._table.setRowCount(len(rows))
        self._row_order_ids = []
        self._row_amounts = []
        self._row_statuses = []
        for row_idx, order in enumerate(rows):
            self._row_order_ids.append(order.id)
            self._row_amounts.append(order.total_amount)
            self._row_statuses.append(order.status)
            compact_raw = " ".join(order.raw_text.split()) or order.order_no
            note_parts = [order.region]
            if order.channel:
                note_parts.append(f"渠道：{order.channel}")
            if order.source:
                note_parts.append(f"来源：{order.source}")
            settlement_record = self._settlement_records.get(order.id)
            winning_status = _settlement_status(settlement_record, order.status)
            payout_text = self._settlement_record_payout_text(settlement_record)
            values = [
                compact_raw,
                "—",
                "—",
                "—",
                _money(order.total_amount),
                "—",
                order.order_no,
                _dash(order.customer_name),
                winning_status,
                payout_text,
                " / ".join(note_parts),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    if col_idx in (0, 10)
                    else Qt.AlignmentFlag.AlignCenter
                )
                if col_idx == 0:
                    item.setToolTip(order.raw_text)
                elif col_idx == 8:
                    if settlement_record is None:
                        item.setToolTip(f"订单原始状态：{order.status}；暂无结算记录")
                    else:
                        item.setToolTip(
                            f"期号：{settlement_record.issue_number}；"
                            f"命中 {settlement_record.hit_count}；"
                            f"未中 {settlement_record.miss_count}；"
                            f"不支持 {settlement_record.unsupported_count}"
                        )
                self._table.setItem(row_idx, col_idx, item)
        self._table.blockSignals(False)

        current_total = sum(self._row_amounts, Decimal("0"))
        self._lbl_current_total.setText(f"当前订单总额：{_money(current_total)}")
        self._lbl_selected_total.setText("选中总额：0.00")
        self._lbl_order_state.setText("订单状态：未选择")
        self._clear_detail()
        if not rows:
            self._status_label.setText("暂无订单数据")
        else:
            self._status_label.setText(f"已加载 {len(rows)} 条订单")

    def _update_pager(self) -> None:
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._lbl_page.setText(f"第 {self._page}/{max_page} 页 · 共 {self._total} 条")
        self._btn_prev.setEnabled(self._page > 1)
        self._btn_next.setEnabled(self._page < max_page)

    def _on_query(self) -> None:
        self._page = 1
        self.reload_data()

    def _on_reset(self) -> None:
        self._cmb_region.setCurrentIndex(0)
        self._cmb_bet_type.setCurrentIndex(0)
        self._cmb_winning.setCurrentIndex(0)
        self._cmb_status.setCurrentIndex(0)
        self._cmb_declarer.setCurrentIndex(0)
        self._edit_order_no.clear()
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

        region, order_no, bet_type, winning_status, declarer, _channel, status, start_dt, end_dt = self._filters()
        try:
            result = self._excel_export_service.export_orders(
                region=region,
                status=status,
                start_date=start_dt,
                end_date=end_dt,
                keyword=order_no,
                declarer_name=declarer,
                bet_type=bet_type,
                winning_status=winning_status,
                include_voided=False,
                output_dir=output_dir,
            )
        except Exception as exc:
            QMessageBox.warning(self, "导出订单", f"导出失败：{exc}")
            self._status_label.setText(f"导出失败：{exc}")
            return

        QMessageBox.information(self, "导出订单", _export_success_message(result))
        self._status_label.setText(f"导出成功：{result.file_name}")

    def _on_import_orders(self) -> None:
        dialog = OrderImportDialog(self)
        dialog.exec()
        self._status_label.setText("订单导入窗口已关闭；请查看导入预览结果和操作日志")

    def _on_filter_settlement_results(self) -> None:
        summary = self._build_current_settlement_summary()
        text = (
            "过滤结算结果为只读统计功能，不写数据库，不写余额。\n\n"
            f"{summary}"
        )
        self._combined_result.setPlainText(text)
        self._status_label.setText("已生成过滤结算结果摘要")
        QMessageBox.information(self, "过滤结算结果", text)

    def _on_combined_settlement_summary(self) -> None:
        text = (
            "综合结算摘要（只读）\n"
            "中奖金额/返水金额：读取已结算快照中的统计字段；未结算订单不参与，不写余额。\n\n"
            f"{self._build_current_settlement_summary()}"
        )
        self._combined_result.setPlainText(text)
        self._status_label.setText("已生成综合结算摘要")
        QMessageBox.information(self, "综合结算摘要", text)

    def _on_toggle_result_panel_size(self) -> None:
        self._result_expanded = not self._result_expanded
        max_height = 180 if self._result_expanded else 82
        min_height = 210 if self._result_expanded else 0
        for result in (self._macau_result, self._hong_kong_result, self._combined_result):
            result.setMaximumHeight(max_height)
        self._result_section.setMinimumHeight(min_height)
        self._btn_expand_prize.setText("收起兑奖框" if self._result_expanded else "扩大兑奖框")
        self._status_label.setText("已扩大底部结果区" if self._result_expanded else "已收起底部结果区")

    def _on_business_action_selected(self, index: int) -> None:
        action = self._cmb_toolbar_placeholder.itemData(index)
        self._cmb_toolbar_placeholder.setCurrentIndex(0)
        if action is None:
            return
        if action == "detail":
            if self._selected_order_id is None:
                self._status_label.setText("请先选择订单再查看详情")
                return
            self._context_tabs.setCurrentIndex(1)
            self._status_label.setText("已切换到所选订单详情")
            return
        if action == "preview":
            self._on_settlement_preview()
            return
        if action == "void":
            self._on_void_order()
            return
        self._status_label.setText("该业务操作不可用")

    def _build_current_settlement_summary(self) -> str:
        orders = self._list_current_filtered_orders()
        records = self._settlement_service.get_settlement_records_by_order_ids([order.id for order in orders])
        total_amount = sum((order.total_amount for order in orders), Decimal("0"))
        payout_values = [
            record.total_payout_amount
            for record in records.values()
            if self._snapshot_has_payout(record.result_snapshot)
        ]
        rebate_values = [
            record.total_rebate_amount
            for record in records.values()
            if self._snapshot_has_rebate(record.result_snapshot)
        ]
        net_values = [
            record.statistic_net_amount
            for record in records.values()
            if self._snapshot_has_statistic_net(record.result_snapshot)
        ]
        total_payout = sum(payout_values, Decimal("0.00"))
        total_rebate = sum(rebate_values, Decimal("0.00"))
        total_net = sum(net_values, Decimal("0.00"))
        status_counts = {
            "已结算": 0,
            "未结算": 0,
            "命中": 0,
            "未中": 0,
            "部分命中": 0,
            "含不支持": 0,
        }
        for order in orders:
            if order.status == ORDER_STATUS_SETTLED:
                status_counts["已结算"] += 1
            elif order.status in {"active", "pending"}:
                status_counts["未结算"] += 1
            display_status = _settlement_status(records.get(order.id), order.status)
            if display_status in status_counts:
                status_counts[display_status] += 1

        payout_text = _money(total_payout) if payout_values else f"—（{LEGACY_NO_PAYOUT_TEXT}）"
        rebate_text = _money(total_rebate) if rebate_values else f"—（{LEGACY_NO_REBATE_TEXT}）"
        net_text = _money(total_net) if net_values else f"—（{LEGACY_NO_NET_TEXT}）"
        return (
            f"订单数：{len(orders)}\n"
            f"已结算数：{status_counts['已结算']}    未结算数：{status_counts['未结算']}\n"
            f"命中订单数：{status_counts['命中']}    未中订单数：{status_counts['未中']}\n"
            f"部分命中订单数：{status_counts['部分命中']}    含不支持订单数：{status_counts['含不支持']}\n"
            f"当前订单总额：{_money(total_amount)}\n"
            f"赔付/中奖金额：{payout_text}\n"
            f"返水金额：{rebate_text}\n"
            f"统计结算金额：{net_text}\n"
            "说明：返水和统计结算金额仅作记账统计，不代表真实付款或入账。"
        )

    def _list_current_filtered_orders(self) -> list[OrderSummary]:
        if not self._validate_dates():
            return []
        region, order_no, bet_type, winning_status, declarer, channel, status, start_dt, end_dt = self._filters()
        rows: list[OrderSummary] = []
        offset = 0
        page_size = 200
        while True:
            page = self._order_service.list_orders(
                region=region,
                order_no=order_no,
                bet_type=bet_type,
                winning_status=winning_status,
                declarer_name=declarer,
                channel=channel,
                status=status,
                start_date=start_dt,
                end_date=end_dt,
                limit=page_size,
                offset=offset,
            )
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def _prev_page(self) -> None:
        if self._page > 1:
            self._page -= 1
            self.reload_data()

    def _next_page(self) -> None:
        max_page = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page < max_page:
            self._page += 1
            self.reload_data()

    def _show_selected_detail(self, _item=None) -> None:
        if self._selected_order_id is not None:
            self._context_tabs.setCurrentIndex(1)

    def _on_selection_changed(self) -> None:
        selected = sorted({index.row() for index in self._table.selectionModel().selectedRows()})
        self._btn_bulk_delete_orders.setEnabled(bool(selected))
        if not selected:
            self._lbl_selected_total.setText("选中总额：0.00")
            self._lbl_order_state.setText("订单状态：未选择")
            self._clear_detail()
            return

        selected_total = sum((self._row_amounts[row] for row in selected), Decimal("0"))
        statuses = {_status_text(self._row_statuses[row]) for row in selected}
        state_text = next(iter(statuses)) if len(statuses) == 1 else "多种状态"
        self._lbl_selected_total.setText(f"选中总额：{_money(selected_total)}")
        self._lbl_order_state.setText(f"订单状态：{state_text}")

        first_row = selected[0]
        if first_row >= len(self._row_order_ids):
            self._clear_detail()
            return
        self._load_detail(self._row_order_ids[first_row])

    def _load_detail(self, order_id: int) -> None:
        detail = self._order_service.get_order(order_id)
        if detail is None:
            self._status_label.setText("订单不存在或已被删除，列表已刷新。")
            self.reload_data()
            return
        self._selected_order_id = order_id
        self._render_detail(detail)
        self._update_result_panels(detail)
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
        previewable = detail.status in VOIDABLE_ORDER_STATUSES
        voidable = detail.status in VOIDABLE_ORDER_STATUSES
        self._btn_preview.setEnabled(previewable)
        self._btn_void.setEnabled(voidable)
        if detail.status == ORDER_STATUS_SETTLED:
            self._btn_preview.setToolTip("该订单已正式结算，不能重复结算预览；请查看已保存结算快照。")
            self._btn_void.setToolTip("已结算订单不能作废，避免破坏结算记录。")
        elif detail.status == ORDER_STATUS_VOIDED:
            self._btn_preview.setToolTip("该订单已作废，不能进行结算预览。")
            self._btn_void.setToolTip("该订单已作废，不能重复作废。")
        elif previewable:
            self._btn_preview.setToolTip("打开结算预览；正式结算前会再次校验开奖和不支持玩法。")
            self._btn_void.setToolTip("作废当前订单；作废前需要填写原因并二次确认。")
        else:
            self._btn_preview.setToolTip(f"当前订单状态不能结算预览：{detail.status}")
            self._btn_void.setToolTip(f"当前订单状态不能作废：{detail.status}")
        self._detail_info.setText(
            "订单号：{no}    申报人：{customer}    渠道：{channel}    地区：{region}    "
            "生肖年份：{zodiac_year}    来源：{source}    状态：{status}    总金额：{total}".format(
                no=detail.order_no,
                customer=_dash(detail.customer_name),
                channel=_dash(detail.channel),
                region=detail.region,
                zodiac_year=_dash(detail.zodiac_year),
                source=_dash(detail.source),
                status=_status_text(detail.status),
                total=_money(detail.total_amount),
            )
        )
        self._raw_text.setPlainText(detail.raw_text)
        self._item_table.setRowCount(len(detail.items))
        for row_idx, item in enumerate(detail.items):
            values = [item.bet_type, item.selection, _money(item.amount), _dash(item.odds), _dash(item.note)]
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
        self._btn_preview.setToolTip("请选择未结算且未作废的订单后进行结算预览")
        self._btn_void.setEnabled(False)
        self._btn_void.setToolTip("请选择未结算且未作废的订单后作废；作废会二次确认并写操作日志")
        self._clear_result_panels()

    def _reload_draws(self) -> None:
        for region in ("澳门", "香港"):
            try:
                draw = self._draw_service.get_latest_draw(region)
            except Exception as exc:
                self._render_draw(region, None, error=str(exc))
            else:
                self._render_draw(region, draw)

    def _render_draw(self, region: str, draw, *, error: str | None = None) -> None:
        widgets = self._draw_widgets[region]
        title: QLabel = widgets["title"]  # type: ignore[assignment]
        placeholder: QLabel = widgets["placeholder"]  # type: ignore[assignment]
        balls: list[tuple[QFrame, QLabel, QLabel]] = widgets["balls"]  # type: ignore[assignment]
        if draw is None:
            title.setText(f"{region}开奖")
            placeholder.setText(f"开奖数据读取失败：{error}" if error else "暂无开奖数据")
            placeholder.show()
            for _cell, number, zodiac in balls:
                number.setText("--")
                number.setStyleSheet("")
                zodiac.clear()
            return

        title.setText(f"{region}开奖 · 第{draw.issue_number}期 · {draw.draw_date.isoformat()}")
        placeholder.hide()
        numbers = [*draw.regular_numbers, draw.special_number]
        for index, ((_cell, number_label, zodiac_label), number) in enumerate(zip(balls, numbers)):
            color = WAVE_COLORS.get(get_wave_color(number), "#7f8c8d")
            number_label.setText(str(number))
            number_label.setStyleSheet(
                f"background: {color}; color: white; font-weight: 700; "
                f"border-radius: {4 if index < 6 else 9}px;"
            )
            zodiac_label.setText(get_zodiac(number, year=draw.draw_date.year))

    def _clear_result_panels(self) -> None:
        empty = "请选择订单查看结算摘要与结算明细。"
        self._macau_result.setPlainText(empty)
        self._hong_kong_result.setPlainText(empty)
        self._combined_result.setPlainText(empty)

    def _update_result_panels(self, detail: OrderDetailResult) -> None:
        record = self._settlement_records.get(detail.id)
        lookup_error = None
        if detail.status == ORDER_STATUS_SETTLED and record is None:
            try:
                record = self._settlement_service.get_settlement_record_by_order_id(detail.id)
            except Exception as exc:
                lookup_error = str(exc)
            if record is not None:
                self._settlement_records[detail.id] = record

        if lookup_error:
            summary = f"结算摘要读取失败：{lookup_error}"
        elif detail.status != ORDER_STATUS_SETTLED:
            preview_snapshot = self._preview_snapshots.get(detail.id)
            if preview_snapshot is None:
                summary = self._empty_settlement_detail_message()
            else:
                summary = self._build_preview_detail_text(preview_snapshot)
        elif record is None:
            summary = "该订单为历史已结算订单，但暂无结算快照记录。"
        else:
            payout_text = (
                _money(record.total_payout_amount)
                if self._snapshot_has_payout(record.result_snapshot)
                else LEGACY_NO_PAYOUT_TEXT
            )
            rebate_text = (
                _money(record.total_rebate_amount)
                if self._snapshot_has_rebate(record.result_snapshot)
                else LEGACY_NO_REBATE_TEXT
            )
            net_text = (
                _money(record.statistic_net_amount)
                if self._snapshot_has_statistic_net(record.result_snapshot)
                else LEGACY_NO_NET_TEXT
            )
            summary = (
                f"订单 ID：{record.order_id}\n"
                f"地区：{record.region}    期号：{record.issue_number}\n"
                f"命中数：{record.hit_count}    未命中数：{record.miss_count}    "
                f"不支持数：{record.unsupported_count}\n"
                f"总明细数：{record.total_items}    总金额：{_money(record.total_amount)}    "
                f"总中奖金额：{payout_text}    返水金额：{rebate_text}    统计结算金额：{net_text}\n"
                f"{self._build_settlement_detail_text(record.result_snapshot)}"
            )

        self._macau_result.setPlainText("当前选中订单不属于澳门，未显示兑奖结果。")
        self._hong_kong_result.setPlainText("当前选中订单不属于香港，未显示兑奖结果。")
        if detail.region == "澳门":
            self._macau_result.setPlainText(summary)
        elif detail.region == "香港":
            self._hong_kong_result.setPlainText(summary)
        self._combined_result.setPlainText(summary)

    def _snapshot_item_summary(self, snapshot: object) -> str:
        if not isinstance(snapshot, dict):
            return MALFORMED_SNAPSHOT_TEXT
        items = snapshot.get("items")
        if not isinstance(items, list) or not items:
            return MALFORMED_SNAPSHOT_TEXT

        summaries: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                return MALFORMED_SNAPSHOT_TEXT
            result_text = self._settlement_item_result_text(item)
            summaries.append(f"{_dash(item.get('bet_type'))}/{_dash(item.get('selection'))}：{result_text}")

        visible = summaries[:3]
        suffix = f"；另有 {len(summaries) - 3} 条" if len(summaries) > 3 else ""
        return "；".join(visible) + suffix

    def _empty_settlement_detail_message(self) -> str:
        return (
            "当前订单暂无结算明细，请先进行结算预览。\n\n"
            "当前仅展示命中 / 未中 / 不支持判断。\n"
            "当前不写余额；返水仅在结算预览或正式结算快照中作为统计项展示。\n"
            "复杂玩法规则以当前 settlement_rules.md 为准。"
        )

    def _build_preview_detail_text(self, snapshot: dict[str, object]) -> str:
        return "结算预览明细（未正式结算）\n" + self._build_settlement_detail_text(snapshot)

    def _build_settlement_detail_text(self, snapshot: object) -> str:
        if not isinstance(snapshot, dict):
            return f"结算明细：{MALFORMED_SNAPSHOT_TEXT}"
        items = snapshot.get("items")
        if not isinstance(items, list) or not items:
            return f"结算明细：{MALFORMED_SNAPSHOT_TEXT}"

        lines = [
            "结算明细：",
            "当前仅展示命中 / 未中 / 不支持判断。",
            "当前展示基础中奖金额、返水金额和统计结算金额；不写余额，不代表真实付款或入账。",
            "复杂玩法规则以当前 settlement_rules.md 为准。",
        ]
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                lines.append(f"{index}. {MALFORMED_SNAPSHOT_TEXT}")
                continue
            result_text = self._settlement_item_result_text(item)
            reference = self._settlement_item_reference_text(item)
            reason = _dash(item.get("reason"))
            unsupported_reason = _dash(item.get("unsupported_reason"))
            odds_text = _dash(item.get("odds")) if "odds" in item else LEGACY_NO_ODDS_TEXT
            payout_text = _dash(item.get("payout_amount")) if "payout_amount" in item else LEGACY_NO_PAYOUT_TEXT
            odds_source = _dash(item.get("odds_source"))
            odds_plan = _dash(item.get("odds_plan_name"))
            payout_note = _dash(item.get("payout_note"))
            rebate_rate = _dash(item.get("rebate_rate")) if "rebate_rate" in item else LEGACY_NO_REBATE_TEXT
            rebate_amount = _dash(item.get("rebate_amount")) if "rebate_amount" in item else LEGACY_NO_REBATE_TEXT
            rebate_note = _dash(item.get("rebate_note")) if "rebate_note" in item else LEGACY_NO_REBATE_TEXT
            lines.extend(
                [
                    (
                        f"{index}. 投注类型：{_dash(item.get('bet_type'))}    "
                        f"投注内容：{_dash(item.get('selection'))}    "
                        f"金额：{_dash(item.get('amount'))}    结果：{result_text}"
                    ),
                    f"   开奖参考：{reference}",
                    (
                        f"   赔率：{odds_text}    中奖金额：{payout_text}    "
                        f"赔率来源：{odds_source}    赔率方案：{odds_plan}"
                    ),
                    f"   赔率/赔付提示：{payout_note}",
                    f"   返水比例：{rebate_rate}    返水金额：{rebate_amount}",
                    f"   返水提示：{rebate_note}",
                    f"   命中 / 未中说明：{reason}",
                    f"   不支持原因：{unsupported_reason}",
                ]
            )
        return "\n".join(lines)

    def _settlement_item_result_text(self, item: dict[str, object]) -> str:
        result = str(item.get("result") or item.get("status") or "").strip().lower()
        if result in {"hit", "win", "winner", "命中", "中"}:
            return "命中"
        if result in {"miss", "lose", "loser", "未中", "不中"}:
            return "未中"
        if result in {"unsupported", "不支持", "暂不支持"}:
            return "不支持"
        if item.get("is_supported") is False:
            return "不支持"
        if item.get("is_winner") is True:
            return "命中"
        if item.get("is_winner") is False:
            return "未中"
        return "状态未知"

    def _settlement_item_reference_text(self, item: dict[str, object]) -> str:
        parts: list[str] = []
        self._append_reference(parts, "特码号码", item.get("draw_special_number"))
        self._append_reference(parts, "特码生肖", item.get("draw_special_zodiac"))
        self._append_reference(parts, "正码", item.get("draw_regular_numbers"))
        self._append_reference(parts, "全部号码", item.get("draw_numbers"))
        self._append_reference(parts, "开奖号尾数", item.get("draw_tails"))
        self._append_reference(parts, "投注生肖", item.get("selected_zodiacs"))
        self._append_reference(parts, "命中生肖", item.get("matched_zodiac"))
        self._append_reference(parts, "投注尾数", item.get("selected_tails"))
        self._append_reference(parts, "命中尾数", item.get("matched_tails"))
        self._append_reference(parts, "投注号码", item.get("selected_numbers"))
        self._append_reference(parts, "出现号码", item.get("hit_numbers"))
        self._append_reference(parts, "命中号码", item.get("matched_numbers"))
        self._append_reference(parts, "特码波色", item.get("draw_special_wave"))
        self._append_reference(parts, "特码单双", item.get("draw_special_odd_even"))
        self._append_reference(parts, "特码大小", item.get("draw_special_big_small"))
        self._append_reference(parts, "投注半波", item.get("selected_halfwaves"))
        self._append_reference(parts, "命中半波", item.get("matched_halfwave"))
        self._append_reference(parts, "命中号码", item.get("matched_number"))
        return "；".join(parts) if parts else "—"

    def _settlement_record_payout_text(self, record: SettlementLedgerResult | None) -> str:
        if record is None:
            return "—"
        if not self._snapshot_has_payout(record.result_snapshot):
            return LEGACY_NO_PAYOUT_TEXT
        return _money(record.total_payout_amount)

    def _snapshot_has_payout(self, snapshot: object) -> bool:
        if not isinstance(snapshot, dict):
            return False
        settlement = snapshot.get("settlement")
        if isinstance(settlement, dict) and "total_payout_amount" in settlement:
            return True
        items = snapshot.get("items")
        return isinstance(items, list) and any(
            isinstance(item, dict) and "payout_amount" in item
            for item in items
        )

    def _snapshot_has_rebate(self, snapshot: object) -> bool:
        if not isinstance(snapshot, dict):
            return False
        summary = snapshot.get("summary")
        if isinstance(summary, dict) and "total_rebate_amount" in summary:
            return True
        settlement = snapshot.get("settlement")
        if isinstance(settlement, dict) and "total_rebate_amount" in settlement:
            return True
        items = snapshot.get("items")
        return isinstance(items, list) and any(
            isinstance(item, dict) and "rebate_amount" in item
            for item in items
        )

    def _snapshot_has_statistic_net(self, snapshot: object) -> bool:
        if not isinstance(snapshot, dict):
            return False
        summary = snapshot.get("summary")
        if isinstance(summary, dict) and "statistic_net_amount" in summary:
            return True
        settlement = snapshot.get("settlement")
        return isinstance(settlement, dict) and "statistic_net_amount" in settlement

    def _append_reference(self, parts: list[str], label: str, value: object | None) -> None:
        text = self._format_reference_value(value)
        if text:
            parts.append(f"{label}={text}")

    def _format_reference_value(self, value: object | None) -> str:
        if value in (None, "", (), [], {}):
            return ""
        if isinstance(value, (list, tuple)):
            return ",".join(str(item) for item in value)
        return str(value)

    def _preview_to_snapshot(self, preview: OrderSettlementPreview) -> dict[str, object]:
        return {
            "settlement": {
                "total_bet_amount": _money(preview.total_bet_amount),
                "total_payout_amount": _money(preview.total_payout_amount),
                "total_rebate_amount": _money(preview.total_rebate_amount),
                "statistic_net_amount": _money(preview.statistic_net_amount),
            },
            "items": [
                {
                    "bet_type": item.bet_type,
                    "selection": item.selection,
                    "amount": _money(item.amount),
                    "is_supported": item.is_supported,
                    "is_winner": item.is_winner,
                    "matched_number": item.matched_number,
                    "reason": item.reason,
                    "draw_special_number": item.draw_special_number,
                    "draw_special_zodiac": item.draw_special_zodiac,
                    "draw_numbers": list(item.draw_numbers),
                    "draw_tails": list(item.draw_tails),
                    "draw_regular_numbers": list(item.draw_regular_numbers),
                    "selected_zodiacs": list(item.selected_zodiacs),
                    "matched_zodiac": item.matched_zodiac,
                    "selected_tails": list(item.selected_tails),
                    "matched_tails": list(item.matched_tails),
                    "selected_numbers": list(item.selected_numbers),
                    "hit_numbers": list(item.hit_numbers),
                    "matched_numbers": list(item.matched_numbers),
                    "draw_special_wave": item.draw_special_wave,
                    "draw_special_odd_even": item.draw_special_odd_even,
                    "draw_special_big_small": item.draw_special_big_small,
                    "selected_halfwaves": list(item.selected_halfwaves),
                    "matched_halfwave": item.matched_halfwave,
                    "unsupported_reason": item.unsupported_reason,
                    "odds": str(item.odds) if item.odds is not None else None,
                    "payout_amount": _money(item.payout_amount),
                    "odds_plan_name": item.odds_plan_name,
                    "odds_source": item.odds_source,
                    "payout_note": item.payout_note,
                    "rebate_rate": str(item.rebate_rate) if item.rebate_rate is not None else None,
                    "rebate_amount": _money(item.rebate_amount),
                    "rebate_note": item.rebate_note,
                }
                for item in preview.results
            ]
        }

    def _selected_order_ids_from_table(self) -> list[int]:
        selection_model = self._table.selectionModel()
        rows = sorted({index.row() for index in selection_model.selectedRows()}) if selection_model else []
        order_ids: list[int] = []
        for row in rows:
            if 0 <= row < len(self._row_order_ids):
                order_ids.append(self._row_order_ids[row])
        return order_ids

    def _confirm_high_risk_operation(self, spec):
        dialog = HighRiskConfirmDialog(spec, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._status_label.setText("已取消高风险维护操作，未写入业务数据。")
            return None
        return dialog.confirmation()

    def _on_clear_orders(self) -> None:
        try:
            spec = self._maintenance_service.build_clear_orders_spec()
        except Exception as exc:
            QMessageBox.warning(self, "清空订单", f"读取影响范围失败：{exc}")
            return
        confirmation = self._confirm_high_risk_operation(spec)
        if confirmation is None:
            return
        try:
            result = self._maintenance_service.clear_orders(confirmation)
        except Exception as exc:
            QMessageBox.warning(self, "清空订单", f"清空订单失败：{exc}")
            self._status_label.setText(f"清空订单失败：{exc}")
            return
        app_events.orders_changed.emit()
        app_events.settlements_changed.emit()
        app_events.logs_changed.emit()
        self._status_label.setText(f"清空订单完成，已备份到：{result.backup_path}")
        QMessageBox.information(
            self,
            "清空订单",
            (
                "清空订单完成\n"
                f"备份文件：{result.backup_path}\n"
                f"删除订单：{result.deleted_orders_count}\n"
                f"删除明细：{result.deleted_order_items_count}\n"
                f"删除结算快照：{result.deleted_settlement_records_count}\n"
                f"操作日志ID：{result.operation_log_id}"
            ),
        )

    def _on_bulk_delete_orders(self) -> None:
        order_ids = self._selected_order_ids_from_table()
        if not order_ids:
            QMessageBox.warning(self, "批量删除订单", "请先选择要删除的订单。")
            return
        try:
            spec = self._maintenance_service.build_bulk_delete_orders_spec(order_ids)
        except Exception as exc:
            QMessageBox.warning(self, "批量删除订单", f"读取影响范围失败：{exc}")
            return
        confirmation = self._confirm_high_risk_operation(spec)
        if confirmation is None:
            return
        try:
            result = self._maintenance_service.bulk_delete_orders(order_ids, confirmation)
        except Exception as exc:
            QMessageBox.warning(self, "批量删除订单", f"批量删除订单失败：{exc}")
            self._status_label.setText(f"批量删除订单失败：{exc}")
            return
        app_events.orders_changed.emit()
        app_events.settlements_changed.emit()
        app_events.logs_changed.emit()
        self._status_label.setText(f"批量删除订单完成，已备份到：{result.backup_path}")
        QMessageBox.information(
            self,
            "批量删除订单",
            (
                "批量删除订单完成\n"
                f"备份文件：{result.backup_path}\n"
                f"删除订单：{result.deleted_orders_count}\n"
                f"删除明细：{result.deleted_order_items_count}\n"
                f"删除结算快照：{result.deleted_settlement_records_count}\n"
                f"操作日志ID：{result.operation_log_id}"
            ),
        )

    def _on_reset_draws(self) -> None:
        try:
            spec = self._maintenance_service.build_reset_draws_spec()
        except Exception as exc:
            QMessageBox.warning(self, "重置开奖", f"读取影响范围失败：{exc}")
            return
        if spec.extra_counts.get("settlement_records", 0):
            message = "存在结算记录，不能直接重置开奖；请先清空订单或使用测试库。"
            QMessageBox.warning(self, "重置开奖", message)
            self._status_label.setText(message)
            return
        confirmation = self._confirm_high_risk_operation(spec)
        if confirmation is None:
            return
        try:
            result = self._maintenance_service.reset_draws(confirmation)
        except MaintenanceError as exc:
            QMessageBox.warning(self, "重置开奖", str(exc))
            self._status_label.setText(str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "重置开奖", f"重置开奖失败：{exc}")
            self._status_label.setText(f"重置开奖失败：{exc}")
            return
        app_events.draws_changed.emit()
        app_events.logs_changed.emit()
        self._status_label.setText(f"重置开奖记录完成，已备份到：{result.backup_path}")
        QMessageBox.information(
            self,
            "重置开奖",
            (
                "重置开奖记录完成\n"
                f"备份文件：{result.backup_path}\n"
                f"删除开奖记录：{result.deleted_draws_count}\n"
                f"操作日志ID：{result.operation_log_id}"
            ),
        )

    def _on_settlement_preview(self) -> None:
        if self._selected_order_id is None:
            self._status_label.setText("请先选择订单")
            return
        detail = self._order_service.get_order(self._selected_order_id)
        if detail is None:
            QMessageBox.warning(self, "结算预览", "订单不存在或已被删除。")
            self.reload_data()
            return
        if detail.status == ORDER_STATUS_SETTLED:
            message = "该订单已正式结算，不能重复结算预览；请查看已保存结算快照。"
            self._status_label.setText(message)
            QMessageBox.warning(self, "结算预览", message)
            self._btn_preview.setEnabled(False)
            return
        if detail.status == ORDER_STATUS_VOIDED:
            message = "该订单已作废，不能进行结算预览。"
            self._status_label.setText(message)
            QMessageBox.warning(self, "结算预览", message)
            self._btn_preview.setEnabled(False)
            return
        if detail.status not in VOIDABLE_ORDER_STATUSES:
            message = f"当前订单状态不能结算预览：{detail.status}"
            self._status_label.setText(message)
            QMessageBox.warning(self, "结算预览", message)
            self._btn_preview.setEnabled(False)
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
        preview = getattr(dialog, "_current_preview", None)
        if isinstance(preview, OrderSettlementPreview):
            self._preview_snapshots[self._selected_order_id] = self._preview_to_snapshot(preview)
        if dialog.settlement_committed():
            self.reload_data()
        detail = self._order_service.get_order(self._selected_order_id)
        if detail is not None:
            self._update_result_panels(detail)

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

        reason, ok = QInputDialog.getMultiLineText(self, "作废订单", "请输入作废原因")
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
        app_events.orders_changed.emit()
        app_events.logs_changed.emit()
        self._status_label.setText(f"订单作废成功：{result.order_no}")
        QMessageBox.information(self, "作废订单", message)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget { font-size: 12px; color: #243238; }
            QFrame#toolbar, QFrame#filterPanel, QFrame#summaryBar {
                background: #ffffff;
                border: 1px solid #c8d5d8;
            }
            QFrame#summaryBar { border-top: 2px solid #7f969b; }
            QLineEdit, QComboBox, QDateEdit {
                min-height: 24px;
                padding: 1px 6px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QLineEdit#orderSearch { border: 1px solid #43c7d4; background: #edfcfd; }
            QPushButton {
                min-height: 24px;
                padding: 1px 8px;
                border: 1px solid #b8c7ca;
                background: #ffffff;
            }
            QPushButton:hover { background: #e8f7f8; border-color: #5fbac2; }
            QPushButton#primaryAction { color: #146c75; font-weight: 600; }
            QPushButton#dangerAction { color: #9f1d1d; border-color: #d79696; font-weight: 600; }
            QPushButton#dangerAction:hover { background: #fff2f2; border-color: #c0392b; }
            QPushButton#unavailableAction:disabled { color: #8b999c; background: #f3f5f5; }
            QTableWidget {
                border: 1px solid #aebfc2;
                gridline-color: #d5dfe1;
                background: #ffffff;
                alternate-background-color: #f7fafb;
                selection-background-color: #d8eef2;
                selection-color: #1e2e32;
            }
            QHeaderView::section {
                background: #dff2f3;
                padding: 4px;
                border: none;
                border-right: 1px solid #afc9cc;
                border-bottom: 1px solid #8fabad;
                font-weight: 600;
            }
            QTabWidget#contextTabs::pane { border: 1px solid #b9c8cb; }
            QTabBar::tab { padding: 4px 14px; background: #edf2f3; border: 1px solid #c5d0d2; }
            QTabBar::tab:selected { background: #ffffff; border-bottom-color: #ffffff; }
            QFrame#drawPanel { border: 1px solid #c3d0d2; background: #ffffff; }
            QLabel#drawTitle { font-weight: 600; color: #176e75; }
            QLabel#drawPlaceholder, QLabel#sectionHint, QLabel#operationStatus { color: #718085; }
            QFrame#drawBallCell { border: 1px solid #d1dadd; background: #ffffff; }
            QLabel#drawNumber, QLabel#specialDrawNumber { color: #627074; font-weight: 600; }
            QLabel#drawZodiac { border-top: 1px solid #d8e0e2; }
            QGroupBox { border: 1px solid #b9c8cb; margin-top: 7px; padding-top: 5px; }
            QGroupBox::title { subcontrol-origin: margin; left: 7px; padding: 0 3px; color: #66777b; }
            QPlainTextEdit { border: 1px solid #c7d2d4; background: #ffffff; }
            """
        )
