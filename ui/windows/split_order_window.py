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

from ui.unavailable import mark_unavailable, unavailable_text


SPLIT_ORDER_UNAVAILABLE_MESSAGE = unavailable_text(
    "拆单助手",
    "拆单需要先完成金额拆分规则、保存格式和操作审计，当前测试版仅保留入口。",
    "当前请在录单窗口保存原始订单，避免产生未审计的拆分结果。",
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

        self._scope_hint = QLabel(SPLIT_ORDER_UNAVAILABLE_MESSAGE)
        self._scope_hint.setObjectName("scopeHint")
        self._scope_hint.setWordWrap(True)
        root.addWidget(self._scope_hint)

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

        self._btn_save = QPushButton("保存拆分结果到文件")
        self._btn_save.setObjectName("saveButton")
        mark_unavailable(self._btn_save)
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
        btn_clear = QPushButton("清空输入")

        self._btn_split.clicked.connect(self._on_start_split)
        self._btn_style.clicked.connect(self._on_style_disabled)
        btn_clear.clicked.connect(self._on_clear_input)

        for btn in (self._btn_split, self._btn_style):
            mark_unavailable(btn)

        for btn in (self._btn_split, self._btn_style, btn_clear):
            btn.setObjectName("actionButton")
            row.addWidget(btn, stretch=1)

        return row

    def _on_start_split(self) -> None:
        self._recognize_text.setPlainText("")
        self._result_text.setPlainText(SPLIT_ORDER_UNAVAILABLE_MESSAGE)

    def _on_style_disabled(self) -> None:
        self._result_text.setPlainText(
            unavailable_text(
                "拆分结果样式调整",
                "样式调整依赖拆单结果，当前测试版未生成可保存的拆分数据。",
            )
        )

    def _on_clear_input(self) -> None:
        self._input_text.clear()
        self._recognize_text.clear()
        self._result_text.clear()

    def _on_save_results(self) -> None:
        self._result_text.setPlainText(
            unavailable_text(
                "保存拆分结果到文件",
                "当前没有已审计的拆分结果可保存，保存入口保持禁用。",
            )
        )

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
