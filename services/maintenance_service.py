"""Guarded high-risk maintenance operations."""

from __future__ import annotations

import csv
import shutil
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from core.config import DATA_DIR, DATABASE_PATH
from core.database import SessionLocal
from models import LotteryDraw, OperationLog, Order, OrderItem, SettlementRecord
from schemas.maintenance_schema import HighRiskConfirmation, HighRiskOperationSpec, MaintenanceResult
from services.log_service import LogService


class MaintenanceError(RuntimeError):
    """Raised when a protected maintenance operation cannot proceed."""


_CONFIRM_PHRASES = {
    "clear_orders": "确认清空订单",
    "clear_logs": "确认清空日志",
    "bulk_delete_orders": "确认批量删除订单",
    "reset_draws": "确认重置开奖",
}

_BACKUP_PREFIXES = {
    "clear_orders": "fortune_before_clear_orders",
    "clear_logs": "fortune_before_clear_logs",
    "bulk_delete_orders": "fortune_before_bulk_delete_orders",
    "reset_draws": "fortune_before_reset_draws",
}


class MaintenanceService:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        *,
        database_path: str | Path = DATABASE_PATH,
        backup_dir: str | Path | None = None,
        log_archive_dir: str | Path | None = None,
        log_service: LogService | None = None,
    ):
        self._session_factory = session_factory
        self._database_path = Path(database_path)
        self._backup_dir = Path(backup_dir) if backup_dir is not None else DATA_DIR / "backups"
        self._log_archive_dir = (
            Path(log_archive_dir) if log_archive_dir is not None else self._backup_dir / "log_archives"
        )
        self._log_service = log_service or LogService(session_factory)

    def build_clear_orders_spec(self) -> HighRiskOperationSpec:
        with self._session_factory() as session:
            orders_count = self._count(session, Order.id)
            item_count = self._count(session, OrderItem.id)
            settlement_count = self._count(session, SettlementRecord.id)
        return HighRiskOperationSpec(
            operation="clear_orders",
            title="清空订单",
            confirm_phrase=_CONFIRM_PHRASES["clear_orders"],
            impact_summary="将删除全部订单、订单明细和对应结算快照；不会删除开奖记录、操作日志、设置或调单快照。",
            affected_count=orders_count,
            backup_path=self._preview_backup_path("clear_orders"),
            warning="这是破坏性维护操作。执行前必须确认已经使用测试库或已备份真实库。",
            extra_counts={
                "orders": orders_count,
                "order_items": item_count,
                "settlement_records": settlement_count,
            },
        )

    def build_bulk_delete_orders_spec(self, order_ids: Sequence[int]) -> HighRiskOperationSpec:
        ids = self._normalize_order_ids(order_ids)
        with self._session_factory() as session:
            orders_count = self._count_orders_by_ids(session, ids)
            item_count = self._count_items_by_order_ids(session, ids)
            settlement_count = self._count_settlements_by_order_ids(session, ids)
        return HighRiskOperationSpec(
            operation="bulk_delete_orders",
            title="批量删除订单",
            confirm_phrase=_CONFIRM_PHRASES["bulk_delete_orders"],
            impact_summary="将删除选中订单、订单明细和对应结算快照；不会删除开奖记录、操作日志或设置。",
            affected_count=orders_count,
            backup_path=self._preview_backup_path("bulk_delete_orders"),
            warning="如选中订单包含已结算订单，将同时删除其结算快照。",
            extra_counts={
                "orders": orders_count,
                "order_items": item_count,
                "settlement_records": settlement_count,
            },
        )

    def build_clear_logs_spec(self) -> HighRiskOperationSpec:
        with self._session_factory() as session:
            logs_count = self._count(session, OperationLog.id)
        return HighRiskOperationSpec(
            operation="clear_logs",
            title="清空日志",
            confirm_phrase=_CONFIRM_PHRASES["clear_logs"],
            impact_summary="将归档并清空当前操作日志，然后写入一条新的清空日志记录；不会删除其它业务数据。",
            affected_count=logs_count,
            backup_path=self._preview_backup_path("clear_logs"),
            warning="操作日志用于追溯关键行为。请确认归档文件创建成功后再执行。",
            extra_counts={"operation_logs": logs_count},
        )

    def build_reset_draws_spec(self) -> HighRiskOperationSpec:
        with self._session_factory() as session:
            draws_count = self._count(session, LotteryDraw.id)
            settlement_count = self._count(session, SettlementRecord.id)
        return HighRiskOperationSpec(
            operation="reset_draws",
            title="重置开奖记录",
            confirm_phrase=_CONFIRM_PHRASES["reset_draws"],
            impact_summary="将清空开奖记录；不删除订单、订单明细、操作日志或设置。存在结算记录时会阻断。",
            affected_count=draws_count,
            backup_path=self._preview_backup_path("reset_draws"),
            warning="开奖是结算依据。存在结算记录时不能直接重置开奖。",
            extra_counts={"lottery_draws": draws_count, "settlement_records": settlement_count},
        )

    def clear_orders(self, confirmation: HighRiskConfirmation) -> MaintenanceResult:
        self._validate_confirmation("clear_orders", confirmation)
        backup_path = self._create_backup("clear_orders")
        with self._session_factory() as session:
            try:
                orders_count = self._count(session, Order.id)
                item_count = self._count(session, OrderItem.id)
                settlement_count = self._count(session, SettlementRecord.id)
                session.execute(delete(SettlementRecord))
                session.execute(delete(OrderItem))
                session.execute(delete(Order))
                log = self._write_maintenance_log(
                    session,
                    action="maintenance/clear_orders",
                    description=(
                        f"清空订单成功；backup_path={backup_path}; "
                        f"deleted_orders_count={orders_count}; "
                        f"deleted_order_items_count={item_count}; "
                        f"deleted_settlement_records_count={settlement_count}; "
                        f"reason={confirmation.reason.strip()}; operator={self._operator(confirmation)}"
                    ),
                    operator=self._operator(confirmation),
                )
                session.commit()
                return MaintenanceResult(
                    operation="clear_orders",
                    success=True,
                    message="清空订单完成",
                    backup_path=backup_path,
                    operation_log_id=log.id,
                    deleted_orders_count=orders_count,
                    deleted_order_items_count=item_count,
                    deleted_settlement_records_count=settlement_count,
                )
            except Exception:
                session.rollback()
                raise

    def bulk_delete_orders(
        self,
        order_ids: Sequence[int],
        confirmation: HighRiskConfirmation,
    ) -> MaintenanceResult:
        self._validate_confirmation("bulk_delete_orders", confirmation)
        ids = self._normalize_order_ids(order_ids)
        if not ids:
            raise MaintenanceError("请选择要批量删除的订单")
        backup_path = self._create_backup("bulk_delete_orders")
        with self._session_factory() as session:
            try:
                orders_count = self._count_orders_by_ids(session, ids)
                if orders_count <= 0:
                    raise MaintenanceError("未找到要删除的订单")
                item_count = self._count_items_by_order_ids(session, ids)
                settlement_count = self._count_settlements_by_order_ids(session, ids)
                session.execute(delete(SettlementRecord).where(SettlementRecord.order_id.in_(ids)))
                session.execute(delete(OrderItem).where(OrderItem.order_id.in_(ids)))
                session.execute(delete(Order).where(Order.id.in_(ids)))
                log = self._write_maintenance_log(
                    session,
                    action="maintenance/bulk_delete_orders",
                    description=(
                        f"批量删除订单成功；backup_path={backup_path}; order_ids={ids}; "
                        f"deleted_orders_count={orders_count}; "
                        f"deleted_order_items_count={item_count}; "
                        f"deleted_settlement_records_count={settlement_count}; "
                        f"reason={confirmation.reason.strip()}; operator={self._operator(confirmation)}"
                    ),
                    operator=self._operator(confirmation),
                )
                session.commit()
                return MaintenanceResult(
                    operation="bulk_delete_orders",
                    success=True,
                    message="批量删除订单完成",
                    backup_path=backup_path,
                    operation_log_id=log.id,
                    deleted_orders_count=orders_count,
                    deleted_order_items_count=item_count,
                    deleted_settlement_records_count=settlement_count,
                )
            except Exception:
                session.rollback()
                raise

    def clear_logs(self, confirmation: HighRiskConfirmation) -> MaintenanceResult:
        self._validate_confirmation("clear_logs", confirmation)
        backup_path = self._create_backup("clear_logs")
        archive_path = self._archive_logs()
        with self._session_factory() as session:
            try:
                logs_count = self._count(session, OperationLog.id)
                session.execute(delete(OperationLog))
                log = self._write_maintenance_log(
                    session,
                    action="maintenance/clear_logs",
                    description=(
                        f"清空日志成功；backup_path={backup_path}; archive_path={archive_path}; "
                        f"deleted_logs_count={logs_count}; "
                        f"reason={confirmation.reason.strip()}; operator={self._operator(confirmation)}"
                    ),
                    operator=self._operator(confirmation),
                )
                session.commit()
                return MaintenanceResult(
                    operation="clear_logs",
                    success=True,
                    message="清空日志完成",
                    backup_path=backup_path,
                    archive_path=archive_path,
                    operation_log_id=log.id,
                    deleted_logs_count=logs_count,
                )
            except Exception:
                session.rollback()
                raise

    def reset_draws(self, confirmation: HighRiskConfirmation) -> MaintenanceResult:
        self._validate_confirmation("reset_draws", confirmation)
        with self._session_factory() as session:
            settlement_count = self._count(session, SettlementRecord.id)
        if settlement_count:
            raise MaintenanceError("存在结算记录，不能直接重置开奖；请先清空订单或使用测试库。")
        backup_path = self._create_backup("reset_draws")
        with self._session_factory() as session:
            try:
                draws_count = self._count(session, LotteryDraw.id)
                session.execute(delete(LotteryDraw))
                log = self._write_maintenance_log(
                    session,
                    action="maintenance/reset_draws",
                    description=(
                        f"重置开奖记录成功；backup_path={backup_path}; "
                        f"deleted_draws_count={draws_count}; "
                        f"settlement_records_count={settlement_count}; "
                        f"reason={confirmation.reason.strip()}; operator={self._operator(confirmation)}"
                    ),
                    operator=self._operator(confirmation),
                )
                session.commit()
                return MaintenanceResult(
                    operation="reset_draws",
                    success=True,
                    message="重置开奖记录完成",
                    backup_path=backup_path,
                    operation_log_id=log.id,
                    deleted_draws_count=draws_count,
                    settlement_records_count=settlement_count,
                )
            except Exception:
                session.rollback()
                raise

    def _validate_confirmation(self, operation: str, confirmation: HighRiskConfirmation) -> None:
        if not confirmation.reason.strip():
            raise MaintenanceError("高风险操作必须填写原因")
        expected = _CONFIRM_PHRASES[operation]
        if confirmation.confirm_phrase.strip() != expected:
            raise MaintenanceError(f"确认短语不匹配，请输入：{expected}")

    def _create_backup(self, operation: str) -> Path:
        self._ensure_database_can_be_copied()
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self._unique_path(self._backup_dir, _BACKUP_PREFIXES[operation], ".db")
        shutil.copy2(self._database_path, backup_path)
        if not backup_path.exists() or backup_path.stat().st_size <= 0:
            raise MaintenanceError("自动备份失败，已阻断高风险操作")
        return backup_path

    def _archive_logs(self) -> Path:
        self._log_archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self._unique_path(self._log_archive_dir, "operation_logs_before_clear", ".csv")
        with self._session_factory() as session:
            rows = list(session.scalars(select(OperationLog).order_by(OperationLog.id.asc())))
        try:
            with archive_path.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["id", "module", "action", "description", "operator", "related_type", "related_id", "created_at"])
                for row in rows:
                    writer.writerow([
                        row.id,
                        row.module,
                        row.action,
                        row.description,
                        row.operator or "",
                        row.related_type or "",
                        row.related_id if row.related_id is not None else "",
                        row.created_at.isoformat(sep=" ") if row.created_at else "",
                    ])
        except Exception as exc:
            raise MaintenanceError(f"操作日志归档失败，已阻断清空日志：{exc}") from exc
        if not archive_path.exists() or archive_path.stat().st_size <= 0:
            raise MaintenanceError("操作日志归档失败，已阻断清空日志")
        return archive_path

    def _preview_backup_path(self, operation: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._backup_dir / f"{_BACKUP_PREFIXES[operation]}_{timestamp}.db"

    def _unique_path(self, directory: Path, prefix: str, suffix: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = directory / f"{prefix}_{timestamp}{suffix}"
        if not base.exists():
            return base
        for index in range(1, 1000):
            candidate = directory / f"{prefix}_{timestamp}_{index:03d}{suffix}"
            if not candidate.exists():
                return candidate
        raise MaintenanceError("无法生成不重复的维护文件名")

    def _ensure_database_can_be_copied(self) -> None:
        if not self._database_path.exists():
            raise MaintenanceError(f"数据库文件不存在：{self._database_path}")
        if not self._database_path.is_file():
            raise MaintenanceError(f"数据库路径不是文件：{self._database_path}")
        if self._database_path.stat().st_size <= 0:
            raise MaintenanceError(f"数据库文件为空：{self._database_path}")

    def _write_maintenance_log(
        self,
        session: Session,
        *,
        action: str,
        description: str,
        operator: str,
    ) -> OperationLog:
        log = self._log_service.create_log(
            module="maintenance",
            action=action,
            description=description,
            operator=operator,
            related_type="maintenance",
            session=session,
        )
        session.flush()
        return log

    def _operator(self, confirmation: HighRiskConfirmation) -> str:
        return confirmation.operator.strip() or "系统操作员"

    def _normalize_order_ids(self, order_ids: Sequence[int]) -> list[int]:
        normalized: list[int] = []
        for order_id in order_ids:
            try:
                value = int(order_id)
            except (TypeError, ValueError):
                continue
            if value > 0 and value not in normalized:
                normalized.append(value)
        return normalized

    def _count(self, session: Session, column) -> int:
        return int(session.scalar(select(func.count(column))) or 0)

    def _count_orders_by_ids(self, session: Session, order_ids: Sequence[int]) -> int:
        if not order_ids:
            return 0
        return int(session.scalar(select(func.count(Order.id)).where(Order.id.in_(order_ids))) or 0)

    def _count_items_by_order_ids(self, session: Session, order_ids: Sequence[int]) -> int:
        if not order_ids:
            return 0
        return int(session.scalar(select(func.count(OrderItem.id)).where(OrderItem.order_id.in_(order_ids))) or 0)

    def _count_settlements_by_order_ids(self, session: Session, order_ids: Sequence[int]) -> int:
        if not order_ids:
            return 0
        return int(
            session.scalar(select(func.count(SettlementRecord.id)).where(SettlementRecord.order_id.in_(order_ids))) or 0
        )
