"""Schemas for guarded high-risk maintenance operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HighRiskOperationSpec:
    operation: str
    title: str
    confirm_phrase: str
    impact_summary: str
    affected_count: int
    backup_path: Path
    warning: str
    extra_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HighRiskConfirmation:
    reason: str
    confirm_phrase: str
    operator: str = "系统操作员"


@dataclass(frozen=True, slots=True)
class MaintenanceResult:
    operation: str
    success: bool
    message: str
    backup_path: Path
    operation_log_id: int | None = None
    archive_path: Path | None = None
    deleted_orders_count: int = 0
    deleted_order_items_count: int = 0
    deleted_settlement_records_count: int = 0
    deleted_logs_count: int = 0
    deleted_draws_count: int = 0
    settlement_records_count: int = 0
