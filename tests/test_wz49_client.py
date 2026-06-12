from __future__ import annotations

import httpx
import pytest

from scrapers.exceptions import (
    ScraperForbiddenError,
    ScraperRateLimitedError,
    ScraperServerError,
    ScraperTimeoutError,
)
from scrapers.wz49_client import Wz49Client


def make_client(handler) -> Wz49Client:
    return Wz49Client(
        base_url="https://49wz777.com/",
        interval=0,
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_fetch_history_page_builds_expected_request() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"success": True, "data": {"recordList": []}})

    client = make_client(handler)
    payload = client.fetch_history_page(lottery_type=2, year=2026, page_num=2, page_size=3)
    assert payload["success"] is True
    assert "/site/h5/lottery/search" in seen["url"]
    assert "pageNum=2" in seen["url"]
    assert "pageSize=3" in seen["url"]


def test_timeout_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    with pytest.raises(ScraperTimeoutError):
        make_client(handler).fetch_latest(lottery_type=2, year=2026)


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (403, ScraperForbiddenError),
        (429, ScraperRateLimitedError),
        (500, ScraperServerError),
    ],
)
def test_http_error_handling(status_code: int, expected: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"success": False})

    with pytest.raises(expected):
        make_client(handler).fetch_latest(lottery_type=2, year=2026)
