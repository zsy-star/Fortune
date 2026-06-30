"""Supported bet type constants."""

from __future__ import annotations

from domain.exceptions import InvalidBetTypeError, InvalidRegionError

BET_TYPE_SPECIAL = "特码"
BET_TYPE_PINGTE_ZODIAC = "平特一肖"
BET_TYPE_LIANXIAO = "连肖"
BET_TYPE_LIANWEI = "连尾"
BET_TYPE_NUMBER = "号码"

SUPPORTED_BET_TYPES: frozenset[str] = frozenset(
    {
        BET_TYPE_SPECIAL,
        BET_TYPE_PINGTE_ZODIAC,
        BET_TYPE_LIANXIAO,
        BET_TYPE_LIANWEI,
        BET_TYPE_NUMBER,
        "三中三",
        "二中二",
        "三中二",
        "二中特",
        "特串",
        "平码",
        "不中",
        "N不中",
        "特码两面",
        "特码波色",
        "六肖中特",
        "包半波",
    }
)

REGION_MACAU = "澳门"
REGION_HONG_KONG = "香港"
SUPPORTED_REGIONS: frozenset[str] = frozenset({REGION_MACAU, REGION_HONG_KONG})


def normalize_bet_type(value: str) -> str:
    bet_type = (value or "").strip()
    if bet_type not in SUPPORTED_BET_TYPES:
        raise InvalidBetTypeError(f"Unsupported bet type: {value!r}")
    return bet_type


def normalize_region(value: str) -> str:
    region = (value or "").strip()
    if region not in SUPPORTED_REGIONS:
        raise InvalidRegionError(f"Unsupported region: {value!r}")
    return region
