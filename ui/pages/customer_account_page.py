"""Customer account and balance ledger page."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
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

from schemas.accounting_schema import AccountLedgerEntryResult, CustomerAccountResult
from services.accounting_service import AccountLedgerService, CustomerAccountService
from ui.app_events import app_events


def _money(value: Decimal) -> str:
    return f"{Decimal(value):.2f}"


def _dash(value: object | None) -> str:
    return str(value) if value not in (None, "") else "—"


class ManualLedgerDialog(QDialog):
    def __init__(self, *, direction: str, parent=None, default_operator: str = "系统操作员"):
        super().__init__(parent)
        self.direction = direction
        title = "手工加款" if direction == "in" else "手工扣款"
        self.setWindowTitle(title)
        self.resize(420, 220)

        layout = QVBoxLayout(self)
        form = QGridLayout()
        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("客户名 / 申报人名称")
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("金额，例如 100.00")
        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("必填，说明加扣款原因")
        self.operator_input = QLineEdit(default_operator)
        for row, (label, widget) in enumerate(
            (
                ("客户", self.customer_input),
                ("金额", self.amount_input),
                ("原因", self.reason_input),
                ("操作人", self.operator_input),
            )
        ):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(widget, row, 1)
        layout.addLayout(form)

        self.hint_label = QLabel("本操作只写余额流水；不自动兑奖、不写结算入账、不计算返水或佣金。")
        self.hint_label.setObjectName("ledgerDialogHint")
        layout.addWidget(self.hint_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def payload(self) -> tuple[str, str, str, str]:
        return (
            self.customer_input.text().strip(),
            self.amount_input.text().strip(),
            self.reason_input.text().strip(),
            self.operator_input.text().strip() or "系统操作员",
        )


class CustomerAccountPage(QWidget):
    def __init__(
        self,
        parent=None,
        account_service: CustomerAccountService | None = None,
        ledger_service: AccountLedgerService | None = None,
    ):
        super().__init__(parent)
        self._account_service = account_service or CustomerAccountService()
        self._ledger_service = ledger_service or AccountLedgerService()
        self._row_customer_ids: list[int] = []
        self._current_customer_name: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_action_row())
        root.addLayout(self._build_summary_row())
        root.addWidget(self._build_separator())

        body = QHBoxLayout()
        body.addWidget(self._build_customer_table(), stretch=1)
        body.addWidget(self._build_ledger_table(), stretch=2)
        root.addLayout(body, stretch=1)

        self._apply_stylesheet()
        app_events.ledger_changed.connect(self._on_ledger_changed)
        self.reload_data()

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._keyword = QLineEdit()
        self._keyword.setPlaceholderText("客户名")
        row.addWidget(QLabel("客户"))
        row.addWidget(self._keyword)
        row.addStretch(1)
        return row

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._btn_query = QPushButton("查询")
        self._btn_query.clicked.connect(self.reload_data)
        self._btn_manual_credit = QPushButton("手工加款")
        self._btn_manual_credit.clicked.connect(self._on_manual_credit)
        self._btn_manual_debit = QPushButton("手工扣款")
        self._btn_manual_debit.clicked.connect(self._on_manual_debit)
        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.clicked.connect(self.reload_data)
        for button in (
            self._btn_query,
            self._btn_manual_credit,
            self._btn_manual_debit,
            self._btn_refresh,
        ):
            row.addWidget(button)
        row.addStretch(1)
        return row

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._lbl_total = QLabel()
        self._lbl_hint = QLabel("余额只能通过流水变动；本页不自动接入结算兑奖、不计算返水或佣金。")
        self._lbl_hint.setObjectName("ledgerHint")
        row.addWidget(self._lbl_total)
        row.addWidget(self._lbl_hint)
        row.addStretch(1)
        return row

    def _build_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setObjectName("ledgerSeparator")
        line.setFixedHeight(2)
        return line

    def _build_customer_table(self) -> QTableWidget:
        self._customer_table = QTableWidget(0, 5)
        self._customer_table.setHorizontalHeaderLabels(["客户ID", "客户名", "余额", "状态", "更新时间"])
        self._customer_table.verticalHeader().setVisible(False)
        self._customer_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._customer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._customer_table.itemSelectionChanged.connect(self._on_customer_selected)
        header = self._customer_table.horizontalHeader()
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        return self._customer_table

    def _build_ledger_table(self) -> QTableWidget:
        self._ledger_table = QTableWidget(0, 9)
        self._ledger_table.setHorizontalHeaderLabels(
            ["时间", "类型", "方向", "金额", "变动前", "变动后", "原因", "操作人", "日志ID"]
        )
        self._ledger_table.verticalHeader().setVisible(False)
        self._ledger_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._ledger_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._ledger_table.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        return self._ledger_table

    def reload_data(self) -> None:
        keyword = self._keyword.text().strip() or None
        try:
            accounts = self._account_service.list_customers(keyword=keyword, limit=500)
            self._fill_customers(accounts)
            self._fill_ledgers(self._load_entries_for_current_selection())
            self._lbl_total.setText(f"客户账户：{len(accounts)} 个")
        except Exception as exc:
            self._customer_table.setRowCount(0)
            self._ledger_table.setRowCount(0)
            self._lbl_total.setText(f"账务数据加载失败：{exc}")

    def _fill_customers(self, accounts: list[CustomerAccountResult]) -> None:
        previous = self._current_customer_name
        self._row_customer_ids = []
        self._customer_table.setRowCount(len(accounts))
        selected_row = -1
        for row, account in enumerate(accounts):
            self._row_customer_ids.append(account.id)
            values = [
                str(account.id),
                account.customer_name,
                _money(account.balance),
                "启用" if account.status == "active" else "停用",
                account.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._customer_table.setItem(row, col, item)
            if previous and account.customer_name == previous:
                selected_row = row
        if selected_row >= 0:
            self._customer_table.selectRow(selected_row)
        elif accounts:
            self._customer_table.selectRow(0)
            self._current_customer_name = accounts[0].customer_name
        else:
            self._current_customer_name = None

    def _load_entries_for_current_selection(self) -> list[AccountLedgerEntryResult]:
        customer = self._current_customer_name or (self._keyword.text().strip() or None)
        return self._ledger_service.list_entries(customer=customer, limit=500)

    def _fill_ledgers(self, entries: list[AccountLedgerEntryResult]) -> None:
        self._ledger_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [
                entry.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                entry.entry_type,
                "收入" if entry.direction == "in" else "支出",
                _money(entry.amount),
                _money(entry.balance_before),
                _money(entry.balance_after),
                entry.reason,
                _dash(entry.operator),
                _dash(entry.audit_log_id),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft if col == 6 else Qt.AlignmentFlag.AlignCenter)
                if col == 6:
                    item.setToolTip(value)
                self._ledger_table.setItem(row, col, item)

    def _on_customer_selected(self) -> None:
        rows = self._customer_table.selectionModel().selectedRows() if self._customer_table.selectionModel() else []
        if not rows:
            self._current_customer_name = None
            self._fill_ledgers([])
            return
        row = rows[0].row()
        item = self._customer_table.item(row, 1)
        self._current_customer_name = item.text() if item is not None else None
        try:
            self._fill_ledgers(self._load_entries_for_current_selection())
        except Exception as exc:
            self._lbl_total.setText(f"流水加载失败：{exc}")

    def _on_manual_credit(self) -> None:
        self._open_manual_dialog("in")

    def _on_manual_debit(self) -> None:
        self._open_manual_dialog("out")

    def _open_manual_dialog(self, direction: str) -> None:
        dialog = ManualLedgerDialog(direction=direction, parent=self)
        if self._current_customer_name:
            dialog.customer_input.setText(self._current_customer_name)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        customer, amount, reason, operator = dialog.payload()
        title = "手工加款" if direction == "in" else "手工扣款"
        message = f"客户：{customer}\n金额：{amount}\n原因：{reason}\n操作人：{operator}\n\n确认写入余额流水？"
        choice = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            self._lbl_total.setText(f"已取消{title}")
            return
        try:
            if direction == "in":
                result = self._ledger_service.add_manual_credit(customer, amount, reason, operator)
            else:
                result = self._ledger_service.add_manual_debit(customer, amount, reason, operator)
        except Exception as exc:
            QMessageBox.warning(self, title, f"操作失败：{exc}")
            self._lbl_total.setText(f"{title}失败：{exc}")
            return
        self._current_customer_name = result.account.customer_name
        self._keyword.setText(result.account.customer_name)
        app_events.ledger_changed.emit()
        app_events.logs_changed.emit()
        QMessageBox.information(
            self,
            title,
            f"操作成功\n客户：{result.account.customer_name}\n余额：{_money(result.account.balance)}",
        )

    def _on_ledger_changed(self) -> None:
        try:
            self.reload_data()
        except Exception as exc:
            self._lbl_total.setText(f"账务数据已变更，但刷新失败：{exc}")

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
            QPushButton:hover { background-color: #ebf5fb; }
            QFrame#ledgerSeparator {
                background-color: #8e44ad;
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
                background-color: #f4ecf7;
                padding: 6px 4px;
                border: 1px solid #bdc3c7;
                font-weight: 600;
            }
            QLabel { font-size: 13px; color: #2c3e50; }
            QLabel#ledgerHint, QLabel#ledgerDialogHint { color: #7f8c8d; }
            QLineEdit {
                padding: 4px 6px;
                border: 1px solid #bdc3c7;
                border-radius: 2px;
                background: #ffffff;
                font-size: 13px;
            }
            """
        )
