from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from app_version import DATABASE_REVISION, RULESET_VERSION
from core.database import initialize_database
from scripts.runtime_init import ensure_runtime_directories


def _initialize(path: Path, tmp_path: Path, revision: str = DATABASE_REVISION):
    return initialize_database(
        path,
        alembic_ini_path=Path("alembic.ini"),
        alembic_script_dir=Path("alembic"),
        backup_dir=tmp_path / "backups",
        target_revision=revision,
    )


def _scalar(path: Path, sql: str):
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(sql).fetchone()[0]


def test_first_start_creates_empty_database_at_head_and_runtime_directories(tmp_path) -> None:
    app_root = tmp_path / "fresh_release"
    created = ensure_runtime_directories(app_root)
    assert {path.relative_to(app_root).as_posix() for path in created} == {
        "data",
        "data/backups",
        "exports",
        "logs",
    }
    database = app_root / "data" / "fortune.db"
    result = _initialize(database, app_root)
    assert result.created is True
    assert result.revision_after == DATABASE_REVISION
    assert _scalar(database, "PRAGMA integrity_check") == "ok"
    for table in ("orders", "order_items", "lottery_draws", "settlement_records"):
        assert _scalar(database, f'SELECT COUNT(*) FROM "{table}"') == 0


def test_second_start_preserves_existing_data_and_does_not_create_upgrade_backup(tmp_path) -> None:
    database = tmp_path / "data" / "fortune.db"
    first = _initialize(database, tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("INSERT INTO app_meta(key, value) VALUES('release_marker', 'keep')")
        connection.commit()
    second = _initialize(database, tmp_path)
    assert first.created is True
    assert second.created is False
    assert second.revision_before == DATABASE_REVISION
    assert second.pre_migration_backup is None
    assert _scalar(database, "SELECT COUNT(*) FROM app_meta WHERE key='release_marker' AND value='keep'") == 1


def test_revision_0009_upgrades_to_head_and_preserves_business_rows(tmp_path) -> None:
    database = tmp_path / "upgrade" / "fortune.db"
    old = _initialize(database, tmp_path, revision="20260705_0009")
    assert old.revision_after == "20260705_0009"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO orders(order_no,region,source,raw_text,total_amount,status,zodiac_year) "
            "VALUES('RC-UP-1','澳门','upgrade-test','特码49各10',10,'active',2026)"
        )
        connection.execute(
            "INSERT INTO lottery_draws(region,issue_number,draw_date,regular_numbers,special_number,status) "
            "VALUES('澳门','RC-UP-DRAW','2026-07-15','[\"01\",\"02\",\"03\",\"04\",\"05\",\"06\"]','49','active')"
        )
        connection.execute("INSERT INTO odds_rebate_plans(name,is_default) VALUES('升级保留方案',1)")
        connection.execute(
            "INSERT INTO odds_rebate_items(plan_id,bet_type,odds,rebate) VALUES(1,'特码',2,0)"
        )
        connection.execute("INSERT INTO declarer_settings(name,plan_id) VALUES('升级申报人',1)")
        connection.execute(
            "INSERT INTO settlement_records(order_id,draw_id,region,issue_number,total_items,hit_count,"
            "miss_count,unsupported_count,total_amount,result_snapshot) "
            "VALUES(1,1,'澳门','RC-UP-DRAW',1,1,0,0,10,'{\"upgrade\":true}')"
        )
        connection.commit()

    upgraded = _initialize(database, tmp_path)
    assert upgraded.revision_before == "20260705_0009"
    assert upgraded.revision_after == DATABASE_REVISION
    assert upgraded.pre_migration_backup is not None
    assert upgraded.pre_migration_backup.exists()
    assert _scalar(upgraded.pre_migration_backup, "PRAGMA integrity_check") == "ok"
    for table in ("orders", "lottery_draws", "odds_rebate_items", "declarer_settings", "settlement_records"):
        assert _scalar(database, f'SELECT COUNT(*) FROM "{table}"') == 1
    assert _scalar(database, "SELECT ruleset_version FROM orders WHERE order_no='RC-UP-1'") == RULESET_VERSION

