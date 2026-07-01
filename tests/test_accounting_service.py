from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import AccountLedgerEntry, CustomerAccount, OperationLog, Order
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.accounting_service import (
    AccountLedgerService,
    AccountingError,
    CustomerAccountService,
)
from services.draw_service import DrawService
from services.order_service import OrderService
from services.settlement_service import SettlementService


def test_get_or_create_customer_does_not_duplicate(session_factory) -> None:
    service = CustomerAccountService(session_factory)

    first = service.get_or_create_customer("张三")
    second = service.get_or_create_customer("张三")

    assert first.id == second.id
    assert second.balance == Decimal("0.00")
    with session_factory() as session:
        assert int(session.scalar(select(func.count(CustomerAccount.id))) or 0) == 1


def test_manual_credit_and_debit_update_balance_and_ledger(session_factory) -> None:
    ledger = AccountLedgerService(session_factory)

    credit = ledger.add_manual_credit("张三", "100.00", "测试加款", "财务")
    debit = ledger.add_manual_debit("张三", Decimal("30.50"), "测试扣款", "财务")

    assert credit.entry.direction == "in"
    assert credit.entry.balance_before == Decimal("0.00")
    assert credit.entry.balance_after == Decimal("100.00")
    assert debit.entry.direction == "out"
    assert debit.entry.balance_before == Decimal("100.00")
    assert debit.entry.balance_after == Decimal("69.50")
    assert CustomerAccountService(session_factory).get_customer_balance("张三") == Decimal("69.50")


def test_manual_debit_cannot_overdraw(session_factory) -> None:
    ledger = AccountLedgerService(session_factory)
    ledger.add_manual_credit("张三", "10", "初始加款", "财务")

    with pytest.raises(AccountingError, match="余额不足"):
        ledger.add_manual_debit("张三", "20", "超额扣款", "财务")

    assert CustomerAccountService(session_factory).get_customer_balance("张三") == Decimal("10.00")
    assert len(ledger.list_entries(customer="张三")) == 1


@pytest.mark.parametrize("amount", ["0", "-1", "0.00"])
def test_manual_ledger_amount_must_be_positive(session_factory, amount: str) -> None:
    with pytest.raises(AccountingError, match="金额必须大于 0"):
        AccountLedgerService(session_factory).add_manual_credit("张三", amount, "测试", "财务")


def test_manual_ledger_reason_is_required(session_factory) -> None:
    with pytest.raises(AccountingError, match="变动原因不能为空"):
        AccountLedgerService(session_factory).add_manual_credit("张三", "10", " ", "财务")


def test_ledger_list_filters_by_customer_and_writes_logs(session_factory) -> None:
    ledger = AccountLedgerService(session_factory)
    ledger.add_manual_credit("张三", "10", "张三加款", "财务")
    ledger.add_manual_credit("李四", "20", "李四加款", "财务")

    zhang_entries = ledger.list_entries(customer="张三")

    assert len(zhang_entries) == 1
    assert zhang_entries[0].customer_name == "张三"
    with session_factory() as session:
        logs = session.scalars(select(OperationLog).where(OperationLog.module == "accounting")).all()
        assert len(logs) == 2
        assert {log.action for log in logs} == {"ledger/manual_credit"}
        assert "balance_before=0.00" in logs[0].description
        assert "balance_after=" in logs[0].description


def test_no_float_usage_in_accounting_service() -> None:
    source = inspect.getsource(__import__("services.accounting_service", fromlist=["dummy"]))

    assert "float(" not in source
    assert "Decimal(" in source


def test_transaction_failure_rolls_back_balance_and_entry(session_factory) -> None:
    ledger = AccountLedgerService(session_factory)
    ledger.add_manual_credit("张三", "50", "初始加款", "财务")

    def fail_log(**kwargs):
        raise RuntimeError("log failed")

    ledger._log_service.create_log = fail_log  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="log failed"):
        ledger.add_manual_credit("张三", "10", "应回滚", "财务")

    assert CustomerAccountService(session_factory).get_customer_balance("张三") == Decimal("50.00")
    assert len(AccountLedgerService(session_factory).list_entries(customer="张三")) == 1


def test_reverse_entry_creates_opposite_ledger_entry(session_factory) -> None:
    ledger = AccountLedgerService(session_factory)
    credit = ledger.add_manual_credit("张三", "50", "初始加款", "财务")

    reversal = ledger.reverse_entry(credit.entry.id, "录入错误", "主管")

    assert reversal.entry.direction == "out"
    assert reversal.entry.balance_before == Decimal("50.00")
    assert reversal.entry.balance_after == Decimal("0.00")
    with session_factory() as session:
        original = session.get(AccountLedgerEntry, credit.entry.id)
        assert original is not None
        assert original.is_reversed is True
        assert original.reversed_by_id == reversal.entry.id


def test_settlement_commit_does_not_auto_post_to_customer_balance(session_factory) -> None:
    order = OrderService(session_factory).create_order(
        OrderCreate(
            customer_name="张三",
            channel="测试",
            region="澳门",
            raw_text="特码 01 10",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )
    draw = DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="20260701001",
            draw_date=date(2026, 7, 1),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="01",
        )
    )

    SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    with session_factory() as session:
        assert int(session.scalar(select(func.count(AccountLedgerEntry.id))) or 0) == 0
        assert int(session.scalar(select(func.count(CustomerAccount.id))) or 0) == 0
        persisted_order = session.get(Order, order.id)
        assert persisted_order is not None
        assert persisted_order.customer_name == "张三"
        assert persisted_order.status == "settled"
