"""Customer account and balance ledger services."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models import AccountLedgerEntry, CustomerAccount
from repositories.accounting_repository import AccountLedgerRepository, CustomerAccountRepository
from schemas.accounting_schema import (
    AccountLedgerEntryResult,
    CustomerAccountResult,
    LedgerMutationResult,
)
from services.log_service import LogService

CENT = Decimal("0.01")
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_DISABLED = "disabled"
ENTRY_TYPE_MANUAL_CREDIT = "manual_credit"
ENTRY_TYPE_MANUAL_DEBIT = "manual_debit"
ENTRY_TYPE_REVERSAL = "manual_reversal"
ENTRY_TYPE_SETTLEMENT_PAYOUT = "settlement_payout"


class AccountingError(ValueError):
    """Raised when an account or ledger operation violates business rules."""


class CustomerAccountService:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory

    def get_or_create_customer(self, customer_name: str, *, note: str | None = None) -> CustomerAccountResult:
        normalized_name = _normalize_customer_name(customer_name)
        with self._session_factory() as session:
            try:
                repo = CustomerAccountRepository(session)
                account = repo.get_by_name(normalized_name)
                if account is None:
                    now = datetime.now()
                    account = CustomerAccount(
                        customer_name=normalized_name,
                        display_name=normalized_name,
                        balance=Decimal("0.00"),
                        status=ACCOUNT_STATUS_ACTIVE,
                        note=note,
                        created_at=now,
                        updated_at=now,
                    )
                    repo.add(account)
                    session.flush()
                session.commit()
                session.refresh(account)
                return _to_account_result(account)
            except IntegrityError:
                session.rollback()
                account = CustomerAccountRepository(session).get_by_name(normalized_name)
                if account is None:
                    raise
                return _to_account_result(account)
            except Exception:
                session.rollback()
                raise

    def list_customers(
        self,
        *,
        status: str | None = None,
        keyword: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[CustomerAccountResult]:
        status = _normalize_optional_status(status)
        limit, offset = _validate_limit_offset(limit, offset)
        keyword = _normalize_optional_text(keyword)
        with self._session_factory() as session:
            rows = CustomerAccountRepository(session).list(
                status=status,
                keyword=keyword,
                limit=limit,
                offset=offset,
            )
            return [_to_account_result(row) for row in rows]

    def get_customer_balance(self, customer: str | int) -> Decimal:
        with self._session_factory() as session:
            account = _resolve_account(session, customer)
            return _money(account.balance)

    def disable_customer(self, customer_id: int) -> CustomerAccountResult:
        return self._set_customer_status(customer_id, ACCOUNT_STATUS_DISABLED)

    def enable_customer(self, customer_id: int) -> CustomerAccountResult:
        return self._set_customer_status(customer_id, ACCOUNT_STATUS_ACTIVE)

    def _set_customer_status(self, customer_id: int, status: str) -> CustomerAccountResult:
        with self._session_factory() as session:
            try:
                account = CustomerAccountRepository(session).get(customer_id)
                if account is None:
                    raise AccountingError(f"未找到客户账户：{customer_id}")
                account.status = status
                account.updated_at = datetime.now()
                session.commit()
                session.refresh(account)
                return _to_account_result(account)
            except Exception:
                session.rollback()
                raise


class AccountLedgerService:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory
        self._log_service = LogService(session_factory)

    def add_manual_credit(
        self,
        customer: str | int,
        amount: Decimal | str | int,
        reason: str,
        operator: str | None = None,
    ) -> LedgerMutationResult:
        return self._append_entry(
            customer=customer,
            direction="in",
            amount=amount,
            reason=reason,
            operator=operator,
            entry_type=ENTRY_TYPE_MANUAL_CREDIT,
            action="ledger/manual_credit",
        )

    def add_manual_debit(
        self,
        customer: str | int,
        amount: Decimal | str | int,
        reason: str,
        operator: str | None = None,
    ) -> LedgerMutationResult:
        return self._append_entry(
            customer=customer,
            direction="out",
            amount=amount,
            reason=reason,
            operator=operator,
            entry_type=ENTRY_TYPE_MANUAL_DEBIT,
            action="ledger/manual_debit",
        )

    def list_entries(
        self,
        *,
        customer: str | int | None = None,
        entry_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AccountLedgerEntryResult]:
        limit, offset = _validate_limit_offset(limit, offset)
        customer_id: int | None = None
        customer_name: str | None = None
        if isinstance(customer, int):
            customer_id = customer
        elif customer not in (None, ""):
            customer_name = _normalize_customer_name(str(customer))
        with self._session_factory() as session:
            rows = AccountLedgerRepository(session).list(
                customer_id=customer_id,
                customer_name=customer_name,
                entry_type=_normalize_optional_text(entry_type),
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )
            return [_to_entry_result(row) for row in rows]

    def count_entries(
        self,
        *,
        customer: str | int | None = None,
        entry_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        customer_id: int | None = None
        customer_name: str | None = None
        if isinstance(customer, int):
            customer_id = customer
        elif customer not in (None, ""):
            customer_name = _normalize_customer_name(str(customer))
        with self._session_factory() as session:
            return AccountLedgerRepository(session).count(
                customer_id=customer_id,
                customer_name=customer_name,
                entry_type=_normalize_optional_text(entry_type),
                start_date=start_date,
                end_date=end_date,
            )

    def get_customer_statement(self, customer: str | int) -> list[AccountLedgerEntryResult]:
        return self.list_entries(customer=customer, limit=500)

    def create_settlement_payout_entry(
        self,
        session: Session,
        *,
        customer: str | int,
        amount: Decimal | str | int,
        reason: str,
        operator: str | None,
        order_id: int,
        settlement_record_id: int,
    ) -> AccountLedgerEntry:
        amount_value = _validate_amount(amount)
        reason = _normalize_required_text(reason, "变动原因")
        operator = _normalize_operator(operator)
        account = _get_or_create_account(session, customer)
        return self._create_entry(
            session,
            account=account,
            direction="in",
            amount=amount_value,
            reason=reason,
            operator=operator,
            entry_type=ENTRY_TYPE_SETTLEMENT_PAYOUT,
            source_type="settlement_record",
            source_id=settlement_record_id,
            action="ledger/settlement_payout",
            order_id=order_id,
            settlement_record_id=settlement_record_id,
        )

    def reverse_entry(self, entry_id: int, reason: str, operator: str | None = None) -> LedgerMutationResult:
        reason = _normalize_required_text(reason, "冲正原因")
        operator = _normalize_operator(operator)
        with self._session_factory() as session:
            try:
                ledger_repo = AccountLedgerRepository(session)
                original = ledger_repo.get(entry_id)
                if original is None:
                    raise AccountingError(f"未找到余额流水：{entry_id}")
                if original.is_reversed:
                    raise AccountingError(f"余额流水已冲正：{entry_id}")
                account = _resolve_account(session, original.customer_id)
                direction = "out" if original.direction == "in" else "in"
                entry = self._create_entry(
                    session,
                    account=account,
                    direction=direction,
                    amount=_money(original.amount),
                    reason=f"冲正流水 {original.id}：{reason}",
                    operator=operator,
                    entry_type=ENTRY_TYPE_REVERSAL,
                    source_type="ledger_reversal",
                    source_id=original.id,
                    action="ledger/reverse",
                )
                original.is_reversed = True
                original.reversed_by_id = entry.id
                session.flush()
                session.commit()
                session.refresh(account)
                session.refresh(entry)
                return LedgerMutationResult(
                    account=_to_account_result(account),
                    entry=_to_entry_result(entry),
                    operation_log_id=entry.audit_log_id or 0,
                )
            except Exception:
                session.rollback()
                raise

    def _append_entry(
        self,
        *,
        customer: str | int,
        direction: str,
        amount: Decimal | str | int,
        reason: str,
        operator: str | None,
        entry_type: str,
        action: str,
    ) -> LedgerMutationResult:
        amount_value = _validate_amount(amount)
        reason = _normalize_required_text(reason, "变动原因")
        operator = _normalize_operator(operator)
        with self._session_factory() as session:
            try:
                account = _get_or_create_account(session, customer)
                entry = self._create_entry(
                    session,
                    account=account,
                    direction=direction,
                    amount=amount_value,
                    reason=reason,
                    operator=operator,
                    entry_type=entry_type,
                    source_type="manual",
                    source_id=None,
                    action=action,
                )
                session.commit()
                session.refresh(account)
                session.refresh(entry)
                return LedgerMutationResult(
                    account=_to_account_result(account),
                    entry=_to_entry_result(entry),
                    operation_log_id=entry.audit_log_id or 0,
                )
            except Exception:
                session.rollback()
                raise

    def _create_entry(
        self,
        session: Session,
        *,
        account: CustomerAccount,
        direction: str,
        amount: Decimal,
        reason: str,
        operator: str,
        entry_type: str,
        source_type: str | None,
        source_id: int | None,
        action: str,
        order_id: int | None = None,
        settlement_record_id: int | None = None,
        adjustment_record_id: int | None = None,
    ) -> AccountLedgerEntry:
        if account.status != ACCOUNT_STATUS_ACTIVE:
            raise AccountingError(f"客户账户已停用：{account.customer_name}")
        if direction not in {"in", "out"}:
            raise AccountingError(f"不支持的流水方向：{direction}")
        balance_before = _money(account.balance)
        balance_after = _money(balance_before + amount if direction == "in" else balance_before - amount)
        if balance_after < Decimal("0.00"):
            raise AccountingError("余额不足，本阶段不允许扣成负数")

        account.balance = balance_after
        account.updated_at = datetime.now()
        entry = AccountLedgerEntry(
            customer_id=account.id,
            customer_name=account.customer_name,
            direction=direction,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            entry_type=entry_type,
            source_type=source_type,
            source_id=source_id,
            order_id=order_id,
            settlement_record_id=settlement_record_id,
            adjustment_record_id=adjustment_record_id,
            reason=reason,
            operator=operator,
            is_reversed=False,
        )
        AccountLedgerRepository(session).add(entry)
        session.flush()
        description = (
            f"customer_id={account.id}; customer_name={account.customer_name}; "
            f"entry_id={entry.id}; direction={direction}; amount={amount:.2f}; "
            f"balance_before={balance_before:.2f}; balance_after={balance_after:.2f}; "
            f"reason={reason}; operator={operator}"
        )
        log = self._log_service.create_log(
            module="accounting",
            action=action,
            description=description,
            operator=operator,
            related_type="account_ledger_entry",
            related_id=entry.id,
            session=session,
        )
        session.flush()
        entry.audit_log_id = log.id
        session.flush()
        return entry


def _get_or_create_account(session: Session, customer: str | int) -> CustomerAccount:
    if isinstance(customer, int):
        return _resolve_account(session, customer)
    name = _normalize_customer_name(str(customer))
    repo = CustomerAccountRepository(session)
    account = repo.get_by_name(name)
    if account is not None:
        return account
    now = datetime.now()
    account = CustomerAccount(
        customer_name=name,
        display_name=name,
        balance=Decimal("0.00"),
        status=ACCOUNT_STATUS_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    repo.add(account)
    session.flush()
    return account


def _resolve_account(session: Session, customer: str | int) -> CustomerAccount:
    repo = CustomerAccountRepository(session)
    if isinstance(customer, int):
        account = repo.get(customer)
    else:
        account = repo.get_by_name(_normalize_customer_name(str(customer)))
    if account is None:
        raise AccountingError(f"未找到客户账户：{customer}")
    return account


def _normalize_customer_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AccountingError("客户名称不能为空")
    if len(text) > 128:
        raise AccountingError("客户名称不能超过 128 个字符")
    return text


def _normalize_required_text(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AccountingError(f"{label}不能为空")
    return text


def _normalize_operator(value: str | None) -> str:
    text = str(value or "").strip()
    return text or "系统操作员"


def _normalize_optional_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_optional_status(value: str | None) -> str | None:
    text = _normalize_optional_text(value)
    if text is None or text == "全部":
        return None
    if text not in {ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_DISABLED}:
        raise AccountingError(f"不支持的账户状态：{text}")
    return text


def _validate_amount(value: Decimal | str | int) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise AccountingError("金额格式不正确") from exc
    if amount <= Decimal("0.00"):
        raise AccountingError("金额必须大于 0")
    return amount


def _money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _validate_limit_offset(limit: int, offset: int) -> tuple[int, int]:
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0
    return limit, offset


def _to_account_result(account: CustomerAccount) -> CustomerAccountResult:
    return CustomerAccountResult(
        id=account.id,
        customer_name=account.customer_name,
        display_name=account.display_name,
        balance=_money(account.balance),
        status=account.status,
        note=account.note,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _to_entry_result(entry: AccountLedgerEntry) -> AccountLedgerEntryResult:
    return AccountLedgerEntryResult(
        id=entry.id,
        customer_id=entry.customer_id,
        customer_name=entry.customer_name,
        direction=entry.direction,
        amount=_money(entry.amount),
        balance_before=_money(entry.balance_before),
        balance_after=_money(entry.balance_after),
        entry_type=entry.entry_type,
        source_type=entry.source_type,
        source_id=entry.source_id,
        order_id=entry.order_id,
        settlement_record_id=entry.settlement_record_id,
        adjustment_record_id=entry.adjustment_record_id,
        reason=entry.reason,
        operator=entry.operator,
        created_at=entry.created_at,
        audit_log_id=entry.audit_log_id,
        is_reversed=entry.is_reversed,
        reversed_by_id=entry.reversed_by_id,
    )
