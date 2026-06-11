"""我要录单弹窗（布局参照业务录单界面，功能后续实现）。"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.order_parser import format_result, parse_lines

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

        # ── 剪贴板自动粘贴（定时轮询 + 窗口激活兜底）──
        self._last_clipboard_text = ""
        self._clipboard = QApplication.clipboard()

        # 定时器每 500ms 检查一次剪贴板
        self._clip_timer = QTimer(self)
        self._clip_timer.setInterval(500)
        self._clip_timer.timeout.connect(self._poll_clipboard)
        self._clip_timer.start()

        # ── 输入解析（300ms 防抖后自动解析）──
        self._parsed_results: list = []
        self._parse_timer = QTimer(self)
        self._parse_timer.setSingleShot(True)
        self._parse_timer.setInterval(300)
        self._parse_timer.timeout.connect(self._do_parse)

        self._apply_stylesheet()

    # ─────────────────── 剪贴板监控 ───────────────────

    def _poll_clipboard(self) -> None:
        """定时检查系统剪贴板，有新文本则填入输入框。"""
        if not getattr(self, "_chk_auto_fetch", None):
            return
        if not self._chk_auto_fetch.isChecked():
            return

        # 直接读取系统剪贴板纯文本
        clip = self._clipboard
        text = clip.text().strip() if clip.mimeData().hasText() else ""
        if not text or text == self._last_clipboard_text:
            return

        self._last_clipboard_text = text

        existing = self._input_text.toPlainText().strip()
        if existing:
            self._input_text.setPlainText(existing + "\n" + text)
        else:
            self._input_text.setPlainText(text)

    def changeEvent(self, event) -> None:
        """窗口获得焦点时立刻检查剪贴板（无需等定时器）。"""
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._poll_clipboard()
        super().changeEvent(event)

    # ─────────────────── 订单解析 ───────────────────

    def _on_input_changed(self) -> None:
        """输入框文本变化时重启防抖定时器。"""
        self._parse_timer.start()  # setSingleShot=True, 每次调用重置倒计时

    def _do_parse(self) -> None:
        """解析输入框中的全部文本，将结果显示到输出框。"""
        raw = self._input_text.toPlainText()
        if not raw.strip():
            self._output_text.clear()
            self._parsed_results = []
            return

        results = parse_lines(raw)
        self._parsed_results = [r for r in results if r.success]

        # 注入默认地域：输入未指定时取当前勾选的地区
        default_region = "澳门" if self._radio_macau.isChecked() else "香港"
        for r in results:
            if r.success and not r.region:
                r.region = default_region

        # 显示结果（每条订单之间空行分隔）
        blocks: list[str] = []
        for r in results:
            blocks.append(format_result(r))
        self._output_text.setPlainText("\n\n".join(blocks))

    def _on_clear_output(self) -> None:
        """清空输入和输出。"""
        self._input_text.clear()
        self._output_text.clear()
        self._parsed_results = []

    def _on_add_result(self) -> None:
        """将成功解析的订单添加到上方表格。"""
        if not self._parsed_results:
            return

        region = "澳门" if self._radio_macau.isChecked() else "香港"
        reporter = self._cmb_channel.currentText()
        calc_method = self._cmb_calc.currentText()

        for r in self._parsed_results:
            for num in r.numbers:
                row = self._order_table.rowCount()
                self._order_table.insertRow(row)
                items = [
                    QTableWidgetItem(region),  # 区域
                    QTableWidgetItem("特码"),  # 投注类型
                    QTableWidgetItem(str(num)),  # 订单信息
                    QTableWidgetItem(""),  # 复选类型
                    QTableWidgetItem(calc_method),  # 计算方式
                    QTableWidgetItem(f"{r.amount:g}"),  # 金额
                    QTableWidgetItem(f"{r.amount:g}"),  # 订单总额
                    QTableWidgetItem("标准"),  # 是否自定义
                    QTableWidgetItem(reporter),  # 申报人
                    QTableWidgetItem(""),  # 备注
                ]
                for col, item in enumerate(items):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._order_table.setItem(row, col, item)

        # 更新总额
        self._update_order_totals()

    def _update_order_totals(self) -> None:
        """更新订单表中的总额标签。"""
        total = 0.0
        for row in range(self._order_table.rowCount()):
            item = self._order_table.item(row, 5)  # "金额" 列
            if item:
                try:
                    total += float(item.text())
                except ValueError:
                    pass
        self._lbl_total.setText(f"当前总额: {total:g}")

    # ─────────────────── UI 构建 ───────────────────

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
            if label == "自动获取":
                cb.setObjectName("autoFetchCheck")
                self._chk_auto_fetch = cb
            checks.addWidget(cb)
        checks.addStretch(1)
        outer.addLayout(checks)

        text_row = QHBoxLayout()
        text_row.setSpacing(6)

        self._input_text = QTextEdit()
        self._input_text.setPlaceholderText("在此输入原始订单文本…\n格式: <类别>各数<金额>  如: 兔各数20")
        self._input_text.textChanged.connect(self._on_input_changed)

        self._output_text = QTextEdit()
        self._output_text.setPlaceholderText("展开结果将显示在此处…")
        self._output_text.setReadOnly(True)

        side_btns = QVBoxLayout()
        side_btns.setSpacing(6)
        btn_clear = QPushButton("清空结果")
        btn_add = QPushButton("添加结果")
        btn_clear.setObjectName("sideActionButton")
        btn_add.setObjectName("sideActionButton")
        btn_clear.setMinimumWidth(88)
        btn_add.setMinimumWidth(88)
        btn_clear.clicked.connect(self._on_clear_output)
        btn_add.clicked.connect(self._on_add_result)
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
