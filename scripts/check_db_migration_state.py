"""Read-only database migration state checker.

This script never stamps, upgrades, creates, or modifies the target database.
It reports the current alembic_version, the current Alembic head, key table
presence, and whether the database looks structurally ahead of its stamped
version.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

KEY_TABLES = (
    "app_meta",
    "orders",
    "order_items",
    "lottery_draws",
    "operation_logs",
    "settlement_records",
    "odds_rebate_plans",
    "odds_rebate_items",
    "declarer_settings",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def alembic_head(repo_root: Path | None = None) -> str:
    root = repo_root or _repo_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("path_separator", "os")
    return ScriptDirectory.from_config(config).get_current_head()


def inspect_database(db_path: Path, *, repo_root: Path | None = None) -> dict[str, object]:
    db_path = db_path.resolve()
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
        if "alembic_version" in tables:
            versions = [
                row[0]
                for row in connection.execute(
                    "select version_num from alembic_version order by version_num"
                ).fetchall()
            ]
        else:
            versions = []

    head = alembic_head(repo_root)
    missing_tables = [table for table in KEY_TABLES if table not in tables]
    current_version = versions[-1] if versions else None
    structurally_ahead = bool(current_version and current_version != head and not missing_tables)
    return {
        "database_path": str(db_path),
        "current_version": current_version,
        "all_versions": versions,
        "head": head,
        "key_tables": list(KEY_TABLES),
        "missing_tables": missing_tables,
        "structurally_ahead": structurally_ahead,
    }


def format_report(state: dict[str, object]) -> str:
    current_version = state["current_version"] or "<missing>"
    missing_tables = state["missing_tables"]
    lines = [
        f"Database: {state['database_path']}",
        f"Current alembic_version: {current_version}",
        f"Current Alembic head: {state['head']}",
        "Key tables:",
    ]
    missing = set(missing_tables)
    for table in state["key_tables"]:  # type: ignore[assignment]
        status = "missing" if table in missing else "present"
        lines.append(f"  - {table}: {status}")
    if state["structurally_ahead"]:
        lines.extend(
            [
                "",
                "Warning: key tables are present but alembic_version is behind head.",
                "Suggested safe handling:",
                "  1. Back up the database first.",
                "  2. Run this read-only check and verify key tables/columns manually.",
                "  3. If the schema matches head, manually run: alembic stamp head",
                "This script will not stamp, upgrade, or modify the database.",
            ]
        )
    elif missing_tables:
        lines.extend(
            [
                "",
                "Warning: some key tables are missing. Do not stamp head until the schema is verified.",
            ]
        )
    else:
        lines.append("")
        lines.append("Schema key-table check passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Fortune database migration checker.")
    parser.add_argument(
        "database",
        nargs="?",
        default=str(_repo_root() / "data" / "fortune.db"),
        help="SQLite database path to inspect in read-only mode.",
    )
    args = parser.parse_args(argv)
    state = inspect_database(Path(args.database))
    print(format_report(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
