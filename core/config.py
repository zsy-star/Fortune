"""全局配置：路径、应用名称等。"""

from pathlib import Path

APP_NAME = "FORTUNE"

# 项目根目录（core 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# 本地数据目录（SQLite 等）
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "fortune.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
