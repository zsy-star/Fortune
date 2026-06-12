from __future__ import annotations

from datetime import date

from schemas.draw_schema import LotteryDrawCreate
from services.draw_service import DrawService


def add_draw(service: DrawService, region: str, issue: str, draw_date: date) -> None:
    service.create_draw(
        LotteryDrawCreate(
            region=region,
            issue_number=issue,
            draw_date=draw_date,
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
            source="test",
        )
    )


def test_draw_service_filters_pagination_count_and_order(session_factory) -> None:
    service = DrawService(session_factory)
    add_draw(service, "澳门", "100", date(2026, 1, 1))
    add_draw(service, "澳门", "101", date(2026, 1, 2))
    add_draw(service, "香港", "050", date(2026, 1, 3))

    assert [d.issue_number for d in service.list_draws(region="澳门")] == ["101", "100"]
    assert [d.issue_number for d in service.list_draws(issue_number="10")] == ["101", "100"]
    assert [d.issue_number for d in service.list_draws(start_date=date(2026, 1, 2))] == ["050", "101"]
    assert [d.issue_number for d in service.list_draws(end_date=date(2026, 1, 2))] == ["101", "100"]
    assert [d.issue_number for d in service.list_draws(limit=1, offset=1)] == ["101"]
    assert service.count_draws(region="澳门") == 2
    assert service.count_draws(region="香港", issue_number="999") == 0
    assert service.list_draws(region="香港", issue_number="999") == []
