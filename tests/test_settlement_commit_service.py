from __future__ import annotations

from datetime import date

import pytest

from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.log_service import LogService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from settlement.exceptions import SettlementDataError


def create_order(
    order_service: OrderService,
    *,
    region: str = "澳门",
    items: list[OrderItemCreate] | None = None,
):
    return order_service.create_order(
        OrderCreate(
            region=region,
            raw_text="settlement commit test",
            source="test",
            items=items or [OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )


def create_draw(
    draw_service: DrawService,
    *,
    region: str = "澳门",
    issue_number: str = "162",
    special_number: str = "01",
):
    return draw_service.create_draw(
        LotteryDrawCreate(
            region=region,
            issue_number=issue_number,
            draw_date=date(2026, 6, 11),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number=special_number,
        )
    )


def settlement_log_count(session_factory) -> int:
    return LogService(session_factory).count_logs(module="settlement", action="commit")


def settlement_record_count(session_factory) -> int:
    return SettlementService(session_factory).count_settlement_records()


def test_commit_order_missing_order_fails(session_factory) -> None:
    draw = create_draw(DrawService(session_factory))

    with pytest.raises(SettlementDataError, match="未找到订单"):
        SettlementService(session_factory).commit_order_settlement(999999, draw.id)

    assert settlement_log_count(session_factory) == 0


def test_commit_order_missing_draw_fails_without_status_change(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(order_service)

    with pytest.raises(SettlementDataError, match="未找到开奖记录"):
        SettlementService(session_factory).commit_order_settlement(order.id, 999999)

    assert order_service.get_order(order.id).status == "active"
    assert settlement_log_count(session_factory) == 0


def test_commit_order_region_mismatch_fails_without_status_change(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(order_service, region="澳门")
    draw = create_draw(DrawService(session_factory), region="香港")

    with pytest.raises(SettlementDataError, match="不一致"):
        SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert order_service.get_order(order.id).status == "active"
    assert settlement_log_count(session_factory) == 0


def test_commit_order_with_unsupported_bet_blocks_persistence(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(
        order_service,
        items=[OrderItemCreate(bet_type="连肖", selection="马X", amount="10")],
    )
    draw = create_draw(DrawService(session_factory))

    with pytest.raises(SettlementDataError, match="存在暂不支持玩法"):
        SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert order_service.get_order(order.id).status == "active"
    assert settlement_log_count(session_factory) == 0
    assert settlement_record_count(session_factory) == 0


def test_commit_saveable_but_unsupported_play_blocks_persistence(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(
        order_service,
        items=[
            OrderItemCreate(
                bet_type="连肖复选",
                selection="兔,狗,虎,蛇,龙",
                amount="50",
                note="复选类型=复4",
            )
        ],
    )
    draw = create_draw(DrawService(session_factory))

    with pytest.raises(SettlementDataError, match="暂不支持玩法"):
        SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert order_service.get_order(order.id).status == "active"
    assert settlement_log_count(session_factory) == 0
    assert settlement_record_count(session_factory) == 0


def test_commit_winning_special_number_updates_status_and_writes_log(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(order_service, items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")])
    draw = create_draw(DrawService(session_factory), special_number="01")

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.order_id == order.id
    assert result.draw_id == draw.id
    assert result.settlement_record_id > 0
    assert result.region == "澳门"
    assert result.issue_number == "162"
    assert result.total_items == 1
    assert result.supported_items == 1
    assert result.unsupported_items == 0
    assert result.win_count == 1
    assert result.lose_count == 0
    assert result.order_status_before == "active"
    assert result.order_status_after == "settled"
    assert result.operation_log_id > 0
    assert result.results[0].is_winner is True
    assert order_service.get_order(order.id).status == "settled"
    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    assert record.id == result.settlement_record_id
    assert record.order_id == order.id
    assert record.draw_id == draw.id
    assert record.issue_number == "162"
    assert record.hit_count == 1
    assert record.miss_count == 0
    assert record.unsupported_count == 0
    assert record.total_amount == order.total_amount
    assert record.result_snapshot["order"]["order_no"] == order.order_no
    assert record.result_snapshot["draw"]["issue_number"] == "162"
    assert record.result_snapshot["settlement"]["hit_count"] == 1
    assert record.result_snapshot["items"][0]["bet_type"] == "特码"
    assert record.result_snapshot["items"][0]["selection"] == "01"
    assert record.result_snapshot["items"][0]["amount"] == "10.00"
    assert record.result_snapshot["items"][0]["is_winner"] is True
    logs = LogService(session_factory).list_logs(module="settlement", action="commit")
    assert len(logs) == 1
    assert order.order_no in logs[0].description
    assert "中奖 1" in logs[0].description


def test_commit_ten_non_hit_writes_snapshot_with_specific_configured_odds(session_factory) -> None:
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "十不中", "5.0", "0")
    order = create_order(
        OrderService(session_factory),
        items=[
            OrderItemCreate(
                bet_type="N不中",
                selection="08,09,10,11,12,13,14,15,16,17",
                amount="4000",
            )
        ],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.win_count == 1
    assert result.total_payout_amount == 20000
    record = SettlementService(session_factory).get_settlement_record_by_order_id(order.id)
    assert record is not None
    item = record.result_snapshot["items"][0]
    assert item["result"] == "hit"
    assert item["odds"] == "5"
    assert item["payout_amount"] == "20000.00"
    assert item["draw_numbers"] == ["02", "03", "04", "05", "06", "07", "01"]


def test_commit_losing_special_number_by_issue_updates_status(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(order_service, items=[OrderItemCreate(bet_type="特码", selection="02", amount="10")])
    create_draw(DrawService(session_factory), issue_number="163", special_number="01")

    result = SettlementService(session_factory).commit_order_settlement_by_issue(order.id, "澳门", "163")

    assert result.win_count == 0
    assert result.lose_count == 1
    assert result.order_status_after == "settled"
    assert result.results[0].is_winner is False
    assert order_service.get_order(order.id).status == "settled"


def test_commit_multi_item_order_counts_results(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(
        order_service,
        items=[
            OrderItemCreate(bet_type="特码", selection="01", amount="10"),
            OrderItemCreate(bet_type="特码", selection="02", amount="20"),
            OrderItemCreate(bet_type="特码波色", selection="红波", amount="30"),
        ],
    )
    draw = create_draw(DrawService(session_factory), special_number="01")

    result = SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    assert result.total_items == 3
    assert result.supported_items == 3
    assert result.unsupported_items == 0
    assert result.win_count == 2
    assert result.lose_count == 1
    assert [item.is_winner for item in result.results] == [True, False, True]
    assert order_service.get_order(order.id).status == "settled"
    assert settlement_log_count(session_factory) == 1


def test_settled_order_cannot_commit_twice(session_factory) -> None:
    order_service = OrderService(session_factory)
    order = create_order(order_service)
    draw = create_draw(DrawService(session_factory))
    service = SettlementService(session_factory)

    service.commit_order_settlement(order.id, draw.id)
    with pytest.raises(SettlementDataError, match="已结算"):
        service.commit_order_settlement(order.id, draw.id)

    assert order_service.get_order(order.id).status == "settled"
    assert settlement_log_count(session_factory) == 1
    assert settlement_record_count(session_factory) == 1


def test_batch_read_settlement_records_by_order_ids(session_factory) -> None:
    order_service = OrderService(session_factory)
    first = create_order(order_service)
    second = create_order(order_service)
    draw = create_draw(DrawService(session_factory))
    service = SettlementService(session_factory)
    service.commit_order_settlement(first.id, draw.id)
    service.commit_order_settlement(second.id, draw.id)

    records = service.get_settlement_records_by_order_ids([first.id, second.id, 999999, first.id])

    assert set(records) == {first.id, second.id}
    assert records[first.id].issue_number == "162"
    assert records[second.id].hit_count == 1
    assert settlement_record_count(session_factory) == 2
