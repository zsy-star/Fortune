"""Read-only post-build checks for Fortune test release directory."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

DEFAULT_EXE_NAME = "Fortune-Test.exe"
FORBIDDEN_RELATIVE_PATHS = (
    "data/fortune.db",
)
FORBIDDEN_DIR_NAMES = (
    "data/backups",
    "exports",
)
FORBIDDEN_DIR_PREFIXES = (
    ".pytest_tmp",
    ".pytest_tmp_cursor",
)


def _find_forbidden_items(release_dir: Path) -> list[str]:
    found: list[str] = []
    for relative in FORBIDDEN_RELATIVE_PATHS:
        path = release_dir / relative
        if path.is_file():
            found.append(relative)

    for relative in FORBIDDEN_DIR_NAMES:
        path = release_dir / relative
        if not path.exists():
            continue
        if relative == "exports":
            xlsx = list(path.glob("*.xlsx"))
            if xlsx:
                found.extend(str(p.relative_to(release_dir)).replace("\\", "/") for p in xlsx)
        if relative == "data/backups":
            backups = list(path.glob("*.db"))
            if backups:
                found.extend(str(p.relative_to(release_dir)).replace("\\", "/") for p in backups)

    for path in release_dir.rglob("*.xlsx"):
        rel = str(path.relative_to(release_dir)).replace("\\", "/")
        if rel not in found:
            found.append(rel)

    for entry in release_dir.iterdir():
        name = entry.name
        if any(name.startswith(prefix) for prefix in FORBIDDEN_DIR_PREFIXES):
            found.append(name)

    return sorted(set(found))


def run_check_test_release(release_dir: Path, exe_name: str = DEFAULT_EXE_NAME) -> dict[str, Any]:
    root = release_dir.resolve()
    failures: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    checks: dict[str, str] = {}

    if not root.is_dir():
        failures.append(f"发布目录不存在：{root}")
        return {
            "ok": False,
            "release_dir": str(root),
            "failures": failures,
            "warnings": warnings,
            "info": info,
            "checks": checks,
        }

    checks["release_dir"] = "ok"
    info.append(f"发布目录：{root}")

    exe_path = root / exe_name
    if exe_path.is_file():
        checks["exe"] = "ok"
        info.append(f"可执行文件：{exe_name}")
    else:
        checks["exe"] = "missing"
        failures.append(f"缺少可执行文件：{exe_name}")

    docs_dir = root / "docs"
    if docs_dir.is_dir() and any(docs_dir.glob("*.md")):
        checks["docs"] = "ok"
        info.append("docs/ 目录存在且含文档")
    else:
        checks["docs"] = "missing"
        warnings.append("docs/ 目录缺失或无 .md 文件（测试人员可能缺少说明）")

    forbidden = _find_forbidden_items(root)
    checks["forbidden_items"] = ",".join(forbidden) if forbidden else "none"
    for item in forbidden:
        failures.append(f"发布目录不应包含：{item}")

    if (root / "data" / "fortune.db").is_file():
        warnings.append("data/fortune.db 存在 — 请确认不是从开发机误打包的真实业务库")

    return {
        "ok": not failures,
        "release_dir": str(root),
        "failures": failures,
        "warnings": warnings,
        "info": info,
        "checks": checks,
    }


def format_report(result: dict[str, Any]) -> str:
    lines = ["Fortune 测试版发布目录自检（只读）"]
    lines.append(f"目录：{result['release_dir']}")
    lines.append("")
    for section, key in (("[信息]", "info"), ("[警告]", "warnings"), ("[失败]", "failures")):
        items = result.get(key, [])
        if items:
            lines.append(section)
            for item in items:
                lines.append(f"  - {item}")
            lines.append("")
    status = "通过" if result["ok"] and not result["failures"] else "未通过"
    if result["ok"] and result.get("warnings"):
        status = "通过（有警告）"
    lines.append(f"总体结果：{status}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fortune 测试版发布目录只读自检")
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--exe-name", default=DEFAULT_EXE_NAME)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_check_test_release(args.release_dir, exe_name=args.exe_name)
    print(format_report(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
