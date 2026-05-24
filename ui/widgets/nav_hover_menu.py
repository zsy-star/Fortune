"""顶部导航悬停展开菜单按钮。"""

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout, QWidget


class NavHoverMenuButton(QWidget):
    """鼠标悬停时在下方展开子选项（如：特码调单 / 连肖调单）。"""

    page_requested = Signal(int)

    def __init__(
        self,
        title: str,
        options: list[tuple[str, int]],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._options = options
        self._option_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._main_btn = QPushButton(title)
        self._main_btn.setCheckable(True)
        self._main_btn.setObjectName("navButton")
        layout.addWidget(self._main_btn)

        self._popup = QFrame(None)
        self._popup.setObjectName("navHoverPopup")
        self._popup.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )

        pop_layout = QVBoxLayout(self._popup)
        pop_layout.setContentsMargins(6, 6, 6, 6)
        pop_layout.setSpacing(2)

        for text, stack_idx in options:
            btn = QPushButton(text)
            btn.setFlat(True)
            btn.setObjectName("navHoverOption")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, idx=stack_idx: self._on_option_clicked(idx))
            pop_layout.addWidget(btn)
            self._option_buttons.append(btn)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(220)
        self._hide_timer.timeout.connect(self._popup.hide)

        self._main_btn.installEventFilter(self)
        self._popup.installEventFilter(self)
        for btn in self._option_buttons:
            btn.installEventFilter(self)

        self._apply_popup_style()

    def main_button(self) -> QPushButton:
        return self._main_btn

    def _apply_popup_style(self) -> None:
        self._popup.setStyleSheet(
            """
            QFrame#navHoverPopup {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
            }
            QPushButton#navHoverOption {
                color: #2c3e50;
                background: transparent;
                border: none;
                padding: 6px 12px;
                font-size: 13px;
                text-align: left;
            }
            QPushButton#navHoverOption:hover {
                color: #27ae60;
                font-weight: 600;
            }
            """
        )

    def _show_popup(self) -> None:
        self._hide_timer.stop()
        global_pos = self._main_btn.mapToGlobal(self._main_btn.rect().bottomLeft())
        self._popup.move(global_pos)
        self._popup.show()

    def _on_option_clicked(self, stack_idx: int) -> None:
        self._popup.hide()
        self._main_btn.setChecked(True)
        self.page_requested.emit(stack_idx)

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Enter:
            self._hide_timer.stop()
            if obj == self._main_btn:
                self._show_popup()
        elif event.type() == QEvent.Type.Leave:
            self._hide_timer.start()
        return super().eventFilter(obj, event)
