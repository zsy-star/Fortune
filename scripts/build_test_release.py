"""Build Fortune Windows test release with PyInstaller."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SPEC = Path("packaging/fortune_test.spec")
DEFAULT_DIST_DIR = Path("dist/Fortune-Test")
DEFAULT_BUILD_DIR = Path("build/fortune_test")


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def find_pyinstaller() -> str | None:
    spec = importlib.util.find_spec("PyInstaller")
    if spec is None:
        return None
    return str(Path(spec.origin).parent / "__main__.py")


def run_pre_release_gate(project_root: Path) -> dict[str, Any]:
    from scripts.pre_release_check import run_pre_release_check

    return run_pre_release_check(project_root)


def plan_build_steps(
    project_root: Path,
    spec_path: Path,
    dist_dir: Path,
    build_dir: Path,
) -> list[str]:
    pyinstaller = find_pyinstaller()
    steps = [
        f"项目根目录：{project_root.resolve()}",
        "步骤 1：运行 pre_release_check（只读）",
        f"步骤 2：确认 spec 文件存在：{spec_path}",
        "步骤 3：确认未将 data/fortune.db、data/backups/、exports/、*.xlsx 纳入 spec datas",
    ]
    if pyinstaller is None:
        steps.append("步骤 4：PyInstaller 未安装 — 请在打包机执行：pip install pyinstaller")
    else:
        steps.append(f"步骤 4：调用 PyInstaller：{pyinstaller}")
        steps.append(
            f"        python {pyinstaller} --noconfirm --distpath {dist_dir.parent} "
            f"--workpath {build_dir} {spec_path}"
        )
    steps.append(f"步骤 5：预期输出目录：{dist_dir}")
    steps.append("步骤 6：将 _internal/docs/ 同步到发布根 docs/（便于测试人员查阅）")
    steps.append("步骤 7：构建后运行 check_test_release.py 验证发布目录")
    return steps


def sync_release_docs(release_dir: Path) -> bool:
    """Copy PyInstaller bundled docs to release root for testers."""
    internal_docs = release_dir / "_internal" / "docs"
    target_docs = release_dir / "docs"
    if not internal_docs.is_dir():
        return False
    if target_docs.exists():
        shutil.rmtree(target_docs)
    shutil.copytree(internal_docs, target_docs)
    return True


def run_build(
    project_root: Path,
    spec_path: Path,
    dist_dir: Path,
    build_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = project_root.resolve()
    spec = (root / spec_path).resolve()
    result: dict[str, Any] = {
        "ok": False,
        "dry_run": dry_run,
        "project_root": str(root),
        "spec_path": str(spec),
        "dist_dir": str((root / dist_dir).resolve()),
        "steps": plan_build_steps(root, spec, root / dist_dir, root / build_dir),
        "pre_release": None,
        "message": "",
    }

    pre_release = run_pre_release_gate(root)
    result["pre_release"] = pre_release
    if not pre_release["ok"]:
        result["message"] = "pre_release_check 存在失败项，已中止构建"
        return result

    if not spec.is_file():
        result["message"] = f"spec 文件不存在：{spec}"
        return result

    if dry_run:
        result["ok"] = True
        result["message"] = "dry-run 完成，未调用 PyInstaller"
        return result

    pyinstaller = find_pyinstaller()
    if pyinstaller is None:
        result["message"] = (
            "未检测到 PyInstaller。请在打包机安装：pip install pyinstaller，然后重试 --build"
        )
        return result

    dist_parent = (root / dist_dir).resolve().parent
    workpath = (root / build_dir).resolve()
    dist_parent.mkdir(parents=True, exist_ok=True)
    workpath.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        pyinstaller,
        "--noconfirm",
        "--distpath",
        str(dist_parent),
        "--workpath",
        str(workpath),
        str(spec),
    ]
    completed = subprocess.run(cmd, cwd=str(root), check=False)
    if completed.returncode != 0:
        result["message"] = f"PyInstaller 构建失败，退出码 {completed.returncode}"
        return result

    release_dir = (root / dist_dir).resolve()
    sync_release_docs(release_dir)

    result["ok"] = True
    result["message"] = f"构建完成：{release_dir}"
    return result


def format_build_report(result: dict[str, Any]) -> str:
    lines = ["Fortune 测试版打包"]
    lines.append(f"模式：{'dry-run' if result.get('dry_run') else 'build'}")
    lines.append("")
    for step in result.get("steps", []):
        lines.append(step)
    lines.append("")
    pre = result.get("pre_release")
    if pre:
        lines.append(
            f"pre_release_check：{'通过' if pre.get('ok') else '未通过'}"
            f"（失败 {len(pre.get('failures', []))}，警告 {len(pre.get('warnings', []))}）"
        )
    lines.append(f"结果：{result.get('message', '')}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fortune 测试版 PyInstaller 打包脚本")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST_DIR)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只打印步骤，不实际打包")
    mode.add_argument("--build", action="store_true", help="执行 PyInstaller 构建")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = parse_args(argv)
    result = run_build(
        args.project_root,
        args.spec,
        args.dist_dir,
        args.build_dir,
        dry_run=args.dry_run,
    )
    print(format_build_report(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
