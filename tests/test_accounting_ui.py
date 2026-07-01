from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QApplication, QMessageBox

from services.accounting_service import AccountLedgerService, CustomerAccountService
from ui.pages.customer_account_page import CustomerAccountPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_customer_account_page_creates_and_shows_balances(session_factory) -> None:
    app()
    ledger = AccountLedgerService(session_factory)
    ledger.add_manual_credit("张三", "100", "初始加款", "财务")
    page = CustomerAccountPage(
        account_service=CustomerAccountService(session_factory),
        ledger_service=AccountLedgerService(session_factory),
    )

    assert page._customer_table.rowCount() == 1
    assert page._customer_table.item(0, 1).text() == "张三"
    assert page._customer_table.item(0, 2).text() == "100.00"
    assert page._ledger_table.rowCount() == 1
    assert page._ledger_table.item(0, 3).text() == "100.00"


class _FakeManualDialog:
    def __init__(self, *, direction: str, parent=None, default_operator: str = "系统操作员"):
        self.direction = direction
        self.customer_input = _FakeInput()

    def exec(self):
        return 1

    def payload(self):
        return ("张三", "40", "UI测试", "财务")


class _FakeInput:
    def setText(self, value: str) -> None:
        self.value = value


def test_customer_account_page_manual_credit_confirms_and_refreshes(session_factory, monkeypatch) -> None:
    app()
    import ui.pages.customer_account_page as module

    monkeypatch.setattr(module, "ManualLedgerDialog", _FakeManualDialog)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    page = CustomerAccountPage(
        account_service=CustomerAccountService(session_factory),
        ledger_service=AccountLedgerService(session_factory),
    )

    page._on_manual_credit()

    assert CustomerAccountService(session_factory).get_customer_balance("张三") == Decimal("40.00")
    assert page._customer_table.rowCount() == 1
    assert page._ledger_table.rowCount() == 1


def test_customer_account_page_manual_debit_failure_does_not_crash(session_factory, monkeypatch) -> None:
    app()
    import ui.pages.customer_account_page as module

    warnings: list[str] = []
    monkeypatch.setattr(module, "ManualLedgerDialog", _FakeManualDialog)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, text: warnings.append(text))
    page = CustomerAccountPage(
        account_service=CustomerAccountService(session_factory),
        ledger_service=AccountLedgerService(session_factory),
    )

    page._on_manual_debit()

    assert warnings
    assert "余额不足" in warnings[0]
