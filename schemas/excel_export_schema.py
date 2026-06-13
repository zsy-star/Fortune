"""DTOs for Excel export service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExcelExportResult:
    export_path: Path
    file_name: str
    report_type: str
    row_count: int
    created_at: datetime
    size_bytes: int
    filters: dict[str, Any]
