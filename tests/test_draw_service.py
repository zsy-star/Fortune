from __future__ import annotations

from datetime import date

import pytest

from domain.exceptions import DuplicateDrawError, InvalidNumberError
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.log_service import LogService
from services.order_service import OrderService
from services.settlement_service import SettlementService


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


def test_manual_create_draw_writes_operation_log(session_factory) -> None:
    service = DrawService(session_factory)
    draw = service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="012",
            draw_date=date(2026, 2, 4),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
            source="manual_ui",
        )
    )

    logs = LogService(session_factory).list_logs(module="draw", action="create")

    assert len(logs) == 1
    assert logs[0].related_type == "lottery_draw"
    assert logs[0].related_id == draw.id


def test_update_draw_success_and_writes_operation_log(session_factory) -> None:
    service = DrawService(session_factory)
    draw = service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="013",
            draw_date=date(2026, 2, 5),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
        )
    )

    updated = service.update_draw(
        draw.id,
        LotteryDrawCreate(
            region="澳门",
            issue_number="013",
            draw_date=date(2026, 2, 6),
            regular_numbers=[8, 9, 10, 11, 12, 13],
            special_number=14,
            source="manual_ui",
        ),
        reason="同步源号码更正",
    )

    assert updated.draw_date == date(2026, 2, 6)
    assert updated.regular_numbers == ["08", "09", "10", "11", "12", "13"]
    assert updated.special_number == "14"
    logs = LogService(session_factory).list_logs(module="draw", action="manual_update")
    assert len(logs) == 1
    assert "reason=同步源号码更正" in logs[0].description
    assert "draw_id=" in logs[0].description
    assert "region=澳门" in logs[0].description
    assert "issue_number=013" in logs[0].description
    assert "before_numbers=regular=[01,02,03,04,05,06], special=07" in logs[0].description
    assert "after_numbers=regular=[08,09,10,11,12,13], special=14" in logs[0].description


def test_update_draw_requires_non_empty_reason(session_factory) -> None:
    service = DrawService(session_factory)
    draw = service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="017",
            draw_date=date(2026, 2, 11),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
        )
    )

    with pytest.raises(ValueError, match="reason"):
        service.update_draw(
            draw.id,
            LotteryDrawCreate(
                region="澳门",
                issue_number="017",
                draw_date=date(2026, 2, 12),
                regular_numbers=[8, 9, 10, 11, 12, 13],
                special_number=14,
            ),
            reason="   ",
        )

    found = service.get_draw("澳门", "017")
    assert found is not None
    assert found.special_number == "07"
    assert LogService(session_factory).count_logs(module="draw", action="manual_update") == 0


def test_update_draw_duplicate_region_issue_rejected(session_factory) -> None:
    service = DrawService(session_factory)
    service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="014",
            draw_date=date(2026, 2, 7),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
        )
    )
    draw = service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="015",
            draw_date=date(2026, 2, 8),
            regular_numbers=[8, 9, 10, 11, 12, 13],
            special_number=14,
        )
    )

    with pytest.raises(DuplicateDrawError):
        service.update_draw(
            draw.id,
            LotteryDrawCreate(
                region="澳门",
                issue_number="014",
                draw_date=date(2026, 2, 9),
                regular_numbers=[15, 16, 17, 18, 19, 20],
                special_number=21,
            ),
            reason="修正重复期号测试",
        )


def test_manual_draw_can_be_used_by_settlement_preview(session_factory) -> None:
    draw = DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="016",
            draw_date=date(2026, 2, 10),
            regular_numbers=[1, 2, 3, 4, 5, 6],
            special_number=7,
            source="manual_ui",
        )
    )
    order = OrderService(session_factory).create_order(
        OrderCreate(
            region="澳门",
            raw_text="manual preview",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="07", amount="10")],
        )
    )

    preview = SettlementService(session_factory).preview_order(order.id, draw.id)

    assert preview.winning_items == 1
