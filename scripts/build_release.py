"""Reproducible, guarded FORTUNE formal release builder."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_version import DATABASE_REVISION, PRODUCT_NAME, RULESET_VERSION, VERSION
from scripts.pre_release_check import run_pre_release_check


RELEASE_BASENAME = f"{PRODUCT_NAME}_v{VERSION}"
SPEC_RELATIVE = Path("packaging/fortune_release.spec")
FORBIDDEN_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "backups",
    "data",
    "exports",
    "logs",
    "tests",
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".key", ".env"}


class ReleaseBuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_status(project_root: Path) -> str:
    completed = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def git_commit(project_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def scan_release_tree(release_dir: Path) -> list[str]:
    failures: list[str] = []
    exe_path = release_dir / "FORTUNE.exe"
    if not exe_path.is_file() or exe_path.stat().st_size <= 0:
        failures.append("FORTUNE.exe缺失或为空")

    for path in release_dir.rglob("*"):
        relative = path.relative_to(release_dir)
        lowered_parts = {part.lower() for part in relative.parts}
        if path.is_dir() and path.name.lower() in FORBIDDEN_DIR_NAMES:
            failures.append(f"禁止目录：{relative.as_posix()}")
            continue
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"禁止文件：{relative.as_posix()}")
        if path.is_file() and path.suffix.lower() == ".pem":
            try:
                if b"PRIVATE KEY" in path.read_bytes():
                    failures.append(f"禁止私钥：{relative.as_posix()}")
            except OSError:
                failures.append(f"无法检查PEM文件：{relative.as_posix()}")
        if path.is_file() and path.suffix.lower() == ".py" and "alembic" not in lowered_parts:
            failures.append(f"不应包含Python源码：{relative.as_posix()}")

    if not any(release_dir.rglob("qwindows.dll")):
        failures.append("缺少Qt platforms/qwindows.dll")
    if not any(release_dir.rglob("imageformats")):
        failures.append("缺少Qt imageformats插件目录")

    internal = release_dir / "_internal"
    migration_dir = internal / "alembic" / "versions"
    expected_migrations = sorted(path.name for path in (ROOT / "alembic" / "versions").glob("*.py"))
    packaged_migrations = sorted(path.name for path in migration_dir.glob("*.py"))
    if packaged_migrations != expected_migrations:
        failures.append("Alembic migration资源不完整")
    if not (internal / "alembic.ini").is_file():
        failures.append("缺少alembic.ini")
    return sorted(set(failures))


def _safe_remove_work_dir(project_root: Path, work_dir: Path) -> None:
    build_root = (project_root / "build" / "release").resolve()
    resolved = work_dir.resolve()
    if build_root not in resolved.parents:
        raise ReleaseBuildError("拒绝删除发布专用build目录之外的路径")
    if resolved.exists():
        shutil.rmtree(resolved)


def _generate_release_icon(icon_path: Path) -> None:
    """Generate a deterministic branded ICO inside the disposable build directory."""

    from PIL import Image, ImageDraw

    size = 256
    image = Image.new("RGBA", (size, size), (12, 28, 48, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 12, 244, 244), radius=48, fill=(18, 43, 72, 255))
    draw.rounded_rectangle((30, 30, 226, 226), radius=38, outline=(225, 174, 72, 255), width=10)
    gold = (245, 198, 92, 255)
    draw.rounded_rectangle((76, 58, 112, 204), radius=10, fill=gold)
    draw.rounded_rectangle((96, 58, 190, 94), radius=10, fill=gold)
    draw.rounded_rectangle((96, 116, 170, 150), radius=10, fill=gold)
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(icon_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def _run_gate(project_root: Path, allow_dirty: bool) -> tuple[str, str]:
    status = git_status(project_root)
    if status and not allow_dirty:
        raise ReleaseBuildError("工作区不干净，正式构建已停止")
    pre = run_pre_release_check(project_root)
    if not pre["ok"] or pre["failures"] or pre["warnings"]:
        raise ReleaseBuildError(
            f"pre_release_check未达到0失败0警告：失败{len(pre['failures'])}，警告{len(pre['warnings'])}"
        )
    migration = subprocess.run(
        [sys.executable, "scripts/check_db_migration_state.py"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if migration.returncode != 0 or DATABASE_REVISION not in migration.stdout:
        raise ReleaseBuildError("数据库migration状态检查失败")
    return status, git_commit(project_root)


def _zip_directory(release_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(release_dir.rglob("*")):
            if path.is_file():
                archive.write(path, Path(release_dir.name) / path.relative_to(release_dir))


def build_release(project_root: Path, *, allow_dirty: bool = False) -> dict[str, Any]:
    root = project_root.resolve()
    spec_path = root / SPEC_RELATIVE
    release_parent = root / "dist" / "releases"
    release_dir = release_parent / RELEASE_BASENAME
    zip_path = release_parent / f"{RELEASE_BASENAME}.zip"
    sha_path = release_parent / f"{RELEASE_BASENAME}_SHA256.txt"
    manifest_path = release_parent / f"{RELEASE_BASENAME}_manifest.json"
    work_dir = root / "build" / "release" / RELEASE_BASENAME

    if not spec_path.is_file():
        raise ReleaseBuildError(f"正式spec不存在：{SPEC_RELATIVE.as_posix()}")
    existing = [path for path in (release_dir, zip_path, sha_path, manifest_path) if path.exists()]
    if existing:
        raise ReleaseBuildError("同名发布产物已存在，拒绝覆盖或混合")

    status, commit = _run_gate(root, allow_dirty)
    _safe_remove_work_dir(root, work_dir)
    release_parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    icon_path = work_dir / "FORTUNE.ico"
    _generate_release_icon(icon_path)

    command_line = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(release_parent),
        "--workpath",
        str(work_dir),
        str(spec_path),
    ]
    build_environment = dict(os.environ)
    build_environment["FORTUNE_RELEASE_ICON"] = str(icon_path)
    completed = subprocess.run(command_line, cwd=root, env=build_environment, check=False)
    if completed.returncode != 0:
        raise ReleaseBuildError(f"PyInstaller构建失败，退出码{completed.returncode}")

    notes_source = root / "docs" / f"RELEASE_NOTES_v{VERSION}.txt"
    shutil.copy2(notes_source, release_dir / notes_source.name)
    failures = scan_release_tree(release_dir)
    if failures:
        raise ReleaseBuildError("发布目录内容检查失败：" + "；".join(failures))

    exe_path = release_dir / "FORTUNE.exe"
    _zip_directory(release_dir, zip_path)
    zip_sha256 = sha256_file(zip_path)
    sha_path.write_text(f"{zip_sha256}  {zip_path.name}\n", encoding="utf-8")
    manifest = {
        "product": PRODUCT_NAME,
        "version": VERSION,
        "ruleset_version": RULESET_VERSION,
        "database_revision": DATABASE_REVISION,
        "build_time": datetime.now(timezone.utc).isoformat(),
        "executable": "FORTUNE.exe",
        "package_type": "onedir",
        "branded_icon": True,
        "executable_sha256": sha256_file(exe_path),
        "zip_sha256": zip_sha256,
        "python_version": sys.version.split()[0],
        "pyinstaller_version": importlib.metadata.version("pyinstaller").strip(),
        "pyside6_version": importlib.metadata.version("pyside6").strip(),
        "git_commit": commit,
        "worktree_clean": not bool(status),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "release_dir": release_dir,
        "zip_path": zip_path,
        "sha_path": sha_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建FORTUNE正式发布候选包")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--version", default=VERSION)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="仅用于本地验收未提交发布配置；manifest会记录worktree_clean=false",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.version != VERSION:
        print(f"版本不一致：参数={args.version}，统一版本={VERSION}", file=sys.stderr)
        return 2
    try:
        result = build_release(args.project_root, allow_dirty=args.allow_dirty)
    except (OSError, subprocess.SubprocessError, ReleaseBuildError) as exc:
        print(f"发布构建失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: str(value) for key, value in result.items() if key != "manifest"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
