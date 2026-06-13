"""辅助工具页面。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from schemas.database_backup_schema import DatabaseBackupInfo
from services.database_backup_service import DatabaseBackupService
from ui.windows import CalculatorWindow, SplitOrderWindow


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def _dash(value: object | None) -> str:
    return str(value) if value not in (None, "") else "-"


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
    def __init__(self, parent=None, backup_service: DatabaseBackupService | None = None):
        super().__init__(parent)
        self._backup_service = backup_service or DatabaseBackupService()
        self._backup_rows: list[DatabaseBackupInfo] = []
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
        root.addWidget(self._build_backup_panel())
        root.addStretch(1)
        self._footer_box = self._build_footer_box()
        root.addWidget(self._footer_box)

        self._apply_stylesheet()
        self._reload_backups()

    def _build_backup_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("backupPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        title = QLabel("数据库备份 / 恢复")
        title.setObjectName("backupTitle")
        hint = QLabel("恢复会覆盖当前数据库。恢复前系统会自动备份当前库，成功后建议重启软件。")
        hint.setObjectName("backupHint")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)

        action_row = QHBoxLayout()
        self._btn_create_backup = QPushButton("立即备份")
        self._btn_refresh_backups = QPushButton("刷新备份列表")
        self._btn_restore_backup = QPushButton("从备份恢复")
        self._btn_create_backup.clicked.connect(self._on_create_backup)
        self._btn_refresh_backups.clicked.connect(self._reload_backups)
        self._btn_restore_backup.clicked.connect(self._on_restore_backup)
        action_row.addWidget(self._btn_create_backup)
        action_row.addWidget(self._btn_refresh_backups)
        action_row.addWidget(self._btn_restore_backup)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self._backup_table = QTableWidget(0, 5)
        self._backup_table.setHorizontalHeaderLabels(["备份文件名", "创建时间", "文件大小", "备份原因", "路径"])
        self._backup_table.verticalHeader().setVisible(False)
        self._backup_table.setAlternatingRowColors(True)
        self._backup_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._backup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._backup_table.itemSelectionChanged.connect(self._on_backup_selection_changed)
        header = self._backup_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._backup_table)

        self._backup_status = QLabel("")
        self._backup_status.setObjectName("backupStatus")
        self._backup_status.setWordWrap(True)
        layout.addWidget(self._backup_status)
        return frame

    def _build_footer_box(self) -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setObjectName("comingSoonBox")
        box.setPlainText("其他功能，陆续开放中，敬请期待")
        box.setMinimumHeight(160)
        return box

    def _reload_backups(self) -> None:
        try:
            self._backup_rows = self._backup_service.list_backups()
        except Exception as exc:
            self._backup_rows = []
            self._backup_table.setRowCount(0)
            self._backup_status.setText(f"备份列表加载失败：{exc}")
            return
        self._fill_backup_table()
        if self._backup_rows:
            self._backup_status.setText(f"已加载 {len(self._backup_rows)} 个备份")
        else:
            self._backup_status.setText("暂无备份文件")

    def _fill_backup_table(self) -> None:
        self._backup_table.setRowCount(len(self._backup_rows))
        for row_idx, backup in enumerate(self._backup_rows):
            values = [
                backup.backup_name,
                backup.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                _format_size(backup.size_bytes),
                _dash(backup.reason),
                str(backup.backup_path),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft if col_idx in (0, 4) else Qt.AlignmentFlag.AlignCenter)
                if col_idx == 4:
                    item.setToolTip(value)
                self._backup_table.setItem(row_idx, col_idx, item)

    def _selected_backup(self) -> DatabaseBackupInfo | None:
        selected = self._backup_table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        if row < 0 or row >= len(self._backup_rows):
            return None
        return self._backup_rows[row]

    def _on_backup_selection_changed(self) -> None:
        backup = self._selected_backup()
        if backup is not None:
            self._backup_status.setText(f"已选择备份：{backup.backup_name}")

    def _on_create_backup(self) -> None:
        try:
            info = self._backup_service.create_backup(reason="manual_ui")
        except Exception as exc:
            QMessageBox.warning(self, "数据库备份", f"备份失败：{exc}")
            self._backup_status.setText(f"备份失败：{exc}")
            return
        self._reload_backups()
        message = (
            "备份成功\n"
            f"备份文件名：{info.backup_name}\n"
            f"大小：{_format_size(info.size_bytes)}\n"
            f"路径：{info.backup_path}"
        )
        self._backup_status.setText(message)
        QMessageBox.information(self, "数据库备份", message)

    def _on_restore_backup(self) -> None:
        backup = self._selected_backup()
        if backup is None:
            QMessageBox.warning(self, "数据库恢复", "请先选择一个备份文件")
            self._backup_status.setText("请先选择一个备份文件")
            return

        confirm_text = (
            "恢复备份会覆盖当前数据库。\n"
            "恢复前系统会自动备份当前数据库。\n"
            "建议确认没有其他窗口正在操作数据。\n"
            "恢复成功后建议重启软件。\n\n"
            f"备份文件名：{backup.backup_name}\n"
            f"创建时间：{backup.created_at:%Y-%m-%d %H:%M:%S}\n"
            f"文件大小：{_format_size(backup.size_bytes)}"
        )
        choice = QMessageBox.question(
            self,
            "确认恢复数据库",
            confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            self._backup_status.setText("已取消恢复操作")
            return

        try:
            result = self._backup_service.restore_backup(backup.backup_path, confirm=True)
        except Exception as exc:
            QMessageBox.warning(self, "数据库恢复", f"恢复失败：{exc}")
            self._backup_status.setText(f"恢复失败：{exc}")
            return

        self._reload_backups()
        message = (
            "恢复成功，建议重启软件后继续使用\n"
            f"恢复来源：{result.restored_from}\n"
            f"恢复前自动备份路径：{result.pre_restore_backup_path}"
        )
        self._backup_status.setText(message)
        QMessageBox.information(self, "数据库恢复", message)

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
            QFrame#backupPanel {
                border: 1px solid #d5d8dc;
                background: #ffffff;
            }
            QLabel#toolTitle {
                color: #27ae60;
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#backupTitle {
                color: #2c3e50;
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#backupHint, QLabel#backupStatus {
                color: #7f8c8d;
                font-size: 13px;
            }
            QPushButton {
                color: #1a5276;
                border: 1px solid #bdc3c7;
                padding: 5px 10px;
                font-size: 13px;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #ebf5fb;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #bdc3c7;
                gridline-color: #d5d8dc;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #ecf0f1;
                padding: 6px 4px;
                border: 1px solid #bdc3c7;
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
