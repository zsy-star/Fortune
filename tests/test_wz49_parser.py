from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.exceptions import DuplicateDrawError, InvalidNumberError
from scrapers.exceptions import ScraperResponseError
from scrapers.wz49_parser import Wz49Parser

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_latest_and_history_response_parsing() -> None:
    parser = Wz49Parser()
    payload = load_fixture("wz49_history_page.json")

    latest = parser.parse_latest(payload, lottery_type=2)
    assert latest.region == "澳门"
    assert latest.issue_number == "162"
    assert latest.draw_date.isoformat() == "2026-06-11"
    assert latest.regular_numbers == ["23", "41", "24", "26", "33", "07"]
    assert latest.special_number == "32"

    history = parser.parse_history_page(payload, lottery_type=2)
    assert len(history) == 2
    assert history[1].issue_number == "161"


def test_parser_standardizes_numbers_and_separates_special() -> None:
    parser = Wz49Parser()
    record = {
        "lotteryTime": "2026年01月01日",
        "lotteryType": 1,
        "periodStr": "001",
        "numberList": [{"number": n} for n in [1, 2, 3, 4, 5, 6, 7]],
    }
    draw = parser.parse_record(record)
    assert draw.region == "香港"
    assert draw.regular_numbers == ["01", "02", "03", "04", "05", "06"]
    assert draw.special_number == "07"


def test_parser_rejects_duplicate_numbers() -> None:
    parser = Wz49Parser()
    record = {
        "lotteryTime": "2026年01月01日",
        "lotteryType": 2,
        "periodStr": "001",
        "numberList": [{"number": n} for n in [1, 2, 3, 4, 5, 6, 6]],
    }
    with pytest.raises(DuplicateDrawError):
        parser.parse_record(record)


def test_parser_rejects_out_of_range_numbers() -> None:
    parser = Wz49Parser()
    record = {
        "lotteryTime": "2026年01月01日",
        "lotteryType": 2,
        "periodStr": "001",
        "numberList": [{"number": n} for n in [1, 2, 3, 4, 5, 6, 50]],
    }
    with pytest.raises(InvalidNumberError):
        parser.parse_record(record)


def test_parser_rejects_missing_required_fields() -> None:
    parser = Wz49Parser()
    with pytest.raises(ScraperResponseError):
        parser.parse_record({"lotteryType": 2, "numberList": []})
