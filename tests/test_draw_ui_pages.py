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
    def __init__(self, payload: LotteryDrawCreate | Exception, reason: str = "人工核对修正"):
        self._payload = payload
        self._reason = reason

    def exec(self):
        return QDialog.DialogCode.Accepted

    def to_draw_create(self, *, source: str = "manual_ui") -> LotteryDrawCreate:
        if isinstance(self._payload, Exception):
            raise self._payload
        self._payload.source = source
        return self._payload

    def correction_reason(self) -> str:
        return self._reason


def _patch_manual_dialog(
    monkeypatch,
    payload: LotteryDrawCreate | Exception,
    *,
    reason: str = "人工核对修正",
    confirm=QMessageBox.StandardButton.Yes,
) -> list[str]:
    question_messages: list[str] = []

    def question(*args, **kwargs):
        if len(args) >= 3:
            question_messages.append(str(args[2]))
        return confirm

    monkeypatch.setattr(
        draw_history_module,
        "_ManualDrawDialog",
        lambda *args, **kwargs: _AcceptedDrawDialog(payload, reason),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "question", question)
    return question_messages


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
    question_messages = _patch_manual_dialog(
        monkeypatch,
        LotteryDrawCreate(
            region="澳门",
            issue_number="202",
            draw_date=date(2026, 6, 16),
            regular_numbers=[8, 9, 10, 11, 12, 13],
            special_number=14,
        ),
        reason="同步源更正",
    )

    page = DrawHistoryPage(draw_service=service)
    page._table.selectRow(0)
    page._on_manual_edit_draw()

    found = service.get_draw("澳门", "202")
    assert found is not None
    assert found.draw_date == date(2026, 6, 16)
    assert found.regular_numbers == ["08", "09", "10", "11", "12", "13"]
    assert found.special_number == "14"
    logs = LogService(session_factory).list_logs(module="draw", action="manual_update")
    assert len(logs) == 1
    assert "reason=同步源更正" in logs[0].description
    assert "before_numbers=regular=[01,02,03,04,05,06], special=07" in logs[0].description
    assert "after_numbers=regular=[08,09,10,11,12,13], special=14" in logs[0].description
    assert len(question_messages) == 1
    assert "地区：澳门" in question_messages[0]
    assert "期号：202" in question_messages[0]
    assert "修正前号码：正码 01 02 03 04 05 06 / 特码 07" in question_messages[0]
    assert "修正后号码：正码 08 09 10 11 12 13 / 特码 14" in question_messages[0]
    assert "修正原因：同步源更正" in question_messages[0]


def test_draw_history_manual_edit_empty_reason_fails(session_factory, monkeypatch) -> None:
    app()
    service = DrawService(session_factory)
    service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="203",
            draw_date=date(2026, 6, 17),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
        )
    )
    question_messages = _patch_manual_dialog(
        monkeypatch,
        LotteryDrawCreate(
            region="澳门",
            issue_number="203",
            draw_date=date(2026, 6, 18),
            regular_numbers=[8, 9, 10, 11, 12, 13],
            special_number=14,
        ),
        reason="   ",
    )

    page = DrawHistoryPage(draw_service=service)
    page._table.selectRow(0)
    page._on_manual_edit_draw()

    found = service.get_draw("澳门", "203")
    assert found is not None
    assert found.special_number == "07"
    assert "修正原因不能为空" in page._status_label.text()
    assert question_messages == []
    assert LogService(session_factory).count_logs(module="draw", action="manual_update") == 0


def test_draw_history_manual_edit_cancel_confirmation_does_not_save(session_factory, monkeypatch) -> None:
    app()
    service = DrawService(session_factory)
    service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="204",
            draw_date=date(2026, 6, 19),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
        )
    )
    update_calls = []
    original_update = service.update_draw

    def track_update(*args, **kwargs):
        update_calls.append((args, kwargs))
        return original_update(*args, **kwargs)

    monkeypatch.setattr(service, "update_draw", track_update)
    question_messages = _patch_manual_dialog(
        monkeypatch,
        LotteryDrawCreate(
            region="澳门",
            issue_number="204",
            draw_date=date(2026, 6, 20),
            regular_numbers=[8, 9, 10, 11, 12, 13],
            special_number=14,
        ),
        reason="录入复核发现错误",
        confirm=QMessageBox.StandardButton.No,
    )

    page = DrawHistoryPage(draw_service=service)
    page._table.selectRow(0)
    page._on_manual_edit_draw()

    found = service.get_draw("澳门", "204")
    assert found is not None
    assert found.special_number == "07"
    assert len(question_messages) == 1
    assert update_calls == []
    assert LogService(session_factory).count_logs(module="draw", action="manual_update") == 0


def test_draw_history_manual_buttons_do_not_disable_sync_buttons(session_factory) -> None:
    app()
    page = DrawHistoryPage(draw_service=DrawService(session_factory))

    assert page._btn_manual_add.isEnabled()
    assert not page._btn_manual_edit.isEnabled()
    assert page._btn_sync_latest.isEnabled()
    assert page._btn_sync_history.isEnabled()
