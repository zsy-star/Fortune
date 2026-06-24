"""号码大全页面。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_RED = {1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46}
_BLUE = {3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48}
_GREEN = {n for n in range(1, 50) if n not in _RED and n not in _BLUE}

_ZODIAC_2026: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("马", (1, 13, 25, 37, 49)),
    ("蛇", (2, 14, 26, 38)),
    ("龙", (3, 15, 27, 39)),
    ("兔", (4, 16, 28, 40)),
    ("虎", (5, 17, 29, 41)),
    ("牛", (6, 18, 30, 42)),
    ("鼠", (7, 19, 31, 43)),
    ("猪", (8, 20, 32, 44)),
    ("狗", (9, 21, 33, 45)),
    ("鸡", (10, 22, 34, 46)),
    ("猴", (11, 23, 35, 47)),
    ("羊", (12, 24, 36, 48)),
)

_WUXING = (
    ("金", (3, 4, 11, 12, 25, 26, 33, 34, 41, 42)),
    ("木", (7, 8, 15, 16, 23, 24, 37, 38, 45, 46)),
    ("水", (13, 14, 21, 22, 29, 30, 43, 44)),
    ("火", (1, 2, 9, 10, 17, 18, 31, 32, 39, 40, 47, 48)),
    ("土", (5, 6, 19, 20, 27, 28, 35, 36, 49)),
)

_ZODIAC_ATTR = (
    ("家禽", "牛、马、羊、鸡、狗、猪"),
    ("野兽", "鼠、虎、兔、龙、蛇、猴"),
    ("吉美", "兔、龙、蛇、马、羊、鸡"),
    ("凶丑", "鼠、牛、虎、猴、狗、猪"),
    ("阴性", "鼠、龙、蛇、马、狗、猪"),
    ("阳性", "牛、虎、兔、羊、猴、鸡"),
    ("天肖", "兔、马、猴、猪、牛、龙"),
    ("地肖", "蛇、羊、鸡、狗、鼠、虎"),
    ("单笔", "鼠、龙、马、蛇、鸡、猪"),
    ("双笔", "虎、猴、狗、兔、羊、牛"),
    ("日肖", "兔、龙、蛇、马、羊、猴"),
    ("夜肖", "鼠、牛、虎、鸡、狗、猪"),
    ("前肖", "鼠、牛、虎、兔、龙、蛇"),
    ("后肖", "马、羊、猴、鸡、狗、猪"),
    ("大肖", "牛、虎、马、羊、狗、猪"),
    ("小肖", "鼠、兔、龙、蛇、猴、鸡"),
    ("左边肖", "鼠、牛、龙、蛇、猴、鸡"),
    ("右边肖", "虎、兔、马、羊、狗、猪"),
)


def _fmt_nums(nums: tuple[int, ...] | set[int]) -> str:
    return " ".join(f"{n:02d}" for n in sorted(nums))


def _half_wave(name: str, nums: set[int]) -> str:
    return f"{name} (共{len(nums)}个) : {_fmt_nums(nums).replace(' ', '-')}"


_WAVE_COLORS = {
    "红": "#c0392b",
    "蓝": "#2471a3",
    "绿": "#1e8449",
}


def _colorize(nums: set[int] | tuple[int, ...], color: str, *, font_size: int = 0) -> str:
    text = " ".join(f"{n:02d}" for n in sorted(nums))
    extra = f"font-size:{font_size}px;font-weight:600;" if font_size else ""
    return f'<span style="color:{color};{extra}">{text}</span>'


def _build_catalog_text() -> str:
    lines: list[str] = [
        "静态号码参考表",
        "当前版本不会自动随年份更新",
        "请以实际开奖年份配置为准",
        "",
        "2026最新",
        "",
    ]

    lines.append("十二生肖")
    for animal, nums in _ZODIAC_2026:
        lines.append(f"({animal}: {_fmt_nums(nums)})")
    lines.append("")

    lines.append("五行")
    for element, nums in _WUXING:
        lines.append(f"{element}: {_fmt_nums(nums)}")
    lines.append("")

    lines.append("波色")
    lines.append(f"红波: {_fmt_nums(_RED)}")
    lines.append(f"蓝波: {_fmt_nums(_BLUE)}")
    lines.append(f"绿波: {_fmt_nums(_GREEN)}")
    lines.append("")

    lines.append("半波 (固定)")
    red_d = {n for n in _RED if n % 2 == 0}
    red_s = {n for n in _RED if n % 2 == 1}
    blue_d = {n for n in _BLUE if n % 2 == 0}
    blue_s = {n for n in _BLUE if n % 2 == 1}
    green_d = {n for n in _GREEN if n % 2 == 0}
    green_s = {n for n in _GREEN if n % 2 == 1}
    for label, group in (
        ("红双", red_d),
        ("红单", red_s),
        ("蓝双", blue_d),
        ("蓝单", blue_s),
        ("绿双", green_d),
        ("绿单", green_s),
    ):
        lines.append(_half_wave(label, group))
    lines.append("")

    he_odd = [n for n in range(1, 50) if ((n // 10) + (n % 10)) % 2 == 1]
    he_even = [n for n in range(1, 50) if ((n // 10) + (n % 10)) % 2 == 0]
    lines.append("合数单/双")
    lines.append(f"合数单: {_fmt_nums(tuple(he_odd))}")
    lines.append(f"合数双: {_fmt_nums(tuple(he_even))}")
    lines.append("")

    lines.append("生肖属性")
    for title, value in _ZODIAC_ATTR:
        lines.append(f"{title}: {value}")

    return "\n".join(lines)


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

_WX_COLORS = {
    "金": "#b8860b",
    "木": "#228b22",
    "水": "#1a5276",
    "火": "#c0392b",
    "土": "#8b7355",
}


def _build_catalog_html() -> str:
    parts: list[str] = [
        _card(
            '<h2 style="font-size:18px;font-weight:bold;color:#1a5276;'
            'margin:0 0 6px 0;">静态号码参考表</h2>'
            '<div style="font-size:14px;color:#5d6d7e;line-height:1.6;">'
            "当前版本不会自动随年份更新<br>"
            "请以实际开奖年份配置为准"
            "</div>"
        )
    ]

    # ---- 十二生肖 ----
    zx_cells: list[str] = []
    for i, (animal, nums) in enumerate(_ZODIAC_2026):
        bg = _ZX_BG[i % 4]
        num_str = " ".join(f"{n:02d}" for n in nums)
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

    # ---- 五行 ----
    wx_rows: list[str] = []
    for element, nums in _WUXING:
        ec = _WX_COLORS.get(element, "#333")
        wx_rows.append(
            f'<tr>'
            f'<td style="font-weight:bold;color:{ec};width:40px;padding:4px 8px;font-size:15px;">{element}</td>'
            f'<td style="font-size:14px;color:#555;padding:4px 8px;">{_fmt_nums(nums)}</td>'
            f'</tr>'
        )
    wx_table = (
        '<table cellpadding="2" cellspacing="0" style="font-size:14px;">'
        + "".join(wx_rows)
        + "</table>"
    )
    parts.append(_card(_section("五行") + wx_table))

    # ---- 波色 ----
    wave_rows = (
        f'<div style="margin:6px 0;">'
        f'<b style="font-size:15px;">红波</b>&nbsp;&nbsp;'
        f'{_colorize(_RED, _WAVE_COLORS["红"], font_size=17)}'
        f'</div>'
        f'<div style="margin:6px 0;">'
        f'<b style="font-size:15px;">蓝波</b>&nbsp;&nbsp;'
        f'{_colorize(_BLUE, _WAVE_COLORS["蓝"], font_size=17)}'
        f'</div>'
        f'<div style="margin:6px 0;">'
        f'<b style="font-size:15px;">绿波</b>&nbsp;&nbsp;'
        f'{_colorize(_GREEN, _WAVE_COLORS["绿"], font_size=17)}'
        f'</div>'
    )
    parts.append(_card(_section("波色") + wave_rows))

    # ---- 半波 ----
    red_d = {n for n in _RED if n % 2 == 0}
    red_s = {n for n in _RED if n % 2 == 1}
    blue_d = {n for n in _BLUE if n % 2 == 0}
    blue_s = {n for n in _BLUE if n % 2 == 1}
    green_d = {n for n in _GREEN if n % 2 == 0}
    green_s = {n for n in _GREEN if n % 2 == 1}

    half_rows: list[str] = []
    for label, group, ck in (
        ("红双", red_d, "红"), ("红单", red_s, "红"),
        ("蓝双", blue_d, "蓝"), ("蓝单", blue_s, "蓝"),
        ("绿双", green_d, "绿"), ("绿单", green_s, "绿"),
    ):
        color = _WAVE_COLORS[ck]
        half_rows.append(
            f'<div style="margin:4px 0;">'
            f'<b style="font-size:14px;">{label}</b> '
            f'<span style="font-size:13px;color:#888;">({len(group)}个)</span>&nbsp;'
            f'{_colorize(group, color, font_size=16)}'
            f'</div>'
        )
    parts.append(_card(_section("半波（固定）") + "".join(half_rows)))

    # ---- 合数单/双 ----
    he_odd = [n for n in range(1, 50) if ((n // 10) + (n % 10)) % 2 == 1]
    he_even = [n for n in range(1, 50) if ((n // 10) + (n % 10)) % 2 == 0]
    he_html = (
        f'<div style="margin:4px 0;">'
        f'<b style="font-size:14px;">合数单</b>&nbsp;&nbsp;'
        f'<span style="font-size:15px;color:#555;">{_fmt_nums(tuple(he_odd))}</span>'
        f'</div>'
        f'<div style="margin:4px 0;">'
        f'<b style="font-size:14px;">合数双</b>&nbsp;&nbsp;'
        f'<span style="font-size:15px;color:#555;">{_fmt_nums(tuple(he_even))}</span>'
        f'</div>'
    )
    parts.append(_card(_section("合数单/双") + he_html))

    # ---- 生肖属性 ----
    attr_rows: list[str] = []
    for idx, (title, value) in enumerate(_ZODIAC_ATTR):
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
    parts.append(_card(_section("生肖属性") + attr_table))

    return (
        '<div style="font-size:15px;line-height:1.7;color:#2c3e50;">'
        + "".join(parts)
        + "</div>"
    )


class NumberCatalogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        root.addLayout(self._build_search_bar())
        self._content = QTextEdit()
        self._content.setReadOnly(True)
        self._content.setHtml(_build_catalog_html())
        root.addWidget(self._content, stretch=1)

        self._apply_stylesheet()

    def _build_search_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

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

        row.addWidget(self._search_edit, stretch=1)
        row.addWidget(btn_search)
        row.addWidget(btn_prev)
        row.addWidget(btn_next)
        return row

    def _search_next(self, backward: bool = False) -> None:
        keyword = self._search_edit.text().strip()
        if not keyword:
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
            self._content.find(keyword, flags)

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
                background-color: #f5f6f8;
            }
            QLineEdit#searchInput {
                padding: 9px 14px;
                border: 1px solid #aed6f1;
                border-radius: 18px;
                background-color: #ffffff;
                font-size: 14px;
            }
            QPushButton {
                padding: 7px 16px;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                background: #ffffff;
                font-size: 13px;
                min-width: 64px;
            }
            QPushButton:hover {
                background: #ebf5fb;
                border-color: #3498db;
            }
            QTextEdit {
                border: 1px solid #e0e4e8;
                border-radius: 8px;
                background: #f5f6f8;
                font-size: 15px;
                padding: 8px;
                color: #2c3e50;
            }
            """
        )
