"""HTTP client for the public 49wz777 draw APIs."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx

from core.config import (
    DRAW_MAX_RETRIES,
    DRAW_REQUEST_INTERVAL,
    DRAW_REQUEST_TIMEOUT,
    DRAW_SOURCE_BASE_URL,
)
from scrapers.exceptions import (
    ScraperForbiddenError,
    ScraperNotFoundError,
    ScraperRateLimitedError,
    ScraperResponseError,
    ScraperServerError,
    ScraperTimeoutError,
)


class Wz49Client:
    """Fetch draw data from 49wz777 public endpoints."""

    api_prefix = "site/h5/"

    def __init__(
        self,
        *,
        base_url: str = DRAW_SOURCE_BASE_URL,
        timeout: float = DRAW_REQUEST_TIMEOUT,
        interval: float = DRAW_REQUEST_INTERVAL,
        max_retries: int = DRAW_MAX_RETRIES,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.interval = interval
        self.max_retries = max_retries
        self._own_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout,
            verify=True,
            headers={
                "User-Agent": "FortuneDrawSync/1.0 (+https://49wz777.com/)",
                "Accept": "application/json,text/plain,*/*",
            },
        )

    def fetch_latest(self, *, lottery_type: int, year: int, page_size: int = 1) -> dict[str, Any]:
        return self.fetch_history_page(
            lottery_type=lottery_type,
            year=year,
            page_num=1,
            page_size=page_size,
            sort=1,
        )

    def fetch_history_page(
        self,
        *,
        lottery_type: int,
        year: int,
        page_num: int,
        page_size: int = 25,
        sort: int = 1,
    ) -> dict[str, Any]:
        return self._get_json(
            "lottery/search",
            params={
                "pageNum": page_num,
                "pageSize": page_size,
                "lotteryType": lottery_type,
                "year": year,
                "sort": sort,
            },
        )

    def fetch_history(
        self,
        *,
        lottery_type: int,
        year: int,
        pages: int,
        page_size: int = 25,
        sort: int = 1,
    ) -> list[dict[str, Any]]:
        responses: list[dict[str, Any]] = []
        for page_num in range(1, pages + 1):
            responses.append(
                self.fetch_history_page(
                    lottery_type=lottery_type,
                    year=year,
                    page_num=page_num,
                    page_size=page_size,
                    sort=sort,
                )
            )
        return responses

    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, self.api_prefix + path.lstrip("/"))
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                time.sleep(min(self.interval * (2 ** (attempt - 2)), 10))
            try:
                response = self._client.get(url, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt == self.max_retries:
                    raise ScraperTimeoutError(f"Request timed out: {path}") from exc
                continue
            except httpx.HTTPError as exc:
                raise ScraperResponseError(f"Request failed: {path}") from exc

            if response.status_code == 403:
                raise ScraperForbiddenError(f"Public access forbidden: {path}")
            if response.status_code == 404:
                raise ScraperNotFoundError(f"Endpoint not found: {path}")
            if response.status_code == 429:
                raise ScraperRateLimitedError(f"Rate limited by source: {path}")
            if response.status_code >= 500:
                last_error = ScraperServerError(f"Server error {response.status_code}: {path}")
                if attempt == self.max_retries:
                    raise last_error
                continue
            if response.status_code >= 400:
                raise ScraperResponseError(f"Unexpected HTTP {response.status_code}: {path}")

            try:
                payload = response.json()
            except ValueError as exc:
                raise ScraperResponseError(f"Response is not JSON: {path}") from exc

            if not isinstance(payload, dict):
                raise ScraperResponseError(f"Response root is not an object: {path}")
            if payload.get("success") is not True:
                raise ScraperResponseError(f"Source returned unsuccessful response: {payload.get('msg')}")
            return payload

        raise ScraperResponseError(f"Request failed after retries: {path}") from last_error
