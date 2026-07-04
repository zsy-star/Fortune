from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import Base, LotteryDraw, OperationLog, Order, OrderItem, SettlementRecord
from schemas.maintenance_schema import HighRiskConfirmation
from services.maintenance_service import MaintenanceError, MaintenanceService


def _make_service(tmp_path):
    db_path = tmp_path / "fortune_maintenance.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    service = MaintenanceService(
        factory,
        database_path=db_path,
        backup_dir=tmp_path / "backups",
        log_archive_dir=tmp_path / "log_archives",
    )
    return service, factory, engine, db_path


def _confirm(operation: str, *, reason: str = "发布前维护") -> HighRiskConfirmation:
    phrases = {
        "clear_orders": "确认清空订单",
        "clear_logs": "确认清空日志",
        "bulk_delete_orders": "确认批量删除订单",
        "reset_draws": "确认重置开奖",
    }
    return HighRiskConfirmation(reason=reason, confirm_phrase=phrases[operation], operator="测试员")


def _seed_order(session, *, order_no: str, draw: LotteryDraw | None = None) -> Order:
    order = Order(
        order_no=order_no,
        customer_name="测试客户",
        channel="测试",
        region="澳门",
        source="test",
        raw_text="特码 01 各10",
        total_amount=Decimal("10.00"),
        status="active",
    )
    session.add(order)
    session.flush()
    session.add(OrderItem(order_id=order.id, bet_type="特码", selection="01", amount=Decimal("10.00")))
    session.flush()
    if draw is not None:
        session.add(
            SettlementRecord(
                order_id=order.id,
                draw_id=draw.id,
                region=draw.region,
                issue_number=draw.issue_number,
                total_items=1,
                hit_count=1,
                miss_count=0,
                unsupported_count=0,
                total_amount=Decimal("10.00"),
                result_snapshot={"summary": {"total_payout_amount": "20.00"}, "items": []},
            )
        )
    return order


def _seed_draw(session, *, issue: str = "2026-001") -> LotteryDraw:
    draw = LotteryDraw(
        region="澳门",
        issue_number=issue,
        draw_date=date(2026, 7, 4),
        regular_numbers=["01", "02", "03", "04", "05", "06"],
        special_number="07",
        source="test",
        status="confirmed",
    )
    session.add(draw)
    session.flush()
    return draw


def _count(factory, model) -> int:
    with factory() as session:
        return len(session.scalars(select(model)).all())


def test_confirmation_requires_reason_and_matching_phrase(tmp_path) -> None:
    service, factory, engine, _db_path = _make_service(tmp_path)
    try:
        with pytest.raises(MaintenanceError, match="原因"):
            service.clear_orders(HighRiskConfirmation(reason="", confirm_phrase="确认清空订单"))

        with pytest.raises(MaintenanceError, match="确认短语"):
            service.clear_orders(HighRiskConfirmation(reason="测试", confirm_phrase="错"))

        assert _count(factory, OperationLog) == 0
    finally:
        engine.dispose()


def test_backup_failure_blocks_operation(tmp_path, monkeypatch) -> None:
    service, factory, engine, _db_path = _make_service(tmp_path)
    try:
        with factory() as session:
            _seed_order(session, order_no="NO-BACKUP")
            session.commit()

        def fail_backup(_operation: str) -> Path:
            raise MaintenanceError("自动备份失败")

        monkeypatch.setattr(service, "_create_backup", fail_backup)

        with pytest.raises(MaintenanceError, match="自动备份失败"):
            service.clear_orders(_confirm("clear_orders"))

        assert _count(factory, Order) == 1
        assert _count(factory, OrderItem) == 1
        assert _count(factory, OperationLog) == 0
    finally:
        engine.dispose()


