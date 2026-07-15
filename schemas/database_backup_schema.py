"""DTOs for database backup and restore operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DatabaseBackupInfo:
    backup_path: Path
    backup_name: str
    created_at: datetime
    size_bytes: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DatabaseRestoreResult:
    restored_from: Path
    database_path: Path
    pre_restore_backup_path: Path
    restored_at: datetime
    size_bytes: int
    message: str


@dataclass(frozen=True, slots=True)
class DatabaseValidationResult:
    """Read-only validation evidence for one SQLite database file."""

    sha256: str
    size_bytes: int
    integrity_check: str
    revision: str
    table_counts: dict[str, int]
    json_value_count: int
