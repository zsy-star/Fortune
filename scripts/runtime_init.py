"""Application runtime directory bootstrap (no business data writes)."""

from __future__ import annotations

import sys
from pathlib import Path

RUNTIME_DIRECTORIES = (
    "data",
    "data/backups",
    "exports",
)


def get_app_root() -> Path:
    """Return application root: exe directory when frozen, project root otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def ensure_runtime_directories(app_root: Path | None = None) -> list[Path]:
    """Create runtime directories if missing. Never deletes or overwrites files."""
    root = (app_root or get_app_root()).resolve()
    created: list[Path] = []
    for relative in RUNTIME_DIRECTORIES:
        target = root / relative
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(target)
        elif not target.is_dir():
            raise NotADirectoryError(f"运行时路径不是目录：{target}")
    return created


def apply_frozen_config_patch() -> Path:
    """Patch core.config paths when running as a PyInstaller frozen executable."""
    root = Path(sys.executable).resolve().parent
    import os

    os.chdir(root)

    import core.config as cfg

    cfg.BASE_DIR = root
    cfg.DATA_DIR = root / "data"
    cfg.DATABASE_PATH = cfg.DATA_DIR / "fortune.db"
    cfg.DATABASE_URL = f"sqlite:///{cfg.DATABASE_PATH.as_posix()}"
    return root


def bootstrap_application() -> Path:
    """Prepare runtime paths before core.database is imported."""
    if getattr(sys, "frozen", False):
        root = apply_frozen_config_patch()
    else:
        import core.config as cfg

        root = cfg.BASE_DIR
    ensure_runtime_directories(root)
    return root
