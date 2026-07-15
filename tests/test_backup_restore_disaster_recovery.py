from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from core.config import DATABASE_PATH
from models import AdjustmentRecord, AppMeta
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.database_backup_service import DatabaseBackupError, DatabaseBackupService
from services.draw_service import DrawService
from services.log_service import LogService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService


EXPECTED_REVISION = "20260715_0010"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module", autouse=True)
def protect_real_database() -> None:
    real_database = DATABASE_PATH.resolve()
    before = _sha256(real_database)
    yield
    assert _sha256(real_database) == before


def _stamp_revision(session_factory, revision: str = EXPECTED_REVISION) -> None:
    engine = session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )


def _database_path(session_factory) -> Path:
    return Path(session_factory.kw["bind"].url.database).resolve()


def _make_service(session_factory, tmp_path: Path) -> DatabaseBackupService:
    return DatabaseBackupService(
        database_path=_database_path(session_factory),
        backup_dir=tmp_path / "backups",
        log_service=LogService(session_factory),
        connection_engine=session_factory.kw["bind"],
        expected_revision=EXPECTED_REVISION,
    )


def _seed_complete_business_state(session_factory) -> dict[str, int]:
    _stamp_revision(session_factory)
    settings = SettingsService(session_factory)
    plan = settings.ensure_default_plan()
    settings.add_item(plan.id, "特码", "2", "0")
    settings.add_declarer("灾备测试申报人", plan.id)

    draw = DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="DR-BASE-001",
            draw_date=date(2026, 7, 15),
            regular_numbers=["01", "02", "03", "04", "05", "06"],
            special_number="49",
        )
    )
    order = OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="灾备基线测试订单",
            source="disaster_recovery_test",
            customer_name="灾备测试申报人",
            zodiac_year=2026,
            items=[OrderItemCreate(bet_type="特码", selection="49", amount="10")],
        )
    )
    SettlementService(session_factory).commit_order_settlement(order.id, draw.id)

    with session_factory() as session:
        session.add(AppMeta(key="dr_marker", value="baseline"))
        session.add(
            AdjustmentRecord(
                adjustment_type="special",
                region="澳门",
                source_filter={"scope": "test"},
                original_total="10",
                adjustment_total="0",
                after_total="10",
                item_count=1,
                positive_count=0,
                negative_count=0,
                record_snapshot={"items": [{"selection": "49"}]},
                summary_snapshot={"total": "10"},
                note="disaster recovery fixture",
            )
        )
        session.commit()
    return {"order_id": order.id, "draw_id": draw.id}


def _create_mutation_order(session_factory) -> int:
    return OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="仅用于验证恢复回退的临时订单",
            source="disaster_recovery_test",
            zodiac_year=2026,
            items=[OrderItemCreate(bet_type="特码", selection="25", amount="7")],
        )
    ).id


def _query_count(database_path: Path, table: str) -> int:
    uri = f"file:{database_path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _assert_snapshots_readable(database_path: Path) -> None:
    uri = f"file:{database_path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        snapshots = connection.execute(
            "SELECT result_snapshot FROM settlement_records"
        ).fetchall()
        assert snapshots
        assert all(isinstance(json.loads(row[0]), dict) for row in snapshots)


def _business_counts(counts: dict[str, int]) -> dict[str, int]:
    return {key: value for key, value in counts.items() if key != "operation_logs"}


def test_normal_backup_is_nonempty_consistent_and_fully_readable(session_factory, tmp_path) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    source_before = service.inspect_database(service.database_path)

    backup = service.create_backup(reason="disaster_recovery_drill")
    inspected = service.inspect_database(backup.backup_path)

    assert backup.backup_path.exists() and backup.size_bytes > 0
    assert inspected.sha256 == _sha256(backup.backup_path)
    assert inspected.integrity_check == "ok"
    assert inspected.revision == EXPECTED_REVISION
    assert inspected.table_counts == source_before.table_counts
    assert inspected.json_value_count >= 3
    _assert_snapshots_readable(backup.backup_path)


def test_backup_names_are_unique_and_never_overwrite(session_factory, tmp_path) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)

    first = service.create_backup()
    second = service.create_backup()

    assert first.backup_path != second.backup_path
    assert first.backup_path.exists() and second.backup_path.exists()


