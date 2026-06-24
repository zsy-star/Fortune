"""DTOs used by the settings service and dialog."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OddsRebateItemResult:
    id: int
    plan_id: int
    bet_type: str
    odds: Decimal
    rebate: Decimal


@dataclass(frozen=True, slots=True)
class OddsRebatePlanResult:
    id: int
    name: str
    is_default: bool
    items: tuple[OddsRebateItemResult, ...]


@dataclass(frozen=True, slots=True)
class OddsRebateItemUpdate:
    id: int
    odds: Decimal | int | float | str
    rebate: Decimal | int | float | str


@dataclass(frozen=True, slots=True)
class DeclarerSettingResult:
    id: int
    name: str
    plan_id: int
    plan_name: str


@dataclass(frozen=True, slots=True)
class SecretSettingsResult:
    import_key: str
    export_key: str
