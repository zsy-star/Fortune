"""我要录单弹窗（布局参照业务录单界面，功能后续实现）。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_TABLE_COLUMNS = [
    "区域",
    "投注类型",
    "订单信息",
    "复选类型",
    "计算方式",
    "金额",
    "订单总额",
    "是否自定义",
    "申报人",
    "备注",
]

_TOOLBAR_BUTTONS = [
    "去分割符",
    "订单标记",
    "去空格",
    "标记香港",
    "去小数点",
    "语义转换",
    "指定替换",
    "替换预设",
]

_CHECKBOX_LABELS = [
    "识别地区",
    "自动获取",
    "智能纠错",
    "特肖模式",
    "抄写法",
    "各->各肖",
]

_FOOTER_HINT = (
    "自助识别支持类型: <特码><平特一肖><连肖><连尾><平特一尾><三中三><二中二>"
    "<三中二><二中特><特串><平码(号码)><不中(5-24)><特码两面><特码波色>"
    "<六肖中特><包半波>"
)


class RecordOrderWindow(QMainWindow):
    """录单独立窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("我要录单")
        self.resize(1180, 720)
        self.setMinimumSize(960, 600)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._build_table_section(), stretch=5)
        root.addWidget(self._build_control_bar())
        root.addWidget(self._build_text_section(), stretch=4)
        root.addWidget(self._build_footer())

        self._apply_stylesheet()

    def _build_table_section(self) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._order_table = QTableWidget(0, len(_TABLE_COLUMNS))
        self._order_table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self._order_table.setAlternatingRowColors(True)
        self._order_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._order_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._order_table.horizontalHeader().setStretchLastSection(True)
        self._order_table.verticalHeader().setVisible(False)
        layout.addWidget(self._order_table, stretch=1)

        summary = QHBoxLayout()
        self._lbl_total = QLabel("当前总额: 0")
        self._lbl_selected_total = QLabel("当前选择总额: 0")
        summary.addWidget(self._lbl_total)
        summary.addStretch(1)
        summary.addWidget(self._lbl_selected_total)
        layout.addLayout(summary)
        return section

    def _build_control_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("controlBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        self._cmb_channel = QComboBox()
        self._cmb_channel.addItems(["个人微信", "个人支付宝", "现金", "其他"])
        self._cmb_channel.setMinimumWidth(120)

        self._radio_macau = QRadioButton("澳门 (ALT+1)")
        self._radio_hk = QRadioButton("香港 (ALT+2)")
        self._radio_macau.setChecked(True)

        self._cmb_calc = QComboBox()
        self._cmb_calc.addItems(["定总", "各数", "包肖"])
        self._cmb_calc.setMinimumWidth(100)

        layout.addWidget(self._cmb_channel)
        layout.addWidget(self._radio_macau)
        layout.addWidget(self._radio_hk)
        layout.addWidget(self._cmb_calc)
        layout.addStretch(1)
        return bar

    def _build_text_section(self) -> QGroupBox:
        group = QGroupBox()
        group.setObjectName("textProcessGroup")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        toolbar = QHBoxLayout()
        link = QLabel('<a href="#">不能识别点我</a>')
        link.setObjectName("helpLink")
        link.setOpenExternalLinks(False)
        toolbar.addWidget(link)
        toolbar.addStretch(1)

        for text in _TOOLBAR_BUTTONS:
            btn = QPushButton(text)
            btn.setObjectName("toolButton")
            btn.setEnabled(True)
            toolbar.addWidget(btn)

        outer.addLayout(toolbar)

        checks = QHBoxLayout()
        for label in _CHECKBOX_LABELS:
            cb = QCheckBox(label)
            if label in ("识别地区", "自动获取"):
                cb.setChecked(True)
            checks.addWidget(cb)
        checks.addStretch(1)
        outer.addLayout(checks)

        text_row = QHBoxLayout()
        text_row.setSpacing(6)

        self._input_text = QTextEdit()
        self._input_text.setPlaceholderText("在此输入原始订单文本…")
        self._input_text.setPlainText("猪羊马三连 500")

        self._output_text = QTextEdit()
        self._output_text.setPlaceholderText("识别结果将显示在此处…")
        self._output_text.setPlainText("澳门:3连猪羊马 各 500")
        self._output_text.setReadOnly(True)

        side_btns = QVBoxLayout()
        side_btns.setSpacing(6)
        btn_clear = QPushButton("清空结果")
        btn_add = QPushButton("添加结果")
        btn_clear.setObjectName("sideActionButton")
        btn_add.setObjectName("sideActionButton")
        btn_clear.setMinimumWidth(88)
        btn_add.setMinimumWidth(88)
        side_btns.addWidget(btn_clear)
        side_btns.addWidget(btn_add)
        side_btns.addStretch(1)

        text_row.addWidget(self._input_text, stretch=1)
        text_row.addWidget(self._output_text, stretch=1)

        side_wrap = QWidget()
        side_wrap.setLayout(side_btns)
        side_wrap.setFixedWidth(96)
        text_row.addWidget(side_wrap)

        outer.addLayout(text_row, stretch=1)
        return group

    def _build_footer(self) -> QLabel:
        label = QLabel(_FOOTER_HINT)
        label.setObjectName("footerHint")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f0f0f0;
            }
            QTableWidget {
                background-color: #ffffff;
                gridline-color: #d0d0d0;
                border: 1px solid #b0b0b0;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                padding: 6px 4px;
                border: 1px solid #c0c0c0;
                font-weight: 600;
            }
            QWidget#controlBar {
                background-color: #fafafa;
                border: 1px solid #c8c8c8;
                border-radius: 2px;
            }
            QGroupBox#textProcessGroup {
                border: 1px solid #a8a8a8;
                border-radius: 2px;
                margin-top: 4px;
                background-color: #ffffff;
            }
            QLabel#helpLink {
                color: #c0392b;
                font-size: 12px;
            }
            QPushButton#toolButton {
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton#sideActionButton {
                padding: 8px 4px;
                font-size: 12px;
            }
            QTextEdit {
                border: 1px solid #a0a0a0;
                font-family: "Microsoft YaHei", "SimSun", sans-serif;
                font-size: 13px;
            }
            QLabel#footerHint {
                color: #555555;
                font-size: 11px;
                padding: 4px 2px;
                background-color: #e8ecef;
                border: 1px solid #c5ccd3;
            }
            """
        )
