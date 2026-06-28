"""DTOs for adjustment record persistence and display."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AdjustmentRecordCreate:
    adjustment_type: str
    region: str
    source_filter: dict[str, Any]
    original_total: str
    adjustment_total: str
    after_total: str
    item_count: int
    positive_count: int
    negative_count: int
    record_snapshot: dict[str, Any]
    summary_snapshot: dict[str, Any]
    note: str | None = None


@dataclass(frozen=True, slots=True)
class AdjustmentRecordResult:
    id: int
    adjustment_type: str
    region: str
    created_at: datetime
    source_filter: dict[str, Any]
    original_total: str
    adjustment_total: str
    after_total: str
    item_count: int
    positive_count: int
    negative_count: int
    record_snapshot: dict[str, Any]
    summary_snapshot: dict[str, Any]
    note: str | None


@dataclass(frozen=True, slots=True)
class AdjustmentRecordSaveResult:
    record: AdjustmentRecordResult
    operation_log_id: int
