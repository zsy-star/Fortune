"""辅助工具页面。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.windows import CalculatorWindow, SplitOrderWindow


class _PuzzleIcon(QWidget):
    """四块拼图风格图标（拆单助手）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(72, 72)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = ("#85c1e9", "#5dade2", "#3498db", "#2874a6")
        size = 32
        gap = 4
        positions = ((0, 0), (36, 0), (0, 36), (36, 36))
        for (x, y), color in zip(positions, colors):
            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x + gap // 2, y + gap // 2, size, size, 6, 6)
        painter.end()


class _CalculatorIcon(QWidget):
    """四键计算器风格图标。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(72, 72)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        specs = [
            (8, 8, "#2ecc71", "+"),
            (40, 8, "#3498db", "×"),
            (8, 40, "#3498db", "−"),
            (40, 40, "#e67e22", "="),
        ]
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        for x, y, color, sym in specs:
            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x, y, 24, 24)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(x, y, 24, 24, Qt.AlignmentFlag.AlignCenter, sym)
        painter.end()


class _ToolLauncher(QFrame):
    """可点击的工具入口卡片。"""

    clicked = Signal(str)

    def __init__(self, tool_id: str, title: str, icon: QWidget, parent=None):
        super().__init__(parent)
        self._tool_id = tool_id
        self.setObjectName("toolLauncher")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(120, 130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_wrap = QWidget()
        icon_layout = QHBoxLayout(icon_wrap)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.addStretch()
        icon_layout.addWidget(icon)
        icon_layout.addStretch()

        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setObjectName("toolTitle")

        layout.addWidget(icon_wrap)
        layout.addWidget(lbl)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._tool_id)
        super().mousePressEvent(event)


class ToolsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._split_order_window: SplitOrderWindow | None = None
        self._calculator_window: CalculatorWindow | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)

        tools_row = QHBoxLayout()
        tools_row.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        tools_row.setSpacing(32)

        split_tool = _ToolLauncher("split_order", "拆单助手", _PuzzleIcon())
        calc_tool = _ToolLauncher("calculator", "计算器", _CalculatorIcon())
        split_tool.clicked.connect(self._on_tool_clicked)
        calc_tool.clicked.connect(self._on_tool_clicked)

        tools_row.addWidget(split_tool)
        tools_row.addWidget(calc_tool)
        tools_row.addStretch(1)

        root.addLayout(tools_row)
        root.addStretch(1)
        self._footer_box = self._build_footer_box()
        root.addWidget(self._footer_box)

        self._apply_stylesheet()

    def _build_footer_box(self) -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setObjectName("comingSoonBox")
        box.setPlainText("其他功能，陆续开放中，敬请期待")
        box.setMinimumHeight(160)
        return box

    def _on_tool_clicked(self, tool_id: str) -> None:
        if tool_id == "split_order":
            self._open_split_order_window()
            return
        if tool_id == "calculator":
            self._open_calculator_window()
            return

    def _open_split_order_window(self) -> None:
        if self._split_order_window is None:
            parent = self.window()
            self._split_order_window = SplitOrderWindow(parent)
            self._split_order_window.destroyed.connect(self._on_split_order_window_destroyed)
        self._split_order_window.show()
        self._split_order_window.raise_()
        self._split_order_window.activateWindow()

    def _on_split_order_window_destroyed(self) -> None:
        self._split_order_window = None

    def _open_calculator_window(self) -> None:
        if self._calculator_window is None:
            parent = self.window()
            self._calculator_window = CalculatorWindow(parent)
            self._calculator_window.destroyed.connect(self._on_calculator_window_destroyed)
        self._calculator_window.show()
        self._calculator_window.raise_()
        self._calculator_window.activateWindow()

    def _on_calculator_window_destroyed(self) -> None:
        self._calculator_window = None

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #ffffff;
            }
            QFrame#toolLauncher {
                background: transparent;
                border: none;
            }
            QFrame#toolLauncher:hover {
                background-color: #f8f9fa;
                border-radius: 8px;
            }
            QLabel#toolTitle {
                color: #27ae60;
                font-size: 15px;
                font-weight: 600;
            }
            QPlainTextEdit#comingSoonBox {
                border: 1px solid #bdc3c7;
                background: #ffffff;
                color: #95a5a6;
                font-size: 13px;
                padding: 10px;
            }
            """
        )
