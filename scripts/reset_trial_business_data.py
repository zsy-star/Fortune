"""Guarded reset tool for disposable FORTUNE trial business data.

The default mode is read-only.  Execution requires both ``--execute`` and the
exact confirmation phrase ``RESET_TRIAL_DATA``.  The production database file
is never removed; a consistent SQLite backup is created before the deletion
transaction starts.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


CONFIRM_PHRASE = "RESET_TRIAL_DATA"
BASE_BUSINESS_TABLES = (
    "settlement_records",
    "order_items",
    "orders",
    "adjustment_records",
)
PRESERVED_TABLES = (
    "declarer_settings",
    "odds_rebate_items",
    "odds_rebate_plans",
    "app_meta",
    "lottery_draws",
    "alembic_version",
)
BUSINESS_LOG_RELATED_TYPES = (
    "order",
    "settlement",
    "settlement_record",
    "adjustment_record",
    "order_import",
    "split_order",
)
BUSINESS_LOG_MODULES = ("order", "settlement", "adjustment")


class TrialDataResetError(RuntimeError):
    """Raised when the trial reset cannot be performed safely."""


@dataclass(frozen=True, slots=True)
class TrialResetInspection:
    database_path: Path
    delete_order: tuple[str, ...]
    before_counts: dict[str, int]
    preserved_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class TrialResetResult:
    inspection: TrialResetInspection
    executed: bool
    backup_path: Path | None
    after_counts: dict[str, int]
    preserved_after_counts: dict[str, int]


FailureHook = Callable[[sqlite3.Connection, str], None]


def _quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise TrialDataResetError(f"非法SQLite标识符：{value!r}")
    return '"' + value.replace('"', '""') + '"'


def _connect(database_path: Path) -> sqlite3.Connection:
    if not database_path.exists() or not database_path.is_file():
        raise TrialDataResetError(f"数据库文件不存在：{database_path}")
    if database_path.stat().st_size <= 0:
        raise TrialDataResetError(f"数据库文件为空：{database_path}")
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    return {str(row[0]) for row in rows}


def _foreign_key_parents(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA foreign_key_list({_quote_identifier(table)})")
    return {str(row[2]) for row in rows}


def _business_tables(connection: sqlite3.Connection, tables: set[str]) -> set[str]:
    selected = {table for table in BASE_BUSINESS_TABLES if table in tables}
    if "orders" not in selected or "order_items" not in selected:
        raise TrialDataResetError("数据库缺少orders或order_items，拒绝猜测表结构")

    protected = set(PRESERVED_TABLES)
    changed = True
    while changed:
        changed = False
        for table in sorted(tables - selected - protected - {"operation_logs"}):
            if _foreign_key_parents(connection, table) & selected:
                selected.add(table)
                changed = True
    return selected


def _delete_order(connection: sqlite3.Connection, selected: set[str]) -> tuple[str, ...]:
    parents = {table: _foreign_key_parents(connection, table) & selected for table in selected}
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(table: str) -> None:
        if table in visited:
            return
        if table in visiting:
            raise TrialDataResetError("业务表外键存在循环，拒绝自动清理")
        visiting.add(table)
        children = sorted(child for child, child_parents in parents.items() if table in child_parents)
        for child in children:
            visit(child)
        visiting.remove(table)
        visited.add(table)
        ordered.append(table)

    for root in ("orders", "adjustment_records"):
        if root in selected:
            visit(root)
    for table in sorted(selected):
        visit(table)
    return tuple(ordered)


def _count_table(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()[0])


def _business_log_where() -> tuple[str, tuple[str, ...]]:
    related_placeholders = ",".join("?" for _ in BUSINESS_LOG_RELATED_TYPES)
    module_placeholders = ",".join("?" for _ in BUSINESS_LOG_MODULES)
    where = (
        f"related_type IN ({related_placeholders}) "
        f"OR module IN ({module_placeholders})"
    )
    return where, (*BUSINESS_LOG_RELATED_TYPES, *BUSINESS_LOG_MODULES)


def _count_business_logs(connection: sqlite3.Connection, tables: set[str]) -> int:
    if "operation_logs" not in tables:
        return 0
    where, values = _business_log_where()
    return int(connection.execute(f"SELECT COUNT(*) FROM operation_logs WHERE {where}", values).fetchone()[0])


def inspect_trial_business_data(database_path: str | Path) -> TrialResetInspection:
    path = Path(database_path).resolve()
    with _connect(path) as connection:
        tables = _table_names(connection)
        selected = _business_tables(connection, tables)
        delete_order = _delete_order(connection, selected)
        before_counts = {table: _count_table(connection, table) for table in delete_order}
        if "operation_logs" in tables:
            before_counts["operation_logs (business-related rows)"] = _count_business_logs(connection, tables)
        preserved_counts = {
            table: _count_table(connection, table)
            for table in PRESERVED_TABLES
            if table in tables
        }
    return TrialResetInspection(
        database_path=path,
        delete_order=delete_order,
        before_counts=before_counts,
        preserved_counts=preserved_counts,
    )


def _unique_backup_path(database_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = backup_dir / f"fortune_before_trial_reset_{timestamp}.db"
    if not base.exists():
        return base
    for index in range(1, 1000):
        candidate = backup_dir / f"fortune_before_trial_reset_{timestamp}_{index:03d}.db"
        if not candidate.exists():
            return candidate
    raise TrialDataResetError("无法生成不重复的试用数据重置备份名")


def _create_backup(database_path: Path, backup_dir: Path) -> Path:
    backup_path = _unique_backup_path(database_path, backup_dir)
    source = _connect(database_path)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    except Exception:
        destination.close()
        source.close()
        backup_path.unlink(missing_ok=True)
        raise
    else:
        destination.close()
        source.close()
    if not backup_path.exists() or backup_path.stat().st_size <= 0:
        raise TrialDataResetError("自动备份失败，已阻止试用数据重置")
    return backup_path


def _reset_log_description(before_counts: dict[str, int], backup_path: Path) -> str:
    count_text = ",".join(f"{table}={count}" for table, count in sorted(before_counts.items()))
    return (
        "试用数据重置；只清理测试业务数据；"
        f"backup={backup_path.name}; deleted_counts={count_text}"
    )


def reset_trial_business_data(
    database_path: str | Path,
    *,
    execute: bool = False,
    confirm: str = "",
    backup_dir: str | Path | None = None,
    failure_hook: FailureHook | None = None,
) -> TrialResetResult:
    inspection = inspect_trial_business_data(database_path)
    if not execute:
        return TrialResetResult(
            inspection=inspection,
            executed=False,
            backup_path=None,
            after_counts=dict(inspection.before_counts),
            preserved_after_counts=dict(inspection.preserved_counts),
        )
    if confirm != CONFIRM_PHRASE:
        raise TrialDataResetError(
            f"确认短语不正确；必须显式输入 {CONFIRM_PHRASE}"
        )

    path = inspection.database_path
    resolved_backup_dir = (
        Path(backup_dir).resolve()
        if backup_dir is not None
        else (path.parent / "backups").resolve()
    )
    backup_path = _create_backup(path, resolved_backup_dir)

    connection = _connect(path)
    try:
        connection.isolation_level = None
        connection.execute("BEGIN IMMEDIATE")
        for table in inspection.delete_order:
            connection.execute(f"DELETE FROM {_quote_identifier(table)}")
            if failure_hook is not None:
                failure_hook(connection, table)

        tables = _table_names(connection)
        if "operation_logs" in tables:
            where, values = _business_log_where()
            connection.execute(f"DELETE FROM operation_logs WHERE {where}", values)
            if failure_hook is not None:
                failure_hook(connection, "operation_logs (business-related rows)")

        foreign_key_errors = list(connection.execute("PRAGMA foreign_key_check"))
        if foreign_key_errors:
            raise TrialDataResetError("清理后外键检查失败，事务已回滚")

        if "operation_logs" in tables:
            connection.execute(
                """
                INSERT INTO operation_logs
                    (module, action, description, operator, related_type, related_id)
                VALUES
                    ('maintenance', 'trial_data_reset', ?, 'system', 'maintenance', NULL)
                """,
                (_reset_log_description(inspection.before_counts, backup_path),),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    after = inspect_trial_business_data(path)
    return TrialResetResult(
        inspection=inspection,
        executed=True,
        backup_path=backup_path,
        after_counts=after.before_counts,
        preserved_after_counts=after.preserved_counts,
    )


def _print_rows(title: str, rows: Iterable[tuple[str, int]]) -> None:
    print(title)
    for table, count in rows:
        print(f"  - {table}: {count}")


def print_result(result: TrialResetResult) -> None:
    print("模式: " + ("EXECUTE" if result.executed else "DRY-RUN（未修改数据）"))
    print(f"数据库: {result.inspection.database_path}")
    print("外键安全删除顺序: " + " -> ".join(result.inspection.delete_order))
    _print_rows("将清理的表/记录:", result.inspection.before_counts.items())
    _print_rows("明确保留的配置、开奖和版本表:", result.inspection.preserved_counts.items())
    if result.executed:
        print(f"执行前备份: {result.backup_path}")
        print("清理前后数量:")
        for table, before in result.inspection.before_counts.items():
            print(f"  - {table}: {before} -> {result.after_counts.get(table, 0)}")
    else:
        print(
            "真正执行必须显式使用: --execute --confirm " + CONFIRM_PHRASE
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安全清理FORTUNE试用业务数据；默认仅dry-run")
    parser.add_argument("--project-root", default=".", help="FORTUNE项目根目录")
    parser.add_argument("--database", default=None, help="可选数据库路径；测试时使用临时数据库")
    parser.add_argument("--backup-dir", default=None, help="可选备份目录")
    parser.add_argument("--execute", action="store_true", help="执行事务清理；默认不执行")
    parser.add_argument("--confirm", default="", help=f"执行确认短语：{CONFIRM_PHRASE}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()
    database_path = Path(args.database).resolve() if args.database else project_root / "data" / "fortune.db"
    try:
        result = reset_trial_business_data(
            database_path,
            execute=args.execute,
            confirm=args.confirm,
            backup_dir=args.backup_dir,
        )
    except TrialDataResetError as exc:
        print(f"拒绝执行: {exc}", file=sys.stderr)
        return 2
    print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
