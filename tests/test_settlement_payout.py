from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import AccountLedgerEntry, CustomerAccount, LotteryDraw, OperationLog, Order, SettlementRecord
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from settlement.exceptions import SettlementDataError


def create_draw(draw_service: DrawService, *, special_number: str = "01"):
    return draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number=f"PAYOUT-{special_number}",
            draw_date=date(2026, 6, 24),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number=special_number,
            source="test",
        )
    )


def create_order(
    order_service: OrderService,
    *,
    customer_name: str | None = None,
    items: list[OrderItemCreate],
):
    return order_service.create_order(
        OrderCreate(
            customer_name=customer_name,
            region="澳门",
            raw_text="settlement payout test",
            source="test",
            items=items,
        )
    )


def create_postable_settlement(
    session_factory,
    *,
    customer_name: str | None = "张三",
    payout_amount: str = "88.00",
    snapshot: dict | None = None,
):
    order = create_order(
        OrderService(session_factory),
        customer_name=customer_name,
        items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")
    SettlementService(session_factory).commit_order_settlement(order.id, draw.id)
    with session_factory() as session:
        record = session.query(SettlementRecord).filter_by(order_id=order.id).one()
        record.result_snapshot = snapshot or {
            "summary": {"total_payout_amount": payout_amount},
            "settlement": {"total_payout_amount": "999.00"},
            "items": [{"payout_amount": "777.00"}],
        }
        session.commit()
        return order.id, record.id, draw.id


def test_post_payout_to_ledger_uses_settlement_snapshot_and_writes_audit(session_factory) -> None:
    order_id, record_id, _draw_id = create_postable_settlement(session_factory, payout_amount="88.00")

    result = SettlementService(session_factory).post_payout_to_ledger(order_id=order_id, operator="财务")

    assert result.success is True
    assert result.customer_name == "张三"
    assert result.payout_amount == Decimal("88.00")
    assert result.balance_before == Decimal("0.00")
    assert result.balance_after == Decimal("88.00")
    assert result.settlement_record_id == record_id
    with session_factory() as session:
        account = session.scalars(select(CustomerAccount).where(CustomerAccount.customer_name == "张三")).one()
        entry = session.get(AccountLedgerEntry, result.ledger_entry_id)
        record = session.get(SettlementRecord, record_id)
        assert account.balance == Decimal("88.00")
        assert entry is not None
        assert entry.direction == "in"
        assert entry.entry_type == "settlement_payout"
        assert entry.source_type == "settlement_record"
        assert entry.source_id == record_id
        assert entry.order_id == order_id
        assert entry.settlement_record_id == record_id
        assert entry.reason == "结算中奖金额入账"
        assert record is not None
        assert record.payout_ledger_entry_id == entry.id
        assert record.payout_posted_amount == Decimal("88.00")
        assert record.payout_posted_at is not None
        assert record.result_snapshot["payout_posting"]["ledger_entry_id"] == entry.id
        log = session.get(OperationLog, entry.audit_log_id)
        assert log is not None
        assert log.module == "accounting"
        assert log.action == "ledger/settlement_payout"
        assert "amount=88.00" in log.description


def test_same_settlement_record_cannot_post_payout_twice(session_factory) -> None:
    order_id, _record_id, _draw_id = create_postable_settlement(session_factory)
    service = SettlementService(session_factory)
    service.post_payout_to_ledger(order_id=order_id, operator="财务")

    with pytest.raises(SettlementDataError, match="已入账|已存在入账流水"):
        service.post_payout_to_ledger(order_id=order_id, operator="财务")

    assert len(service._ledger_service.list_entries(customer="张三")) == 1


def test_missing_settlement_record_cannot_post_payout(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        customer_name="张三",
        items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
    )

    with pytest.raises(SettlementDataError, match="未找到结算记录"):
        SettlementService(session_factory).post_payout_to_ledger(order_id=order.id, operator="财务")


def test_unsettled_order_with_record_cannot_post_payout(session_factory) -> None:
    order_id, _record_id, _draw_id = create_postable_settlement(session_factory)
    with session_factory() as session:
        order = session.get(Order, order_id)
        assert order is not None
        order.status = "active"
        session.commit()

    with pytest.raises(SettlementDataError, match="只有已正式结算"):
        SettlementService(session_factory).post_payout_to_ledger(order_id=order_id, operator="财务")


def test_legacy_snapshot_without_total_payout_cannot_post_payout(session_factory) -> None:
    order_id, _record_id, _draw_id = create_postable_settlement(
        session_factory,
        snapshot={"items": [{"payout_amount": "88.00"}]},
    )

    with pytest.raises(SettlementDataError, match="旧结算快照无中奖金额"):
        SettlementService(session_factory).post_payout_to_ledger(order_id=order_id, operator="财务")


def test_zero_payout_cannot_post_to_ledger(session_factory) -> None:
    order_id, _record_id, _draw_id = create_postable_settlement(session_factory, payout_amount="0.00")

    with pytest.raises(SettlementDataError, match="中奖金额为 0"):
        SettlementService(session_factory).post_payout_to_ledger(order_id=order_id, operator="财务")


def test_missing_customer_name_cannot_post_payout(session_factory) -> None:
    order_id, _record_id, _draw_id = create_postable_settlement(session_factory, customer_name=None)

    with pytest.raises(SettlementDataError, match="缺少客户"):
        SettlementService(session_factory).post_payout_to_ledger(order_id=order_id, operator="财务")


def test_post_payout_failure_rolls_back_balance_entry_and_marker(session_factory) -> None:
    order_id, record_id, _draw_id = create_postable_settlement(session_factory)
    service = SettlementService(session_factory)
    original_create = service._ledger_service.create_settlement_payout_entry

    def fail_after_create(*args, **kwargs):
        original_create(*args, **kwargs)
        raise RuntimeError("forced failure")

    service._ledger_service.create_settlement_payout_entry = fail_after_create  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="forced failure"):
        service.post_payout_to_ledger(order_id=order_id, operator="财务")

    with session_factory() as session:
        assert int(session.scalar(select(func.count(AccountLedgerEntry.id))) or 0) == 0
        assert int(session.scalar(select(func.count(CustomerAccount.id))) or 0) == 0
        record = session.get(SettlementRecord, record_id)
        assert record is not None
        assert record.payout_ledger_entry_id is None
        assert record.payout_posted_at is None
        assert record.payout_posted_amount is None


