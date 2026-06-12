from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from models import LotteryDraw
from scrapers.wz49_parser import Wz49Parser
from services.draw_service import DrawService
from services.draw_sync_service import DrawSyncService
from services.log_service import LogService

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class FakeClient:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.history_calls: list[int] = []

    def fetch_latest(self, *, lottery_type: int, year: int, page_size: int = 1) -> dict:
        return self.payloads[0]

    def fetch_history_page(self, *, lottery_type: int, year: int, page_num: int, page_size: int = 25, sort: int = 1) -> dict:
        self.history_calls.append(page_num)
        return self.payloads[min(page_num - 1, len(self.payloads) - 1)]

    def close(self) -> None:
        pass


def fixture_payload() -> dict:
    return json.loads((FIXTURE_DIR / "wz49_history_page.json").read_text(encoding="utf-8"))


def make_service(session_factory, payloads: list[dict]) -> DrawSyncService:
    return DrawSyncService(
        client=FakeClient(payloads),
        parser=Wz49Parser(),
        draw_service=DrawService(session_factory),
        log_service=LogService(session_factory),
    )


def test_first_sync_creates_records_and_second_sync_skips(session_factory) -> None:
    service = make_service(session_factory, [fixture_payload()])

    first = service.sync_latest(lottery_type=2, year=2026)
    assert first.created == 1
    assert first.skipped == 0

    second = service.sync_latest(lottery_type=2, year=2026)
    assert second.created == 0
    assert second.skipped == 1

    with session_factory() as session:
        assert session.scalar(select(func.count(LotteryDraw.id))) == 1
        assert session.scalars(select(LotteryDraw)).one().issue_number == "162"


def test_same_issue_correction_updates_record(session_factory) -> None:
    payload = fixture_payload()
    corrected = fixture_payload()
    corrected["data"]["recordList"][0]["numberList"][-1]["number"] = "31"

    service = make_service(session_factory, [payload])
    assert service.sync_latest(lottery_type=2, year=2026).created == 1

    correction_service = make_service(session_factory, [corrected])
    result = correction_service.sync_latest(lottery_type=2, year=2026)
    assert result.updated == 1

    with session_factory() as session:
        draw = session.scalars(select(LotteryDraw)).one()
        assert draw.special_number == "31"
        assert session.scalar(select(func.count(LotteryDraw.id))) == 1


def test_history_paging_processes_requested_pages(session_factory) -> None:
    payload = fixture_payload()
    fake_client = FakeClient([payload, payload])
    service = DrawSyncService(
        client=fake_client,
        parser=Wz49Parser(),
        draw_service=DrawService(session_factory),
        log_service=LogService(session_factory),
    )

    result = service.sync_history_pages(lottery_type=2, year=2026, pages=2, page_size=2)
    assert fake_client.history_calls == [1, 2]
    assert result.created == 2
    assert result.skipped == 2
