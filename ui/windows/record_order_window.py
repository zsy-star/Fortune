"""我要录单弹窗（布局参照业务录单界面，功能后续实现）。"""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from schemas.order_intake_schema import IntakeMetadata, IntakeTableRow
from services.order_intake_service import OrderIntakeService
from services.order_parser import format_result, parse_lines
from services.settings_service import SettingsService
from ui.app_events import app_events
from ui.unavailable import UNAVAILABLE_TOOLTIP

_TABLE_COLUMNS = [
    "区域",
    "投注类型",
    "订单信息",
    "复选类型",
    "计算方式",
    "金额",
    "每号金额",
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
    "当前测试版重点支持特码类录入和结算；"
    "其他玩法可能可录入，但暂不保证结算；"
    "未开放选项已禁用，不会影响当前录单保存。"
)

_UNAVAILABLE_CHECKBOXES = {"识别地区", "智能纠错", "特肖模式", "抄写法", "各->各肖"}


class RecordOrderWindow(QMainWindow):
    """录单独立窗口。"""

    def __init__(
        self,
        parent=None,
        order_intake_service: OrderIntakeService | None = None,
        settings_service: SettingsService | None = None,
    ):
        super().__init__(parent)
        self._order_intake_service = order_intake_service or OrderIntakeService()
        self._settings_service = settings_service or SettingsService()
        self._declarer_plans: dict[str, str | None] = {}
        self._declarer_config_load_failed = False
        self._table_user_adjusted = False
        self._table_loading = False
        self.setWindowTitle("我要录单")
        self.resize(1280, 840)
        self.setMinimumSize(1024, 680)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 垂直分割器：表格区 ↔ 控制栏+文本区 ──
        text_panel = QWidget()
        tp_layout = QVBoxLayout(text_panel)
        tp_layout.setContentsMargins(0, 0, 0, 0)
        tp_layout.setSpacing(4)
        tp_layout.addWidget(self._build_control_bar())
        tp_layout.addWidget(self._build_text_section(), stretch=1)

        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.setChildrenCollapsible(False)
        v_splitter.addWidget(self._build_table_section())
        v_splitter.addWidget(text_panel)
        v_splitter.setStretchFactor(0, 7)
        v_splitter.setStretchFactor(1, 3)

        root.addWidget(v_splitter, stretch=1)
        root.addWidget(self._build_footer())

        # ── 剪贴板自动粘贴（信号驱动 + 窗口激活兜底）──
        self._last_clipboard_text = ""
        self._clipboard = QApplication.clipboard()
        self._clip_mode_append = True  # True=追加, False=替换
        self._clipboard.dataChanged.connect(self._poll_clipboard)

        # ── 输入解析（300ms 防抖后自动解析）──
        self._parsed_results: list = []
        self._last_parse_results: list = []
        self._last_parse_raw = ""
        self._replace_presets: list[tuple[str, str]] = []  # (查找, 替换)
        self._parse_timer = QTimer(self)
        self._parse_timer.setSingleShot(True)
        self._parse_timer.setInterval(300)
        self._parse_timer.timeout.connect(self._do_parse)

        self._apply_stylesheet()
        self._apply_font_scale()
        self.reload_declarers()

    # ─────────────────── 窗口缩放 → 字体自适应 ───────────────────

    def _apply_font_scale(self) -> None:
        """根据当前窗口高度设置输入/输出框的原生字号（12‒22px）。

        使用 QFont.setPixelSize() 而非 QSS，因为 QSS 的字号会被 QTextEdit
        内部文档层的默认样式覆盖；setPixelSize 走原生渲染管线，不受 QSS 干扰。
        """
        h = self.height()
        clamped = max(680, min(1440, h))
        size = int(12 + (clamped - 680) * (22 - 12) / (1440 - 680))

        font = self._input_text.font()
        font.setPixelSize(size)
        self._input_text.setFont(font)
        self._output_text.setFont(font)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_input_text"):
            self._apply_font_scale()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload_declarers()

    # ─────────────────── 剪贴板监控 ───────────────────

    def _poll_clipboard(self) -> None:
        """剪贴板变化时自动填入输入框（信号驱动）。"""
        if not getattr(self, "_chk_auto_fetch", None):
            return
        if not self._chk_auto_fetch.isChecked():
            return

        # 直接读取系统剪贴板纯文本
        clip = self._clipboard
        mime_data = clip.mimeData()
        if mime_data is None:
            return
        text = clip.text().strip() if mime_data.hasText() else ""
        if not text or text == self._last_clipboard_text:
            return

        self._last_clipboard_text = text

        existing = self._input_text.toPlainText()
        # 去重：内容已存在则跳过
        if text in existing:
            return

        if self._clip_mode_append and existing.strip():
            self._input_text.setPlainText(existing.rstrip() + "\n" + text)
        else:
            self._input_text.setPlainText(text)

    def _on_toggle_clip_mode(self) -> None:
        """切换剪贴板模式：追加 ↔ 替换。"""
        self._clip_mode_append = not self._clip_mode_append
        self._btn_clip_mode.setText("[追加]" if self._clip_mode_append else "[替换]")

    def changeEvent(self, event) -> None:
        """窗口获得焦点时立刻检查剪贴板（无需等定时器）。"""
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.reload_declarers()
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
            self._last_parse_results = []
            self._last_parse_raw = ""
            return

        # 自动应用替换预设
        raw = self._apply_replace_presets(raw)
        self._last_parse_raw = raw

        results = parse_lines(raw)
        # 回填每行的原始输入文本
        raw_lines = [l.strip() for l in raw.splitlines() if l.strip()]
        for r, line in zip(results, raw_lines):
            r.original_text = line

        self._parsed_results = [r for r in results if r.success]
        self._last_parse_results = results

        # 注入默认地域：输入未指定时取当前勾选的地区
        default_region = "澳门" if self._radio_macau.isChecked() else "香港"
        for r in results:
            if r.success and not r.region:
                r.region = default_region

        # 显示结果（错误行红色，其余保持纯文本格式）
        blocks: list[str] = []
        for r in results:
            text = format_result(r)
            # 转义 HTML 特殊字符
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if not r.success:
                text = f"<span style='color:red;'>{text}</span>"
            blocks.append(text)
        html = "<pre style='margin:0;'>" + "\n\n".join(blocks) + "</pre>"
        self._output_text.setHtml(html)

    def _on_clear_output(self) -> None:
        """清空输入、输出、表格及解析状态。"""
        self._input_text.clear()
        self._output_text.clear()
        self._parsed_results = []
        self._last_parse_results = []
        self._last_parse_raw = ""
        # 清空表格内容（保留地区/渠道/计算方式）
        self._order_table.setRowCount(0)
        self._lbl_total.setText("当前总额: 0")
        self._lbl_selected_total.setText("当前选择总额: 0")
        self._table_user_adjusted = False

    def _on_add_result(self) -> None:
        """将成功解析的订单添加到上方表格——每个解析结果一行。"""
        if not self._parsed_results:
            return

        region = "澳门" if self._radio_macau.isChecked() else "香港"
        reporter = self._selected_declarer_name() or "未设置"
        calc_method = self._cmb_calc.currentText()

        self._table_loading = True
        try:
            for r in self._parsed_results:
                row = self._order_table.rowCount()
                self._order_table.insertRow(row)
                # 号码用逗号拼接，如 01,02,03
                nums_text = ",".join(f"{n:02d}" for n in r.numbers)
                items = [
                    QTableWidgetItem(region),  # 区域
                    QTableWidgetItem("特码"),  # 投注类型
                    QTableWidgetItem(nums_text),  # 订单信息
                    QTableWidgetItem(""),  # 复选类型
                    QTableWidgetItem(calc_method),  # 计算方式
                    QTableWidgetItem(f"{r.total:g}"),  # 金额（总金额）
                    QTableWidgetItem(f"{r.amount:g}"),  # 每号金额
                    QTableWidgetItem("标准"),  # 是否自定义
                    QTableWidgetItem(reporter),  # 申报人
                    QTableWidgetItem(r.original_text),  # 备注
                ]
                for col, item in enumerate(items):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._order_table.setItem(row, col, item)
        finally:
            self._table_loading = False

        # 更新总额
        self._update_order_totals()

    def _current_region(self) -> str:
        return "澳门" if self._radio_macau.isChecked() else "香港"

    def _current_raw_text_for_save(self) -> str:
        return self._apply_replace_presets(self._input_text.toPlainText())

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "保存订单", message)

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, "保存订单", message)

    def _confirm_warning(self, message: str) -> bool:
        result = QMessageBox.question(
            self,
            "保存订单",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def _on_save_order(self) -> None:
        """通过 OrderIntakeService 保存当前解析成功的原始订单文本。"""
        raw = self._current_raw_text_for_save()
        if not raw.strip() and self._order_table.rowCount() == 0:
            self._show_warning("请输入订单内容")
            return

        if self._table_user_adjusted:
            save_result = self._save_adjusted_table(raw)
            if save_result is None:
                return
            order = save_result.order
            message = "订单保存成功"
            if order is not None:
                message = f"订单保存成功：{order.order_no} (ID: {order.id})"
            self._emit_order_saved_events()
            self._show_info(message)
            self._on_clear_output()
            return

        if raw != self._last_parse_raw or not self._last_parse_results:
            self._show_warning("请先解析订单内容")
            return

        failed_results = [r for r in self._last_parse_results if not r.success]
        if failed_results:
            errors = [r.error or "解析失败" for r in failed_results]
            self._show_warning("\n".join(errors))
            return

        if not self._parsed_results:
            self._show_warning("请先解析订单内容")
            return

        try:
            preview = self._order_intake_service.preview_raw_text(
                raw,
                customer_name=self._selected_declarer_name(),
                config_plan_name=self._selected_config_plan_name(),
                channel=self._cmb_channel.currentText(),
                region=self._current_region(),
                source="record_window",
            )
            if not preview.can_save:
                reason = "\n".join(preview.errors) if preview.errors else "预览结果不可保存"
                self._show_warning(reason)
                return

            if preview.warnings:
                warning_text = "保存前请确认以下提示：\n" + "\n".join(preview.warnings)
                if not self._confirm_warning(warning_text):
                    return

            save_result = self._order_intake_service.save_preview(preview)
            if not save_result.success:
                self._show_warning(save_result.error or "订单保存失败")
                return
        except Exception as exc:
            self._show_warning(f"订单保存失败：{exc}")
            return

        order = save_result.order
        message = "订单保存成功"
        if order is not None:
            message = f"订单保存成功：{order.order_no} (ID: {order.id})"
        self._emit_order_saved_events()
        self._show_info(message)
        self._on_clear_output()

    def _emit_order_saved_events(self) -> None:
        app_events.orders_changed.emit()
        app_events.logs_changed.emit()

    def _save_adjusted_table(self, raw: str):
        rows = self._table_rows_for_save()
        if not rows:
            self._show_warning("表格没有可保存的订单明细")
            return None

        try:
            preview = self._order_intake_service.preview_table_rows(
                rows,
                IntakeMetadata(
                    customer_name=self._selected_declarer_name(),
                    config_plan_name=self._selected_config_plan_name(),
                    channel=self._cmb_channel.currentText(),
                    region=self._current_region(),
                    source="record_window_adjusted",
                    raw_text=raw,
                ),
            )
        except Exception as exc:
            self._show_warning(f"表格数据校验失败：{exc}")
            return None

        if not preview.can_save:
            reason = "\n".join(preview.errors) if preview.errors else "表格数据不可保存"
            self._show_warning(reason)
            return None

        if preview.warnings:
            warning_text = "保存前请确认以下提示：\n" + "\n".join(preview.warnings)
            if not self._confirm_warning(warning_text):
                return None

        save_result = self._order_intake_service.save_preview(preview)
        if not save_result.success:
            self._show_warning(save_result.error or "订单保存失败")
            return None
        return save_result

    def _table_rows_for_save(self) -> list[IntakeTableRow]:
        rows: list[IntakeTableRow] = []
        for row in range(self._order_table.rowCount()):
            rows.append(
                IntakeTableRow(
                    row_number=row + 1,
                    region=self._table_text(row, 0),
                    bet_type=self._table_text(row, 1),
                    selection=self._table_text(row, 2),
                    total_amount=self._table_text(row, 5),
                    per_item_amount=self._table_text(row, 6),
                    note=self._table_text(row, 9),
                    source_line=self._table_text(row, 9) or None,
                )
            )
        return rows

    def _table_text(self, row: int, column: int) -> str:
        item = self._order_table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _update_order_totals(self) -> None:
        """更新订单表中的总额标签。"""
        total = Decimal("0")
        for row in range(self._order_table.rowCount()):
            item = self._order_table.item(row, 5)  # "金额" 列
            if item:
                try:
                    total += Decimal(item.text().strip())
                except (InvalidOperation, ValueError):
                    pass
        self._lbl_total.setText(f"当前总额: {total:g}")

    def _on_delete_selected(self) -> None:
        """删除表格中选中的行，并重新计算总额。"""
        rows = {idx.row() for idx in self._order_table.selectedIndexes()}
        if not rows:
            return  # 无选中行，静默返回

        # 从高到低删除，避免索引偏移
        for row in sorted(rows, reverse=True):
            self._order_table.removeRow(row)

        self._table_user_adjusted = True
        self._update_order_totals()

    def _on_table_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._table_loading:
            return
        self._table_user_adjusted = True
        self._update_order_totals()

    def _on_remove_separators(self) -> None:
        """去分隔符：规范化输入文本中的数字分隔符。"""
        import re

        raw = self._input_text.toPlainText()
        if not raw.strip():
            return

        lines: list[str] = []
        for line in raw.splitlines():
            # 中文逗号 / 顿号 / 斜杠 → 英文逗号
            line = line.replace("，", ",").replace("、", ",").replace("/", ",")
            # 去掉逗号两侧空格
            line = re.sub(r"\s*,\s*", ",", line)
            # 相邻汉字之间的空格移除（如「澳 门」→「澳门」）
            line = re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", line)
            # 去掉「各/各数」前后的空格
            line = re.sub(r"\s*(各(?:数)?)\s*", r"\1", line)
            # 合并剩余连续空格
            line = re.sub(r"\s+", " ", line)
            lines.append(line.strip())

        self._input_text.setPlainText("\n".join(lines))
        # textChanged 信号会自动触发 _on_input_changed → 防抖解析

    def _on_order_mark(self) -> None:
        """订单标记：弹出对话框输入标记文字，为每条非空行添加前缀。"""
        mark, ok = QInputDialog.getText(
            self, "订单标记", "请输入标记文字（将添加到每条订单前面）："
        )
        if not ok or not mark.strip():
            return  # 取消或空输入，不做任何改动

        mark = mark.strip()
        raw = self._input_text.toPlainText()
        lines: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(f"{mark} {stripped}")
            else:
                lines.append(line)  # 保留空行
        self._input_text.setPlainText("\n".join(lines))
        # textChanged 信号会自动触发 _on_input_changed → 防抖解析

    def _on_remove_spaces(self) -> None:
        """去空格：移除输入文本中的所有空白字符。"""
        import re

        raw = self._input_text.toPlainText()
        if not raw.strip():
            return

        lines: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped:
                # 移除行内所有空白
                lines.append(re.sub(r"\s+", "", stripped))
            else:
                lines.append("")
        self._input_text.setPlainText("\n".join(lines))
        # textChanged 信号会自动触发 _on_input_changed → 防抖解析

    def _on_mark_hk(self) -> None:
        """标记香港：将每条订单的地域设为香港。"""
        raw = self._input_text.toPlainText()
        lines: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append(line)
                continue
            if stripped.startswith("澳门"):
                stripped = "香港" + stripped[2:]
            elif not stripped.startswith("香港"):
                stripped = "香港 " + stripped
            lines.append(stripped)
        self._input_text.setPlainText("\n".join(lines))
        # 同时切换地区单选按钮
        self._radio_hk.setChecked(True)
        # textChanged 信号会自动触发 _on_input_changed → 防抖解析

    def _on_remove_decimal(self) -> None:
        """去小数点：将小数点替换为空格，用作号码分隔符。"""
        raw = self._input_text.toPlainText()
        if not raw.strip():
            return

        lines: list[str] = []
        for line in raw.splitlines():
            line = line.replace(".", " ")
            lines.append(line)
        self._input_text.setPlainText("\n".join(lines))
        # textChanged 信号会自动触发 _on_input_changed → 防抖解析

    def _on_semantic_convert(self) -> None:
        """语义转换：全角→半角 + 中文数字→阿拉伯数字。"""
        import re

        raw = self._input_text.toPlainText()
        if not raw.strip():
            return

        # ── 全角 → 半角 ──
        def _full_to_half(text: str) -> str:
            result: list[str] = []
            for ch in text:
                code = ord(ch)
                if 0xFF01 <= code <= 0xFF5E:
                    result.append(chr(code - 0xFEE0))
                elif code == 0x3000:  # 全角空格
                    result.append(" ")
                else:
                    result.append(ch)
            return "".join(result)

        # ── 中文数字 → 阿拉伯 ──
        _CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3,
                      "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
                      "十": 10, "百": 100, "千": 1000}
        _CN_UNITS = {"十": 10, "百": 100, "千": 1000}

        def _cn_to_int(s: str) -> int | None:
            """中文数字→整数，如「二十」→20，「三十五」→35，「一百二十」→120。"""
            if not s or all(ch not in _CN_DIGIT for ch in s):
                return None
            total = 0
            section = 0  # 当前积累的小节值（万以下）
            for ch in s:
                if ch in _CN_UNITS:
                    unit = _CN_UNITS[ch]
                    if section == 0:
                        section = 1
                    total += section * unit
                    section = 0
                else:
                    val = _CN_DIGIT.get(ch)
                    if val is None:
                        return None
                    section = val
            total += section
            return total

        lines: list[str] = []
        for line in raw.splitlines():
            # 1) 全角→半角
            line = _full_to_half(line)
            # 2) 中文数字金额替换：各/各数 后跟中文数字 → 阿拉伯数字
            line = re.sub(
                r"(各(?:数)?)\s*([零一二两三四五六七八九十百千]+)",
                lambda m: f"{m.group(1)}{_cn_to_int(m.group(2))}",
                line,
            )
            lines.append(line)
        self._input_text.setPlainText("\n".join(lines))
        # textChanged 信号会自动触发 _on_input_changed → 防抖解析

    def _on_specified_replace(self) -> None:
        """指定替换：弹出自定义对话框，将符号 A 替换为符号 B。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("指定替换")
        dlg.setFixedSize(360, 160)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        # 第一行：查找内容
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("查找："))
        edt_find = QLineEdit()
        edt_find.setPlaceholderText("输入要查找的符号")
        row1.addWidget(edt_find)
        layout.addLayout(row1)

        # 第二行：替换为
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("替换："))
        edt_replace = QLineEdit()
        edt_replace.setPlaceholderText("输入要替换成的符号")
        row2.addWidget(edt_replace)
        layout.addLayout(row2)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        find = edt_find.text()
        replace = edt_replace.text()
        if not find:
            return  # 查找内容为空，不做操作

        self._apply_text_replace(find, replace)

    def _apply_text_replace(self, find: str, replace: str) -> None:
        """在输入框中执行文本替换（抽离便于测试）。"""
        raw = self._input_text.toPlainText()
        self._input_text.setPlainText(raw.replace(find, replace))
        # textChanged 信号会自动触发 _on_input_changed → 防抖解析

    def _apply_replace_presets(self, text: str) -> str:
        """对输入文本应用所有替换预设规则。"""
        for find, replace in self._replace_presets:
            if find:
                text = text.replace(find, replace)
        return text

    def _on_replace_presets(self) -> None:
        """替换预设：管理自动替换规则列表。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("替换预设")
        dlg.setMinimumSize(520, 340)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # 提示
        hint = QLabel("设置自动替换规则（解析输入时自动生效）：")
        hint.setStyleSheet("color:#555; font-size:12px;")
        layout.addWidget(hint)

        # ── 滚动区域 ──
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: 1px solid #ccc; border-radius: 4px; }")

        container = QWidget()
        self._preset_list_layout = QVBoxLayout(container)
        self._preset_list_layout.setSpacing(6)
        self._preset_list_layout.setContentsMargins(8, 8, 8, 8)
        self._preset_list_layout.addStretch(1)  # 底部弹簧，保持行紧凑
        scroll_area.setWidget(container)

        # 已保存的规则行
        preset_rows: list[tuple[QLineEdit, QLineEdit]] = []

        def _add_row(find_val: str = "", replace_val: str = "") -> None:
            # 移除底部弹簧
            if self._preset_list_layout.count():
                last = self._preset_list_layout.itemAt(self._preset_list_layout.count() - 1)
                if last.spacerItem():
                    self._preset_list_layout.removeItem(last)

            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(6)
            lbl_find = QLabel("查找")
            lbl_find.setStyleSheet("color:#666; font-size:12px;")
            edt_find = QLineEdit(find_val)
            edt_find.setPlaceholderText("输入要查找的符号")
            edt_find.setMinimumWidth(130)
            lbl_replace = QLabel("替换")
            lbl_replace.setStyleSheet("color:#666; font-size:12px;")
            edt_replace = QLineEdit(replace_val)
            edt_replace.setPlaceholderText("输入要替换成的符号")
            edt_replace.setMinimumWidth(130)
            btn_del = QPushButton("×")
            btn_del.setFixedSize(24, 24)
            btn_del.setStyleSheet(
                "QPushButton { border: none; color: #c0392b; font-size: 16px; font-weight: bold; }"
                "QPushButton:hover { color: #e74c3c; }"
            )
            btn_del.setToolTip("删除此规则")
            row.addWidget(lbl_find)
            row.addWidget(edt_find, stretch=1)
            row.addWidget(lbl_replace)
            row.addWidget(edt_replace, stretch=1)
            row.addWidget(btn_del)
            self._preset_list_layout.addWidget(row_widget)
            self._preset_list_layout.addStretch(1)  # 重新加底部弹簧
            preset_rows.append((edt_find, edt_replace))
            btn_del.clicked.connect(lambda: _remove_row(row_widget, edt_find, edt_replace))

        def _remove_row(
            row_widget: QWidget,
            edt_find: QLineEdit,
            edt_replace: QLineEdit,
        ) -> None:
            preset_rows.remove((edt_find, edt_replace))
            self._preset_list_layout.removeWidget(row_widget)
            row_widget.deleteLater()

        for find, replace in self._replace_presets:
            _add_row(find, replace)

        layout.addWidget(scroll_area, stretch=1)

        # 添加按钮
        btn_add = QPushButton("+ 添加预设")
        btn_add.setStyleSheet(
            "QPushButton { border: 1px dashed #aaa; padding: 6px; color: #555; }"
            "QPushButton:hover { border-color: #2980b9; color: #2980b9; }"
        )
        btn_add.clicked.connect(lambda: _add_row())
        layout.addWidget(btn_add)

        # 确定/取消
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.setMinimumWidth(80)
        btn_cancel.setMinimumWidth(80)
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # 保存预设
        self._replace_presets.clear()
        for edt_find, edt_replace in preset_rows:
            find = edt_find.text().strip()
            replace = edt_replace.text()
            if find:
                self._replace_presets.append((find, replace))

        # 立即对当前输入框内容应用新预设
        raw = self._input_text.toPlainText()
        if raw.strip():
            self._input_text.setPlainText(self._apply_replace_presets(raw))

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
        self._order_table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self._order_table.itemChanged.connect(self._on_table_item_changed)
        self._order_table.horizontalHeader().setStretchLastSection(True)
        self._order_table.verticalHeader().setVisible(False)
        # 列宽：订单信息列给足空间展示逗号拼接的号码
        header = self._order_table.horizontalHeader()
        header.resizeSection(0, 60)   # 区域
        header.resizeSection(1, 70)   # 投注类型
        header.resizeSection(2, 200)  # 订单信息（号码列表，重点列）
        header.resizeSection(3, 70)   # 复选类型
        header.resizeSection(4, 70)   # 计算方式
        header.resizeSection(5, 70)   # 金额
        header.resizeSection(6, 70)   # 每号金额
        header.resizeSection(7, 70)   # 是否自定义
        header.resizeSection(8, 80)   # 申报人
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

        self._cmb_declarer = QComboBox()
        self._cmb_declarer.setMinimumWidth(130)
        self._cmb_declarer.setToolTip("申报人来自设置中心；未配置时可保持未设置")
        self._cmb_declarer.currentIndexChanged.connect(self._update_declarer_plan_label)
        self._lbl_declarer_plan = QLabel("配置方案：未绑定配置方案")
        self._lbl_declarer_plan.setObjectName("declarerPlanLabel")

        self._radio_macau = QRadioButton("澳门 (ALT+1)")
        self._radio_hk = QRadioButton("香港 (ALT+2)")
        self._radio_macau.setChecked(True)

        self._cmb_calc = QComboBox()
        self._cmb_calc.addItems(["定总", "各数", "包肖"])
        self._cmb_calc.setMinimumWidth(100)

        layout.addWidget(QLabel("渠道"))
        layout.addWidget(self._cmb_channel)
        layout.addWidget(QLabel("申报人"))
        layout.addWidget(self._cmb_declarer)
        layout.addWidget(self._lbl_declarer_plan)
        layout.addWidget(self._radio_macau)
        layout.addWidget(self._radio_hk)
        layout.addWidget(self._cmb_calc)
        layout.addStretch(1)
        return bar

    def reload_declarers(self) -> None:
        """Read configured declarers through SettingsService with a safe empty fallback."""
        if not hasattr(self, "_cmb_declarer"):
            return
        previous_name = self._selected_declarer_name()
        self._declarer_plans = {}
        self._declarer_config_load_failed = False
        self._cmb_declarer.blockSignals(True)
        self._cmb_declarer.clear()
        try:
            declarers = self._settings_service.list_declarers()
        except Exception as exc:
            self._declarer_config_load_failed = True
            self._cmb_declarer.addItem("未设置（配置读取失败）", None)
            self._cmb_declarer.setToolTip(f"申报人配置读取失败：{exc}")
        else:
            if declarers:
                for declarer in declarers:
                    plan_name = str(getattr(declarer, "plan_name", "") or "").strip() or None
                    self._declarer_plans[declarer.name] = plan_name
                    self._cmb_declarer.addItem(declarer.name, declarer.name)
                previous_index = self._cmb_declarer.findData(previous_name)
                if previous_index >= 0:
                    self._cmb_declarer.setCurrentIndex(previous_index)
                self._cmb_declarer.setToolTip("申报人来自设置中心")
            else:
                self._cmb_declarer.addItem("未设置（请在设置中心配置）", None)
                self._cmb_declarer.setToolTip("设置中心尚未配置申报人；订单仍可保存")
        self._cmb_declarer.blockSignals(False)
        self._update_declarer_plan_label()

    def _selected_declarer_name(self) -> str | None:
        if not hasattr(self, "_cmb_declarer"):
            return None
        value = self._cmb_declarer.currentData()
        text = str(value).strip() if value is not None else ""
        return text or None

    def _selected_config_plan_name(self) -> str | None:
        declarer_name = self._selected_declarer_name()
        if declarer_name is None:
            return None
        return self._declarer_plans.get(declarer_name)

    def _update_declarer_plan_label(self, _index: int | None = None) -> None:
        if not hasattr(self, "_lbl_declarer_plan"):
            return
        if self._declarer_config_load_failed:
            text = "配置读取失败"
        else:
            text = self._selected_config_plan_name() or "未绑定配置方案"
        self._lbl_declarer_plan.setText(f"配置方案：{text}")

    def _build_text_section(self) -> QGroupBox:
        group = QGroupBox()
        group.setObjectName("textProcessGroup")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        toolbar = QHBoxLayout()
        link = QLabel("识别异常请先检查格式；当前测试版不提供在线帮助入口。")
        link.setObjectName("helpLink")
        toolbar.addWidget(link)
        toolbar.addStretch(1)

        for text in _TOOLBAR_BUTTONS:
            btn = QPushButton(text)
            btn.setObjectName("toolButton")
            if text == "去分割符":
                btn.setEnabled(True)
                btn.setToolTip("规范化数字分隔符")
                btn.clicked.connect(self._on_remove_separators)
            elif text == "订单标记":
                btn.setEnabled(True)
                btn.setToolTip("在每条订单前添加标记")
                btn.clicked.connect(self._on_order_mark)
            elif text == "去空格":
                btn.setEnabled(True)
                btn.setToolTip("移除所有空格")
                btn.clicked.connect(self._on_remove_spaces)
            elif text == "标记香港":
                btn.setEnabled(True)
                btn.setToolTip("将所有订单标记为香港区域")
                btn.clicked.connect(self._on_mark_hk)
            elif text == "去小数点":
                btn.setEnabled(True)
                btn.setToolTip("小数点替换为空格（1.5→1 5）")
                btn.clicked.connect(self._on_remove_decimal)
            elif text == "语义转换":
                btn.setEnabled(True)
                btn.setToolTip("全角转半角 + 中文数字转阿拉伯")
                btn.clicked.connect(self._on_semantic_convert)
            elif text == "指定替换":
                btn.setEnabled(True)
                btn.setToolTip("将指定符号替换为目标符号")
                btn.clicked.connect(self._on_specified_replace)
            elif text == "替换预设":
                btn.setEnabled(True)
                btn.setToolTip("管理自动替换规则列表")
                btn.clicked.connect(self._on_replace_presets)
            else:
                btn.setEnabled(False)
                btn.setToolTip(UNAVAILABLE_TOOLTIP)
            toolbar.addWidget(btn)

        outer.addLayout(toolbar)

        checks = QHBoxLayout()
        for label in _CHECKBOX_LABELS:
            cb = QCheckBox(label)
            if label == "自动获取":
                cb.setChecked(True)
            if label in _UNAVAILABLE_CHECKBOXES:
                cb.setChecked(False)
                cb.setEnabled(False)
                cb.setToolTip(UNAVAILABLE_TOOLTIP)
            if label == "自动获取":
                cb.setObjectName("autoFetchCheck")
                self._chk_auto_fetch = cb
                # 追加/替换模式切换按钮
                self._btn_clip_mode = QPushButton("[追加]")
                self._btn_clip_mode.setFixedWidth(50)
                self._btn_clip_mode.setToolTip("点击切换：追加模式/替换模式")
                self._btn_clip_mode.setStyleSheet(
                    "QPushButton { border: 1px solid #aaa; border-radius: 2px; "
                    "padding: 2px 4px; font-size: 11px; background: #f5f5f5; }"
                    "QPushButton:hover { background: #e0e0e0; }"
                )
                self._btn_clip_mode.clicked.connect(self._on_toggle_clip_mode)
                checks.addWidget(self._btn_clip_mode)
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
        btn_del = QPushButton("删除选中行")
        btn_save = QPushButton("保存订单")
        btn_clear.setObjectName("sideActionButton")
        btn_add.setObjectName("sideActionButton")
        btn_del.setObjectName("sideActionButton")
        btn_save.setObjectName("sideActionButton")
        btn_clear.setMinimumWidth(88)
        btn_add.setMinimumWidth(88)
        btn_del.setMinimumWidth(88)
        btn_save.setMinimumWidth(88)
        btn_clear.clicked.connect(self._on_clear_output)
        btn_add.clicked.connect(self._on_add_result)
        btn_del.clicked.connect(self._on_delete_selected)
        btn_save.clicked.connect(self._on_save_order)
        side_btns.addWidget(btn_clear)
        side_btns.addWidget(btn_add)
        side_btns.addWidget(btn_del)
        side_btns.addWidget(btn_save)
        side_btns.addStretch(1)

        # ── 水平分割器：输入框 ↔ 输出框 ──
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        h_splitter.setChildrenCollapsible(False)
        h_splitter.addWidget(self._input_text)
        h_splitter.addWidget(self._output_text)
        h_splitter.setStretchFactor(0, 1)
        h_splitter.setStretchFactor(1, 1)

        text_row.addWidget(h_splitter, stretch=1)

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
                background-color: #ffffff;
            }
            QLabel#footerHint {
                color: #555555;
                font-size: 11px;
                padding: 4px 2px;
                background-color: #e8ecef;
                border: 1px solid #c5ccd3;
            }
            QSplitter::handle {
                background-color: #c0c0c0;
                border: 1px solid #a0a0a0;
            }
            QSplitter::handle:vertical {
                min-height: 8px;
                height: 8px;
            }
            QSplitter::handle:horizontal {
                min-width: 8px;
                width: 8px;
            }
            QSplitter::handle:hover {
                background-color: #3498db;
            }
            """
        )
