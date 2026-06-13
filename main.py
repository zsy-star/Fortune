"""FORTUNE 桌面应用入口。"""

import sys

from PySide6.QtWidgets import QApplication

from core.config import APP_NAME
from core.database import init_db
from ui.main_window import MainWindow
from ui.matplotlib_setup import ensure_matplotlib_configured


def main() -> int:
    init_db()
    ensure_matplotlib_configured()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
