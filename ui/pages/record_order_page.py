"""Reserved full-page order intake entry."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class RecordOrderPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("我要录单")
        title.setObjectName("placeholderTitle")
        message = QLabel(
            "当前版本请使用顶部「我要录单」按钮打开录单弹窗。\n"
            "本页面为后续整页录单预留。"
        )
        message.setObjectName("placeholderMessage")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        layout.addWidget(title)
        layout.addWidget(message)
        layout.addStretch(1)

        self.setStyleSheet(
            """
            QLabel#placeholderTitle {
                color: #2c3e50;
                font-size: 18px;
                font-weight: 600;
            }
            QLabel#placeholderMessage {
                color: #566573;
                font-size: 14px;
                padding: 12px;
                border: 1px solid #d5d8dc;
                background: #f8f9fa;
            }
            """
        )