def test_clear_orders_deletes_orders_items_and_settlements_only(tmp_path) -> None:
    service, factory, engine, _db_path = _make_service(tmp_path)
    try:
        with factory() as session:
            draw = _seed_draw(session)
            _seed_order(session, order_no="A", draw=draw)
            _seed_order(session, order_no="B", draw=draw)
            session.add(OperationLog(module="seed", action="seed", description="保留日志"))
            session.commit()

        result = service.clear_orders(_confirm("clear_orders"))

        assert result.deleted_orders_count == 2
        assert result.deleted_order_items_count == 2
        assert result.deleted_settlement_records_count == 2
        assert result.backup_path.exists()
        assert _count(factory, Order) == 0
        assert _count(factory, OrderItem) == 0
        assert _count(factory, SettlementRecord) == 0
        assert _count(factory, LotteryDraw) == 1
        assert _count(factory, OperationLog) == 2
    finally:
        engine.dispose()


def test_bulk_delete_orders_deletes_selected_orders_only(tmp_path) -> None:
    service, factory, engine, _db_path = _make_service(tmp_path)
    try:
        with factory() as session:
            draw = _seed_draw(session)
            first = _seed_order(session, order_no="SELECTED-1", draw=draw)
            second = _seed_order(session, order_no="SELECTED-2", draw=draw)
            kept = _seed_order(session, order_no="KEPT")
            session.commit()
            first_id, second_id, kept_id = first.id, second.id, kept.id

        result = service.bulk_delete_orders([first_id, second_id], _confirm("bulk_delete_orders"))

        assert result.deleted_orders_count == 2
        assert result.deleted_order_items_count == 2
        assert result.deleted_settlement_records_count == 2
        with factory() as session:
            remaining_orders = session.scalars(select(Order).order_by(Order.id)).all()
            assert [order.id for order in remaining_orders] == [kept_id]
        assert _count(factory, LotteryDraw) == 1
        assert _count(factory, OperationLog) == 1
    finally:
        engine.dispose()


def test_bulk_delete_orders_blocks_empty_selection(tmp_path) -> None:
    service, _factory, engine, _db_path = _make_service(tmp_path)
    try:
        with pytest.raises(MaintenanceError, match="选择"):
            service.bulk_delete_orders([], _confirm("bulk_delete_orders"))
    finally:
        engine.dispose()


def test_clear_logs_archives_then_keeps_new_maintenance_log(tmp_path) -> None:
    service, factory, engine, _db_path = _make_service(tmp_path)
    try:
        with factory() as session:
            session.add_all(
                [
                    OperationLog(module="order", action="create", description="录单"),
                    OperationLog(module="settlement", action="commit", description="结算"),
                ]
            )
            session.commit()

        result = service.clear_logs(_confirm("clear_logs"))

        assert result.deleted_logs_count == 2
        assert result.archive_path is not None
        assert result.archive_path.exists()
        assert "录单" in result.archive_path.read_text(encoding="utf-8-sig")
        with factory() as session:
            logs = session.scalars(select(OperationLog)).all()
            assert len(logs) == 1
            assert logs[0].module == "maintenance"
            assert logs[0].action == "maintenance/clear_logs"
        assert _count(factory, Order) == 0
    finally:
        engine.dispose()


def test_reset_draws_clears_draws_when_no_settlements(tmp_path) -> None:
    service, factory, engine, _db_path = _make_service(tmp_path)
    try:
        with factory() as session:
            _seed_draw(session, issue="RESET-1")
            _seed_draw(session, issue="RESET-2")
            session.commit()

        result = service.reset_draws(_confirm("reset_draws"))

        assert result.deleted_draws_count == 2
        assert _count(factory, LotteryDraw) == 0
        assert _count(factory, OperationLog) == 1
    finally:
        engine.dispose()


def test_reset_draws_blocks_when_settlement_records_exist(tmp_path) -> None:
    service, factory, engine, _db_path = _make_service(tmp_path)
    try:
        with factory() as session:
            draw = _seed_draw(session)
            _seed_order(session, order_no="SETTLED", draw=draw)
            session.commit()

        with pytest.raises(MaintenanceError, match="存在结算记录"):
            service.reset_draws(_confirm("reset_draws"))

        assert _count(factory, LotteryDraw) == 1
        assert _count(factory, Order) == 1
        assert _count(factory, OrderItem) == 1
        assert _count(factory, OperationLog) == 0
    finally:
        engine.dispose()
