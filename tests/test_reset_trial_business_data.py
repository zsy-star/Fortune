from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from domain.play_rules import FORTUNE_RULESET_2026_V2
from models import (
    AdjustmentRecord,
    AppMeta,
    Base,
    DeclarerSetting,
    LotteryDraw,
    OddsRebateItem,
    OddsRebatePlan,
    OperationLog,
    Order,
    OrderItem,
    SettlementRecord,
)
from scripts.reset_trial_business_data import (
    TrialDataResetError,
    inspect_trial_business_data,
    reset_trial_business_data,
)


def _seed_trial_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "trial_reset.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "INSERT INTO alembic_version (version_num) VALUES ('20260715_0010')"
        )

    with Session(engine) as session:
        plan = OddsRebatePlan(name="保留方案", is_default=True)
        session.add(plan)
        session.flush()
        session.add(OddsRebateItem(plan_id=plan.id, bet_type="特码", odds="40", rebate="1"))
        session.add(DeclarerSetting(name="保留申报人", plan_id=plan.id))
        session.add(AppMeta(key="retained_setting", value="yes"))
        draw = LotteryDraw(
            region="澳门",
            issue_number="TRIAL-001",
            draw_date=date(2026, 7, 15),
            regular_numbers=["01", "02", "03", "04", "05", "06"],
            special_number="07",
            source="test",
            status="confirmed",
        )
        session.add(draw)
        session.flush()

        order = Order(
            order_no="ORD-TRIAL-001",
            region="澳门",
            source="test",
            raw_text="sensitive trial order text",
            total_amount="10",
            zodiac_year=2026,
            ruleset_version=FORTUNE_RULESET_2026_V2,
            status="settled",
        )
        session.add(order)
        session.flush()
        session.add(OrderItem(order_id=order.id, bet_type="特码", selection="07", amount="10"))

        business_log = OperationLog(
            module="settlement",
            action="commit",
            description="sensitive business log",
            related_type="order",
            related_id=order.id,
        )
        retained_log = OperationLog(
            module="settings",
            action="update",
            description="retained settings log",
            related_type="settings",
        )
        session.add_all([business_log, retained_log])
        session.flush()
        session.add(
            SettlementRecord(
                order_id=order.id,
                draw_id=draw.id,
                operation_log_id=business_log.id,
                region="澳门",
                issue_number=draw.issue_number,
                total_items=1,
                hit_count=1,
                miss_count=0,
                unsupported_count=0,
                total_amount="10",
                result_snapshot={"sensitive": "trial snapshot"},
            )
        )
        session.add(
            AdjustmentRecord(
                adjustment_type="special_throw",
                region="澳门",
                source_filter={"order_id": order.id},
                original_total="10",
                adjustment_total="-10",
                after_total="0",
                item_count=1,
                positive_count=0,
                negative_count=1,
                record_snapshot={"sensitive": "throw record"},
                summary_snapshot={"sensitive": "throw summary"},
            )
        )
        session.commit()
    engine.dispose()
    return database_path


def _table_count(database_path: Path, table: str) -> int:
    with sqlite3.connect(database_path) as connection:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def test_default_dry_run_reports_without_modifying_data(tmp_path: Path) -> None:
    database_path = _seed_trial_database(tmp_path)
    before_bytes = database_path.read_bytes()

    result = reset_trial_business_data(database_path)

    assert result.executed is False
    assert result.backup_path is None
    assert result.inspection.before_counts["orders"] == 1
    assert result.inspection.before_counts["order_items"] == 1
    assert result.inspection.before_counts["settlement_records"] == 1
    assert result.inspection.before_counts["adjustment_records"] == 1
    assert result.inspection.before_counts["operation_logs (business-related rows)"] == 1
    assert result.inspection.preserved_counts["declarer_settings"] == 1
    assert result.inspection.preserved_counts["lottery_draws"] == 1
    assert database_path.read_bytes() == before_bytes


def test_wrong_confirmation_phrase_refuses_execution_without_backup(tmp_path: Path) -> None:
    database_path = _seed_trial_database(tmp_path)
    backup_dir = tmp_path / "backups"

    with pytest.raises(TrialDataResetError, match="确认短语不正确"):
        reset_trial_business_data(
            database_path,
            execute=True,
            confirm="RESET_DATA",
            backup_dir=backup_dir,
        )

    assert not backup_dir.exists()
    assert _table_count(database_path, "orders") == 1


def test_execute_creates_backup_cleans_business_and_preserves_configuration(tmp_path: Path) -> None:
    database_path = _seed_trial_database(tmp_path)
    before = inspect_trial_business_data(database_path)

    result = reset_trial_business_data(
        database_path,
        execute=True,
        confirm="RESET_TRIAL_DATA",
        backup_dir=tmp_path / "backups",
    )

    assert result.executed is True
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert result.backup_path.stat().st_size > 0
    assert _table_count(result.backup_path, "orders") == 1
    assert all(count == 0 for count in result.after_counts.values())
    assert result.preserved_after_counts == before.preserved_counts
    assert _table_count(database_path, "orders") == 0
    assert _table_count(database_path, "order_items") == 0
    assert _table_count(database_path, "settlement_records") == 0
    assert _table_count(database_path, "adjustment_records") == 0
    assert _table_count(database_path, "declarer_settings") == 1
    assert _table_count(database_path, "odds_rebate_plans") == 1
    assert _table_count(database_path, "odds_rebate_items") == 1
    assert _table_count(database_path, "app_meta") == 1
    assert _table_count(database_path, "lottery_draws") == 1
    assert _table_count(database_path, "alembic_version") == 1

    with sqlite3.connect(database_path) as connection:
        logs = connection.execute(
            "SELECT module, action, description FROM operation_logs ORDER BY id"
        ).fetchall()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert [(row[0], row[1]) for row in logs] == [
        ("settings", "update"),
        ("maintenance", "trial_data_reset"),
    ]
    assert "sensitive trial order text" not in logs[-1][2]
    assert foreign_key_errors == []


def test_failure_rolls_back_entire_cleanup_transaction(tmp_path: Path) -> None:
    database_path = _seed_trial_database(tmp_path)
    before = inspect_trial_business_data(database_path)

    def fail_after_first_delete(_connection: sqlite3.Connection, table: str) -> None:
        if table == before.delete_order[0]:
            raise RuntimeError("injected reset failure")

    with pytest.raises(RuntimeError, match="injected reset failure"):
        reset_trial_business_data(
            database_path,
            execute=True,
            confirm="RESET_TRIAL_DATA",
            backup_dir=tmp_path / "backups",
            failure_hook=fail_after_first_delete,
        )

    after = inspect_trial_business_data(database_path)
    assert after.before_counts == before.before_counts
    assert after.preserved_counts == before.preserved_counts
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1

