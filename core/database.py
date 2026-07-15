"""Database engine and safe Alembic-backed runtime initialization."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app_version import DATABASE_REVISION
from core.config import (
    ALEMBIC_INI_PATH,
    ALEMBIC_SCRIPT_DIR,
    BACKUP_DIR,
    DATABASE_PATH,
    DATABASE_URL,
)


engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@dataclass(frozen=True, slots=True)
class DatabaseInitializationResult:
    database_path: Path
    created: bool
    revision_before: str | None
    revision_after: str
    pre_migration_backup: Path | None


def _revision(database_path: Path) -> str | None:
    if not database_path.is_file() or database_path.stat().st_size == 0:
        return None
    uri = f"file:{database_path.as_posix()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone() is None:
                return None
            row = connection.execute(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            ).fetchone()
            return str(row[0]) if row else None
    except sqlite3.DatabaseError:
        return None


def _backup_before_migration(database_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = backup_dir / f"fortune_before_migration_{timestamp}.db"
    temporary = destination.with_suffix(".tmp")
    source_uri = f"file:{database_path.as_posix()}?mode=ro"
    try:
        with closing(sqlite3.connect(source_uri, uri=True, timeout=10)) as source:
            with closing(sqlite3.connect(temporary, timeout=10)) as target:
                source.backup(target)
                target.commit()
        with closing(sqlite3.connect(temporary, timeout=10)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("迁移前数据库备份完整性检查失败")
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def _restore_failed_migration(database_path: Path, backup_path: Path) -> None:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=".fortune_migration_rollback_",
        suffix=".tmp",
        dir=database_path.parent,
    )
    os.close(descriptor)
    temporary = Path(raw_path)
    try:
        shutil.copy2(backup_path, temporary)
        os.replace(temporary, database_path)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_database(
    database_path: str | Path,
    *,
    alembic_ini_path: str | Path,
    alembic_script_dir: str | Path,
    backup_dir: str | Path,
    target_revision: str = DATABASE_REVISION,
) -> DatabaseInitializationResult:
    """Create or upgrade one database through real Alembic migrations."""

    path = Path(database_path).resolve()
    ini_path = Path(alembic_ini_path).resolve()
    script_dir = Path(alembic_script_dir).resolve()
    backups = Path(backup_dir).resolve()
    if not ini_path.is_file() or not script_dir.is_dir():
        raise RuntimeError("Alembic发布资源缺失，无法安全初始化数据库")

    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.is_file() and path.stat().st_size > 0
    revision_before = _revision(path)
    pre_migration_backup = None
    if existed and revision_before != target_revision:
        pre_migration_backup = _backup_before_migration(path, backups)

    config = Config(str(ini_path))
    config.set_main_option("script_location", str(script_dir))
    config.set_main_option("path_separator", "os")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    try:
        command.upgrade(config, target_revision)
        revision_after = _revision(path)
        if revision_after != target_revision:
            raise RuntimeError(
                f"数据库迁移未达到目标revision：{revision_after or '未设置'}"
            )
    except Exception:
        if pre_migration_backup is not None:
            _restore_failed_migration(path, pre_migration_backup)
        elif not existed:
            path.unlink(missing_ok=True)
        raise

    return DatabaseInitializationResult(
        database_path=path,
        created=not existed,
        revision_before=revision_before,
        revision_after=revision_after,
        pre_migration_backup=pre_migration_backup,
    )


def init_db() -> DatabaseInitializationResult:
    engine.dispose()
    return initialize_database(
        DATABASE_PATH,
        alembic_ini_path=ALEMBIC_INI_PATH,
        alembic_script_dir=ALEMBIC_SCRIPT_DIR,
        backup_dir=BACKUP_DIR,
    )


def get_session():
    """Return a new SQLAlchemy session; the caller is responsible for closing it."""

    return SessionLocal()
