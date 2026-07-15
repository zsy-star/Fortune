"""Read-only settlement support status for order items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.play_rules import (
    FORTUNE_RULESET_2026_V2,
    SettlementAvailability,
    get_blocking_play_rule_by_normalized_type,
    get_play_rule,
    is_v2_ruleset,
)
from settlement.bet_normalizer import BetTypeNormalizer
from settlement.exceptions import InvalidSelectionError, UnsupportedBetTypeError
from settlement.matchers import parse_lianma_groups
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
        zodiac_year: int | None = None,
        require_zodiac_year: bool = False,
    ) -> SettlementSupportResult:
        play_type = (bet_type or "").strip()
        raw_selection = (selection or "").strip()
        if not play_type:
            return self._unsupported(play_type, raw_selection, "投注类型为空")
        if not raw_selection:
            return self._unsupported(play_type, raw_selection, "投注内容为空")
        if require_zodiac_year and zodiac_year is None and play_type in {
            "平特一肖",
            "平特一肖带主肖",
            "连肖",
            "多生肖",
        }:
            return self._unsupported(play_type, raw_selection, "生肖玩法正式结算需要订单保存的生肖年份")

        rule = get_play_rule(play_type)
        if rule is not None and rule.availability is not SettlementAvailability.SUPPORTED:
            if rule.availability is SettlementAvailability.BLOCKED_PENDING_RULE_FIX:
                reason = f"V2规则修复尚未完成：{rule.notes or rule.canonical_bet_type}"
            elif rule.availability is SettlementAvailability.BLOCKED_PENDING_EVIDENCE:
                reason = f"缺少正式结算所需的真实规则证据：{rule.notes or rule.canonical_bet_type}"
            else:
                reason = f"V2规则元数据标记为不支持：{rule.notes or rule.canonical_bet_type}"
            return self._unsupported(play_type, raw_selection, reason)

        try:
            normalizer = self._normalizer if zodiac_year is None else BetTypeNormalizer(zodiac_year=zodiac_year)
            normalized = normalizer.normalize(play_type, raw_selection, note=note)
        except UnsupportedBetTypeError as exc:
            return self._unsupported(play_type, raw_selection, str(exc))
        except InvalidSelectionError as exc:
            return self._unsupported(play_type, raw_selection, f"投注内容暂不能正式结算：{exc}")

        normalized_rule = get_blocking_play_rule_by_normalized_type(
            normalized.normalized_bet_type
        )
        if rule is None and normalized_rule is not None:
            return self._unsupported(
                play_type,
                raw_selection,
                "V2规则别名同样受门禁限制："
                f"{normalized_rule.canonical_bet_type}；{normalized_rule.notes}",
                normalized_bet_type=normalized.normalized_bet_type,
            )

        if normalized.normalized_bet_type not in MATCHERS:
            return self._unsupported(
                play_type,
                raw_selection,
                f"当前结算引擎未接入玩法：{normalized.normalized_bet_type}",
                normalized_bet_type=normalized.normalized_bet_type,
            )

        if play_type in {"二中二", "三中三"}:
            groups = parse_lianma_groups(normalized.selection)
            if len(groups) != 1:
                return self._unsupported(
                    play_type,
                    raw_selection,
                    f"V2暂只允许单个{play_type}组合正式结算；当前识别到{len(groups)}个组合",
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

    def check_ruleset_version(self, ruleset_version: object) -> SettlementSupportResult:
        if is_v2_ruleset(ruleset_version):
            return SettlementSupportResult(
                is_supported=True,
                status="supported",
                play_type="规则版本",
                selection=FORTUNE_RULESET_2026_V2,
                reason="V2正式结算规则版本已识别",
                message=f"规则版本「{FORTUNE_RULESET_2026_V2}」允许进入V2结算门禁。",
                suggestion="继续逐项检查订单玩法支持状态。",
            )
        value = str(ruleset_version or "未设置").strip() or "未设置"
        return self._unsupported(
            "规则版本",
            value,
            f"未知、缺失或非V2规则版本：{value}；禁止自动按V2解释",
        )

    def check_order_items(
        self,
        items: list[Any] | tuple[Any, ...],
        *,
        ruleset_version: object = FORTUNE_RULESET_2026_V2,
        zodiac_year: int | None = None,
        require_zodiac_year: bool = False,
    ) -> list[SettlementSupportResult]:
        order_items = list(items)
        ruleset_result = self.check_ruleset_version(ruleset_version)
        if not ruleset_result.is_supported:
            if not order_items:
                return [ruleset_result]
            return [
                self._unsupported(
                    str(getattr(item, "bet_type", "") or ""),
                    str(getattr(item, "selection", "") or ""),
                    "订单规则版本门禁：" + ruleset_result.reason,
                )
                for item in order_items
            ]
        return [
            self.check_item(
                str(getattr(item, "bet_type", "") or ""),
                str(getattr(item, "selection", "") or ""),
                note=getattr(item, "note", None),
                zodiac_year=zodiac_year,
                require_zodiac_year=require_zodiac_year,
            )
            for item in order_items
        ]

    def unsupported_results(
        self,
        items: list[Any] | tuple[Any, ...],
        *,
        ruleset_version: object = FORTUNE_RULESET_2026_V2,
        zodiac_year: int | None = None,
        require_zodiac_year: bool = False,
    ) -> list[SettlementSupportResult]:
        return [
            result
            for result in self.check_order_items(
                items,
                ruleset_version=ruleset_version,
                zodiac_year=zodiac_year,
                require_zodiac_year=require_zodiac_year,
            )
            if not result.is_supported
        ]

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
