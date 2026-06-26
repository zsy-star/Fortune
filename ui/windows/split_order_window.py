"""拆单助手弹窗。"""

from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

SPLIT_ORDER_SCOPE_MESSAGE = (
    "拆单助手第一阶段仅用于文本整理：去空行、压缩空格、按逗号/顿号/分号拆成多行。"
    "本工具不会保存订单、不会写数据库、不会参与结算，也不计算金额或复杂玩法拆单规则。"
)
_SPLIT_PATTERN = re.compile(r"[，、；;,]+")


class SplitOrderWindow(QMainWindow):
    """拆单助手 V0.1 — 只做低风险文本整理和拆行。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("拆单助手 V0.1")
        self.resize(520, 640)
        self.setMinimumSize(460, 560)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._result_lines: list[str] = []
        self._numbered = False

        self._scope_hint = QLabel(SPLIT_ORDER_SCOPE_MESSAGE)
        self._scope_hint.setObjectName("scopeHint")
        self._scope_hint.setWordWrap(True)
        root.addWidget(self._scope_hint)

        self._input_text = QPlainTextEdit()
        self._input_text.setPlaceholderText("粘贴需要整理的文本；会按逗号、顿号、分号拆成多行")
        self._input_text.setMinimumHeight(100)
        root.addWidget(self._input_text)

        recognize_box = QGroupBox("识别结果")
        recognize_layout = QVBoxLayout(recognize_box)
        self._recognize_text = QPlainTextEdit()
        self._recognize_text.setReadOnly(True)
        self._recognize_text.setMinimumHeight(72)
        self._recognize_text.setPlainText("等待拆分。第一阶段只整理文本，不识别玩法、不计算金额。")
        recognize_layout.addWidget(self._recognize_text)
        root.addWidget(recognize_box)

        root.addLayout(self._build_config_row())
        root.addLayout(self._build_action_row())

        result_box = QGroupBox("拆分结果区域")
        result_layout = QVBoxLayout(result_box)
        self._result_text = QPlainTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setMinimumHeight(140)
        result_layout.addWidget(self._result_text)
        root.addWidget(result_box, stretch=1)

        self._btn_save = QPushButton("保存拆分结果到文件")
        self._btn_save.setObjectName("saveButton")
        self._btn_save.clicked.connect(self._on_save_results)
        root.addWidget(self._btn_save)

        self._apply_stylesheet()

    def _build_config_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        row.addWidget(QLabel("单个号码最大金额："))
        self._edit_max_amount = QLineEdit("20")
        self._edit_max_amount.setFixedWidth(80)
        self._edit_max_amount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._edit_max_amount)

        row.addSpacing(16)

        self._region_group = QButtonGroup(self)
        region_specs = [
            ("不要地区标识", 0, True),
            ("澳门", 1, False),
            ("香港", 2, False),
        ]
        for text, idx, checked in region_specs:
            rb = QRadioButton(text)
            rb.setChecked(checked)
            self._region_group.addButton(rb, idx)
            row.addWidget(rb)

        row.addStretch(1)
        return row

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._btn_split = QPushButton("开始拆分")
        self._btn_style = QPushButton("调整拆分结果样式")
        self._btn_copy = QPushButton("复制结果")
        btn_clear = QPushButton("清空输入")

        self._btn_split.clicked.connect(self._on_start_split)
        self._btn_style.clicked.connect(self._on_toggle_numbered_style)
        self._btn_copy.clicked.connect(self._on_copy_results)
        btn_clear.clicked.connect(self._on_clear_input)

        for btn in (self._btn_split, self._btn_style, self._btn_copy, btn_clear):
            btn.setObjectName("actionButton")
            row.addWidget(btn, stretch=1)

        return row

    def _on_start_split(self) -> None:
        raw = self._input_text.toPlainText()
        if not raw.strip():
            self._set_status("请输入需要拆分的内容")
            QMessageBox.warning(self, "拆单助手", "请输入需要拆分的内容")
            return
        self._result_lines = self._split_text(raw)
        self._numbered = False
        self._render_results()
        self._set_status(f"拆分完成：共 {len(self._result_lines)} 行。未写入订单数据库。")

    def _split_text(self, raw: str) -> list[str]:
        lines: list[str] = []
        for source_line in raw.splitlines():
            stripped_line = source_line.strip()
            if not stripped_line:
                continue
            for part in _SPLIT_PATTERN.split(stripped_line):
                cleaned = re.sub(r"\s+", " ", part.strip())
                if cleaned:
                    lines.append(cleaned)
        return lines

    def _render_results(self) -> None:
        if self._numbered:
            text = "\n".join(f"{index}. {line}" for index, line in enumerate(self._result_lines, start=1))
        else:
            text = "\n".join(self._result_lines)
        self._result_text.setPlainText(text)

    def _set_status(self, message: str) -> None:
        self._recognize_text.setPlainText(message)

    def _on_toggle_numbered_style(self) -> None:
        if not self._result_lines:
            self._set_status("没有可调整样式的拆分结果")
            QMessageBox.information(self, "拆单助手", "没有可调整样式的拆分结果")
            return
        self._numbered = not self._numbered
        self._render_results()
        self._set_status("已添加行号样式" if self._numbered else "已取消行号样式")

    def _on_clear_input(self) -> None:
        self._input_text.clear()
        self._recognize_text.clear()
        self._result_text.clear()
        self._result_lines = []
        self._numbered = False

    def _on_save_results(self) -> None:
        text = self._result_text.toPlainText().strip()
        if not text:
            self._set_status("没有可保存的拆分结果")
            QMessageBox.warning(self, "拆单助手", "没有可保存的拆分结果")
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "保存拆分结果",
            "split_order_result.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            self._set_status("已取消保存")
            return
        try:
            Path(path).write_text(text + "\n", encoding="utf-8")
        except Exception as exc:
            self._set_status(f"保存失败：{exc}")
            QMessageBox.warning(self, "拆单助手", f"保存失败：{exc}")
            return
        self._set_status(f"保存成功：{path}")
        QMessageBox.information(self, "拆单助手", f"保存成功：{path}")

    def _on_copy_results(self) -> None:
        text = self._result_text.toPlainText().strip()
        if not text:
            self._set_status("没有可复制的拆分结果")
            QMessageBox.warning(self, "拆单助手", "没有可复制的拆分结果")
            return
        QApplication.clipboard().setText(text)
        self._set_status("拆分结果已复制到剪贴板")
        QMessageBox.information(self, "拆单助手", "拆分结果已复制到剪贴板")

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f0f0f0;
            }
            QPlainTextEdit, QLineEdit {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                font-size: 13px;
                padding: 6px;
            }
            QGroupBox {
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                margin-top: 10px;
                padding-top: 12px;
                background: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton#actionButton {
                padding: 8px 12px;
                background: #ecf0f1;
                border: 1px solid #bdc3c7;
                font-size: 13px;
            }
            QPushButton#actionButton:hover {
                background: #dfe6e9;
            }
            QPushButton#saveButton {
                padding: 10px;
                background: #ecf0f1;
                border: 1px solid #95a5a6;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#saveButton:hover {
                background: #dfe6e9;
            }
            QLabel#scopeHint {
                color: #7f8c8d;
                font-size: 13px;
                padding: 8px;
                border: 1px solid #d5d8dc;
                background: #f8f9fa;
            }
            QRadioButton, QLabel {
                font-size: 13px;
            }
            """
        )
