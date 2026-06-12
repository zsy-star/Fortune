"""Operation log DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class OperationLogResult:
    id: int
    module: str
    action: str
    description: str
    operator: str | None
    related_type: str | None
    related_id: int | None
    created_at: datetime
