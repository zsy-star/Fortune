"""订单分析页面（占位）。"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from utils.placeholder_ui import build_placeholder_page


class OrderAnalysisPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(build_placeholder_page("订单分析", self))
