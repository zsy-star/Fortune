"""全局配置：资源路径、可写运行目录和应用名称。"""

import sys
from pathlib import Path

from app_version import PRODUCT_NAME

APP_NAME = PRODUCT_NAME

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_DIR = (
    Path(getattr(sys, "_MEIPASS")).resolve()
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None)
    else _PROJECT_ROOT
)
BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else _PROJECT_ROOT
)

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "fortune.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
BACKUP_DIR = DATA_DIR / "backups"
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"
ALEMBIC_INI_PATH = RESOURCE_DIR / "alembic.ini"
ALEMBIC_SCRIPT_DIR = RESOURCE_DIR / "alembic"

DRAW_SOURCE_BASE_URL = "https://49wz777.com/"
DRAW_REQUEST_TIMEOUT = 15
DRAW_REQUEST_INTERVAL = 2
DRAW_MAX_RETRIES = 3