def test_post_payout_does_not_modify_order_or_draw_and_does_not_recalculate_odds(session_factory) -> None:
    order_id, record_id, draw_id = create_postable_settlement(session_factory, payout_amount="66.00")
    with session_factory() as session:
        order_before = session.get(Order, order_id)
        draw_before = session.get(LotteryDraw, draw_id)
        assert order_before is not None
        assert draw_before is not None
        order_status = order_before.status
        order_total = order_before.total_amount
        draw_numbers = tuple(draw_before.regular_numbers)
        draw_special = draw_before.special_number

    result = SettlementService(session_factory).post_payout_to_ledger(
        settlement_record_id=record_id,
        operator="财务",
    )

    assert result.payout_amount == Decimal("66.00")
    with session_factory() as session:
        order_after = session.get(Order, order_id)
        draw_after = session.get(LotteryDraw, draw_id)
        assert order_after is not None
        assert draw_after is not None
        assert order_after.status == order_status
        assert order_after.total_amount == order_total
        assert tuple(draw_after.regular_numbers) == draw_numbers
        assert draw_after.special_number == draw_special


def test_hit_item_uses_default_odds_and_decimal_payout(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "特码", "0.3", "0")
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="特码", selection="01", amount="0.10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is True
    assert item.odds == Decimal("0.3000")
    assert item.payout_amount == Decimal("0.03")
    assert preview.total_payout_amount == Decimal("0.03")
    assert item.odds_source == "默认方案"
    assert item.odds_plan_name == "默认方案"


