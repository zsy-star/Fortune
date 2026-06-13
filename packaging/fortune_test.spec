# -*- mode: python ; coding: utf-8 -*-
# Fortune 测试版 PyInstaller spec
#
# 入口：main.py
# 产物：dist/Fortune-Test/Fortune-Test.exe（onedir）
#
# 禁止打包进安装包的目录/文件（切勿加入 datas 或 binaries）：
#   - data/fortune.db          真实业务数据库
#   - data/backups/            私人备份
#   - exports/                 测试导出
#   - *.xlsx                   测试 Excel
#   - .pytest_tmp* / .pytest_tmp_cursor*  测试临时目录
#
# 允许打包的文档资源：README.md、docs/（不含上述敏感文件）

import sys
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).resolve().parent
MAIN_SCRIPT = str(PROJECT_ROOT / "main.py")

# 可选图标：存在则使用，不存在不报错
_icon_candidates = (
    PROJECT_ROOT / "packaging" / "fortune.ico",
    PROJECT_ROOT / "assets" / "fortune.ico",
    PROJECT_ROOT / "fortune.ico",
)
_icon = next((str(p) for p in _icon_candidates if p.is_file()), None)

# 仅打包文档资源，不包含 data/、exports/、备份或测试产物
_doc_datas = []
for relative in ("README.md",):
    path = PROJECT_ROOT / relative
    if path.is_file():
        _doc_datas.append((str(path), "."))

_docs_dir = PROJECT_ROOT / "docs"
if _docs_dir.is_dir():
    for doc in sorted(_docs_dir.glob("*.md")):
        _doc_datas.append((str(doc), "docs"))

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=_doc_datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "matplotlib.backends.backend_qtagg",
        "openpyxl",
        "sqlalchemy.sql.default_comparator",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_*",
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
    name="Fortune-Test",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Fortune-Test",
)
