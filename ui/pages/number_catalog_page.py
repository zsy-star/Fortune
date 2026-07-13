"""号码大全页面。"""

from __future__ import annotations

from html import escape

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.number_catalog_data import (
    COLORED_ZODIAC_GROUPS,
    FIVE_ELEMENT_TEXT_COLORS,
    FIXED_NUMBER_GROUP_SECTIONS,
    NINE_STAR_GROUPS,
    REFERENCE_FIVE_ELEMENT_NUMBERS_2026,
    REFERENCE_TEXT_SECTIONS,
    WAVE_TEXT_COLORS,
    ZODIAC_ATTRIBUTES,
    composite_size_reference_groups,
    digit_sum_groups,
    half_wave_groups,
    head_groups,
    head_parity_groups,
    middle_edge_groups,
    modulo_groups,
    size_groups,
    size_parity_groups,
    sum_parity_groups,
    sum_tail_groups,
    tail_size_groups,
)
from domain.color_rules import WAVE_NUMBERS
from domain.zodiac_config import (
    MAX_ZODIAC_YEAR,
    MIN_ZODIAC_YEAR,
    get_default_zodiac_year,
    get_zodiac_number_map,
)


def _ordered_numbers(numbers: tuple[int, ...] | set[int]) -> tuple[int, ...]:
    return tuple(sorted(numbers)) if isinstance(numbers, set) else tuple(numbers)


def _fmt_nums(numbers: tuple[int, ...] | set[int], separator: str = " ") -> str:
    return separator.join(f"{number:02d}" for number in _ordered_numbers(numbers))


def _colorize(
    numbers: tuple[int, ...] | set[int], color: str, *, font_size: int = 0, separator: str = " "
) -> str:
    extra = f"font-size:{font_size}px;font-weight:600;" if font_size else ""
    return f'<span style="color:{color};{extra}">{_fmt_nums(numbers, separator)}</span>'


def _section(title: str) -> str:
    return (
        '<h3 style="font-size:16px;font-weight:bold;color:#1a5276;'
        'border-left:4px solid #3498db;padding:4px 0 4px 12px;margin:0 0 12px 0;">'
        f"{title}</h3>"
    )


def _card(body: str) -> str:
    return (
        '<div style="background:#ffffff;border-radius:8px;padding:14px 18px;'
        'margin-bottom:12px;border:1px solid #e0e4e8;">'
        f"{body}</div>"
    )


_ZX_BG = [
    "#fdf2f2",  # light red
    "#fef9e7",  # light yellow
    "#f0faf5",  # light green
    "#f5f0fa",  # light purple
]

def _render_number_groups(
    title: str,
    groups: dict[str, tuple[int, ...]] | tuple[tuple[str, tuple[int, ...]], ...],
    *,
    colors: dict[str, str] | None = None,
    show_counts: bool = False,
    separator: str = " ",
) -> str:
    items = groups.items() if isinstance(groups, dict) else groups
    rows: list[str] = []
    for label, numbers in items:
        color = (colors or {}).get(label, "#1F2937")
        count = f'<span style="font-size:13px;color:#6b7280;">（共{len(numbers)}个）</span>' if show_counts else ""
        rows.append(
            '<div style="margin:5px 0;">'
            f'<b style="font-size:14px;color:{color};">{escape(label)}</b>{count}&nbsp;&nbsp;'
            f'{_colorize(numbers, color, font_size=15, separator=separator)}'
            "</div>"
        )
    return _card(_section(title) + "".join(rows))


def _render_text_section(title: str, lines: tuple[str, ...]) -> str:
    body = "".join(f'<div style="margin:4px 0;color:#374151;">{escape(line)}</div>' for line in lines)
    return _card(_section(title) + body)


