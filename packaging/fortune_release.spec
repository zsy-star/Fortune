# -*- mode: python ; coding: utf-8 -*-
"""FORTUNE v1.0.0-rc1 formal Windows onedir build."""

import os
from pathlib import Path

block_cipher = None
PROJECT_ROOT = Path(SPECPATH).resolve().parent
MAIN_SCRIPT = str(PROJECT_ROOT / "main.py")
VERSION_FILE = str(PROJECT_ROOT / "packaging" / "fortune_version_info.txt")
ICON_FILE = os.environ.get("FORTUNE_RELEASE_ICON")
if not ICON_FILE or not Path(ICON_FILE).is_file():
    raise RuntimeError("FORTUNE_RELEASE_ICON未指向有效的正式图标")

datas = [
    (str(PROJECT_ROOT / "alembic.ini"), "."),
    (str(PROJECT_ROOT / "alembic" / "env.py"), "alembic"),
    (str(PROJECT_ROOT / "alembic" / "script.py.mako"), "alembic"),
]
for migration in sorted((PROJECT_ROOT / "alembic" / "versions").glob("*.py")):
    datas.append((str(migration), "alembic/versions"))

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.qt_compat",
    "openpyxl",
    "alembic.command",
    "alembic.config",
    "alembic.ddl.sqlite",
    "alembic.operations",
    "alembic.runtime.migration",
    "alembic.script",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.sql.default_comparator",
]

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["QtAgg"]}},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "tests",
        "PyQt5",
        "PyQt6",
        "IPython",
        "astroid",
        "ipykernel",
        "jedi",
        "notebook",
        "sphinx",
        "tkinter",
        "_tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FORTUNE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=VERSION_FILE,
    icon=ICON_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FORTUNE_v1.0.0-rc1",
)
