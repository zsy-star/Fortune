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
