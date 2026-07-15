"""Versioned play-rule metadata used by intake and settlement safety gates.

This module deliberately describes rule availability without implementing or
changing any matcher.  V2 matchers can be enabled one play at a time after
their business examples and payout behaviour are covered by tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


FORTUNE_RULESET_2026_V1 = "FORTUNE_RULESET_2026_V1"
FORTUNE_RULESET_2026_V2 = "FORTUNE_RULESET_2026_V2"


class RulesetVersion(str, Enum):
    V1 = FORTUNE_RULESET_2026_V1
    V2 = FORTUNE_RULESET_2026_V2


class DrawScope(str, Enum):
    SPECIAL_ONLY = "special_only"
    REGULAR_SIX = "regular_six"
    ALL_SEVEN = "all_seven"
    UNKNOWN = "unknown"


class SelectionUnit(str, Enum):
    NUMBER = "number"
    ZODIAC = "zodiac"
    TAIL = "tail"
    NUMBER_GROUP = "number_group"
    ZODIAC_GROUP = "zodiac_group"
    COMBINATION = "combination"
    UNKNOWN = "unknown"


class DuplicatePolicy(str, Enum):
    REPEAT_AS_INDEPENDENT_STAKES = "repeat_as_independent_stakes"
    FORBID_WITHIN_GROUP = "forbid_within_group"
    ALLOW_ACROSS_SUBITEMS = "allow_across_subitems"
    UNKNOWN = "unknown"


class SettlementAvailability(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    BLOCKED_PENDING_RULE_FIX = "blocked_pending_rule_fix"
    BLOCKED_PENDING_EVIDENCE = "blocked_pending_evidence"


@dataclass(frozen=True, slots=True)
class PlayRule:
    canonical_bet_type: str
    normalized_type: str | None
    draw_scope: DrawScope
    selection_unit: SelectionUnit
    duplicate_policy: DuplicatePolicy
    odds_keys: tuple[str, ...]
    rebate_keys: tuple[str, ...]
    payout_tiers: tuple[str, ...]
    availability: SettlementAvailability
    matcher_id: str | None
    matcher_version: str | None
    notes: str


def _play(
    canonical_bet_type: str,
    normalized_type: str | None,
    draw_scope: DrawScope,
    selection_unit: SelectionUnit,
    duplicate_policy: DuplicatePolicy,
    *,
    availability: SettlementAvailability = SettlementAvailability.SUPPORTED,
    odds_keys: tuple[str, ...] = (),
    rebate_keys: tuple[str, ...] = (),
    payout_tiers: tuple[str, ...] = (),
    matcher_id: str | None = None,
    matcher_version: str | None = None,
    notes: str = "",
) -> PlayRule:
    return PlayRule(
        canonical_bet_type=canonical_bet_type,
        normalized_type=normalized_type,
        draw_scope=draw_scope,
        selection_unit=selection_unit,
        duplicate_policy=duplicate_policy,
        odds_keys=odds_keys,
        rebate_keys=rebate_keys,
        payout_tiers=payout_tiers,
        availability=availability,
        matcher_id=matcher_id,
        matcher_version=matcher_version,
        notes=notes,
    )


_RULES = (
    _play(
        "特码",
        "special_number",
        DrawScope.SPECIAL_ONLY,
        SelectionUnit.NUMBER,
        DuplicatePolicy.REPEAT_AS_INDEPENDENT_STAKES,
        odds_keys=("特码", "特码号码", "号码"),
        rebate_keys=("特码", "统一返水", "默认返水"),
        matcher_id="match_special_number",
        notes="当前 matcher 仅检查特别号。",
    ),
    _play(
        "号码",
        "special_number",
        DrawScope.SPECIAL_ONLY,
        SelectionUnit.NUMBER,
        DuplicatePolicy.REPEAT_AS_INDEPENDENT_STAKES,
        odds_keys=("号码", "特码", "特码号码"),
        rebate_keys=("号码", "统一返水", "默认返水"),
        matcher_id="match_special_number",
    ),
    _play(
        "特码生肖",
        "special_zodiac",
        DrawScope.SPECIAL_ONLY,
        SelectionUnit.ZODIAC,
        DuplicatePolicy.ALLOW_ACROSS_SUBITEMS,
        odds_keys=("特码生肖", "生肖"),
        rebate_keys=("特码生肖", "统一返水", "默认返水"),
        matcher_id="match_zodiac",
        notes="真正的特码生肖类型；不等同于平特一肖。",
    ),
    _play(
        "平码",
        "regular_number",
        DrawScope.REGULAR_SIX,
        SelectionUnit.NUMBER,
        DuplicatePolicy.REPEAT_AS_INDEPENDENT_STAKES,
        odds_keys=("平码",),
        rebate_keys=("平码", "统一返水", "默认返水"),
        matcher_id="match_regular_number",
    ),
    _play(
        "二中二",
        "lianma_two_two",
        DrawScope.REGULAR_SIX,
        SelectionUnit.COMBINATION,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("二中二",),
        rebate_keys=("二中二", "统一返水", "默认返水"),
        matcher_id="match_two_in_two",
        matcher_version="2.0",
        notes="V2按独立订单明细逐个二中二组合结算。",
    ),
    _play(
        "三中三",
        "lianma_three_three",
        DrawScope.REGULAR_SIX,
        SelectionUnit.COMBINATION,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("三中三",),
        rebate_keys=("三中三", "统一返水", "默认返水"),
        matcher_id="match_three_in_three",
        matcher_version="2.0",
        notes="V2按独立订单明细逐个三中三组合结算。",
    ),
    _play(
        "平特一肖",
        "pingte_zodiac",
        DrawScope.ALL_SEVEN,
        SelectionUnit.ZODIAC,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("平特一肖", "平肖", "生肖"),
        rebate_keys=("平特一肖", "平肖", "生肖", "统一返水", "默认返水"),
        matcher_id="pingte_zodiac_v2",
        matcher_version="2.0",
        notes="V2按生肖逐条结算，检查全部7个开奖号。",
    ),
    _play(
        "平特一肖带主肖",
        "pingte_main_zodiac",
        DrawScope.ALL_SEVEN,
        SelectionUnit.ZODIAC,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("平特一肖带主肖", "平特一肖主肖", "平肖主肖"),
        rebate_keys=("平特一肖带主肖", "平特一肖主肖", "平肖主肖", "统一返水", "默认返水"),
        matcher_id="pingte_zodiac_v2",
        matcher_version="2.0",
        notes="主肖按保存的生肖年份动态识别；仅使用主肖专用赔率键。",
    ),
    _play(
        "平尾",
        "ping_tail",
        DrawScope.ALL_SEVEN,
        SelectionUnit.TAIL,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("平尾",),
        rebate_keys=("平尾", "统一返水", "默认返水"),
        matcher_id="flat_tail_v2",
        matcher_version="2.0",
        notes="V2逐尾独立结算，检查全部7个开奖号。",
    ),
    _play(
        "连肖",
        "lianxiao_zodiac",
        DrawScope.ALL_SEVEN,
        SelectionUnit.ZODIAC_GROUP,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("连肖",),
        rebate_keys=("连肖", "统一返水", "默认返水"),
        matcher_id="lianxiao_zodiac_v2",
        matcher_version="2.0",
        notes="V2按整组生肖结算，所选生肖均须出现在全部7个开奖号中。",
    ),
    _play(
        "连肖复选",
        "linked_zodiac_fuxuan",
        DrawScope.ALL_SEVEN,
        SelectionUnit.COMBINATION,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        availability=SettlementAvailability.BLOCKED_PENDING_RULE_FIX,
        odds_keys=("连肖复选",),
        rebate_keys=("连肖复选", "统一返水", "默认返水"),
        notes="组合展开与逐组合派彩尚未实施。",
    ),
    _play(
        "N不中",
        "non_hit_number",
        DrawScope.REGULAR_SIX,
        SelectionUnit.NUMBER_GROUP,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("N不中", "不中"),
        rebate_keys=("N不中", "不中", "统一返水", "默认返水"),
        matcher_id="non_hit_number_v2",
        matcher_version="2.0",
        notes="V2只检查前6个平码；特别号不参与N不中判断。",
    ),
    _play(
        "三中二",
        "lianma_three_two",
        DrawScope.REGULAR_SIX,
        SelectionUnit.COMBINATION,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("三中二中2", "三中二中3"),
        rebate_keys=("三中二", "统一返水", "默认返水"),
        payout_tiers=("中2", "中3"),
        matcher_id="three_in_two_v2",
        matcher_version="2.0",
        notes="V2逐组合检查前6个平码；中2和中3分别使用专用赔率。",
    ),
    _play(
        "几中几复选",
        "number_fuxuan",
        DrawScope.REGULAR_SIX,
        SelectionUnit.COMBINATION,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        availability=SettlementAvailability.BLOCKED_PENDING_RULE_FIX,
        odds_keys=("几中几复选",),
        rebate_keys=("几中几复选", "统一返水", "默认返水"),
        matcher_id="match_number_fuxuan",
        notes="基础玩法标识和逐组合派彩尚未实施。",
    ),
    _play(
        "包半波",
        "package_half_wave",
        DrawScope.UNKNOWN,
        SelectionUnit.COMBINATION,
        DuplicatePolicy.UNKNOWN,
        availability=SettlementAvailability.BLOCKED_PENDING_EVIDENCE,
        odds_keys=("包半波",),
        rebate_keys=("包半波", "统一返水", "默认返水"),
        matcher_id="match_package_half_wave",
        notes="缺少完整真实订单和派彩证据。",
    ),
    _play(
        "连尾",
        "linked_tail",
        DrawScope.UNKNOWN,
        SelectionUnit.TAIL,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        availability=SettlementAvailability.BLOCKED_PENDING_EVIDENCE,
        odds_keys=("连尾",),
        rebate_keys=("连尾", "统一返水", "默认返水"),
        matcher_id="match_linked_tail",
        notes="2至5连尾规则证据不足。",
    ),
    _play(
        "二中特",
        None,
        DrawScope.UNKNOWN,
        SelectionUnit.NUMBER_GROUP,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        availability=SettlementAvailability.BLOCKED_PENDING_EVIDENCE,
        notes="奖级与特别号组合规则待确认。",
    ),
    _play(
        "二中特复选",
        None,
        DrawScope.UNKNOWN,
        SelectionUnit.COMBINATION,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        availability=SettlementAvailability.BLOCKED_PENDING_EVIDENCE,
        notes="复选结构、奖级和赔率键待确认。",
    ),
    _play(
        "特串",
        None,
        DrawScope.UNKNOWN,
        SelectionUnit.NUMBER_GROUP,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        availability=SettlementAvailability.BLOCKED_PENDING_EVIDENCE,
        notes="精确选码和位置规则待确认。",
    ),
    _play(
        "四肖",
        None,
        DrawScope.UNKNOWN,
        SelectionUnit.ZODIAC_GROUP,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        availability=SettlementAvailability.BLOCKED_PENDING_EVIDENCE,
        notes="仅允许记账保存。",
    ),
    _play(
        "正码特",
        None,
        DrawScope.UNKNOWN,
        SelectionUnit.NUMBER_GROUP,
        DuplicatePolicy.UNKNOWN,
        availability=SettlementAvailability.BLOCKED_PENDING_EVIDENCE,
        notes="指定位置与多位置计注规则待确认。",
    ),
    _play(
        "平特0尾",
        "ping_tail",
        DrawScope.ALL_SEVEN,
        SelectionUnit.TAIL,
        DuplicatePolicy.FORBID_WITHIN_GROUP,
        odds_keys=("平特0尾", "平尾0尾", "0尾"),
        rebate_keys=("平特0尾", "平尾0尾", "0尾", "统一返水", "默认返水"),
        matcher_id="flat_tail_v2",
        matcher_version="2.0",
        notes="V2 0尾检查全部7个开奖号；仅使用0尾专用赔率键。",
    ),
)


PLAY_RULES: dict[str, PlayRule] = {rule.canonical_bet_type: rule for rule in _RULES}


def get_play_rule(bet_type: str) -> PlayRule | None:
    """Return canonical V2 metadata without guessing unknown play names."""

    label = str(bet_type or "").strip()
    if re.fullmatch(r"(?:[Nn]|\d+|[零〇一二两三四五六七八九十]+)?不中", label):
        return PLAY_RULES["N不中"]
    return PLAY_RULES.get(label)


def get_blocking_play_rule_by_normalized_type(normalized_type: str) -> PlayRule | None:
    """Prevent a settlement alias from bypassing a canonical V2 safety gate."""

    value = str(normalized_type or "").strip()
    if not value:
        return None
    return next(
        (
            rule
            for rule in PLAY_RULES.values()
            if rule.normalized_type == value
            and rule.availability is not SettlementAvailability.SUPPORTED
        ),
        None,
    )


def is_known_ruleset_version(value: object) -> bool:
    try:
        RulesetVersion(str(value))
    except ValueError:
        return False
    return True


def is_v2_ruleset(value: object) -> bool:
    return str(value) == FORTUNE_RULESET_2026_V2
