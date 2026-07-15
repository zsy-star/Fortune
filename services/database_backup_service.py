"""Validated, atomic SQLite database backup and restore service."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import JSON
from sqlalchemy.engine import Engine
from sqlalchemy.orm import close_all_sessions

from core.config import BASE_DIR, DATA_DIR, DATABASE_PATH
from core.database import engine as application_engine
from models import Base
from schemas.database_backup_schema import (
    DatabaseBackupInfo,
    DatabaseRestoreResult,
    DatabaseValidationResult,
)
from services.log_service import LogService


class DatabaseBackupError(RuntimeError):
    """Raised when a database backup or restore operation is unsafe or failed."""


_MODEL_TABLES = tuple(sorted(Base.metadata.tables))
_REQUIRED_TABLES = frozenset((*_MODEL_TABLES, "alembic_version"))
_EXPECTED_COLUMNS = {
    table.name: frozenset(column.name for column in table.columns)
    for table in Base.metadata.sorted_tables
}
_JSON_COLUMNS = tuple(
    (table.name, column.name)
    for table in Base.metadata.sorted_tables
    for column in table.columns
    if isinstance(column.type, JSON)
)


def _code_alembic_head() -> str:
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "alembic"))
    config.set_main_option("path_separator", "os")
    head = ScriptDirectory.from_config(config).get_current_head()
    if not head:
        raise DatabaseBackupError("无法确定代码 Alembic head")
    return str(head)


class DatabaseBackupService:
    def __init__(
        self,
        *,
        database_path: str | Path = DATABASE_PATH,
        backup_dir: str | Path | None = None,
        log_service: LogService | None = None,
        connection_engine: Engine | None = None,
        expected_revision: str | None = None,
    ):
        self._database_path = Path(database_path).resolve()
        self._backup_dir = (
            Path(backup_dir).resolve()
            if backup_dir is not None
            else (DATA_DIR / "backups").resolve()
        )
        self._log_service = log_service or LogService()
        self._connection_engine = connection_engine
        if self._connection_engine is None and self._database_path == DATABASE_PATH.resolve():
            self._connection_engine = application_engine
        self._expected_revision = str(expected_revision or _code_alembic_head())

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def backup_dir(self) -> Path:
        return self._backup_dir

    @property
    def expected_revision(self) -> str:
        return self._expected_revision

    def inspect_database(self, database_path: str | Path) -> DatabaseValidationResult:
        """Validate a database without mutating it and return audit evidence."""
        return self._validate_database(Path(database_path).resolve())

    def create_backup(self, reason: str | None = None) -> DatabaseBackupInfo:
        created_at = datetime.now()
        backup_path: Path | None = None
        try:
            self._validate_database(self._database_path)
            self._ensure_backup_directory()
            backup_path = self._unique_backup_path("fortune_backup", created_at)
            self._create_validated_snapshot(self._database_path, backup_path)
            info = self._backup_info(backup_path, reason=reason, created_at=created_at)
            self._write_log(
                action="backup",
                description=(
                    f"数据库备份成功：文件={info.backup_name}，大小={info.size_bytes}，"
                    f"revision={self._expected_revision}，原因={reason or '-'}，result=success"
                ),
            )
            return info
        except DatabaseBackupError as exc:
            self._write_failure_log("backup", exc)
            raise
        except Exception as exc:
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)
            wrapped = DatabaseBackupError(f"数据库备份失败：{self._safe_error_text(exc)}")
            self._write_failure_log("backup", wrapped)
            raise wrapped from exc

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
        self._ensure_file(path, role="备份")
        return self._backup_info(path)

    def restore_backup(
        self,
        backup_name_or_path: str | Path,
        *,
        confirm: bool = False,
    ) -> DatabaseRestoreResult:
        if not confirm:
            raise DatabaseBackupError("恢复数据库需要 confirm=True")

        source: Path | None = None
        pre_restore_backup_path: Path | None = None
        staging_path: Path | None = None
        rollback_path: Path | None = None
        original_sha256: str | None = None
        restored_at = datetime.now()
        target_replaced = False
        rollback_completed = False
        try:
            source = self._resolve_backup_path(backup_name_or_path).resolve()
            if source == self._database_path:
                raise DatabaseBackupError("备份文件与当前数据库不能是同一路径")
            self._validate_database(source, role="备份")
            self._validate_database(self._database_path)
            self._ensure_backup_directory()

            pre_restore_backup_path = self._unique_backup_path(
                "fortune_before_restore",
                restored_at,
            )
            self._create_validated_snapshot(
                self._database_path,
                pre_restore_backup_path,
            )

            staging_path = self._temporary_path(self._database_path.parent, "restore")
            self._create_validated_snapshot(source, staging_path)
            self._prepare_connections_for_replace()
            original_sha256 = self._sha256(self._database_path)
            rollback_path = self._create_byte_exact_rollback_copy(original_sha256)
            try:
                os.replace(staging_path, self._database_path)
                target_replaced = True
                staging_path = None
            except Exception as exc:
                raise DatabaseBackupError(
                    f"恢复原子替换失败，原数据库保持不变：{self._safe_error_text(exc)}"
                ) from exc

            try:
                validation = self._validate_database(self._database_path)
            except Exception as validation_exc:
                self._rollback_from_byte_exact_copy(rollback_path, original_sha256)
                rollback_path = None
                rollback_completed = True
                raise DatabaseBackupError(
                    "恢复后的数据库校验失败，已按原文件字节回滚"
                ) from validation_exc

            self._dispose_connections()
            result = DatabaseRestoreResult(
                restored_from=source,
                database_path=self._database_path,
                pre_restore_backup_path=pre_restore_backup_path,
                restored_at=restored_at,
                size_bytes=validation.size_bytes,
                message="恢复已完成并通过完整性校验，请重启软件后继续使用",
            )
            self._write_log(
                action="restore",
                description=(
                    f"数据库恢复成功：来源文件={source.name}，"
                    f"恢复前备份={pre_restore_backup_path.name}，"
                    f"revision={validation.revision}，大小={validation.size_bytes}，result=success"
                ),
            )
            return result
        except DatabaseBackupError as exc:
            if target_replaced and not rollback_completed and rollback_path is not None:
                try:
                    self._rollback_from_byte_exact_copy(rollback_path, original_sha256)
                    rollback_path = None
                    rollback_completed = True
                except Exception as rollback_exc:
                    exc = DatabaseBackupError(
                        "恢复失败且自动回滚失败；原恢复前备份仍保留，请停止使用并人工恢复："
                        + self._safe_error_text(rollback_exc)
                    )
            self._dispose_connections()
            self._write_failure_log("restore", exc)
            raise exc
        except Exception as exc:
            self._dispose_connections()
            wrapped = DatabaseBackupError(f"恢复失败：{self._safe_error_text(exc)}")
            self._write_failure_log("restore", wrapped)
            raise wrapped from exc
        finally:
            if staging_path is not None:
                staging_path.unlink(missing_ok=True)
            if rollback_path is not None:
                rollback_path.unlink(missing_ok=True)

    def _validate_database(
        self,
        path: Path,
        *,
        role: str = "数据库",
    ) -> DatabaseValidationResult:
        self._ensure_file(path, role=role)
        try:
            with path.open("rb") as stream:
                if stream.read(16) != b"SQLite format 3\x00":
                    raise DatabaseBackupError(f"文件 {path.name} 不是有效的 SQLite 数据库")
        except OSError as exc:
            raise DatabaseBackupError(
                f"无法读取数据库文件 {path.name}：{self._safe_error_text(exc)}"
            ) from exc

        uri = f"file:{path.as_posix()}?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
                connection.execute("PRAGMA query_only = ON")
                integrity_rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
                if integrity_rows != ["ok"]:
                    raise DatabaseBackupError(
                        f"数据库 {path.name} integrity_check 失败"
                    )

                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                missing_tables = sorted(_REQUIRED_TABLES - tables)
                if missing_tables:
                    raise DatabaseBackupError(
                        f"数据库 {path.name} 缺少关键表：{','.join(missing_tables)}"
                    )

                for table_name, expected_columns in _EXPECTED_COLUMNS.items():
                    actual_columns = {
                        str(row[1])
                        for row in connection.execute(
                            f'PRAGMA table_info("{table_name}")'
                        )
                    }
                    missing_columns = sorted(expected_columns - actual_columns)
                    if missing_columns:
                        raise DatabaseBackupError(
                            f"数据库 {path.name} 的表 {table_name} 缺少字段："
                            + ",".join(missing_columns)
                        )

                versions = [
                    str(row[0])
                    for row in connection.execute(
                        "SELECT version_num FROM alembic_version ORDER BY version_num"
                    )
                ]
                if versions != [self._expected_revision]:
                    actual = ",".join(versions) if versions else "<missing>"
                    raise DatabaseBackupError(
                        f"数据库 revision 不兼容：当前={actual}，要求={self._expected_revision}"
                    )

                table_counts = {
                    table_name: int(
                        connection.execute(
                            f'SELECT COUNT(*) FROM "{table_name}"'
                        ).fetchone()[0]
                    )
                    for table_name in _MODEL_TABLES
                }
                json_value_count = self._validate_json_columns(connection)
        except DatabaseBackupError:
            raise
        except sqlite3.DatabaseError as exc:
            raise DatabaseBackupError(
                f"数据库 {path.name} 无法打开或 integrity_check 失败：{self._safe_error_text(exc)}"
            ) from exc

        return DatabaseValidationResult(
            sha256=self._sha256(path),
            size_bytes=path.stat().st_size,
            integrity_check="ok",
            revision=self._expected_revision,
            table_counts=table_counts,
            json_value_count=json_value_count,
        )

    def _validate_json_columns(self, connection: sqlite3.Connection) -> int:
        value_count = 0
        for table_name, column_name in _JSON_COLUMNS:
            rows = connection.execute(
                f'SELECT "{column_name}" FROM "{table_name}" '
                f'WHERE "{column_name}" IS NOT NULL'
            )
            for (raw_value,) in rows:
                try:
                    if isinstance(raw_value, (str, bytes, bytearray)):
                        json.loads(raw_value)
                    else:
                        json.loads(str(raw_value))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise DatabaseBackupError(
                        f"表 {table_name} 的 JSON 字段 {column_name} 无法读取"
                    ) from exc
                value_count += 1
        return value_count

    def _create_byte_exact_rollback_copy(self, expected_sha256: str) -> Path:
        rollback_path = self._temporary_path(self._database_path.parent, "rollback")
        try:
            shutil.copy2(self._database_path, rollback_path)
            with rollback_path.open("rb+") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            if self._sha256(rollback_path) != expected_sha256:
                raise DatabaseBackupError("恢复回滚副本 SHA-256 校验失败")
            self._validate_database(rollback_path)
            return rollback_path
        except Exception:
            rollback_path.unlink(missing_ok=True)
            raise

    def _rollback_from_byte_exact_copy(
        self,
        rollback_path: Path,
        expected_sha256: str | None,
    ) -> None:
        close_all_sessions()
        self._dispose_connections()
        for suffix in ("-wal", "-shm"):
            Path(str(self._database_path) + suffix).unlink(missing_ok=True)
        os.replace(rollback_path, self._database_path)
        if expected_sha256 is None or self._sha256(self._database_path) != expected_sha256:
            raise DatabaseBackupError("恢复回滚后的数据库 SHA-256 不一致")
        self._validate_database(self._database_path)

    def _create_validated_snapshot(self, source: Path, destination: Path) -> None:
        if source.resolve() == destination.resolve():
            raise DatabaseBackupError("备份源文件与目标文件不能是同一路径")
        if destination.exists():
            raise DatabaseBackupError(f"备份文件已存在，拒绝覆盖：{destination.name}")

        temporary = self._temporary_path(destination.parent, "snapshot")
        try:
            self._sqlite_backup(source, temporary)
            self._validate_database(temporary)
            os.replace(temporary, destination)
            self._validate_database(destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)

    def _sqlite_backup(self, source: Path, destination: Path) -> None:
        self._ensure_file(source, role="数据库")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_uri = f"file:{source.as_posix()}?mode=ro"
        try:
            with closing(
                sqlite3.connect(source_uri, uri=True, timeout=10)
            ) as source_connection:
                with closing(sqlite3.connect(destination, timeout=10)) as destination_connection:
                    source_connection.backup(destination_connection)
                    destination_connection.commit()
            if not destination.exists() or destination.stat().st_size <= 0:
                raise DatabaseBackupError("SQLite 备份未生成有效文件")
            with destination.open("rb+") as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def _prepare_connections_for_replace(self) -> None:
        close_all_sessions()
        self._dispose_connections()
        try:
            with closing(sqlite3.connect(self._database_path, timeout=10)) as connection:
                row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if row is not None and int(row[0]) != 0:
                    raise DatabaseBackupError("数据库仍有活动连接，无法安全恢复")
        except sqlite3.DatabaseError as exc:
            raise DatabaseBackupError(
                "无法释放数据库连接，恢复已取消：" + self._safe_error_text(exc)
            ) from exc
        self._dispose_connections()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self._database_path) + suffix)
            try:
                sidecar.unlink(missing_ok=True)
            except OSError as exc:
                raise DatabaseBackupError(
                    "数据库连接文件仍被占用，恢复已取消：" + self._safe_error_text(exc)
                ) from exc

    def _dispose_connections(self) -> None:
        if self._connection_engine is not None:
            self._connection_engine.dispose()

    def _ensure_backup_directory(self) -> None:
        try:
            self._backup_dir.mkdir(parents=True, exist_ok=True)
            probe = self._temporary_path(self._backup_dir, "write_probe")
            probe.write_bytes(b"ok")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise DatabaseBackupError(
                "备份目录不可写：" + self._safe_error_text(exc)
            ) from exc

    def _ensure_file(self, path: Path, *, role: str) -> None:
        if not path.exists():
            raise DatabaseBackupError(f"{role}文件不存在：{path.name}")
        if not path.is_file():
            raise DatabaseBackupError(f"{role}路径不是文件：{path.name}")
        if path.stat().st_size <= 0:
            raise DatabaseBackupError(f"{role}文件为空：{path.name}")

    def _unique_backup_path(self, prefix: str, moment: datetime) -> Path:
        timestamp = moment.strftime("%Y%m%d_%H%M%S_%f")
        base = self._backup_dir / f"{prefix}_{timestamp}.db"
        if not base.exists():
            return base
        for index in range(1, 1000):
            candidate = self._backup_dir / f"{prefix}_{timestamp}_{index:03d}.db"
            if not candidate.exists():
                return candidate
        raise DatabaseBackupError("无法生成不重复的备份文件名")

    def _temporary_path(self, directory: Path, purpose: str) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".fortune_{purpose}_",
            suffix=".tmp",
            dir=directory,
        )
        os.close(descriptor)
        path = Path(raw_path)
        path.unlink(missing_ok=True)
        return path

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

    def _write_failure_log(self, operation: str, exc: Exception) -> None:
        # A failed backup/restore must not mutate the live SQLite file merely to
        # record the failure; doing so would invalidate byte-for-byte rollback
        # evidence.  The application logger still records a non-sensitive audit
        # event without database paths, keys, or business content.
        logging.warning(
            "database_%s_failed error_type=%s result=failed",
            operation,
            type(exc).__name__,
        )

    def _write_log(self, *, action: str, description: str) -> None:
        self._log_service.create_log(
            module="database",
            action=action,
            description=description,
            operator="system",
            related_type="database",
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe_error_text(exc: Exception) -> str:
        if isinstance(exc, OSError) and exc.strerror:
            return str(exc.strerror)
        return type(exc).__name__
