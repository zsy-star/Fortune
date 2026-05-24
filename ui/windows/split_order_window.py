"""拆单助手弹窗。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class SplitOrderWindow(QMainWindow):
    """拆单助手 V0.1 — 布局参照业务工具，逻辑后续实现。"""

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

        self._input_text = QPlainTextEdit()
        self._input_text.setPlaceholderText("输入区域，当前版本仅支持特码")
        self._input_text.setMinimumHeight(100)
        root.addWidget(self._input_text)

        recognize_box = QGroupBox("识别结果")
        recognize_layout = QVBoxLayout(recognize_box)
        self._recognize_text = QPlainTextEdit()
        self._recognize_text.setReadOnly(True)
        self._recognize_text.setMinimumHeight(72)
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

        btn_save = QPushButton("保存拆分结果到文件")
        btn_save.setObjectName("saveButton")
        btn_save.clicked.connect(self._on_save_results)
        root.addWidget(btn_save)

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

        btn_split = QPushButton("开始拆分")
        btn_style = QPushButton("调整拆分结果样式")
        btn_clear = QPushButton("清空输入")

        btn_split.clicked.connect(self._on_start_split)
        btn_clear.clicked.connect(self._on_clear_input)

        for btn in (btn_split, btn_style, btn_clear):
            btn.setObjectName("actionButton")
            row.addWidget(btn, stretch=1)

        return row

    def _on_start_split(self) -> None:
        # 占位：后续接入拆单逻辑
        raw = self._input_text.toPlainText().strip()
        if not raw:
            self._recognize_text.setPlainText("")
            self._result_text.setPlainText("")
            return
        self._recognize_text.setPlainText(raw)
        self._result_text.setPlainText("（拆分功能开发中，敬请期待）")

    def _on_clear_input(self) -> None:
        self._input_text.clear()
        self._recognize_text.clear()
        self._result_text.clear()

    def _on_save_results(self) -> None:
        # 占位：后续接入文件保存
        pass

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
            QRadioButton, QLabel {
                font-size: 13px;
            }
            """
        )
