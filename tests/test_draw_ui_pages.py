from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from schemas.draw_schema import LotteryDrawCreate
from services.draw_service import DrawService
from ui.pages.draw_history_page import DrawHistoryPage
from ui.pages.today_draw_page import TodayDrawPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def add_draw(session_factory) -> None:
    DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="162",
            draw_date=date(2026, 6, 11),
            regular_numbers=[23, 41, 24, 26, 33, 7],
            special_number=32,
            source="49wz777",
        )
    )


def test_today_draw_page_loads_latest_and_empty_region(session_factory) -> None:
    app()
    add_draw(session_factory)

    page = TodayDrawPage(draw_service=DrawService(session_factory))
    page.reload_data()

    assert "第162期" in page._region_widgets["澳门"]["badge"].text()
    assert page._region_widgets["香港"]["meta"].text() == "暂无开奖数据"


def test_today_draw_page_empty_state(session_factory) -> None:
    app()

    page = TodayDrawPage(draw_service=DrawService(session_factory))
    page.reload_data()

    assert page._region_widgets["澳门"]["meta"].text() == "暂无开奖数据"
    assert page._region_widgets["香港"]["meta"].text() == "暂无开奖数据"


def test_draw_history_page_loads_records(session_factory) -> None:
    app()
    add_draw(session_factory)

    page = DrawHistoryPage(draw_service=DrawService(session_factory))
    page.reload_data()

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "澳门"
    assert page._table.item(0, 1).text() == "162"
