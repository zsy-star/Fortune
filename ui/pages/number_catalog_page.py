"""号码大全页面。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
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


class NumberCatalogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        root.addLayout(self._build_search_bar())
        self._content = QPlainTextEdit()
        self._content.setReadOnly(True)
        self._content.setPlainText(_build_catalog_text())
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

        self._highlight_selection()

    def _highlight_selection(self) -> None:
        cursor = self._content.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#fff176"))
        cursor.mergeCharFormat(fmt)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #ffffff;
            }
            QLineEdit#searchInput {
                padding: 8px 12px;
                border: 1px solid #aed6f1;
                border-radius: 16px;
                background-color: #ebf5fb;
                font-size: 13px;
            }
            QPushButton {
                padding: 6px 14px;
                border: 1px solid #bdc3c7;
                background: #ffffff;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #ebf5fb;
            }
            QPlainTextEdit {
                border: 1px solid #ecf0f1;
                background: #ffffff;
                font-size: 13px;
                line-height: 1.5;
                padding: 12px;
                color: #2c3e50;
            }
            """
        )
