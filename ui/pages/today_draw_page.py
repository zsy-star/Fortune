"""今日开奖页面。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_BALL_COLORS = {
    "blue": "#5b6dfb",
    "green": "#008b7d",
    "orange": "#ff7043",
}


@dataclass(frozen=True)
class BallInfo:
    number: str
    zodiac: str
    color: str  # blue | green | orange


@dataclass(frozen=True)
class DrawBlockData:
    region_label: str
    issue: str
    balls: tuple[BallInfo, ...]
    time_text: str
    badge_color: str


_MACAU_DRAW = DrawBlockData(
    region_label="澳门",
    issue="102",
    balls=(
        BallInfo("47", "猴", "blue"),
        BallInfo("03", "龙", "blue"),
        BallInfo("32", "猪", "green"),
        BallInfo("46", "鸡", "orange"),
        BallInfo("39", "龙", "green"),
        BallInfo("36", "羊", "blue"),
        BallInfo("20", "猪", "blue"),
    ),
    time_text="第103期开奖时间：4月13日  星期一  21点32分",
    badge_color="#008b7d",
)

_HK_DRAW = DrawBlockData(
    region_label="香港",
    issue="039",
    balls=(
        BallInfo("14", "蛇", "blue"),
        BallInfo("42", "牛", "blue"),
        BallInfo("40", "兔", "orange"),
        BallInfo("11", "猴", "green"),
        BallInfo("17", "虎", "green"),
        BallInfo("28", "兔", "green"),
        BallInfo("02", "蛇", "orange"),
    ),
    time_text="第040期开奖时间：未知",
    badge_color="#3498db",
)


class TodayDrawPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(20)

        root.addWidget(self._build_draw_block(_MACAU_DRAW))
        root.addWidget(self._build_draw_block(_HK_DRAW))
        root.addWidget(self._build_control_panel())
        root.addStretch(1)

        self._apply_stylesheet()

    def _build_draw_block(self, data: DrawBlockData) -> QWidget:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        badge = QLabel(f"{data.region_label}: 第{data.issue}期开奖结果")
        badge.setObjectName("drawBadge")
        badge.setStyleSheet(
            f"background-color: {data.badge_color}; color: #ffffff; "
            "padding: 6px 14px; font-size: 14px; font-weight: 600; border-radius: 2px;"
        )
        badge.setFixedHeight(32)
        layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)

        balls_row = QHBoxLayout()
        balls_row.setSpacing(6)
        balls_row.addStretch(1)

        for idx, ball in enumerate(data.balls):
            if idx == len(data.balls) - 1:
                balls_row.addSpacing(28)
            balls_row.addWidget(self._build_ball_cell(ball))

        balls_row.addStretch(1)
        layout.addLayout(balls_row)

        time_lbl = QLabel(data.time_text)
        time_lbl.setObjectName("drawTime")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(time_lbl)

        return block

    def _build_ball_cell(self, ball: BallInfo) -> QWidget:
        cell = QWidget()
        col = QVBoxLayout(cell)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        num_lbl = QLabel(ball.number)
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_lbl.setFixedSize(52, 52)
        bg = _BALL_COLORS.get(ball.color, _BALL_COLORS["blue"])
        num_lbl.setStyleSheet(
            f"background-color: {bg}; color: #ffffff; font-size: 20px; "
            "font-weight: 700; border-radius: 4px;"
        )

        zodiac_lbl = QLabel(ball.zodiac)
        zodiac_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zodiac_lbl.setFixedSize(52, 36)
        zodiac_lbl.setObjectName("zodiacCell")

        col.addWidget(num_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addWidget(zodiac_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        return cell

    def _build_control_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("controlPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        self._cmb_line = QComboBox()
        self._cmb_line.addItems(
            [
                "VIP线路 (稳定性好)",
                "备用线路1",
                "备用线路2",
            ]
        )
        self._cmb_line.setMinimumWidth(220)
        layout.addWidget(self._cmb_line, alignment=Qt.AlignmentFlag.AlignLeft)

        actions = QGridLayout()
        actions.setHorizontalSpacing(40)

        action_specs = [
            ("刷新澳门开奖", "澳门开奖数据应用到澳门兑奖"),
            ("刷新香港开奖", "香港开奖数据应用到香港兑奖"),
            ("刷新全部开奖", "所有开奖结果应用到兑奖"),
        ]
        for col, (top, bottom) in enumerate(action_specs):
            btn_top = QPushButton(top)
            btn_bottom = QPushButton(bottom)
            for btn in (btn_top, btn_bottom):
                btn.setFlat(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setObjectName("actionLink")
            actions.addWidget(btn_top, 0, col, alignment=Qt.AlignmentFlag.AlignCenter)
            actions.addWidget(btn_bottom, 1, col, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(actions)

        manual_row = QHBoxLayout()
        self._chk_manual = QCheckBox("启用手动输入")
        manual_row.addWidget(self._chk_manual)
        manual_row.addStretch(1)
        layout.addLayout(manual_row)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("开奖结果："))
        self._edit_results = QLineEdit()
        self._edit_results.setPlaceholderText("输入开奖号码，空格分开")
        btn_apply = QPushButton("应用到订单")
        btn_apply.setObjectName("applyButton")
        input_row.addWidget(self._edit_results, stretch=1)
        input_row.addWidget(btn_apply)
        layout.addLayout(input_row)

        return panel

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #ffffff;
            }
            QLabel#drawTime {
                color: #c0392b;
                font-size: 14px;
                margin-top: 4px;
            }
            QLabel#zodiacCell {
                background-color: #ffffff;
                border: 1px solid #2c3e50;
                font-size: 16px;
                color: #2c3e50;
            }
            QFrame#controlPanel {
                border: 1px solid #bdc3c7;
                background-color: #fafafa;
                border-radius: 4px;
                margin-top: 8px;
            }
            QPushButton#actionLink {
                color: #2980b9;
                font-size: 13px;
                border: none;
                padding: 4px 8px;
            }
            QPushButton#actionLink:hover {
                color: #1a5276;
                text-decoration: underline;
            }
            QComboBox {
                padding: 4px 8px;
                border: 1px solid #bdc3c7;
                background: #ffffff;
                font-size: 13px;
            }
            QLineEdit {
                padding: 6px 8px;
                border: 1px solid #bdc3c7;
                font-size: 13px;
            }
            QPushButton#applyButton {
                padding: 6px 14px;
                border: 1px solid #bdc3c7;
                background: #ecf0f1;
                font-size: 13px;
            }
            QPushButton#applyButton:hover {
                background: #dfe6e9;
            }
            QCheckBox {
                font-size: 13px;
            }
            """
        )
