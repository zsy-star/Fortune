from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from schemas.draw_schema import LotteryDrawCreate
from services.draw_service import DrawService
from services.log_service import LogService
import ui.pages.draw_history_page as draw_history_module
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


class _AcceptedDrawDialog:
    def __init__(self, payload: LotteryDrawCreate | Exception):
        self._payload = payload

    def exec(self):
        return QDialog.DialogCode.Accepted

    def to_draw_create(self, *, source: str = "manual_ui") -> LotteryDrawCreate:
        if isinstance(self._payload, Exception):
            raise self._payload
        self._payload.source = source
        return self._payload


def _patch_manual_dialog(monkeypatch, payload: LotteryDrawCreate | Exception) -> None:
    monkeypatch.setattr(draw_history_module, "_ManualDrawDialog", lambda *args, **kwargs: _AcceptedDrawDialog(payload))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)


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


def test_draw_history_manual_add_valid_draw_success(session_factory, monkeypatch) -> None:
    app()
    payload = LotteryDrawCreate(
        region="澳门",
        issue_number="200",
        draw_date=date(2026, 6, 12),
        regular_numbers=[1, 2, 3, 4, 5, 6],
        special_number=7,
    )
    _patch_manual_dialog(monkeypatch, payload)

    page = DrawHistoryPage(draw_service=DrawService(session_factory))
    page._on_manual_add_draw()

    found = DrawService(session_factory).get_draw("澳门", "200")
    assert found is not None
    assert found.source == "manual_ui"
    assert page._table.rowCount() == 1
    assert LogService(session_factory).count_logs(module="draw", action="create") == 1


def test_draw_history_manual_add_duplicate_fails(session_factory, monkeypatch) -> None:
    app()
    service = DrawService(session_factory)
    service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="201",
            draw_date=date(2026, 6, 13),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
        )
    )
    _patch_manual_dialog(
        monkeypatch,
        LotteryDrawCreate(
            region="澳门",
            issue_number="201",
            draw_date=date(2026, 6, 14),
            regular_numbers=[8, 9, 10, 11, 12, 13],
            special_number=14,
        ),
    )

    page = DrawHistoryPage(draw_service=service)
    page._on_manual_add_draw()

    assert "失败" in page._status_label.text()
    assert service.count_draws() == 1


def test_draw_history_manual_add_invalid_number_fails(session_factory, monkeypatch) -> None:
    app()
    _patch_manual_dialog(monkeypatch, ValueError("Invalid number: 50"))

    page = DrawHistoryPage(draw_service=DrawService(session_factory))
    page._on_manual_add_draw()

    assert "失败" in page._status_label.text()
    assert DrawService(session_factory).count_draws() == 0


def test_draw_history_manual_add_repeated_number_fails(session_factory, monkeypatch) -> None:
    app()
    _patch_manual_dialog(monkeypatch, ValueError("regular_numbers and special_number cannot repeat"))

    page = DrawHistoryPage(draw_service=DrawService(session_factory))
    page._on_manual_add_draw()

    assert "失败" in page._status_label.text()
    assert DrawService(session_factory).count_draws() == 0


def test_draw_history_manual_edit_existing_draw_success(session_factory, monkeypatch) -> None:
    app()
    service = DrawService(session_factory)
    service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="202",
            draw_date=date(2026, 6, 15),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
        )
    )
    _patch_manual_dialog(
        monkeypatch,
        LotteryDrawCreate(
            region="澳门",
            issue_number="202",
            draw_date=date(2026, 6, 16),
            regular_numbers=[8, 9, 10, 11, 12, 13],
            special_number=14,
        ),
    )

    page = DrawHistoryPage(draw_service=service)
    page._table.selectRow(0)
    page._on_manual_edit_draw()

    found = service.get_draw("澳门", "202")
    assert found is not None
    assert found.draw_date == date(2026, 6, 16)
    assert found.regular_numbers == ["08", "09", "10", "11", "12", "13"]
    assert found.special_number == "14"
    assert LogService(session_factory).count_logs(module="draw", action="manual_update") == 1


def test_draw_history_manual_buttons_do_not_disable_sync_buttons(session_factory) -> None:
    app()
    page = DrawHistoryPage(draw_service=DrawService(session_factory))

    assert page._btn_manual_add.isEnabled()
    assert not page._btn_manual_edit.isEnabled()
    assert page._btn_sync_latest.isEnabled()
    assert page._btn_sync_history.isEnabled()
