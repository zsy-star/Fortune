from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.database_backup_service import DatabaseBackupError, DatabaseBackupService
from services.log_service import LogService
from services.order_service import OrderService


def db_path_from_factory(session_factory) -> Path:
    return Path(session_factory.kw["bind"].url.database)


def create_order(order_service: OrderService, raw_text: str):
    return order_service.create_order(
        OrderCreate(
            region="澳门",
            raw_text=raw_text,
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )


def make_service(session_factory, tmp_path) -> DatabaseBackupService:
    with session_factory.kw["bind"].begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260715_0010')")
        )
    return DatabaseBackupService(
        database_path=db_path_from_factory(session_factory),
        backup_dir=tmp_path / "backups",
        log_service=LogService(session_factory),
        connection_engine=session_factory.kw["bind"],
        expected_revision="20260715_0010",
    )


def order_count(session_factory) -> int:
    return OrderService(session_factory).count_orders()


def backup_log_count(session_factory) -> int:
    return sum(
        log.action == "backup"
        for log in LogService(session_factory).list_logs(module="database", limit=500)
    )


def restore_log_count(session_factory) -> int:
    return sum(
        log.action == "restore"
        for log in LogService(session_factory).list_logs(module="database", limit=500)
    )


def test_create_backup_missing_database_fails(tmp_path, session_factory) -> None:
    service = DatabaseBackupService(
        database_path=tmp_path / "missing.db",
        backup_dir=tmp_path / "backups",
        log_service=LogService(session_factory),
    )

    with pytest.raises(DatabaseBackupError, match="数据库文件不存在"):
        service.create_backup()

    assert backup_log_count(session_factory) == 0


def test_create_backup_file_with_timestamp_size_and_log(tmp_path, session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, "backup source")
    service = make_service(session_factory, tmp_path)

    info = service.create_backup(reason="manual test")

    assert info.backup_path.exists()
    assert info.backup_name.startswith("fortune_backup_")
    assert info.backup_name.endswith(".db")
    assert info.size_bytes > 0
    assert info.reason == "manual test"
    assert info.backup_path.parent == tmp_path / "backups"
    assert backup_log_count(session_factory) == 1
    logs = LogService(session_factory).list_logs(module="database", action="backup")
    assert info.backup_name in logs[0].description
    assert "manual test" in logs[0].description


def test_backup_names_do_not_overwrite_and_list_backups(tmp_path, session_factory) -> None:
    create_order(OrderService(session_factory), "first backup")
    service = make_service(session_factory, tmp_path)

    first = service.create_backup(reason="first")
    second = service.create_backup(reason="second")
    listed = service.list_backups()

    assert first.backup_path.exists()
    assert second.backup_path.exists()
    assert first.backup_path != second.backup_path
    assert {first.backup_name, second.backup_name}.issubset({item.backup_name for item in listed})
    assert service.get_backup_info(first.backup_name).size_bytes == first.size_bytes


def test_restore_requires_confirm(tmp_path, session_factory) -> None:
    create_order(OrderService(session_factory), "restore confirm")
    service = make_service(session_factory, tmp_path)
    backup = service.create_backup()

    with pytest.raises(DatabaseBackupError, match="confirm=True"):
        service.restore_backup(backup.backup_name, confirm=False)


def test_restore_creates_pre_restore_backup_and_restores_database(tmp_path, session_factory) -> None:
    order_service = OrderService(session_factory)
    original = create_order(order_service, "original before backup")
    service = make_service(session_factory, tmp_path)
    backup = service.create_backup(reason="before mutation")
    mutated = create_order(order_service, "after backup mutation")
    assert order_count(session_factory) == 2

    result = service.restore_backup(backup.backup_name, confirm=True)

    assert result.restored_from == backup.backup_path
    assert result.database_path == db_path_from_factory(session_factory)
    assert result.pre_restore_backup_path.exists()
    assert result.pre_restore_backup_path.name.startswith("fortune_before_restore_")
    assert result.size_bytes > 0
    assert "重启软件" in result.message
    assert OrderService(session_factory).get_order(original.id) is not None
    assert OrderService(session_factory).get_order(mutated.id) is None


def test_restore_missing_or_empty_backup_fails(tmp_path, session_factory) -> None:
    create_order(OrderService(session_factory), "restore invalid")
    service = make_service(session_factory, tmp_path)

    with pytest.raises(DatabaseBackupError, match="备份文件不存在"):
        service.restore_backup("missing.db", confirm=True)

    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    with pytest.raises(DatabaseBackupError, match="备份文件为空"):
        service.restore_backup(empty, confirm=True)

    assert restore_log_count(session_factory) == 0


def test_restore_success_writes_log(tmp_path, session_factory) -> None:
    create_order(OrderService(session_factory), "restore log")
    service = make_service(session_factory, tmp_path)
    backup = service.create_backup()

    result = service.restore_backup(backup.backup_name, confirm=True)

    assert restore_log_count(session_factory) == 1
    logs = LogService(session_factory).list_logs(module="database", action="restore")
    assert result.restored_from.name in logs[0].description
    assert result.pre_restore_backup_path.name in logs[0].description
    assert str(result.restored_from.parent) not in logs[0].description
    assert str(result.database_path) not in logs[0].description


def test_restore_copy_failure_keeps_database_and_pre_restore_backup(tmp_path, session_factory) -> None:
    order_service = OrderService(session_factory)
    create_order(order_service, "safe original")
    service = make_service(session_factory, tmp_path)
    backup = service.create_backup()
    create_order(order_service, "safe mutation")
    database_path = db_path_from_factory(session_factory)
    original_bytes = database_path.read_bytes()
    real_replace = __import__("os").replace

    def fail_restore_replace(src, dst, *args, **kwargs):
        dst_path = Path(dst)
        if dst_path.resolve() == database_path.resolve():
            raise OSError("replace failed")
        return real_replace(src, dst, *args, **kwargs)

    with patch("services.database_backup_service.os.replace", side_effect=fail_restore_replace):
        with pytest.raises(DatabaseBackupError, match="原子替换失败"):
            service.restore_backup(backup.backup_name, confirm=True)

    assert database_path.read_bytes() == original_bytes
    assert any(
        path.name.startswith("fortune_before_restore_")
        for path in service.backup_dir.glob("*.db")
    )
    assert order_count(session_factory) == 2
    assert restore_log_count(session_factory) == 0


def test_service_uses_temp_database_not_real_fortune_db(tmp_path, session_factory) -> None:
    service = make_service(session_factory, tmp_path)

    assert service.database_path == db_path_from_factory(session_factory)
    assert "data/fortune.db" not in service.database_path.as_posix()
    assert "data/backups" not in service.backup_dir.as_posix()