def _build_catalog_html(year: int | None = None) -> str:
    selected_year = year or get_default_zodiac_year()
    parts: list[str] = [
        _card(
            '<h2 style="font-size:18px;font-weight:bold;color:#1a5276;'
            'margin:0 0 6px 0;">号码大全 / 静态号码参考表</h2>'
            '<div style="font-size:14px;color:#5d6d7e;line-height:1.6;">'
            "资料基准：2026最新；生肖号码按所选开奖年份显示，请以实际开奖年份为准。<br>"
            f"当前生肖年份：{selected_year}"
            "</div>"
        )
    ]

    # ---- 十二生肖 ----
    zx_cells: list[str] = []
    for i, (animal, nums) in enumerate(get_zodiac_number_map(selected_year).items()):
        bg = _ZX_BG[i % 4]
        num_str = " ".join(nums)
        zx_cells.append(
            f'<td style="background:{bg};border-radius:4px;padding:8px 10px;'
            f'text-align:center;width:25%;">'
            f'<b style="font-size:16px;">{animal}</b><br>'
            f'<span style="font-size:14px;color:#444;">{num_str}</span></td>'
        )
    zx_rows_html = "".join(
        f"<tr>{''.join(zx_cells[i:i+4])}</tr>"
        for i in range(0, len(zx_cells), 4)
    )
    zx_table = (
        '<table cellpadding="4" cellspacing="4" style="font-size:14px;width:100%;">'
        + zx_rows_html
        + "</table>"
    )
    parts.append(_card(_section("十二生肖") + zx_table))

    # The supplied five-element table is an explicitly static 2026 reference.
    wx_rows: list[str] = []
    for element, nums in REFERENCE_FIVE_ELEMENT_NUMBERS_2026.items():
        ec = FIVE_ELEMENT_TEXT_COLORS[element]
        wx_rows.append(
            f'<tr>'
            f'<td style="font-weight:bold;color:{ec};width:40px;padding:4px 8px;font-size:15px;">{element}</td>'
            f'<td style="font-size:14px;color:{ec};padding:4px 8px;">{_fmt_nums(nums)}</td>'
            f'</tr>'
        )
    wx_table = (
        '<table cellpadding="2" cellspacing="0" style="font-size:14px;">'
        + "".join(wx_rows)
        + "</table>"
    )
    parts.append(_card(_section("五行（2026静态参考）") + wx_table))

    parts.append(_render_number_groups("波色", dict(WAVE_NUMBERS), colors=WAVE_TEXT_COLORS))

    half_colors = {
        label: WAVE_TEXT_COLORS[f"{label[0]}波"] for label in half_wave_groups()
    }
    parts.append(
        _render_number_groups(
            "半波（固定不变）", half_wave_groups(), colors=half_colors, show_counts=True, separator="-"
        )
    )
    parts.append(_render_number_groups("合数单 / 合数双", sum_parity_groups()))

    attr_rows: list[str] = []
    for idx, (title, value) in enumerate(ZODIAC_ATTRIBUTES):
        bg = "#f9fbfc" if idx % 2 == 0 else "#ffffff"
        attr_rows.append(
            f'<tr style="background:{bg};">'
            f'<td style="font-weight:bold;color:#1a5276;width:80px;padding:6px 10px;font-size:14px;">{title}</td>'
            f'<td style="font-size:14px;color:#444;padding:6px 10px;">{value}</td>'
            f'</tr>'
        )
    attr_table = (
        '<table cellpadding="0" cellspacing="0" style="font-size:14px;width:100%;">'
        + "".join(attr_rows)
        + "</table>"
    )
    color_rows = "".join(
        '<div style="margin:6px 10px;">'
        f'<b style="color:{color};">{label}</b>&nbsp;&nbsp;'
        f'<span style="font-weight:600;color:{color};">{value}</span>'
        "</div>"
        for label, value, color in COLORED_ZODIAC_GROUPS
    )
    parts.append(_card(_section("生肖属性") + attr_table + color_rows))

    size_middle_groups = {
        "大数": size_groups()["大"],
        "小数": size_groups()["小"],
        **middle_edge_groups(),
    }
    parts.append(_render_number_groups("大小中边数", size_middle_groups, show_counts=True, separator="-"))

    text_sections = dict(REFERENCE_TEXT_SECTIONS)
    for section_title in ("生肖的五行属性", "生肖身份分类", "月份（民间参考）"):
        parts.append(_render_text_section(section_title, text_sections[section_title]))

    parts.append(_render_number_groups("大小（固定不变）", size_groups(), show_counts=True, separator="-"))
    parts.append(_render_number_groups("合数（固定不变）", digit_sum_groups(), separator="-"))
    parts.append(_render_number_groups("头数（固定不变）", head_groups()))

    for title, groups in FIXED_NUMBER_GROUP_SECTIONS[:2]:
        parts.append(_render_number_groups(title, groups, separator="-"))

    parts.append(
        _render_number_groups(
            "合大 & 合小（附件静态参考）", composite_size_reference_groups(), separator="-"
        )
    )
    parts.append(_render_number_groups("尾大 & 尾小（固定不变）", tail_size_groups(), separator="-"))
    parts.append(_render_number_groups("半单双（固定不变）", size_parity_groups(), separator="-"))
    parts.append(_render_number_groups("合尾（固定不变）", sum_tail_groups(), separator="-"))
    parts.append(_render_number_groups("头数单与双（固定不变）", head_parity_groups(), separator="-"))

    modulus_names = {3: "三", 4: "四", 5: "五", 6: "六", 7: "七"}
    for modulus, name in modulus_names.items():
        parts.append(_render_number_groups(f"模{name}数（固定不变）", modulo_groups(modulus), separator="-"))

    for section_title, lines in REFERENCE_TEXT_SECTIONS[3:]:
        parts.append(_render_text_section(section_title, lines))

    for title, groups in FIXED_NUMBER_GROUP_SECTIONS[2:]:
        parts.append(_render_number_groups(title, groups))

    parts.append(_render_number_groups("九星号码（静态参考）", NINE_STAR_GROUPS))
    parts.append(
        _card(
            '<div style="font-size:14px;color:#5d6d7e;text-align:center;padding:6px 0;">'
            "本页为静态号码参考资料；实际录单、结算支持范围以系统提示为准。"
            "</div>"
        )
    )

    return (
        '<div style="font-size:15px;line-height:1.7;color:#2c3e50;">'
        + "".join(parts)
        + "</div>"
    )


