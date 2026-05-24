"""连肖调单页面（占位，后续完善）。"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from utils.placeholder_ui import build_placeholder_page


class LianxiaoOrderPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(build_placeholder_page("连肖调单", self))
