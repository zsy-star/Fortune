"""操作日志页面。"""

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, QTime, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_SAMPLE_LOG_LINES = [
    "2026-04-13 16:49:52 - 通过自动识别添加订单:['澳门', '特码', '1', '各', '10']-->成功",
    "2026-04-13 16:49:59 - received 1 pieces of data from the enter window",
    "2026-04-13 16:50:18 - 清空了所有订单",
    "2026-04-13 16:50:25 - 通过自动识别添加订单:['香港', '平特一肖', '龙', '各', '100']-->成功",
    "2026-04-13 16:50:31 - received 2 pieces of data from the enter window",
    "2026-04-13 16:50:45 - 用户切换区域: 澳门 -> 香港",
    "2026-04-13 16:51:02 - 导出订单报表: 成功",
]

_SAMPLE_TOTAL_COUNT = 17203

_DEFAULT_QDATETIME = QDateTime(QDate(2026, 4, 13), QTime(16, 49, 0))


def _to_qdatetime(dt: datetime) -> QDateTime:
    return QDateTime(QDate(dt.year, dt.month, dt.day), QTime(dt.hour, dt.minute, dt.second))


class OperationLogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_logs = list(_SAMPLE_LOG_LINES)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        root.addLayout(self._build_filter_row())
        root.addLayout(self._build_action_row())
        root.addLayout(self._build_summary_row())
        root.addWidget(self._build_separator())
        root.addWidget(self._build_log_area(), stretch=1)

        self._apply_stylesheet()
        self._refresh_log_display()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QPushButton#logActionLink {
                color: #1a5276;
                border: none;
                padding: 2px 4px;
                font-size: 13px;
                text-align: left;
            }
            QPushButton#logActionLink:hover {
                color: #2874a6;
                text-decoration: underline;
            }
            QFrame#logSeparator {
                background-color: #3498db;
                border: none;
                max-height: 2px;
            }
            QPlainTextEdit#logView {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                padding: 8px;
                color: #2c3e50;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
            QDateTimeEdit {
                padding: 4px 6px;
                border: 1px solid #bdc3c7;
                border-radius: 2px;
                background: #ffffff;
                font-size: 13px;
            }
            """
        )

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        row.addWidget(QLabel("开始时间:"))
        self._dt_start = QDateTimeEdit()
        self._dt_start.setDisplayFormat("yyyy/M/d HH:mm")
        self._dt_start.setCalendarPopup(True)
        self._dt_start.setDateTime(_DEFAULT_QDATETIME)
        self._dt_start.setMinimumWidth(180)
        row.addWidget(self._dt_start)

        row.addWidget(QLabel("结束时间:"))
        self._dt_end = QDateTimeEdit()
        self._dt_end.setDisplayFormat("yyyy/M/d HH:mm")
        self._dt_end.setCalendarPopup(True)
        self._dt_end.setDateTime(_DEFAULT_QDATETIME)
        self._dt_end.setMinimumWidth(180)
        row.addWidget(self._dt_end)

        row.addStretch(1)
        return row

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        specs = [
            ("今天", self._on_today),
            ("昨天", self._on_yesterday),
            ("最近三天", self._on_last_three_days),
            ("设置的时间段", self._on_apply_time_range),
            ("清空日志", self._on_clear_logs),
            ("重置日志", self._on_reset_logs),
        ]
        for text, handler in specs:
            btn = QPushButton(text)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("logActionLink")
            btn.clicked.connect(handler)
            row.addWidget(btn)

        row.addStretch(1)
        return row

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._lbl_total = QLabel()
        self._lbl_displayed = QLabel()
        self._lbl_displayed.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        row.addWidget(self._lbl_total)
        row.addStretch(1)
        row.addWidget(self._lbl_displayed)
        return row

    def _build_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setObjectName("logSeparator")
        line.setFixedHeight(2)
        return line

    def _build_log_area(self) -> QPlainTextEdit:
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._log_view.setObjectName("logView")

        font = QFont("Consolas", 10)
        if not font.exactMatch():
            font = QFont("Microsoft YaHei", 10)
        self._log_view.setFont(font)
        return self._log_view

    def _update_summary(self, displayed_count: int) -> None:
        self._lbl_total.setText(f"共有{_SAMPLE_TOTAL_COUNT}条操作记录")
        self._lbl_displayed.setText(f"已显示{displayed_count}条记录")

    def _refresh_log_display(self) -> None:
        text = "\n".join(self._all_logs)
        self._log_view.setPlainText(text)
        self._update_summary(len(self._all_logs))

    def _set_day_range(self, day: datetime) -> None:
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = day.replace(hour=23, minute=59, second=59, microsecond=0)
        self._dt_start.setDateTime(_to_qdatetime(start))
        self._dt_end.setDateTime(_to_qdatetime(end))

    def _on_today(self) -> None:
        self._set_day_range(datetime.now())

    def _on_yesterday(self) -> None:
        self._set_day_range(datetime.now() - timedelta(days=1))

    def _on_last_three_days(self) -> None:
        end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)
        start = (end - timedelta(days=2)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self._dt_start.setDateTime(_to_qdatetime(start))
        self._dt_end.setDateTime(_to_qdatetime(end))

    def _on_apply_time_range(self) -> None:
        # 后续按开始/结束时间过滤数据库日志；当前展示全部示例数据
        self._refresh_log_display()

    def _on_clear_logs(self) -> None:
        self._all_logs.clear()
        self._refresh_log_display()

    def _on_reset_logs(self) -> None:
        self._all_logs = list(_SAMPLE_LOG_LINES)
        self._dt_start.setDateTime(_DEFAULT_QDATETIME)
        self._dt_end.setDateTime(_DEFAULT_QDATETIME)
        self._refresh_log_display()