def test_miss_and_unsupported_items_have_zero_payout(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "特码", "47", "0")
    order = create_order(
        OrderService(session_factory),
        items=[
            OrderItemCreate(bet_type="特码", selection="02", amount="10"),
            OrderItemCreate(bet_type="连肖", selection="马X", amount="10"),
        ],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    miss, unsupported = preview.results

    assert miss.is_winner is False
    assert miss.payout_amount == Decimal("0.00")
    assert miss.payout_note == "未命中，不计算中奖金额"
    assert unsupported.is_supported is False
    assert unsupported.payout_amount == Decimal("0.00")
    assert unsupported.payout_note == "不支持玩法，不计算中奖金额"
    assert preview.total_payout_amount == Decimal("0.00")


def test_hit_without_odds_configuration_has_zero_payout_and_note(session_factory) -> None:
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is True
    assert item.odds is None
    assert item.payout_amount == Decimal("0.00")
    assert item.odds_source == "未配置"
    assert item.payout_note == "未配置赔率"


def test_hit_without_matching_odds_item_has_zero_payout_and_note(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "波色", "2", "0")
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is True
    assert item.payout_amount == Decimal("0.00")
    assert item.odds_plan_name == "默认方案"
    assert item.odds_source == "默认方案"
    assert item.payout_note == "未找到赔率配置"


def test_declarer_bound_plan_takes_priority_over_default_plan(session_factory) -> None:
    settings = SettingsService(session_factory)
    default = settings.ensure_default_plan()
    settings.add_item(default.id, "特码", "2", "0")
    custom = settings.create_plan("申报人方案")
    settings.add_item(custom.id, "特码", "3", "0")
    settings.add_declarer("林林", custom.id)
    order = create_order(
        OrderService(session_factory),
        customer_name="林林",
        items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.payout_amount == Decimal("30.00")
    assert item.odds == Decimal("3.0000")
    assert item.odds_plan_name == "申报人方案"
    assert item.odds_source == "申报人绑定方案"


def test_default_plan_is_used_when_declarer_has_no_binding(session_factory) -> None:
    settings = SettingsService(session_factory)
    default = settings.ensure_default_plan()
    settings.add_item(default.id, "特码", "2", "0")
    order = create_order(
        OrderService(session_factory),
        customer_name="未绑定申报人",
        items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.payout_amount == Decimal("20.00")
    assert item.odds_plan_name == "默认方案"
    assert item.odds_source == "默认方案"


def test_n_non_hit_prefers_n_odds_over_non_hit_fallback(session_factory) -> None:
    settings = SettingsService(session_factory)
    default = settings.ensure_default_plan()
    settings.add_item(default.id, "不中", "2", "0")
    settings.add_item(default.id, "N不中", "3", "0")
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="N不中", selection="08,09,10", amount="100")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is True
    assert item.odds == Decimal("3.0000")
    assert item.payout_amount == Decimal("300.00")


def test_n_non_hit_falls_back_to_non_hit_odds(session_factory) -> None:
    settings = SettingsService(session_factory)
    default = settings.ensure_default_plan()
    settings.add_item(default.id, "不中", "2", "0")
    order = create_order(
        OrderService(session_factory),
        items=[OrderItemCreate(bet_type="N不中", selection="08,09,10", amount="100")],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)
    item = preview.results[0]

    assert item.is_winner is True
    assert item.odds == Decimal("2.0000")
    assert item.payout_amount == Decimal("200.00")


def test_commit_snapshot_contains_payout_fields_without_balance_or_rebate(session_factory) -> None:
    settings = SettingsService(session_factory)
    default = settings.ensure_default_plan()
    settings.add_item(default.id, "特码", "47", "0")
    order = create_order(
        OrderService(session_factory),
        items=[
            OrderItemCreate(bet_type="特码", selection="01", amount="10"),
            OrderItemCreate(bet_type="特码", selection="02", amount="10"),
        ],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.total_payout_amount == Decimal("470.00")
    with session_factory() as session:
        record = session.query(SettlementRecord).filter_by(order_id=order.id).one()
        snapshot = record.result_snapshot

    assert snapshot["settlement"]["total_payout_amount"] == "470.00"
    assert snapshot["items"][0]["odds"] == "47"
    assert snapshot["items"][0]["payout_amount"] == "470.00"
    assert snapshot["items"][0]["odds_plan_name"] == "默认方案"
    assert snapshot["items"][0]["odds_source"] == "默认方案"
    assert snapshot["items"][1]["payout_amount"] == "0.00"
    assert "balance" not in str(snapshot).lower()
    assert "rebate" not in str(snapshot).lower()
