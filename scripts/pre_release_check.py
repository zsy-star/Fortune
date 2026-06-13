"""Read-only pre-release checks for packaging and commercial acceptance.

This script MUST NOT modify, delete, or create any project files or data.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

REQUIRED_DOCS = (
    "docs/commercial_test_scope.md",
    "docs/commercial_acceptance_checklist.md",
    "docs/pre_packaging_checklist.md",
    "docs/manual_test_script.md",
)

REQUIRED_ROOT_FILES = (
    "requirements.txt",
    "README.md",
)

KEY_DEPENDENCIES = (
    "PySide6",
    "sqlalchemy",
    "openpyxl",
)

MIN_PYTHON = (3, 10)


def _check_python_version() -> tuple[str, str | None]:
    current = sys.version_info[:3]
    label = f"{current[0]}.{current[1]}.{current[2]}"
    if current[:2] < MIN_PYTHON:
        return label, f"Python 版本过低：{label}，建议 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    return label, None


def _check_import(module_name: str) -> str | None:
    if importlib.util.find_spec(module_name) is None:
        return f"无法 import 关键依赖：{module_name}"
    return None


def _exports_dir_can_be_created(project_root: Path) -> bool:
    exports_dir = project_root / "exports"
    if exports_dir.exists():
        return True
    if not project_root.exists() or not project_root.is_dir():
        return False
    try:
        return bool(Path(project_root).stat().st_mode & 0o200)
    except OSError:
        return False


def _find_pytest_tmp_dirs(project_root: Path) -> list[str]:
    names: list[str] = []
    try:
        for entry in project_root.iterdir():
            if entry.is_dir() and entry.name.startswith(".pytest_tmp_cursor"):
                names.append(entry.name)
    except OSError:
        pass
    names.sort()
    return names


def _find_xlsx_files(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    try:
        return sorted(path.name for path in directory.glob("*.xlsx"))
    except OSError:
        return []


def run_pre_release_check(project_root: Path) -> dict[str, Any]:
    """Run read-only checks. Returns a structured summary dict."""
    root = project_root.resolve()
    failures: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    checks: dict[str, str] = {}

    python_label, python_error = _check_python_version()
    checks["python_version"] = python_label
    info.append(f"当前 Python 版本：{python_label}")
    if python_error:
        failures.append(python_error)

    for module_name in KEY_DEPENDENCIES:
        import_error = _check_import(module_name)
        key = f"import_{module_name.lower()}"
        if import_error:
            checks[key] = "missing"
            failures.append(import_error)
        else:
            checks[key] = "ok"

    for relative in REQUIRED_ROOT_FILES:
        path = root / relative
        key = relative.replace("/", "_").replace(".", "_")
        if path.is_file():
            checks[key] = "ok"
        else:
            checks[key] = "missing"
            failures.append(f"缺少必需文件：{relative}")

    for relative in REQUIRED_DOCS:
        path = root / relative
        key = relative.replace("/", "_").replace(".", "_")
        if path.is_file():
            checks[key] = "ok"
        else:
            checks[key] = "missing"
            failures.append(f"缺少必需文档：{relative}")

    data_dir = root / "data"
    backups_dir = data_dir / "backups"
    exports_dir = root / "exports"
    db_path = data_dir / "fortune.db"
    launch_bat = root / "启动Fortune.bat"

    if data_dir.is_dir():
        checks["data_dir"] = "ok"
        info.append("data 目录存在")
    else:
        checks["data_dir"] = "missing"
        warnings.append("data 目录不存在（首次运行时会自动创建）")

    if backups_dir.is_dir():
        checks["data_backups_dir"] = "ok"
        info.append("data/backups 目录存在")
    else:
        checks["data_backups_dir"] = "missing"
        warnings.append("data/backups 目录不存在（首次备份前可能需要创建）")

    if exports_dir.is_dir():
        checks["exports_dir"] = "ok"
        info.append("exports 目录存在")
    elif _exports_dir_can_be_created(root):
        checks["exports_dir"] = "can_create"
        info.append("exports 目录不存在，但项目根目录可写，首次导出时可创建")
    else:
        checks["exports_dir"] = "missing"
        warnings.append("exports 目录不存在且项目根目录可能不可写")

    if db_path.is_file():
        checks["fortune_db"] = "present"
        info.append("data/fortune.db 存在（打包前请确认不含真实业务数据）")
    else:
        checks["fortune_db"] = "absent"
        info.append("data/fortune.db 不存在（干净环境或尚未首次运行）")

    if launch_bat.is_file():
        checks["launch_bat"] = "present"
        info.append("启动Fortune.bat 存在（通常不提交仓库，打包时可单独提供）")
    else:
        checks["launch_bat"] = "absent"
        info.append("启动Fortune.bat 不存在")

    tmp_dirs = _find_pytest_tmp_dirs(root)
    checks["pytest_tmp_cursor_dirs"] = ",".join(tmp_dirs) if tmp_dirs else "none"
    if tmp_dirs:
        warnings.append(
            "存在 .pytest_tmp_cursor* 临时测试目录："
            + ", ".join(tmp_dirs)
            + "（打包前勿纳入安装包）"
        )

    export_xlsx = _find_xlsx_files(exports_dir)
    checks["exports_xlsx"] = ",".join(export_xlsx) if export_xlsx else "none"
    if export_xlsx:
        warnings.append(
            "exports/ 下存在测试 .xlsx 文件："
            + ", ".join(export_xlsx)
            + "（打包前勿纳入安装包）"
        )

    root_xlsx = _find_xlsx_files(root)
    checks["root_xlsx"] = ",".join(root_xlsx) if root_xlsx else "none"
    if root_xlsx:
        warnings.append(
            "项目根目录存在 .xlsx 文件："
            + ", ".join(root_xlsx)
            + "（打包前请移出或删除测试导出）"
        )

    return {
        "ok": not failures,
        "project_root": str(root),
        "failures": failures,
        "warnings": warnings,
        "info": info,
        "checks": checks,
    }


def format_report(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Fortune 打包前只读自检")
    lines.append(f"项目根目录：{result['project_root']}")
    lines.append("")

    if result["info"]:
        lines.append("[信息]")
        for item in result["info"]:
            lines.append(f"  - {item}")
        lines.append("")

    if result["warnings"]:
        lines.append("[警告]")
        for item in result["warnings"]:
            lines.append(f"  - {item}")
        lines.append("")

    if result["failures"]:
        lines.append("[失败]")
        for item in result["failures"]:
            lines.append(f"  - {item}")
        lines.append("")

    status = "通过" if result["ok"] and not result["failures"] else "未通过"
    if result["ok"] and result["warnings"]:
        status = "通过（有警告）"
    lines.append(f"总体结果：{status}")
    lines.append(f"失败项：{len(result['failures'])}，警告项：{len(result['warnings'])}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fortune 打包前只读自检（不修改任何文件）")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="项目根目录，默认当前目录",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_pre_release_check(args.project_root)
    print(format_report(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