def _build_catalog_text(year: int | None = None) -> str:
    document = QTextDocument()
    document.setHtml(_build_catalog_html(year))
    return document.toPlainText()


class NumberCatalogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._zodiac_year = get_default_zodiac_year()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        root.addLayout(self._build_search_bar())
        self._search_status = QLabel("")
        self._search_status.setObjectName("searchStatusLabel")
        root.addWidget(self._search_status)
        self._content = QTextEdit()
        self._content.setObjectName("catalogContent")
        self._content.setReadOnly(True)
        self._content.setHtml(_build_catalog_html(self._zodiac_year))
        root.addWidget(self._content, stretch=1)

        self._apply_stylesheet()

    def _build_search_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._year_label = QLabel(f"当前生肖年份：{self._zodiac_year}")
        self._year_label.setObjectName("zodiacYearLabel")
        self._year_spin = QSpinBox()
        self._year_spin.setObjectName("zodiacYearSpin")
        self._year_spin.setRange(MIN_ZODIAC_YEAR, MAX_ZODIAC_YEAR)
        self._year_spin.setValue(self._zodiac_year)
        self._year_spin.setPrefix("生肖年份 ")
        self._year_spin.valueChanged.connect(self._on_year_changed)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("请输入查找的内容")
        self._search_edit.setObjectName("searchInput")
        self._search_edit.returnPressed.connect(self._search_next)

        btn_search = QPushButton("搜索")
        btn_prev = QPushButton("上一个")
        btn_next = QPushButton("下一个")

        btn_search.clicked.connect(self._search_next)
        btn_prev.clicked.connect(lambda: self._search_next(backward=True))
        btn_next.clicked.connect(self._search_next)

        row.addWidget(self._year_label)
        row.addWidget(self._year_spin)
        row.addWidget(self._search_edit, stretch=1)
        row.addWidget(btn_search)
        row.addWidget(btn_prev)
        row.addWidget(btn_next)
        return row

    def _on_year_changed(self, year: int) -> None:
        self._zodiac_year = year
        self._year_label.setText(f"当前生肖年份：{year}")
        self._content.setHtml(_build_catalog_html(year))
        self._content.setExtraSelections([])
        self._search_status.clear()

    def _search_next(self, backward: bool = False) -> None:
        keyword = self._search_edit.text().strip()
        if not keyword:
            self._search_status.setText("请输入要查找的内容。")
            return

        flags = QTextDocument.FindFlag(0)
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward

        found = self._content.find(keyword, flags)
        if not found:
            cursor = self._content.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
            )
            self._content.setTextCursor(cursor)
            found = self._content.find(keyword, flags)

        if not found:
            self._content.setExtraSelections([])
            self._search_status.setText(f"未找到“{keyword}”。")
            return

        self._search_status.clear()
        self._apply_extra_selection()

    def _apply_extra_selection(self) -> None:
        """Highlight current selection as a non-destructive overlay.

        Uses QTextEdit.ExtraSelection so the highlight sits on a virtual
        layer above the document.  The default blue selection is cleared
        afterwards so the yellow background is visible.
        """
        cursor = self._content.textCursor()
        if not cursor.hasSelection():
            self._content.setExtraSelections([])
            return

        extra = QTextEdit.ExtraSelection()
        extra.cursor = QTextCursor(cursor)  # copy with selection intact
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#fff176"))
        extra.format = fmt
        self._content.setExtraSelections([extra])

        # Clear default blue selection so yellow is visible on top
        cursor.clearSelection()
        self._content.setTextCursor(cursor)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #F5F7FA;
            }
            QLineEdit#searchInput {
                padding: 9px 14px;
                border: 1px solid #c4ceda;
                border-radius: 18px;
                background-color: #ffffff;
                font-size: 14px;
            }
            QLabel#searchStatusLabel {
                color: #B42318;
                font-size: 13px;
                min-height: 16px;
            }
            QPushButton {
                padding: 7px 16px;
                border: 1px solid #c4ceda;
                border-radius: 5px;
                background: #ffffff;
                color: #1f4e79;
                font-size: 13px;
                font-weight: 600;
                min-width: 64px;
            }
            QPushButton:hover {
                background: #edf5ff;
                border-color: #8eb8e8;
            }
            QTextEdit {
                border: 1px solid #cfd8e3;
                border-radius: 8px;
                background: #ffffff;
                font-size: 15px;
                padding: 8px;
                color: #243447;
            }
            """
        )
