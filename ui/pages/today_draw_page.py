"""今日开奖页面：读取本地开奖库，支持手动后台刷新。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from domain.color_rules import get_wave_color
from domain.zodiac_rules import get_zodiac
from models import LotteryDraw
from services.draw_service import DrawService
from services.draw_sync_service import DrawSyncResult
from ui.app_events import app_events
from ui.workers import DrawSyncTask

REGION_LOTTERY_TYPE = {"澳门": 2, "香港": 1}
REGION_BADGE_COLORS = {"澳门": "#008b7d", "香港": "#3498db"}
WAVE_COLORS = {"红波": "#e74c3c", "蓝波": "#3498db", "绿波": "#27ae60"}


@dataclass(frozen=True)
class BallInfo:
    number: str
    zodiac: str
    color: str


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
    time_text="兼容旧页面引用",
    badge_color=REGION_BADGE_COLORS["澳门"],
)


class TodayDrawPage(QWidget):
    def __init__(self, parent=None, draw_service: DrawService | None = None):
        super().__init__(parent)
        self._draw_service = draw_service or DrawService()
        self._sync_task: DrawSyncTask | None = None
        self._region_widgets: dict[str, dict[str, object]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(20)

        for region in REGION_LOTTERY_TYPE:
            root.addWidget(self._build_draw_block(region))

        root.addWidget(self._build_status_panel())
        root.addStretch(1)

        self._apply_stylesheet()
        app_events.draws_changed.connect(self._on_draws_changed)
        self.reload_data()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload_data()

    def reload_data(self) -> None:
        for region in REGION_LOTTERY_TYPE:
            draw = self._draw_service.get_latest_draw(region)
            self._render_region(region, draw)

    def _on_draws_changed(self) -> None:
        try:
            self.reload_data()
        except Exception as exc:
            self._sync_status.setText(f"开奖数据已变更，但自动刷新失败：{exc}")

    def _build_draw_block(self, region: str) -> QWidget:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        badge = QLabel(f"{region}: 暂无开奖数据")
        badge.setObjectName("drawBadge")
        badge.setStyleSheet(
            f"background-color: {REGION_BADGE_COLORS[region]}; color: #ffffff; "
            "padding: 6px 14px; font-size: 14px; font-weight: 600; border-radius: 2px;"
        )
        badge.setFixedHeight(32)

        refresh_btn = QPushButton(f"刷新{region}开奖")
        refresh_btn.setObjectName("refreshButton")
        refresh_btn.clicked.connect(lambda _checked=False, r=region: self._refresh_region(r))

        header.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        header.addStretch(1)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        meta = QLabel("暂无开奖数据")
        meta.setObjectName("drawMeta")
        meta.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(meta)

        balls_row = QHBoxLayout()
        balls_row.setSpacing(6)
        balls_row.addStretch(1)
        ball_widgets: list[QWidget] = []
        for idx in range(7):
            if idx == 6:
                balls_row.addSpacing(28)
            cell = self._build_ball_cell("--", "", special=idx == 6)
            balls_row.addWidget(cell)
            ball_widgets.append(cell)
        balls_row.addStretch(1)
        layout.addLayout(balls_row)

        status = QLabel("当前状态：本地无数据")
        status.setObjectName("drawStatus")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status)

        self._region_widgets[region] = {
            "badge": badge,
            "meta": meta,
            "balls": ball_widgets,
            "status": status,
            "button": refresh_btn,
        }
        return block

    def _build_ball_cell(self, number: str, zodiac: str, *, special: bool = False) -> QWidget:
        cell = QWidget()
        col = QVBoxLayout(cell)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        num_lbl = QLabel(number)
        num_lbl.setObjectName("specialBall" if special else "normalBall")
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_lbl.setFixedSize(52, 52)

        zodiac_lbl = QLabel(zodiac)
        zodiac_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zodiac_lbl.setFixedSize(52, 36)
        zodiac_lbl.setObjectName("zodiacCell")

        col.addWidget(num_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addWidget(zodiac_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        return cell

    def _build_status_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("controlPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)

        self._btn_refresh_all = QPushButton("刷新全部开奖")
        self._btn_refresh_all.setObjectName("refreshButton")
        self._btn_refresh_all.clicked.connect(self._refresh_all)
        self._sync_status = QLabel("页面打开时只读取本地数据库，不自动联网。")
        self._sync_status.setObjectName("syncStatus")

        layout.addWidget(self._btn_refresh_all)
        layout.addWidget(self._sync_status, stretch=1)
        return panel

    def _render_region(self, region: str, draw: LotteryDraw | None) -> None:
        widgets = self._region_widgets[region]
        badge: QLabel = widgets["badge"]  # type: ignore[assignment]
        meta: QLabel = widgets["meta"]  # type: ignore[assignment]
        status: QLabel = widgets["status"]  # type: ignore[assignment]
        balls: list[QWidget] = widgets["balls"]  # type: ignore[assignment]

        if draw is None:
            badge.setText(f"{region}: 暂无开奖数据")
            meta.setText("暂无开奖数据")
            status.setText("当前状态：本地无数据")
            for cell in balls:
                self._set_ball(cell, "--", "", None)
            return

        badge.setText(f"{region}: 第{draw.issue_number}期开奖结果")
        updated = draw.updated_at.strftime("%Y-%m-%d %H:%M:%S") if draw.updated_at else "-"
        latest_hint = ""
        if draw.draw_date != date.today():
            latest_hint = f"    最新一期：{draw.draw_date.isoformat()}"
        meta.setText(
            f"开奖日期：{draw.draw_date.isoformat()}    来源：{draw.source or '-'}"
            f"    数据库更新时间：{updated}{latest_hint}"
        )
        status.setText(f"当前状态：{draw.status}")

        numbers = list(draw.regular_numbers) + [draw.special_number]
        for idx, (cell, number) in enumerate(zip(balls, numbers)):
            zodiac = get_zodiac(number, year=draw.draw_date.year)
            self._set_ball(cell, number, zodiac, get_wave_color(number), special=idx == 6)

    def _set_ball(
        self,
        cell: QWidget,
        number: str,
        zodiac: str,
        wave_color: str | None,
        *,
        special: bool = False,
    ) -> None:
        num_lbl = cell.findChild(QLabel, "specialBall" if special else "normalBall")
        if num_lbl is None:
            num_lbl = cell.findChildren(QLabel)[0]
        zodiac_lbl = cell.findChild(QLabel, "zodiacCell")
        bg = WAVE_COLORS.get(wave_color or "", "#95a5a6")
        if special:
            bg = WAVE_COLORS.get(wave_color or "", "#e67e22")
        num_lbl.setText(number)
        num_lbl.setStyleSheet(
            f"background-color: {bg}; color: #ffffff; font-size: 20px; "
            "font-weight: 700; border-radius: 4px;"
        )
        if zodiac_lbl is not None:
            zodiac_lbl.setText(zodiac)

    def _refresh_region(self, region: str) -> None:
        self._start_sync([region])

    def _refresh_all(self) -> None:
        self._start_sync(list(REGION_LOTTERY_TYPE))

    def _start_sync(self, regions: list[str]) -> None:
        if self._sync_task and self._sync_task.is_active():
            self._sync_status.setText("已有同步任务正在执行，请稍候。")
            return

        self._set_refresh_enabled(False)
        self._pending_regions = list(regions)
        self._sync_totals = DrawSyncResult()
        self._sync_next_region()

    def _sync_next_region(self) -> None:
        if not self._pending_regions:
            self._set_refresh_enabled(True)
            self._sync_status.setText(self._summary_text(self._sync_totals))
            return

        region = self._pending_regions.pop(0)
        self._sync_status.setText(f"正在获取{region}开奖...")
        self._sync_task = DrawSyncTask(
            mode="latest",
            lottery_type=REGION_LOTTERY_TYPE[region],
            year=date.today().year,
            parent=self,
        )
        self._sync_task.progress.connect(self._on_sync_progress)
        self._sync_task.succeeded.connect(lambda result, r=region: self._on_sync_success(r, result))
        self._sync_task.failed.connect(lambda message, r=region: self._on_sync_failed(r, message))
        self._sync_task.finished.connect(self._sync_next_region)
        self._sync_task.start()

    @Slot(str)
    def _on_sync_progress(self, message: str) -> None:
        self._sync_status.setText(message)

    def _on_sync_success(self, region: str, result: DrawSyncResult) -> None:
        self._sync_totals.created += result.created
        self._sync_totals.updated += result.updated
        self._sync_totals.skipped += result.skipped
        self._sync_totals.failed += result.failed
        self._sync_totals.errors.extend(result.errors)
        if result.skipped and not result.created and not result.updated and not result.failed:
            self._sync_status.setText(f"{region}没有新数据，当前已经是最新一期。")
        else:
            self._sync_status.setText(f"{region}{self._summary_text(result)}")
        app_events.draws_changed.emit()
        app_events.logs_changed.emit()

    def _on_sync_failed(self, region: str, message: str) -> None:
        self._sync_totals.failed += 1
        self._sync_totals.errors.append(f"{region}: {message}")
        self._sync_status.setText(f"{region}刷新失败：{self._friendly_error(message)}")
        app_events.logs_changed.emit()

    def _set_refresh_enabled(self, enabled: bool) -> None:
        self._btn_refresh_all.setEnabled(enabled)
        for widgets in self._region_widgets.values():
            button: QPushButton = widgets["button"]  # type: ignore[assignment]
            button.setEnabled(enabled)

    def _summary_text(self, result: DrawSyncResult) -> str:
        if result.skipped and not result.created and not result.updated and not result.failed:
            return "没有新数据，当前已经是最新一期。"
        return (
            f"新增{result.created}条，更新{result.updated}条，"
            f"跳过{result.skipped}条，失败{result.failed}条。"
        )

    def _friendly_error(self, message: str) -> str:
        lower = message.lower()
        if "timed out" in lower or "timeout" in lower:
            return "网络超时，请稍后重试。"
        if "forbidden" in lower or "403" in lower:
            return "数据源拒绝访问。"
        if "rate limited" in lower or "429" in lower:
            return "请求过于频繁，请稍后再试。"
        if "server error" in lower or "500" in lower:
            return "数据源服务器异常。"
        if "response" in lower or "json" in lower:
            return "网站响应格式发生变化。"
        return message

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #F5F7FA;
            }
            QLabel#drawMeta {
                color: #243447;
                font-size: 13px;
            }
            QLabel#drawStatus, QLabel#syncStatus {
                color: #6b7c8f;
                font-size: 13px;
            }
            QLabel#zodiacCell {
                background-color: #ffffff;
                border: 1px solid #cfd8e3;
                border-radius: 4px;
                font-size: 16px;
                color: #243447;
            }
            QFrame#controlPanel {
                border: 1px solid #d7dee7;
                background-color: #ffffff;
                border-radius: 6px;
                margin-top: 8px;
            }
            QPushButton#refreshButton {
                padding: 6px 14px;
                border: 1px solid #c4ceda;
                border-radius: 5px;
                background: #ffffff;
                color: #1f4e79;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#refreshButton:hover {
                background: #edf5ff;
                border-color: #8eb8e8;
            }
            QPushButton#refreshButton:disabled {
                color: #95a5a6;
            }
            """
        )
