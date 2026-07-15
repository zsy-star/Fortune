"""Isolated post-build acceptance for a copied FORTUNE onedir release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_version import DATABASE_REVISION, RULESET_VERSION, VERSION
from core.database import initialize_database
from schemas.draw_schema import LotteryDrawCreate
from services.database_backup_service import DatabaseBackupError, DatabaseBackupService
from services.draw_service import DrawService
from services.log_service import LogService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from services.settlement_support_service import SettlementSupportService
from settlement.exceptions import SettlementDataError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_value(database: Path, sql: str):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(sql).fetchone()[0]


def _run_packaged_smoke(release_dir: Path, result_path: Path) -> dict:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["FORTUNE_SMOKE_RESULT"] = str(result_path)
    result_path.unlink(missing_ok=True)
    completed = subprocess.run(
        [str(release_dir / "FORTUNE.exe"), "--smoke-test"],
        cwd=release_dir,
        env=env,
        check=False,
        timeout=90,
    )
    if completed.returncode != 0 or not result_path.is_file():
        raise RuntimeError(f"发布EXE启动冒烟失败，退出码{completed.returncode}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def _session_factory(database: Path):
    engine = create_engine(
        f"sqlite:///{database.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine), engine


def _golden_cases():
    namespace = runpy.run_path(str(ROOT / "tests" / "test_v2_supported_plays_e2e.py"))
    return namespace["GOLDEN_ORDERS"]


def _exercise_business_and_backup(database: Path, release_dir: Path) -> dict:
    factory, engine = _session_factory(database)
    intake = OrderIntakeService(factory)
    settings = SettingsService(factory)

    missing = intake.parse_and_save(
        "特码49各10",
        region="澳门",
        source="release-missing-odds",
        zodiac_year=2026,
    )
    assert missing.success and missing.order is not None
    missing_draw = DrawService(factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="RC-MISSING-ODDS",
            draw_date=date(2026, 7, 15),
            regular_numbers=["01", "02", "03", "04", "05", "06"],
            special_number="49",
            source="release-acceptance",
        )
    )
    settlement = SettlementService(factory)
    assert settlement.preview_order(missing.order.id, missing_draw.id).settlement_ready is False
    try:
        settlement.commit_order_settlement(missing.order.id, missing_draw.id)
    except SettlementDataError:
        pass
    else:
        raise AssertionError("缺赔率订单未被正式结算门禁阻止")
    assert settlement.get_settlement_record_by_order_id(missing.order.id) is None

    plan = settings.ensure_default_plan()
    settings.add_declarer("RC验收申报人", plan.id)
    configured: set[str] = set()
    for case in _golden_cases():
        for key, odds, rebate in case.odds:
            if key not in configured:
                settings.add_item(plan.id, key, odds, rebate)
                configured.add(key)

    committed_orders: list[int] = []
    total_items = 0
    for case in _golden_cases():
        saved = intake.parse_and_save(
            case.text,
            customer_name="RC验收申报人",
            config_plan_name=plan.name,
            region=case.region,
            source="release-acceptance",
            zodiac_year=2026,
        )
        assert saved.success and saved.order is not None
        draw = DrawService(factory).create_draw(
            LotteryDrawCreate(
                region=case.region,
                issue_number=f"RC-{case.name}",
                draw_date=date(2026, 7, 15),
                regular_numbers=list(case.regular_numbers),
                special_number=case.special_number,
                source="release-acceptance",
            )
        )
        preview = settlement.preview_order(saved.order.id, draw.id)
        assert preview.settlement_ready is True
        committed = settlement.commit_order_settlement(saved.order.id, draw.id)
        assert committed.total_payout_amount == case.total_payout
        assert settlement.get_settlement_record_by_order_id(saved.order.id) is not None
        try:
            settlement.commit_order_settlement(saved.order.id, draw.id)
        except SettlementDataError:
            pass
        else:
            raise AssertionError("重复commit未被阻止")
        committed_orders.append(saved.order.id)
        saved_detail = OrderService(factory).get_order(saved.order.id)
        assert saved_detail is not None
        total_items += len(saved_detail.items)

    expanded = intake.parse_and_save(
        "家肖的大数各100\n野肖的小数各50",
        customer_name="RC验收申报人",
        config_plan_name=plan.name,
        region="澳门",
        source="release-acceptance",
        zodiac_year=2026,
    )
    assert expanded.success and expanded.order is not None
    expanded_detail = OrderService(factory).get_order(expanded.order.id)
    assert expanded_detail is not None
    assert len(expanded_detail.items) == 25
    assert str(expanded.order.total_amount) == "1900.00"

    blocked = (
        ("连肖复选", "兔,狗,虎,蛇,龙", "复选类型=复4"),
        ("几中几复选", "01,02,03,04", "复选类型=复3"),
        ("二中特", "01,02", None),
        ("二中特复选", "01,02,03", "复选类型=复2"),
        ("特串", "01,02", None),
        ("四肖", "鼠,虎,龙,猴", None),
        ("包半波", "红单", None),
        ("连尾", "1尾,2尾", None),
        ("正码特", "01", None),
        ("胆拖", "01,02,03", None),
    )
    assert all(
        not SettlementSupportService().check_item(bet_type, selection, note=note).is_supported
        for bet_type, selection, note in blocked
    )

    backup_service = DatabaseBackupService(
        database_path=database,
        backup_dir=release_dir / "data" / "backups",
        log_service=LogService(factory),
        connection_engine=engine,
        expected_revision=DATABASE_REVISION,
    )
    backup = backup_service.create_backup(reason="release_acceptance")
    assert backup.size_bytes > 0
    assert backup_service.inspect_database(backup.backup_path).integrity_check == "ok"
    order_count_before = _sqlite_value(database, "SELECT COUNT(*) FROM orders")
    mutation = intake.parse_and_save(
        "特码25各7",
        region="澳门",
        source="release-restore-mutation",
        zodiac_year=2026,
    )
    assert mutation.success and mutation.order is not None
    restored = backup_service.restore_backup(backup.backup_path, confirm=True)
    assert restored.pre_restore_backup_path.is_file()
    assert "重启软件" in restored.message
    assert _sqlite_value(database, "SELECT COUNT(*) FROM orders") == order_count_before
    assert OrderService(factory).get_order(mutation.order.id) is None

    invalid = release_dir / "empty_restore.db"
    invalid.write_bytes(b"")
    before_hash = _sha256(database)
    try:
        backup_service.restore_backup(invalid, confirm=True)
    except DatabaseBackupError:
        pass
    else:
        raise AssertionError("空恢复文件未被拒绝")
    finally:
        invalid.unlink(missing_ok=True)
    assert _sha256(database) == before_hash
    return {
        "golden_orders_committed": len(committed_orders),
        "golden_items": total_items,
        "domestic_wild_items": len(expanded_detail.items),
        "blocked_plays": len(blocked),
        "backup_integrity": "ok",
        "restore_pre_backup": restored.pre_restore_backup_path.name,
    }


def _exercise_upgrade(release_dir: Path, work_dir: Path) -> dict:
    internal = release_dir / "_internal"
    database = work_dir / "upgrade" / "fortune.db"
    backups = work_dir / "upgrade" / "backups"
    old = initialize_database(
        database,
        alembic_ini_path=internal / "alembic.ini",
        alembic_script_dir=internal / "alembic",
        backup_dir=backups,
        target_revision="20260705_0009",
    )
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO orders(order_no,region,source,raw_text,total_amount,status,zodiac_year) "
            "VALUES('RC-PKG-UP','澳门','upgrade','特码49各10',10,'active',2026)"
        )
        connection.commit()
    upgraded = initialize_database(
        database,
        alembic_ini_path=internal / "alembic.ini",
        alembic_script_dir=internal / "alembic",
        backup_dir=backups,
    )
    assert old.revision_after == "20260705_0009"
    assert upgraded.revision_after == DATABASE_REVISION
    assert upgraded.pre_migration_backup is not None
    assert _sqlite_value(database, "SELECT ruleset_version FROM orders") == RULESET_VERSION
    return {
        "from": old.revision_after,
        "to": upgraded.revision_after,
        "backup": upgraded.pre_migration_backup.name,
        "orders_preserved": _sqlite_value(database, "SELECT COUNT(*) FROM orders"),
    }


def run_acceptance(release_dir: Path, work_dir: Path) -> dict:
    release = release_dir.resolve()
    work = work_dir.resolve()
    if not (release / "FORTUNE.exe").is_file():
        raise RuntimeError("FORTUNE.exe不存在")
    if (release / "data" / "fortune.db").exists():
        raise RuntimeError("验收副本不是全新目录：已存在fortune.db")
    work.mkdir(parents=True, exist_ok=True)
    first = _run_packaged_smoke(release, work / "first_start.json")
    database = release / "data" / "fortune.db"
    assert database.is_file()
    assert Path(first["database_path"]).resolve() == database.resolve()
    assert first["version"] == VERSION
    assert first["database_revision"] == DATABASE_REVISION
    assert first["page_count"] >= 10
    assert _sqlite_value(database, "PRAGMA integrity_check") == "ok"
    assert _sqlite_value(database, "SELECT version_num FROM alembic_version") == DATABASE_REVISION
    assert _sqlite_value(database, "SELECT COUNT(*) FROM orders") == 0

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("INSERT INTO app_meta(key,value) VALUES('second_start_marker','keep')")
        connection.commit()
    second = _run_packaged_smoke(release, work / "second_start.json")
    assert second["database_created"] is False
    assert _sqlite_value(database, "SELECT COUNT(*) FROM app_meta WHERE key='second_start_marker'") == 1

    return {
        "packaged_start": {
            "first": first,
            "second_database_created": second["database_created"],
            "integrity_check": "ok",
        },
        "business": _exercise_business_and_backup(database, release),
        "upgrade": _exercise_upgrade(release, work),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验收隔离目录中的FORTUNE发布副本")
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_acceptance(args.release_dir, args.work_dir)
    except Exception as exc:
        print(f"发布验收失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
