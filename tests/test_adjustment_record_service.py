from __future__ import annotations

from sqlalchemy import func, select

from models import AdjustmentRecord, OperationLog, Order, SettlementRecord
from schemas.adjustment_record_schema import AdjustmentRecordCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.adjustment_record_service import AdjustmentRecordService
from services.order_service import OrderService


def _payload(adjustment_type: str, *, region: str = "全部") -> AdjustmentRecordCreate:
    return AdjustmentRecordCreate(
        adjustment_type=adjustment_type,
        region=region,
        source_filter={"region": region},
        original_total="100.00",
        adjustment_total="10.00" if adjustment_type == "special" else "0.00",
        after_total="110.00" if adjustment_type == "special" else "100.00",
        item_count=1,
        positive_count=1 if adjustment_type == "special" else 0,
        negative_count=0,
        record_snapshot={
            "rows": [
                {
                    "name": "01" if adjustment_type == "special" else "牛,马",
                    "original_amount": "100.00",
                    "adjustment_amount": "10.00" if adjustment_type == "special" else "0.00",
                    "after_amount": "110.00" if adjustment_type == "special" else "100.00",
                }
            ]
        },
        summary_snapshot={"stats": {"total": "100.00"}},
        note="service test",
    )


def test_adjustment_record_service_saves_special_record_and_log(session_factory) -> None:
    service = AdjustmentRecordService(session_factory)

    result = service.create_record(_payload("special", region="澳门"))

    assert result.record.id > 0
    assert result.operation_log_id > 0
    assert result.record.adjustment_type == "special"
    assert result.record.region == "澳门"
    assert result.record.original_total == "100.00"
    assert result.record.adjustment_total == "10.00"
    assert result.record.after_total == "110.00"
    assert result.record.record_snapshot["rows"][0]["name"] == "01"
    with session_factory() as session:
        record = session.get(AdjustmentRecord, result.record.id)
        assert record is not None
        log = session.get(OperationLog, result.operation_log_id)
        assert log is not None
        assert log.module == "adjustment"
        assert log.action == "adjustment/create"
        assert log.related_type == "adjustment_record"
        assert log.related_id == record.id
        assert "record_snapshot" not in log.description


def test_adjustment_record_service_saves_lianxiao_record(session_factory) -> None:
    service = AdjustmentRecordService(session_factory)

    result = service.create_record(_payload("lianxiao", region="香港"))

    assert result.record.adjustment_type == "lianxiao"
    assert result.record.region == "香港"
    assert result.record.adjustment_total == "0.00"
    assert result.record.after_total == "100.00"
    assert result.record.positive_count == 0
    assert result.record.record_snapshot["rows"][0]["name"] == "牛,马"
    records = service.list_records(adjustment_type="lianxiao", region="香港")
    assert [record.id for record in records] == [result.record.id]


def test_adjustment_record_service_formats_record_text(session_factory) -> None:
    service = AdjustmentRecordService(session_factory)
    result = service.create_record(_payload("special"))

    text = service.format_record_text(result.record)

    assert "特码调单记录" in text
    assert f"记录 ID：{result.record.id}" in text
    assert "原金额合计：100.00" in text
    assert "本记录仅为调单快照，不代表已兑奖或已结算" in text


def test_adjustment_record_service_does_not_modify_orders_or_settlements(session_factory) -> None:
    order_service = OrderService(session_factory)
    order_service.create_order(
        OrderCreate(
            customer_name="调单测试",
            channel="测试",
            region="澳门",
            raw_text="特码 01 10",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )
    with session_factory() as session:
        before_orders = int(session.scalar(select(func.count(Order.id))) or 0)
        before_settlements = int(session.scalar(select(func.count(SettlementRecord.id))) or 0)

    AdjustmentRecordService(session_factory).create_record(_payload("special"))

    with session_factory() as session:
        after_orders = int(session.scalar(select(func.count(Order.id))) or 0)
        after_settlements = int(session.scalar(select(func.count(SettlementRecord.id))) or 0)
        order = session.scalars(select(Order)).one()
        assert after_orders == before_orders
        assert after_settlements == before_settlements
        assert order.status == "active"
