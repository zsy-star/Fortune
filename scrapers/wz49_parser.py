"""Parser for 49wz777 draw JSON responses."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from schemas.draw_schema import LotteryDrawCreate
from scrapers.exceptions import ScraperResponseError

LOTTERY_TYPE_REGION = {
    2: "澳门",
    1: "香港",
}

SUPPORTED_LOTTERY_TYPES = frozenset(LOTTERY_TYPE_REGION)
_CHINESE_DATE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$")


class Wz49Parser:
    """Convert source JSON records into LotteryDrawCreate DTOs."""

    def parse_latest(self, payload: dict[str, Any], *, lottery_type: int) -> LotteryDrawCreate:
        records = self._record_list(payload)
        if not records:
            raise ScraperResponseError("Latest response contains no records")
        return self.parse_record(records[0], lottery_type=lottery_type)

    def parse_history_page(self, payload: dict[str, Any], *, lottery_type: int) -> list[LotteryDrawCreate]:
        return [self.parse_record(record, lottery_type=lottery_type) for record in self._record_list(payload)]

    def parse_record(self, record: dict[str, Any], *, lottery_type: int | None = None) -> LotteryDrawCreate:
        if not isinstance(record, dict):
            raise ScraperResponseError("Draw record is not an object")

        source_type = lottery_type if lottery_type is not None else record.get("lotteryType")
        try:
            region = LOTTERY_TYPE_REGION[int(source_type)]
        except (TypeError, ValueError, KeyError):
            raise ScraperResponseError(f"Unsupported lotteryType: {source_type!r}") from None

        issue_number = str(record.get("periodStr") or record.get("period") or "").strip()
        if not issue_number:
            raise ScraperResponseError("Draw record is missing periodStr/period")

        draw_date = self._parse_draw_date(record.get("lotteryTime"))
        number_list = record.get("numberList")
        if not isinstance(number_list, list) or len(number_list) != 7:
            raise ScraperResponseError("Draw record numberList must contain 7 numbers")

        numbers: list[str] = []
        for item in number_list:
            if not isinstance(item, dict) or "number" not in item:
                raise ScraperResponseError("Draw number item is missing number")
            numbers.append(str(item["number"]).strip())

        return LotteryDrawCreate(
            region=region,
            issue_number=issue_number,
            draw_date=draw_date,
            regular_numbers=numbers[:6],
            special_number=numbers[6],
            source="49wz777",
            status="confirmed",
        )

    def _record_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ScraperResponseError("Response data is missing or not an object")
        records = data.get("recordList")
        if not isinstance(records, list):
            raise ScraperResponseError("Response data.recordList is missing or not a list")
        return records

    def _parse_draw_date(self, value: Any) -> date:
        text = str(value or "").strip()
        if not text:
            raise ScraperResponseError("Draw record is missing lotteryTime")
        match = _CHINESE_DATE.match(text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            return date(year, month, day)
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise ScraperResponseError(f"Unsupported lotteryTime format: {text!r}") from None
