"""占位页面 UI 构建（减少各页面重复代码）。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def build_placeholder_page(title: str, parent: QWidget | None = None) -> QWidget:
    """生成带标题与提示的占位布局。"""
    page = QWidget(parent)
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)

    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    hint = QLabel("功能开发中，敬请期待…")
    hint.setObjectName("pageHint")
    hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    layout.addWidget(title_label)
    layout.addWidget(hint)
    layout.addStretch(1)
    return page