def test_restore_returns_to_backup_state_and_pre_restore_backup_contains_mutation(
    session_factory,
    tmp_path,
) -> None:
    ids = _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    backup = service.create_backup(reason="restore_baseline")
    backup_state = service.inspect_database(backup.backup_path)
    mutation_order_id = _create_mutation_order(session_factory)
    assert OrderService(session_factory).get_order(mutation_order_id) is not None

    result = service.restore_backup(backup.backup_path, confirm=True)

    restored_state = service.inspect_database(service.database_path)
    pre_restore_state = service.inspect_database(result.pre_restore_backup_path)
    assert OrderService(session_factory).get_order(mutation_order_id) is None
    assert OrderService(session_factory).get_order(ids["order_id"]) is not None
    assert _business_counts(restored_state.table_counts) == _business_counts(
        backup_state.table_counts
    )
    assert restored_state.table_counts["operation_logs"] == (
        backup_state.table_counts["operation_logs"] + 1
    )
    assert pre_restore_state.table_counts["orders"] == backup_state.table_counts["orders"] + 1
    assert _query_count(result.pre_restore_backup_path, "orders") == 2
    assert restored_state.integrity_check == pre_restore_state.integrity_check == "ok"
    assert restored_state.revision == pre_restore_state.revision == EXPECTED_REVISION
    assert "重启软件" in result.message
    _assert_snapshots_readable(service.database_path)
    _assert_snapshots_readable(result.pre_restore_backup_path)

    settings = SettingsService(session_factory)
    assert settings.list_plans()
    assert settings.list_declarers()
    assert DrawService(session_factory).get_draw_by_id(ids["draw_id"]) is not None
    assert SettlementService(session_factory).get_settlement_record_by_order_id(
        ids["order_id"]
    ) is not None


@pytest.mark.parametrize(
    "filename,payload,error_text",
    [
        ("empty.db", b"", "文件为空"),
        ("random.db", os.urandom(256), "不是有效的 SQLite"),
        ("text.db", b"this is not sqlite", "不是有效的 SQLite"),
    ],
)
def test_empty_random_and_non_sqlite_files_are_rejected_without_business_data_loss(
    session_factory,
    tmp_path,
    caplog,
    filename: str,
    payload: bytes,
    error_text: str,
) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    before = service.inspect_database(service.database_path)
    before_sha256 = _sha256(service.database_path)
    invalid = tmp_path / filename
    invalid.write_bytes(payload)

    with pytest.raises(DatabaseBackupError, match=error_text):
        service.restore_backup(invalid, confirm=True)

    after = service.inspect_database(service.database_path)
    assert _business_counts(after.table_counts) == _business_counts(before.table_counts)
    assert after.integrity_check == "ok"
    assert _sha256(service.database_path) == before_sha256
    assert any("database_restore_failed" in record.getMessage() for record in caplog.records)


def test_database_missing_model_tables_is_rejected(session_factory, tmp_path) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    before = service.inspect_database(service.database_path)
    before_sha256 = _sha256(service.database_path)
    incomplete = tmp_path / "missing_tables.db"
    with closing(sqlite3.connect(incomplete)) as connection:
        connection.execute(
            "CREATE TABLE alembic_version (version_num TEXT NOT NULL PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO alembic_version VALUES (?)",
            (EXPECTED_REVISION,),
        )
        connection.commit()

    with pytest.raises(DatabaseBackupError, match="缺少关键表"):
        service.restore_backup(incomplete, confirm=True)

    assert _business_counts(service.inspect_database(service.database_path).table_counts) == (
        _business_counts(before.table_counts)
    )
    assert _sha256(service.database_path) == before_sha256


def test_wrong_or_unknown_revision_is_rejected(session_factory, tmp_path) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    valid = service.create_backup()
    before_sha256 = _sha256(service.database_path)
    wrong_revision = tmp_path / "wrong_revision.db"
    shutil.copy2(valid.backup_path, wrong_revision)
    with closing(sqlite3.connect(wrong_revision)) as connection:
        connection.execute("UPDATE alembic_version SET version_num='unknown_revision'")
        connection.commit()

    with pytest.raises(DatabaseBackupError, match="revision 不兼容"):
        service.restore_backup(wrong_revision, confirm=True)

    assert service.inspect_database(service.database_path).integrity_check == "ok"
    assert _sha256(service.database_path) == before_sha256


def test_integrity_check_failure_is_rejected(session_factory, tmp_path) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    valid = service.create_backup()
    before_sha256 = _sha256(service.database_path)
    corrupted = tmp_path / "corrupted.db"
    shutil.copy2(valid.backup_path, corrupted)
    data = bytearray(corrupted.read_bytes())
    assert len(data) > 8192
    data[4096:8192] = b"\xff" * 4096
    corrupted.write_bytes(data)

    with pytest.raises(DatabaseBackupError, match="integrity_check|无法打开"):
        service.restore_backup(corrupted, confirm=True)

    assert service.inspect_database(service.database_path).integrity_check == "ok"
    assert _sha256(service.database_path) == before_sha256


