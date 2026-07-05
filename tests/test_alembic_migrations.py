from __future__ import annotations

import hashlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from models import Base
from scripts.check_db_migration_state import KEY_TABLES, inspect_database


REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(db_path: Path) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    config.set_main_option("path_separator", "os")
    return config


def _head(config: Config) -> str:
    return ScriptDirectory.from_config(config).get_current_head()


def test_alembic_upgrade_head_from_empty_sqlite_creates_current_key_tables(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "fortune_alembic.db"
    config = _alembic_config(db_path)
    monkeypatch.setenv("FORTUNE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert set(KEY_TABLES).issubset(tables)
        assert {"customer_accounts", "account_ledger_entries"}.isdisjoint(tables)
        assert {"odds_rebate_plans", "odds_rebate_items"}.issubset(tables)
        settlement_columns = {column["name"] for column in inspect(engine).get_columns("settlement_records")}
        assert {
            "payout_posted_at",
            "payout_ledger_entry_id",
            "payout_posted_amount",
        }.isdisjoint(settlement_columns)

        with engine.connect() as connection:
            version = connection.execute(text("select version_num from alembic_version")).scalar_one()
        assert version == _head(config)

        order_columns = {column["name"] for column in inspect(engine).get_columns("orders")}
        assert "zodiac_year" in order_columns
    finally:
        engine.dispose()


def test_add_zodiac_year_migration_keeps_existing_orders_and_amounts(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "fortune_existing_orders.db"
    config = _alembic_config(db_path)
    monkeypatch.setenv("FORTUNE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    command.upgrade(config, "20260702_0008")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into orders
                        (order_no, customer_name, channel, region, source, raw_text, total_amount, status)
                    values
                        ('ORD-LEGACY-001', 'legacy', 'test', '澳门', 'test', '01各10', 10.00, 'active')
                    """
                )
            )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            row = connection.execute(
                text("select order_no, total_amount, zodiac_year from orders where order_no = 'ORD-LEGACY-001'")
            ).one()
            version = connection.execute(text("select version_num from alembic_version")).scalar_one()
        assert row.order_no == "ORD-LEGACY-001"
        assert float(row.total_amount) == 10.0
        assert row.zodiac_year == 2026
        assert version == _head(config)
    finally:
        engine.dispose()


def test_app_meta_is_created_by_alembic_upgrade_head(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "fortune_alembic_app_meta.db"
    config = _alembic_config(db_path)
    monkeypatch.setenv("FORTUNE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert "app_meta" in tables
        assert "app_meta" in Base.metadata.tables
    finally:
        engine.dispose()


def test_alembic_head_contains_orm_key_tables() -> None:
    orm_tables = set(Base.metadata.tables)
    assert set(KEY_TABLES).issubset(orm_tables)
    assert {"customer_accounts", "account_ledger_entries"}.isdisjoint(orm_tables)
    assert {"odds_rebate_plans", "odds_rebate_items"}.issubset(orm_tables)


def test_read_only_migration_check_script_does_not_modify_database(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "fortune_lagged.db"
    config = _alembic_config(db_path)
    monkeypatch.setenv("FORTUNE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(text("update alembic_version set version_num = '20260612_0001'"))
    finally:
        engine.dispose()

    before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
    state = inspect_database(db_path, repo_root=REPO_ROOT)
    after_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()

    assert before_hash == after_hash
    assert state["current_version"] == "20260612_0001"
    assert state["head"] == _head(config)
    assert state["missing_tables"] == []
    assert state["structurally_ahead"] is True
