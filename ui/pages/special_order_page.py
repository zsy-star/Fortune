"""特码调单页面。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.pages.order_analysis_page import _build_macau_rows

_ZODIAC = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")
_GRID_COLUMNS = (range(1, 14), range(14, 27), range(27, 40), range(40, 50))


def _zodiac_short(num: int) -> str:
    return _ZODIAC[(num - 1) % 12]


class SpecialOrderPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = _build_macau_rows()
        self._original: dict[int, float] = {
            i + 1: float(row.bet_count) for i, row in enumerate(self._rows)
        }
        self._adjust_edits: dict[int, QLineEdit] = {}
        self._total_labels: dict[int, QLabel] = {}
        self._original_labels: dict[int, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_body_row(), stretch=1)
        root.addLayout(self._build_footer_row())

        self._apply_stylesheet()
        self._recalc_all()

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        self._filter_group = QButtonGroup(self)
        self._radio_macau = QRadioButton("只看澳门")
        self._radio_hk = QRadioButton("只看香港")
        self._radio_macau.setChecked(True)
        self._filter_group.addButton(self._radio_macau, 0)
        self._filter_group.addButton(self._radio_hk, 1)
        row.addWidget(self._radio_macau)
        row.addWidget(self._radio_hk)
        row.addStretch(1)
        return row

    def _build_body_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["号码", "下注数", "盈亏", "ID"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setMinimumWidth(280)
        self._table.setMaximumWidth(340)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._fill_table()

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self._build_adjust_grid(), stretch=3)
        right.addLayout(self._build_summary_row())
        right.addLayout(self._build_control_row())
        right.addLayout(self._build_action_row())
        right.addWidget(self._build_output_area(), stretch=2)

        row.addWidget(self._table, stretch=0)
        row.addLayout(right, stretch=1)
        return row

    def _fill_table(self) -> None:
        self._table.setRowCount(len(self._rows))
        for idx, row in enumerate(self._rows):
            num_item = QTableWidgetItem(row.label)
            num_item.setForeground(QColor(row.number_color))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            bet_item = QTableWidgetItem(str(row.bet_count))
            bet_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pl_item = QTableWidgetItem(str(row.profit_loss))
            pl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if row.profit_loss < 0:
                pl_item.setForeground(QColor("#c0392b"))
            elif row.profit_loss > 0:
                pl_item.setForeground(QColor("#3498db"))
            id_item = QTableWidgetItem(str(idx + 1))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(idx, 0, num_item)
            self._table.setItem(idx, 1, bet_item)
            self._table.setItem(idx, 2, pl_item)
            self._table.setItem(idx, 3, id_item)

    def _build_adjust_grid(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)

        container = QWidget()
        grid = QHBoxLayout(container)
        grid.setSpacing(8)

        for col_nums in _GRID_COLUMNS:
            col = QVBoxLayout()
            col.setSpacing(2)
            header = QHBoxLayout()
            header.addWidget(QLabel("原金额", alignment=Qt.AlignmentFlag.AlignCenter))
            header.addWidget(QLabel("调整", alignment=Qt.AlignmentFlag.AlignCenter))
            header.addWidget(QLabel("总计", alignment=Qt.AlignmentFlag.AlignCenter))
            col.addLayout(header)

            for num in col_nums:
                col.addLayout(self._build_number_row(num))
            col.addStretch(1)
            grid.addLayout(col)

        scroll.setWidget(container)
        return scroll

    def _build_number_row(self, num: int) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)

        zodiac = _zodiac_short(num)
        title = QLabel(f"{zodiac}:{num:02d}")
        title.setFixedWidth(42)
        title.setObjectName("numTitle")

        orig = float(self._original.get(num, 0))
        lbl_orig = QLabel(f"{orig:g}")
        lbl_orig.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_orig.setFixedWidth(48)
        lbl_orig.setObjectName("origAmount")

        edit_adj = QLineEdit()
        edit_adj.setPlaceholderText("0")
        edit_adj.setFixedWidth(48)
        edit_adj.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit_adj.textChanged.connect(lambda _t, n=num: self._on_adjust_changed(n))

        lbl_total = QLabel(f"{orig:g}")
        lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_total.setFixedWidth(48)
        lbl_total.setObjectName("totalAmount")

        self._original_labels[num] = lbl_orig
        self._adjust_edits[num] = edit_adj
        self._total_labels[num] = lbl_total

        row.addWidget(title)
        row.addWidget(lbl_orig)
        row.addWidget(edit_adj)
        row.addWidget(lbl_total)
        return row

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._grp_original = QGroupBox("原特码数据")
        self._grp_adjusted = QGroupBox("调整后数据")
        self._lbl_orig_stats = QLabel()
        self._lbl_adj_stats = QLabel()
        self._lbl_orig_stats.setWordWrap(True)
        self._lbl_adj_stats.setWordWrap(True)

        orig_layout = QVBoxLayout(self._grp_original)
        orig_layout.addWidget(self._lbl_orig_stats)
        adj_layout = QVBoxLayout(self._grp_adjusted)
        adj_layout.addWidget(self._lbl_adj_stats)

        row.addWidget(self._grp_original, stretch=1)
        row.addWidget(self._grp_adjusted, stretch=1)
        return row

    def _build_control_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("最大亏损:"))
        self._edit_max_loss = QLineEdit("-9112")
        self._edit_max_loss.setFixedWidth(80)
        row.addWidget(self._edit_max_loss)

        self._lbl_adjuster = QLabel("调整器: 0")
        row.addWidget(self._lbl_adjuster)
        row.addSpacing(12)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 400)
        self._slider.setValue(200)
        self._slider.valueChanged.connect(self._on_slider_changed)
        row.addWidget(self._slider, stretch=1)

        self._lbl_slider_val = QLabel("200")
        self._lbl_slider_val.setFixedWidth(36)
        row.addWidget(self._lbl_slider_val)
        return row

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        for text in (
            "保存本次调整",
            "调整改为10的倍数",
            "清空当前调整",
            "清空输出框",
            "重置所有数据",
            "特码兑奖",
        ):
            btn = QPushButton(text)
            btn.setObjectName("actionButton")
            if text == "清空当前调整":
                btn.clicked.connect(self._clear_adjustments)
            elif text == "清空输出框":
                btn.clicked.connect(lambda: self._output.clear())
            elif text == "重置所有数据":
                btn.clicked.connect(self._reset_all)
            row.addWidget(btn)
        row.addStretch(1)
        return row

    def _build_output_area(self) -> QPlainTextEdit:
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("调整日志与识别结果将显示在此处…")
        return self._output

    def _build_footer_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._cmd_input = QLineEdit()
        self._cmd_input.setPlaceholderText(
            "指出输入框，特码类型：多个数字务必加 '各' 字，此处 '各' 均做各数处理"
        )
        btn_ext = QPushButton("打开扩展")
        btn_log = QPushButton("调整记录")
        btn_ext.setObjectName("footerButton")
        btn_log.setObjectName("footerButton")
        row.addWidget(self._cmd_input, stretch=1)
        row.addWidget(btn_ext)
        row.addWidget(btn_log)
        return row

    def _parse_adjustment(self, num: int) -> float:
        text = self._adjust_edits[num].text().strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    def _on_adjust_changed(self, num: int) -> None:
        orig = self._original.get(num, 0.0)
        adj = self._parse_adjustment(num)
        total = orig + adj
        self._total_labels[num].setText(f"{total:g}")
        self._recalc_summary()

    def _recalc_all(self) -> None:
        for num in range(1, 50):
            self._on_adjust_changed(num)

    def _recalc_summary(self) -> None:
        originals = [self._original.get(n, 0.0) for n in range(1, 50)]
        adjustments = [self._parse_adjustment(n) for n in range(1, 50)]
        totals = [o + a for o, a in zip(originals, adjustments)]

        def stats(values: list[float], *, show_adj: bool = False, adj_sum: float = 0.0) -> str:
            total_sum = sum(values)
            profits = [v for v in values if v > 0]
            losses = [v for v in values if v < 0]
            max_profit = max(profits) if profits else 0
            max_loss = min(losses) if losses else 0
            lines = [
                f"特码总额: {total_sum:g}",
                f"最大盈利: {max_profit:g}",
                f"最大亏损: {max_loss:g}",
                f"盈利数量: {len(profits)}",
                f"亏损数量: {len(losses)}",
            ]
            if show_adj:
                lines.append(f"调整金额: {adj_sum:g}")
            return "    ".join(lines)

        adj_sum = sum(adjustments)
        self._lbl_orig_stats.setText(stats(originals))
        self._lbl_adj_stats.setText(stats(totals, show_adj=True, adj_sum=adj_sum))

    def _on_slider_changed(self, value: int) -> None:
        self._lbl_adjuster.setText(f"调整器: {value}")
        self._lbl_slider_val.setText(str(value))

    def _clear_adjustments(self) -> None:
        for edit in self._adjust_edits.values():
            edit.clear()
        self._recalc_all()

    def _reset_all(self) -> None:
        self._clear_adjustments()
        self._slider.setValue(200)
        self._output.clear()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QGroupBox {
                font-weight: 600;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel#numTitle {
                font-size: 11px;
                color: #2c3e50;
            }
            QLabel#origAmount, QLabel#totalAmount {
                background: #f4f6f7;
                border: 1px solid #d5d8dc;
                padding: 2px;
                font-size: 11px;
            }
            QLineEdit {
                border: 1px solid #bdc3c7;
                padding: 2px 4px;
                font-size: 11px;
            }
            QPushButton#actionButton, QPushButton#footerButton {
                padding: 4px 10px;
                font-size: 12px;
            }
            QTableWidget {
                border: 1px solid #bdc3c7;
                font-size: 12px;
            }
            QHeaderView::section {
                background: #ecf0f1;
                padding: 4px;
                border: 1px solid #bdc3c7;
            }
            """
        )
