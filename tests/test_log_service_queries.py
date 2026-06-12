from __future__ import annotations

from datetime import datetime, timedelta

from services.log_service import LogService


def test_log_service_filters_count_pagination_and_order(session_factory) -> None:
    service = LogService(session_factory)
    first = service.create_log(
        module="draw_sync",
        action="start",
        description="同步开始",
        operator="system",
        related_type="draw",
        related_id=1,
    )
    second = service.create_log(
        module="订单详情",
        action="查看订单",
        description="查看订单 ORD001",
        related_type="order",
        related_id=2,
    )

    assert [log.id for log in service.list_logs(limit=10)] == [second.id, first.id]
    assert service.count_logs(module="订单") == 1
    assert service.count_logs(action="查看") == 1
    assert service.count_logs(keyword="同步") == 1
    assert service.count_logs(related_type="order") == 1
    assert service.count_logs(operator="system") == 1

    now = datetime.now()
    assert service.count_logs(start_date=now - timedelta(days=1), end_date=now + timedelta(days=1)) == 2
    assert [log.id for log in service.list_logs(limit=1, offset=1)] == [first.id]

    log = service.list_logs(keyword="ORD001")[0]
    assert log.description == "查看订单 ORD001"
