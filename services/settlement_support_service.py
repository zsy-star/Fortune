"""Read-only settlement support status for order items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from settlement.bet_normalizer import BetTypeNormalizer
from settlement.exceptions import InvalidSelectionError, UnsupportedBetTypeError
from settlement.settlement_engine import MATCHERS


@dataclass(frozen=True, slots=True)
class SettlementSupportResult:
    is_supported: bool
    status: str
    play_type: str
    selection: str
    normalized_bet_type: str | None = None
    reason: str = ""
    message: str = ""
    suggestion: str = ""


class SettlementSupportService:
    """Centralized first-release support check.

    This service only answers whether an order item can enter formal
    settlement with the current engine. It does not evaluate winning, read
    draws, or write business data.
    """

    def __init__(self, normalizer: BetTypeNormalizer | None = None):
        self._normalizer = normalizer or BetTypeNormalizer()

    def check_item(
        self,
        bet_type: str,
        selection: str,
        *,
        note: str | None = None,
    ) -> SettlementSupportResult:
        play_type = (bet_type or "").strip()
        raw_selection = (selection or "").strip()
        if not play_type:
            return self._unsupported(play_type, raw_selection, "投注类型为空")
        if not raw_selection:
            return self._unsupported(play_type, raw_selection, "投注内容为空")

        try:
            normalized = self._normalizer.normalize(play_type, raw_selection, note=note)
        except UnsupportedBetTypeError as exc:
            return self._unsupported(play_type, raw_selection, str(exc))
        except InvalidSelectionError as exc:
            return self._unsupported(play_type, raw_selection, f"投注内容暂不能正式结算：{exc}")

        if normalized.normalized_bet_type not in MATCHERS:
            return self._unsupported(
                play_type,
                raw_selection,
                f"当前结算引擎未接入玩法：{normalized.normalized_bet_type}",
                normalized_bet_type=normalized.normalized_bet_type,
            )

        return SettlementSupportResult(
            is_supported=True,
            status="supported",
            play_type=play_type,
            selection=raw_selection,
            normalized_bet_type=normalized.normalized_bet_type,
            reason="第一版正式结算已支持",
            message=f"玩法「{play_type}」第一版正式结算已支持。",
            suggestion="可正常进行结算预览和正式结算。",
        )

    def check_order_items(self, items: list[Any] | tuple[Any, ...]) -> list[SettlementSupportResult]:
        return [
            self.check_item(
                str(getattr(item, "bet_type", "") or ""),
                str(getattr(item, "selection", "") or ""),
                note=getattr(item, "note", None),
            )
            for item in items
        ]

    def unsupported_results(self, items: list[Any] | tuple[Any, ...]) -> list[SettlementSupportResult]:
        return [result for result in self.check_order_items(items) if not result.is_supported]

    def summarize_order_items(self, items: list[Any] | tuple[Any, ...]) -> str:
        results = self.check_order_items(items)
        unsupported = [result for result in results if not result.is_supported]
        if not results:
            return "无订单明细，无法判断结算支持状态。"
        if not unsupported:
            return "结算支持：全部明细第一版正式结算已支持。"
        lines = [
            f"{result.play_type}/{result.selection}：{result.reason}"
            for result in unsupported
        ]
        return "结算支持：含暂不支持正式结算玩法；" + "；".join(lines)

    def _unsupported(
        self,
        play_type: str,
        selection: str,
        reason: str,
        *,
        normalized_bet_type: str | None = None,
    ) -> SettlementSupportResult:
        display_type = play_type or "未知玩法"
        message = f"玩法「{display_type}」可记账，暂不支持正式结算：{reason}"
        return SettlementSupportResult(
            is_supported=False,
            status="unsupported",
            play_type=display_type,
            selection=selection,
            normalized_bet_type=normalized_bet_type,
            reason=reason,
            message=message,
            suggestion="可保存为记账订单；正式结算前请人工核对，或等待规则确认后再结算。",
        )
