"""FORTUNE 桌面应用入口。"""

import json
import os
import sys
from pathlib import Path

from scripts.runtime_init import bootstrap_application

bootstrap_application()

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app_version import DATABASE_REVISION, DISPLAY_VERSION, RULESET_VERSION, VERSION
from core.config import APP_NAME, DATABASE_PATH
from core.database import init_db
from ui.main_window import MainWindow
from ui.matplotlib_setup import ensure_matplotlib_configured


def main() -> int:
    initialization = init_db()
    ensure_matplotlib_configured()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        result_path = os.environ.get("FORTUNE_SMOKE_RESULT", "").strip()
        if result_path:
            Path(result_path).write_text(
                json.dumps(
                    {
                        "product": APP_NAME,
                        "version": VERSION,
                        "display_version": DISPLAY_VERSION,
                        "ruleset_version": RULESET_VERSION,
                        "database_revision": DATABASE_REVISION,
                        "database_path": str(DATABASE_PATH),
                        "database_created": initialization.created,
                        "window_title": window.windowTitle(),
                        "page_count": window._stack.count(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
