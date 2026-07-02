from __future__ import annotations

from datetime import date
from decimal import Decimal

from models import SettlementRecord
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService


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
