"""Reserved page for future lianxiao order adjustment."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

UNAVAILABLE_MESSAGE = (
    "当前测试版暂未开放连肖调单持久化功能。\n"
    "本页仅为后续连肖调单功能预留，不参与正式记账、结算、导出。"
)


class LianxiaoOrderPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        self._title = QLabel("连肖调单")
        self._title.setObjectName("scopeTitle")

        self._message = QLabel(UNAVAILABLE_MESSAGE)
        self._message.setObjectName("scopeMessage")
        self._message.setWordWrap(True)
        self._message.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._btn_adjust = QPushButton("调整")
        self._btn_print = QPushButton("打印")
        self._btn_copy = QPushButton("自定义复制")
        for button in (self._btn_adjust, self._btn_print, self._btn_copy):
            button.setEnabled(False)
            button.setToolTip("当前测试版暂未开放")

        root.addWidget(self._title)
        root.addWidget(self._message)
        root.addWidget(self._btn_adjust)
        root.addWidget(self._btn_print)
        root.addWidget(self._btn_copy)
        root.addStretch(1)

        self._apply_stylesheet()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #ffffff;
            }
            QLabel#scopeTitle {
                color: #2c3e50;
                font-size: 18px;
                font-weight: 600;
            }
            QLabel#scopeMessage {
                color: #566573;
                font-size: 14px;
                line-height: 1.6;
                padding: 12px;
                border: 1px solid #d5d8dc;
                background: #f8f9fa;
            }
            QPushButton {
                max-width: 160px;
                padding: 6px 12px;
                color: #95a5a6;
                border: 1px solid #d5d8dc;
                background: #f4f6f7;
            }
            """
        )