def test_atomic_replace_failure_keeps_current_database_and_cleans_temporary_files(
    session_factory,
    tmp_path,
) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    backup = service.create_backup()
    mutation_order_id = _create_mutation_order(session_factory)
    before = service.inspect_database(service.database_path)
    before_sha256 = _sha256(service.database_path)
    real_replace = os.replace

    def fail_target_replace(source, destination):
        if Path(destination).resolve() == service.database_path:
            raise OSError("simulated replace failure")
        return real_replace(source, destination)

    with patch("services.database_backup_service.os.replace", side_effect=fail_target_replace):
        with pytest.raises(DatabaseBackupError, match="原子替换失败"):
            service.restore_backup(backup.backup_path, confirm=True)

    after = service.inspect_database(service.database_path)
    assert OrderService(session_factory).get_order(mutation_order_id) is not None
    assert _business_counts(after.table_counts) == _business_counts(before.table_counts)
    assert _sha256(service.database_path) == before_sha256
    assert list(service.database_path.parent.glob(".fortune_restore_*.tmp")) == []
    assert list(service.backup_dir.glob(".fortune_snapshot_*.tmp")) == []
    assert any(
        path.name.startswith("fortune_before_restore_")
        for path in service.backup_dir.glob("*.db")
    )


def test_post_replace_validation_failure_rolls_back_pre_restore_database(
    session_factory,
    tmp_path,
) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    backup = service.create_backup()
    mutation_order_id = _create_mutation_order(session_factory)
    before = service.inspect_database(service.database_path)
    before_sha256 = _sha256(service.database_path)
    real_validate = service._validate_database
    target_validation_count = 0

    def fail_first_post_replace_validation(path, **kwargs):
        nonlocal target_validation_count
        if Path(path).resolve() == service.database_path:
            target_validation_count += 1
            if target_validation_count == 2:
                raise DatabaseBackupError("simulated post-replace validation failure")
        return real_validate(path, **kwargs)

    with patch.object(
        service,
        "_validate_database",
        side_effect=fail_first_post_replace_validation,
    ):
        with pytest.raises(DatabaseBackupError, match="回滚"):
            service.restore_backup(backup.backup_path, confirm=True)

    after = service.inspect_database(service.database_path)
    assert OrderService(session_factory).get_order(mutation_order_id) is not None
    assert _business_counts(after.table_counts) == _business_counts(before.table_counts)
    assert _sha256(service.database_path) == before_sha256
    assert after.integrity_check == "ok"
    assert list(service.database_path.parent.glob(".fortune_rollback_*.tmp")) == []


def test_unwritable_backup_target_is_rejected_and_failure_is_logged(
    session_factory,
    tmp_path,
    caplog,
) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    before = service.inspect_database(service.database_path)
    before_sha256 = _sha256(service.database_path)

    with patch.object(
        service,
        "_ensure_backup_directory",
        side_effect=DatabaseBackupError("备份目录不可写"),
    ):
        with pytest.raises(DatabaseBackupError, match="备份目录不可写"):
            service.create_backup()

    after = service.inspect_database(service.database_path)
    assert _business_counts(after.table_counts) == _business_counts(before.table_counts)
    assert _sha256(service.database_path) == before_sha256
    assert any("database_backup_failed" in record.getMessage() for record in caplog.records)


def test_current_database_cannot_be_used_as_restore_source(session_factory, tmp_path) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    before = service.inspect_database(service.database_path)
    before_sha256 = _sha256(service.database_path)

    with pytest.raises(DatabaseBackupError, match="不能是同一路径"):
        service.restore_backup(service.database_path, confirm=True)

    after = service.inspect_database(service.database_path)
    assert _business_counts(after.table_counts) == _business_counts(before.table_counts)
    assert after.integrity_check == "ok"
    assert _sha256(service.database_path) == before_sha256


def test_success_and_failure_logs_do_not_expose_full_database_paths(
    session_factory,
    tmp_path,
    caplog,
) -> None:
    _seed_complete_business_state(session_factory)
    service = _make_service(session_factory, tmp_path)
    backup = service.create_backup()
    backup_logs = LogService(session_factory).list_logs(module="database", limit=100)
    assert any(log.action == "backup" for log in backup_logs)
    assert all(str(service.database_path) not in log.description for log in backup_logs)
    assert all(str(service.backup_dir) not in log.description for log in backup_logs)

    service.restore_backup(backup.backup_path, confirm=True)
    invalid = tmp_path / "sensitive_source_name.db"
    invalid.write_bytes(b"bad")
    with pytest.raises(DatabaseBackupError):
        service.restore_backup(invalid, confirm=True)

    logs = LogService(session_factory).list_logs(module="database", limit=100)
    assert any(log.action == "restore" for log in logs)
    assert all(str(service.database_path) not in log.description for log in logs)
    assert all(str(service.backup_dir) not in log.description for log in logs)
    failure_messages = [
        record.getMessage()
        for record in caplog.records
        if "database_restore_failed" in record.getMessage()
    ]
    assert failure_messages
    assert all(str(service.database_path) not in message for message in failure_messages)
    assert all(str(service.backup_dir) not in message for message in failure_messages)
