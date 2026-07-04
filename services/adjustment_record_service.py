"""Adjustment record service."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models import AdjustmentRecord
from repositories.adjustment_record_repository import AdjustmentRecordRepository
from schemas.adjustment_record_schema import (
    AdjustmentRecordCreate,
    AdjustmentRecordResult,
    AdjustmentRecordSaveResult,
)
from services.log_service import LogService

ADJUSTMENT_TYPE_LABELS = {
    "special": "特码",
    "lianxiao": "连肖",
    "special_throw": "特码抛出",
    "special_throw_reversal": "特码撤销",
    "lianxiao_throw": "连肖抛出",
    "lianxiao_throw_reversal": "连肖撤销",
}
VALID_ADJUSTMENT_TYPES = set(ADJUSTMENT_TYPE_LABELS)
ADJUSTMENT_TYPE_GROUPS = {
    "special_all": {"special", "special_throw", "special_throw_reversal"},
    "lianxiao_all": {"lianxiao", "lianxiao_throw", "lianxiao_throw_reversal"},
}
VALID_REGIONS = {"全部", "澳门", "香港"}


class AdjustmentRecordService:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory
        self._log_service = LogService(session_factory)

    def create_record(self, payload: AdjustmentRecordCreate) -> AdjustmentRecordSaveResult:
        return self._create_record(payload, action="adjustment/create")

    def create_record_with_action(
        self,
        *,
        adjustment_type: str,
        region: str,
        source_filter: dict[str, Any],
        original_total: str,
        adjustment_total: str,
        after_total: str,
        item_count: int,
        positive_count: int,
        negative_count: int,
        record_snapshot: dict[str, Any],
        summary_snapshot: dict[str, Any],
        note: str | None,
        action: str,
        operator: str | None = None,
    ) -> AdjustmentRecordSaveResult:
        payload = AdjustmentRecordCreate(
            adjustment_type=adjustment_type,
            region=region,
            source_filter=source_filter,
            original_total=original_total,
            adjustment_total=adjustment_total,
            after_total=after_total,
            item_count=item_count,
            positive_count=positive_count,
            negative_count=negative_count,
            record_snapshot=record_snapshot,
            summary_snapshot=summary_snapshot,
            note=note,
        )
        return self._create_record(payload, action=action, operator=operator)

    def _create_record(
        self,
        payload: AdjustmentRecordCreate,
        *,
        action: str,
        operator: str | None = None,
    ) -> AdjustmentRecordSaveResult:
        self._validate_payload(payload)
        with self._session_factory() as session:
            try:
                repo = AdjustmentRecordRepository(session)
                record = AdjustmentRecord(
                    adjustment_type=payload.adjustment_type,
                    region=payload.region,
                    source_filter=payload.source_filter,
                    original_total=payload.original_total,
                    adjustment_total=payload.adjustment_total,
                    after_total=payload.after_total,
                    item_count=payload.item_count,
                    positive_count=payload.positive_count,
                    negative_count=payload.negative_count,
                    record_snapshot=payload.record_snapshot,
                    summary_snapshot=payload.summary_snapshot,
                    note=payload.note,
                )
                repo.add(record)
                session.flush()
                log = self._log_service.create_log(
                    module="adjustment",
                    action=action,
                    description=(
                        f"Created adjustment record; record_id={record.id}; "
                        f"adjustment_type={record.adjustment_type}; region={record.region}; "
                        f"original_total={record.original_total}; "
                        f"adjustment_total={record.adjustment_total}; "
                        f"after_total={record.after_total}; item_count={record.item_count}"
                    ),
                    operator=operator,
                    related_type="adjustment_record",
                    related_id=record.id,
                    session=session,
                )
                session.flush()
                session.refresh(record)
                result = AdjustmentRecordSaveResult(
                    record=self._to_result(record),
                    operation_log_id=log.id,
                )
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise

    def get_record(self, record_id: int) -> AdjustmentRecordResult | None:
        with self._session_factory() as session:
            record = AdjustmentRecordRepository(session).get(record_id)
            return self._to_result(record) if record is not None else None

    def list_records(
        self,
        *,
        adjustment_type: str | None = None,
        region: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AdjustmentRecordResult]:
        adjustment_type = self._normalize_optional_type(adjustment_type)
        region = self._normalize_optional_region(region)
        limit, offset = self._validate_limit_offset(limit, offset)
        with self._session_factory() as session:
            if adjustment_type in ADJUSTMENT_TYPE_GROUPS:
                records = AdjustmentRecordRepository(session).list(
                    adjustment_type=None,
                    region=region,
                    limit=500,
                    offset=0,
                )
                group = ADJUSTMENT_TYPE_GROUPS[adjustment_type]
                filtered = [record for record in records if record.adjustment_type in group]
                return [self._to_result(record) for record in filtered[offset : offset + limit]]
            records = AdjustmentRecordRepository(session).list(
                adjustment_type=adjustment_type,
                region=region,
                limit=limit,
                offset=offset,
            )
            return [self._to_result(record) for record in records]

    def count_records(
        self,
        *,
        adjustment_type: str | None = None,
        region: str | None = None,
    ) -> int:
        adjustment_type = self._normalize_optional_type(adjustment_type)
        region = self._normalize_optional_region(region)
        with self._session_factory() as session:
            return AdjustmentRecordRepository(session).count(
                adjustment_type=adjustment_type,
                region=region,
            )

    def format_record_text(self, record: AdjustmentRecordResult) -> str:
        type_label = ADJUSTMENT_TYPE_LABELS.get(record.adjustment_type, "未知类型")
        title = f"{type_label}调单记录"
        lines = [
            title,
            f"记录 ID：{record.id}",
            f"保存时间：{record.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"地区：{self._display_value(record.region)}",
            f"原金额合计：{self._display_value(record.original_total)}",
            f"调整金额合计：{self._display_value(record.adjustment_total)}",
            f"调整后合计：{self._display_value(record.after_total)}",
            f"条目数：{self._display_value(record.item_count)}",
            f"正调整数：{self._display_value(record.positive_count)}",
            f"负调整数：{self._display_value(record.negative_count)}",
        ]
        status = self._record_status(record)
        if status:
            lines.append(f"状态：{status}")
        if record.note:
            lines.append(f"备注：{record.note}")
        lines.extend(["", "明细快照"])
        lines.extend(self._format_snapshot(record.record_snapshot))
        lines.extend(["", "统计快照"])
        lines.extend(self._format_snapshot(record.summary_snapshot))
        lines.extend(
            [
                "",
                "说明：本记录仅为调单快照，不代表已兑奖或已结算。",
            ]
        )
        return "\n".join(lines)

    def _format_snapshot(self, snapshot: Any, indent: int = 0) -> list[str]:
        prefix = "  " * indent
        if snapshot in (None, "", {}, []):
            return [f"{prefix}—"]
        if isinstance(snapshot, str):
            parsed = self._parse_legacy_snapshot(snapshot)
            if parsed is not None:
                return self._format_snapshot(parsed, indent)
            return [
                f"{prefix}旧格式调单快照，仅显示原始内容",
                f"{prefix}{snapshot}",
            ]
        if isinstance(snapshot, dict):
            lines: list[str] = []
            for key, value in snapshot.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.extend(self._format_snapshot(value, indent + 1))
                else:
                    lines.append(f"{prefix}{key}: {self._display_value(value)}")
            return lines or [f"{prefix}—"]
        if isinstance(snapshot, list):
            lines = []
            for index, value in enumerate(snapshot, start=1):
                if isinstance(value, dict):
                    compact = "\t".join(f"{key}={self._display_value(item)}" for key, item in value.items())
                    lines.append(f"{prefix}{index}. {compact}")
                elif isinstance(value, list):
                    lines.append(f"{prefix}{index}.")
                    lines.extend(self._format_snapshot(value, indent + 1))
                else:
                    lines.append(f"{prefix}{index}. {self._display_value(value)}")
            return lines or [f"{prefix}—"]
        return [f"{prefix}{self._display_value(snapshot)}"]

    def _parse_legacy_snapshot(self, snapshot: str) -> Any | None:
        try:
            parsed = json.loads(snapshot)
        except (TypeError, ValueError):
            return None
        if isinstance(parsed, (dict, list)):
            return parsed
        return None

    def _display_value(self, value: Any) -> str:
        if value in (None, "", {}, []):
            return "—"
        return str(value)

    def _validate_payload(self, payload: AdjustmentRecordCreate) -> None:
        if payload.adjustment_type not in VALID_ADJUSTMENT_TYPES:
            raise ValueError(f"Unsupported adjustment type: {payload.adjustment_type}")
        if payload.region not in VALID_REGIONS:
            raise ValueError(f"Unsupported adjustment region: {payload.region}")
        if payload.item_count < 0 or payload.positive_count < 0 or payload.negative_count < 0:
            raise ValueError("Adjustment counts cannot be negative")
        if not isinstance(payload.record_snapshot, dict) or not isinstance(payload.summary_snapshot, dict):
            raise ValueError("Adjustment snapshots must be dictionaries")

    def _normalize_optional_type(self, adjustment_type: str | None) -> str | None:
        if adjustment_type in (None, "", "全部"):
            return None
        if adjustment_type not in VALID_ADJUSTMENT_TYPES and adjustment_type not in ADJUSTMENT_TYPE_GROUPS:
            raise ValueError(f"Unsupported adjustment type: {adjustment_type}")
        return adjustment_type

    def _normalize_optional_region(self, region: str | None) -> str | None:
        if region in (None, "", "全部"):
            return None
        if region not in {"澳门", "香港"}:
            raise ValueError(f"Unsupported adjustment region: {region}")
        return region

    def _validate_limit_offset(self, limit: int, offset: int) -> tuple[int, int]:
        if limit < 1:
            limit = 1
        if limit > 500:
            limit = 500
        if offset < 0:
            offset = 0
        return limit, offset

    def _to_result(self, record: AdjustmentRecord) -> AdjustmentRecordResult:
        return AdjustmentRecordResult(
            id=record.id,
            adjustment_type=record.adjustment_type,
            region=record.region,
            created_at=record.created_at,
            source_filter=record.source_filter if isinstance(record.source_filter, dict) else {},
            original_total=record.original_total,
            adjustment_total=record.adjustment_total,
            after_total=record.after_total,
            item_count=record.item_count,
            positive_count=record.positive_count,
            negative_count=record.negative_count,
            record_snapshot=record.record_snapshot if record.record_snapshot is not None else {},
            summary_snapshot=record.summary_snapshot if record.summary_snapshot is not None else {},
            note=record.note,
        )

    def _record_status(self, record: AdjustmentRecordResult) -> str:
        if record.adjustment_type in {"special_throw_reversal", "lianxiao_throw_reversal"}:
            return "reversal"
        if record.adjustment_type in {"special_throw", "lianxiao_throw"}:
            reversed_ids = {
                item.record_snapshot.get("reversed_record_id")
                for item in self.list_records(limit=500)
                if item.adjustment_type in {"special_throw_reversal", "lianxiao_throw_reversal"}
                and isinstance(item.record_snapshot, dict)
            }
            return "reversed" if record.id in reversed_ids else "active"
        return "legacy"
