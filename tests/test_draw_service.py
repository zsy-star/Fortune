from __future__ import annotations

from datetime import date

import pytest

from domain.exceptions import DuplicateDrawError, InvalidNumberError
from schemas.draw_schema import LotteryDrawCreate
from services.draw_service import DrawService


def test_create_draw_and_query(session_factory) -> None:
    service = DrawService(session_factory)
    draw = service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="001",
            draw_date=date(2026, 1, 1),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
            source="manual",
        )
    )

    assert draw.id is not None
    assert draw.regular_numbers == ["01", "02", "03", "04", "05", "06"]
    assert draw.special_number == "07"

    found = service.get_draw("澳门", "001")
    assert found is not None
    assert found.issue_number == "001"
    assert service.get_latest_draw("澳门").issue_number == "001"


def test_duplicate_draw_rejected(session_factory) -> None:
    service = DrawService(session_factory)
    payload = LotteryDrawCreate(
        region="香港",
        issue_number="009",
        draw_date=date(2026, 2, 1),
        regular_numbers=[1, 2, 3, 4, 5, 6],
        special_number=7,
    )
    service.create_draw(payload)

    with pytest.raises(DuplicateDrawError):
        service.create_draw(
            LotteryDrawCreate(
                region="香港",
                issue_number="009",
                draw_date=date(2026, 2, 1),
                regular_numbers=[8, 9, 10, 11, 12, 13],
                special_number=14,
            )
        )


def test_draw_rejects_repeated_numbers() -> None:
    with pytest.raises(DuplicateDrawError):
        LotteryDrawCreate(
            region="澳门",
            issue_number="010",
            draw_date=date(2026, 2, 2),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=6,
        )


def test_draw_rejects_out_of_range_numbers() -> None:
    with pytest.raises(InvalidNumberError):
        LotteryDrawCreate(
            region="澳门",
            issue_number="011",
            draw_date=date(2026, 2, 3),
            regular_numbers=[1, 2, 3, 4, 5, 50],
            special_number=7,
        )
