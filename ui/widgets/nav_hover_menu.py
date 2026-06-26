"""顶部导航悬停展开菜单按钮。"""

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget


class NavHoverMenuButton(QWidget):
    """主按钮可直接切页，旁边箭头/悬停展示子选项。

    早期实现把整个导航项做成 ``Qt.Popup`` 悬浮菜单：鼠标从主按钮移动到
    弹层时，按钮会立刻收到 Leave 并隐藏弹层，随后再次 Enter/Show，形成闪烁。
    当前实现把「主按钮点击」和「子菜单入口」拆开，并在隐藏前检查鼠标是否仍
    位于按钮或弹层范围内，保证菜单稳定。
    """

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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self._main_btn = QPushButton(title)
        self._main_btn.setCheckable(True)
        self._main_btn.setObjectName("navButton")
        layout.addWidget(self._main_btn)

        self._menu_btn = QPushButton("▾")
        self._menu_btn.setObjectName("navMenuArrow")
        self._menu_btn.setFixedWidth(24)
        self._menu_btn.setToolTip("展开调单子菜单")
        self._menu_btn.clicked.connect(self._toggle_popup)
        layout.addWidget(self._menu_btn)

        self._popup = QFrame(None)
        self._popup.setObjectName("navHoverPopup")
        self._popup.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self._popup.setMouseTracking(True)
        self._main_btn.clicked.connect(self._popup.hide)

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
        self._hide_timer.setInterval(180)
        self._hide_timer.timeout.connect(self._hide_popup_if_cursor_left)

        self.installEventFilter(self)
        self._main_btn.installEventFilter(self)
        self._menu_btn.installEventFilter(self)
        self._popup.installEventFilter(self)
        for btn in self._option_buttons:
            btn.installEventFilter(self)

        self._apply_popup_style()

    def main_button(self) -> QPushButton:
        return self._main_btn

    def menu_button(self) -> QPushButton:
        return self._menu_btn

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
        global_pos = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.setMinimumWidth(max(self.width(), 120))
        self._popup.move(global_pos)
        if not self._popup.isVisible():
            self._popup.show()

    def _toggle_popup(self) -> None:
        if self._popup.isVisible():
            self._popup.hide()
        else:
            self._show_popup()

    def _on_option_clicked(self, stack_idx: int) -> None:
        self._popup.hide()
        self._main_btn.setChecked(True)
        self.page_requested.emit(stack_idx)

    def _cursor_inside(self, widget: QWidget) -> bool:
        if not widget.isVisible():
            return False
        rect = widget.rect()
        top_left = widget.mapToGlobal(rect.topLeft())
        bottom_right = widget.mapToGlobal(rect.bottomRight())
        global_rect = rect.translated(top_left)
        global_rect.setBottomRight(bottom_right)
        return global_rect.adjusted(-4, -4, 4, 4).contains(QCursor.pos())

    def _hide_popup_if_cursor_left(self) -> None:
        if self._cursor_inside(self) or self._cursor_inside(self._popup):
            return
        self._popup.hide()

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Enter:
            self._hide_timer.stop()
            if obj in (self, self._main_btn, self._menu_btn):
                self._show_popup()
        elif event.type() == QEvent.Type.Leave:
            self._hide_timer.start()
        return super().eventFilter(obj, event)
