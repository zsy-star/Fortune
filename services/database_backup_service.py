"""Backend service for SQLite database backup and restore."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from core.config import DATA_DIR, DATABASE_PATH
from schemas.database_backup_schema import DatabaseBackupInfo, DatabaseRestoreResult
from services.log_service import LogService


class DatabaseBackupError(RuntimeError):
    """Raised when a database backup or restore operation is unsafe or failed."""


class DatabaseBackupService:
    def __init__(
        self,
        *,
        database_path: str | Path = DATABASE_PATH,
        backup_dir: str | Path | None = None,
        log_service: LogService | None = None,
    ):
        self._database_path = Path(database_path)
        self._backup_dir = Path(backup_dir) if backup_dir is not None else DATA_DIR / "backups"
        self._log_service = log_service or LogService()

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def backup_dir(self) -> Path:
        return self._backup_dir

    def create_backup(self, reason: str | None = None) -> DatabaseBackupInfo:
        self._ensure_database_can_be_copied()
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now()
        backup_path = self._unique_backup_path("fortune_backup", created_at)
        self._copy_database_to_backup(backup_path)
        info = self._backup_info(backup_path, reason=reason, created_at=created_at)
        self._write_log(
            action="backup",
            description=(
                f"数据库备份成功：文件={info.backup_name}，路径={info.backup_path}，"
                f"大小={info.size_bytes}，原因={reason or '-'}"
            ),
        )
        return info

    def list_backups(self) -> list[DatabaseBackupInfo]:
        if not self._backup_dir.exists():
            return []
        rows = []
        for path in self._backup_dir.glob("*.db"):
            if path.is_file():
                rows.append(self._backup_info(path))
        return sorted(rows, key=lambda item: (item.created_at, item.backup_name), reverse=True)

    def get_backup_info(self, backup_name_or_path: str | Path) -> DatabaseBackupInfo:
        path = self._resolve_backup_path(backup_name_or_path)
        self._ensure_backup_file(path)
        return self._backup_info(path)

    def restore_backup(self, backup_name_or_path: str | Path, *, confirm: bool = False) -> DatabaseRestoreResult:
        if not confirm:
            raise DatabaseBackupError("恢复数据库需要 confirm=True")

        source = self._resolve_backup_path(backup_name_or_path)
        self._ensure_backup_file(source)
        self._ensure_database_can_be_copied()
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        restored_at = datetime.now()
        pre_restore_backup_path = self._unique_backup_path("fortune_before_restore", restored_at)
        self._copy_database_to_backup(pre_restore_backup_path)

        try:
            shutil.copy2(source, self._database_path)
        except Exception as exc:
            raise DatabaseBackupError(
                f"恢复失败，已保留恢复前备份：{pre_restore_backup_path}，错误：{exc}"
            ) from exc

        size_bytes = self._database_path.stat().st_size
        if size_bytes <= 0:
            raise DatabaseBackupError(f"恢复失败：恢复后的数据库为空，恢复前备份保留在 {pre_restore_backup_path}")

        result = DatabaseRestoreResult(
            restored_from=source,
            database_path=self._database_path,
            pre_restore_backup_path=pre_restore_backup_path,
            restored_at=restored_at,
            size_bytes=size_bytes,
            message="恢复已完成，建议重启软件后继续使用",
        )
        self._write_log(
            action="restore",
            description=(
                f"数据库恢复成功：恢复来源={source}，数据库路径={self._database_path}，"
                f"恢复前自动备份={pre_restore_backup_path}，大小={size_bytes}"
            ),
        )
        return result

    def _ensure_database_can_be_copied(self) -> None:
        if not self._database_path.exists():
            raise DatabaseBackupError(f"数据库文件不存在：{self._database_path}")
        if not self._database_path.is_file():
            raise DatabaseBackupError(f"数据库路径不是文件：{self._database_path}")
        if self._database_path.stat().st_size <= 0:
            raise DatabaseBackupError(f"数据库文件为空：{self._database_path}")

    def _ensure_backup_file(self, path: Path) -> None:
        if not path.exists():
            raise DatabaseBackupError(f"备份文件不存在：{path}")
        if not path.is_file():
            raise DatabaseBackupError(f"备份路径不是文件：{path}")
        if path.stat().st_size <= 0:
            raise DatabaseBackupError(f"备份文件为空：{path}")

    def _unique_backup_path(self, prefix: str, moment: datetime) -> Path:
        timestamp = moment.strftime("%Y%m%d_%H%M%S")
        base = self._backup_dir / f"{prefix}_{timestamp}.db"
        if not base.exists():
            return base
        for index in range(1, 1000):
            candidate = self._backup_dir / f"{prefix}_{timestamp}_{index:03d}.db"
            if not candidate.exists():
                return candidate
        raise DatabaseBackupError("无法生成不重复的备份文件名")

    def _copy_database_to_backup(self, backup_path: Path) -> None:
        if backup_path.exists():
            raise DatabaseBackupError(f"备份文件已存在，拒绝覆盖：{backup_path}")
        shutil.copy2(self._database_path, backup_path)
        if not backup_path.exists() or backup_path.stat().st_size <= 0:
            raise DatabaseBackupError(f"备份文件创建失败或为空：{backup_path}")

    def _resolve_backup_path(self, backup_name_or_path: str | Path) -> Path:
        path = Path(backup_name_or_path)
        if path.is_absolute() or path.parent != Path("."):
            return path
        return self._backup_dir / path

    def _backup_info(
        self,
        path: Path,
        *,
        reason: str | None = None,
        created_at: datetime | None = None,
    ) -> DatabaseBackupInfo:
        stat = path.stat()
        return DatabaseBackupInfo(
            backup_path=path,
            backup_name=path.name,
            created_at=created_at or datetime.fromtimestamp(stat.st_mtime),
            size_bytes=stat.st_size,
            reason=reason,
        )

    def _write_log(self, *, action: str, description: str) -> None:
        self._log_service.create_log(
            module="database",
            action=action,
            description=description,
            operator="system",
            related_type="database",
        )
