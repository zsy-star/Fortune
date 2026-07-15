"""Normalize parser/order bet labels into settlement rule types."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from domain.color_rules import FIVE_ELEMENT_NUMBERS, WAVE_NUMBERS
from domain.exceptions import InvalidNumberError
from domain.non_hit_rules import (
    NON_HIT_MAX_COUNT,
    NON_HIT_MIN_COUNT,
    format_non_hit_count_chinese,
    parse_non_hit_count_label,
)
from domain.number_rules import normalize_number
from domain.zodiac_config import (
    ZODIAC_SEQUENCE,
    get_default_zodiac_year,
    get_main_zodiac,
    get_zodiac_number_map,
    is_main_zodiac,
    validate_zodiac_year,
)
from settlement.exceptions import InvalidSelectionError, UnsupportedBetTypeError

SPECIAL_NUMBER = "special_number"
SPECIAL_ZODIAC = "special_zodiac"
SPECIAL_COLOR = "special_color"
SPECIAL_HALF_WAVE = "special_half_wave"
SPECIAL_SIZE = "special_size"
SPECIAL_PARITY = "special_parity"
SPECIAL_TAIL = "special_tail"
SPECIAL_HEAD = "special_head"
SPECIAL_SUM_PARITY = "special_sum_parity"
SPECIAL_SUM_SIZE = "special_sum_size"
SPECIAL_ELEMENT = "special_element"
SPECIAL_ZODIAC_GROUP = "special_zodiac_group"
LIANXIAO_ZODIAC = "lianxiao_zodiac"
PINGTE_ZODIAC = "pingte_zodiac"
PINGTE_MAIN_ZODIAC = "pingte_main_zodiac"
LINKED_TAIL = "linked_tail"
NON_HIT_NUMBER = "non_hit_number"
SIX_SPECIAL_ZODIAC = "six_special_zodiac"
REGULAR_NUMBER = "regular_number"
PACKAGE_HALF_WAVE = "package_half_wave"
PING_TAIL = "ping_tail"
LIANMA_TWO_TWO = "lianma_two_two"
LIANMA_THREE_THREE = "lianma_three_three"
LIANMA_THREE_TWO = "lianma_three_two"
NUMBER_FUXUAN = "number_fuxuan"

SUPPORTED_NORMALIZED_TYPES = {
    SPECIAL_NUMBER,
    SPECIAL_ZODIAC,
    SPECIAL_COLOR,
    SPECIAL_HALF_WAVE,
    SPECIAL_SIZE,
    SPECIAL_PARITY,
    SPECIAL_TAIL,
    SPECIAL_HEAD,
    SPECIAL_SUM_PARITY,
    SPECIAL_SUM_SIZE,
    SPECIAL_ELEMENT,
    SPECIAL_ZODIAC_GROUP,
    LIANXIAO_ZODIAC,
    PINGTE_ZODIAC,
    PINGTE_MAIN_ZODIAC,
    LINKED_TAIL,
    NON_HIT_NUMBER,
    SIX_SPECIAL_ZODIAC,
    REGULAR_NUMBER,
    PACKAGE_HALF_WAVE,
    PING_TAIL,
    LIANMA_TWO_TWO,
    LIANMA_THREE_THREE,
    LIANMA_THREE_TWO,
    NUMBER_FUXUAN,
}

UNSUPPORTED_BET_TYPES = {
    "胆拖",
    "拖码",
    "组选",
    "全包",
    "平码一肖",
    "三中一",
    "二中特",
    "特串",
    "四肖",
}

FUXUAN_UNSUPPORTED_BET_TYPES = {"连肖复选"}
FUXUAN_UNSUPPORTED_REASON = "复选类玩法结算规则待确认"
LIANMA_UNSUPPORTED_BET_TYPES: set[str] = set()
LIANMA_UNSUPPORTED_REASON = "连码类玩法结算规则待确认"
PINGWEI_UNSUPPORTED_BET_TYPES: set[str] = set()
PINGWEI_UNSUPPORTED_REASON = "平尾结算规则待确认"

BET_TYPE_ALIASES = {
    SPECIAL_NUMBER: {"特码", "特号", "号码", "特码号码", "单号投注", "纯数字"},
    SPECIAL_ZODIAC: {"特码生肖", "生肖", "一肖"},
    SPECIAL_COLOR: {"特码波色", "波色", "色波"},
    SPECIAL_HALF_WAVE: {"特码半波", "半波"},
    SPECIAL_SIZE: {"特码大小", "大小", "特码两面"},
    SPECIAL_PARITY: {"特码单双", "单双"},
    SPECIAL_TAIL: {"特码尾数", "尾数"},
    SPECIAL_HEAD: {"特码头数", "头数"},
    SPECIAL_SUM_PARITY: {"特码合数单双", "合数单双"},
    SPECIAL_SUM_SIZE: {"特码合数大小", "合数大小"},
    SPECIAL_ELEMENT: {"特码五行", "五行"},
    LIANXIAO_ZODIAC: {"连肖", "多生肖"},
    PINGTE_ZODIAC: {"平特一肖"},
    PINGTE_MAIN_ZODIAC: {"平特一肖带主肖"},
    LINKED_TAIL: {"连尾"},
    NON_HIT_NUMBER: {"不中", "N不中"},
    SIX_SPECIAL_ZODIAC: {"六肖中特"},
    REGULAR_NUMBER: {"平码"},
    PACKAGE_HALF_WAVE: {"包半波"},
    PING_TAIL: {"平尾", "平特0尾"},
    LIANMA_TWO_TWO: {"二中二"},
    LIANMA_THREE_THREE: {"三中三"},
    LIANMA_THREE_TWO: {"三中二"},
    NUMBER_FUXUAN: {"几中几复选", "复式组合"},
}

SIZE_SELECTIONS = {"大", "小"}
PARITY_SELECTIONS = {"单", "双"}
SUM_PARITY_SELECTIONS = {"合单", "合双"}
SUM_SIZE_SELECTIONS = {"合大", "合小"}
PACKAGE_HALF_WAVE_SIZE_SELECTIONS = {"红大", "红小", "蓝大", "蓝小", "绿大", "绿小"}
PACKAGE_HALF_WAVE_SELECTIONS = {
    "红单",
    "红双",
    "蓝单",
    "蓝双",
    "绿单",
    "绿双",
    "红大",
    "红小",
    "蓝大",
    "蓝小",
    "绿大",
    "绿小",
}


@dataclass(frozen=True, slots=True)
class NormalizedBet:
    original_bet_type: str
    normalized_bet_type: str
    selection: str


class BetTypeNormalizer:
    """Normalize known settlement bet labels without guessing unknown rules."""

    def __init__(self, *, zodiac_year: int | None = None):
        self._zodiac_year = validate_zodiac_year(zodiac_year or get_default_zodiac_year())

    @property
    def zodiac_year(self) -> int:
        return self._zodiac_year

    def normalize(self, bet_type: str, selection: str, note: str | None = None) -> NormalizedBet:
        original_bet_type = (bet_type or "").strip()
        raw_selection = (selection or "").strip()
        if not original_bet_type:
            raise UnsupportedBetTypeError("投注类型不能为空")
        if not raw_selection:
            raise InvalidSelectionError("投注内容不能为空")

        if original_bet_type in FUXUAN_UNSUPPORTED_BET_TYPES:
            raise UnsupportedBetTypeError(FUXUAN_UNSUPPORTED_REASON)
        if original_bet_type in LIANMA_UNSUPPORTED_BET_TYPES:
            raise UnsupportedBetTypeError(LIANMA_UNSUPPORTED_REASON)
        if original_bet_type in PINGWEI_UNSUPPORTED_BET_TYPES:
            raise UnsupportedBetTypeError(PINGWEI_UNSUPPORTED_REASON)
        if original_bet_type in UNSUPPORTED_BET_TYPES:
            raise UnsupportedBetTypeError(f"暂不支持玩法：{original_bet_type}")

        normalized_type = self._normalize_type(original_bet_type, raw_selection)
        normalized_selection = self._normalize_selection(
            normalized_type,
            raw_selection,
            original_bet_type=original_bet_type,
            note=note,
        )
        return NormalizedBet(original_bet_type, normalized_type, normalized_selection)

    def _normalize_type(self, bet_type: str, selection: str) -> str:
        if re.fullmatch(r"(?:[Nn]|\d+|[零〇一二两三四五六七八九十]+)?不中", bet_type):
            return NON_HIT_NUMBER
        for normalized_type, aliases in BET_TYPE_ALIASES.items():
            if bet_type in aliases:
                return self._infer_special_type(selection) if normalized_type == SPECIAL_NUMBER else normalized_type

        if self._is_zodiac(bet_type):
            return SPECIAL_ZODIAC
        if bet_type in WAVE_NUMBERS:
            return SPECIAL_COLOR
        if self._is_half_wave(bet_type):
            return SPECIAL_HALF_WAVE
        if bet_type in PACKAGE_HALF_WAVE_SIZE_SELECTIONS:
            return PACKAGE_HALF_WAVE
        if bet_type in SIZE_SELECTIONS:
            return SPECIAL_SIZE
        if bet_type in PARITY_SELECTIONS:
            return SPECIAL_PARITY
        if self._is_tail(bet_type):
            return SPECIAL_TAIL
        if self._is_head(bet_type):
            return SPECIAL_HEAD
        if bet_type in SUM_PARITY_SELECTIONS:
            return SPECIAL_SUM_PARITY
        if bet_type in SUM_SIZE_SELECTIONS:
            return SPECIAL_SUM_SIZE
        if bet_type in FIVE_ELEMENT_NUMBERS:
            return SPECIAL_ELEMENT

        raise UnsupportedBetTypeError(f"未知或未实现玩法：{bet_type}")

    def _normalize_selection(
        self,
        normalized_type: str,
        selection: str,
        *,
        original_bet_type: str,
        note: str | None = None,
    ) -> str:
        if normalized_type == SPECIAL_NUMBER:
            return self._normalize_number_selection(selection)
        if normalized_type == SPECIAL_ZODIAC:
            if not self._is_zodiac(selection):
                raise InvalidSelectionError(f"无效生肖：{selection}")
            return selection
        if normalized_type == SPECIAL_COLOR:
            if selection not in WAVE_NUMBERS:
                raise InvalidSelectionError(f"无效波色：{selection}")
            return selection
        if normalized_type == SPECIAL_HALF_WAVE:
            if not self._is_half_wave(selection):
                raise InvalidSelectionError(f"无效半波：{selection}")
            return selection
        if normalized_type == SPECIAL_SIZE:
            if selection not in SIZE_SELECTIONS:
                raise InvalidSelectionError(f"无效大小：{selection}")
            return selection
        if normalized_type == SPECIAL_PARITY:
            if selection not in PARITY_SELECTIONS:
                raise InvalidSelectionError(f"无效单双：{selection}")
            return selection
        if normalized_type == SPECIAL_TAIL:
            if not self._is_tail(selection):
                raise InvalidSelectionError(f"无效尾数：{selection}")
            return selection[-2:] if selection.startswith("尾") else f"尾{selection[0]}"
        if normalized_type == SPECIAL_HEAD:
            if not self._is_head(selection):
                raise InvalidSelectionError(f"无效头数：{selection}")
            return selection[:2] if selection.endswith("头") else f"{selection[-1]}头"
        if normalized_type == SPECIAL_SUM_PARITY:
            if selection not in SUM_PARITY_SELECTIONS:
                raise InvalidSelectionError(f"无效合数单双：{selection}")
            return selection
        if normalized_type == SPECIAL_SUM_SIZE:
            if selection not in SUM_SIZE_SELECTIONS:
                raise InvalidSelectionError(f"无效合数大小：{selection}")
            return selection
        if normalized_type == SPECIAL_ELEMENT:
            if selection not in FIVE_ELEMENT_NUMBERS:
                raise InvalidSelectionError(f"无效五行：{selection}")
            return selection
        if normalized_type in {SPECIAL_ZODIAC_GROUP, LIANXIAO_ZODIAC}:
            return self._normalize_zodiac_group_selection(selection)
        if normalized_type in {PINGTE_ZODIAC, PINGTE_MAIN_ZODIAC}:
            return self._normalize_pingte_zodiac_selection(selection, normalized_type)
        if normalized_type == LINKED_TAIL:
            return self._normalize_tail_group_selection(selection)
        if normalized_type == NON_HIT_NUMBER:
            return self._normalize_non_hit_selection(selection, original_bet_type)
        if normalized_type == SIX_SPECIAL_ZODIAC:
            return self._normalize_six_special_zodiac_selection(selection)
        if normalized_type == REGULAR_NUMBER:
            return self._normalize_number_group_selection(selection, preserve_duplicates=True)
        if normalized_type == PACKAGE_HALF_WAVE:
            return self._normalize_package_half_wave_selection(selection)
        if normalized_type == PING_TAIL:
            return self._normalize_ping_tail_selection(selection, original_bet_type)
        if normalized_type in {LIANMA_TWO_TWO, LIANMA_THREE_THREE, LIANMA_THREE_TWO}:
            group_size = 2 if normalized_type == LIANMA_TWO_TWO else 3
            return self._normalize_lianma_groups(selection, group_size)
        if normalized_type == NUMBER_FUXUAN:
            return self._normalize_number_fuxuan_selection(selection, note=note)
        raise UnsupportedBetTypeError(f"未实现玩法：{normalized_type}")

    def _infer_special_type(self, selection: str) -> str:
        if self._looks_like_number_selection(selection):
            return SPECIAL_NUMBER
        if self._is_zodiac(selection):
            return SPECIAL_ZODIAC
        if selection in WAVE_NUMBERS:
            return SPECIAL_COLOR
        if self._is_half_wave(selection):
            return SPECIAL_HALF_WAVE
        if selection in SIZE_SELECTIONS:
            return SPECIAL_SIZE
        if selection in PARITY_SELECTIONS:
            return SPECIAL_PARITY
        if self._is_tail(selection):
            return SPECIAL_TAIL
        if self._is_head(selection):
            return SPECIAL_HEAD
        if selection in SUM_PARITY_SELECTIONS:
            return SPECIAL_SUM_PARITY
        if selection in SUM_SIZE_SELECTIONS:
            return SPECIAL_SUM_SIZE
        if selection in FIVE_ELEMENT_NUMBERS:
            return SPECIAL_ELEMENT
        raise InvalidSelectionError(f"无法识别特码投注内容：{selection}")

    def _normalize_number_selection(self, selection: str) -> str:
        numbers = self._split_numbers(selection)
        try:
            return ",".join(normalize_number(number) for number in numbers)
        except InvalidNumberError as exc:
            raise InvalidSelectionError(f"无效号码：{selection}") from exc

    def _normalize_number_group_selection(
        self,
        selection: str,
        *,
        preserve_duplicates: bool = False,
    ) -> str:
        numbers = self._split_numbers(selection)
        try:
            normalized_numbers = [normalize_number(number) for number in numbers]
        except InvalidNumberError as exc:
            raise InvalidSelectionError(f"无效号码：{selection}") from exc
        if preserve_duplicates:
            return ",".join(normalized_numbers)
        return ",".join(dict.fromkeys(normalized_numbers))

    def _normalize_non_hit_selection(self, selection: str, bet_type: str) -> str:
        tokens = [
            token
            for token in re.split(r"[\s,，、\./|+-]+", selection.strip())
            if token
        ]
        if not tokens:
            raise InvalidSelectionError("N不中号码列表不能为空")
        try:
            normalized_numbers = [normalize_number(number) for number in tokens]
        except InvalidNumberError as exc:
            raise InvalidSelectionError(f"N不中号码必须为01-49：{selection}") from exc

        duplicates = sorted(
            {number for number in normalized_numbers if normalized_numbers.count(number) > 1},
            key=int,
        )
        if duplicates:
            raise InvalidSelectionError(f"N不中号码重复：{','.join(duplicates)}")

        try:
            expected_count = parse_non_hit_count_label(bet_type)
        except ValueError as exc:
            raise InvalidSelectionError(str(exc)) from exc
        actual_count = len(normalized_numbers)
        effective_count = expected_count if expected_count is not None else actual_count
        if effective_count < NON_HIT_MIN_COUNT or effective_count > NON_HIT_MAX_COUNT:
            raise InvalidSelectionError(
                f"N不中选择号码数量必须为{NON_HIT_MIN_COUNT}-{NON_HIT_MAX_COUNT}个，"
                f"实际{actual_count}个"
            )
        if actual_count != effective_count:
            label = format_non_hit_count_chinese(effective_count)
            raise InvalidSelectionError(
                f"N不中阶数与号码数量不匹配：{label}不中需要{effective_count}个不同号码，"
                f"实际{actual_count}个"
            )
        return ",".join(sorted(normalized_numbers, key=int))

    def _split_numbers(self, selection: str) -> list[str]:
        tokens = [token for token in re.split(r"[\s,，、/|+-]+", selection.strip()) if token]
        if not tokens:
            raise InvalidSelectionError("号码投注内容不能为空")
        return tokens

    def _normalize_zodiac_group_selection(self, selection: str) -> str:
        zodiacs = set(get_zodiac_number_map(self._zodiac_year))
        tokens = [token for token in re.split(r"[\s,，、/|+-]+", selection.strip()) if token]
        if len(tokens) <= 1:
            compact = "".join(tokens) if tokens else selection.strip()
            tokens = list(compact)
        if len(tokens) < 2:
            raise InvalidSelectionError(f"生肖列表至少需要 2 个生肖：{selection}")
        invalid = [token for token in tokens if token not in zodiacs]
        if invalid:
            raise InvalidSelectionError(f"无法解析生肖列表：{selection}")
        unique_tokens = list(dict.fromkeys(tokens))
        if len(unique_tokens) != len(tokens):
            duplicates = sorted(
                {token for token in tokens if tokens.count(token) > 1},
                key=ZODIAC_SEQUENCE.index,
            )
            raise InvalidSelectionError(f"连肖生肖重复：{','.join(duplicates)}")
        if len(unique_tokens) < 2:
            raise InvalidSelectionError(f"生肖列表至少需要 2 个不同生肖：{selection}")
        return ",".join(sorted(unique_tokens, key=ZODIAC_SEQUENCE.index))

    def _normalize_pingte_zodiac_selection(self, selection: str, normalized_type: str) -> str:
        zodiacs = set(get_zodiac_number_map(self._zodiac_year))
        tokens = [token for token in re.split(r"[\s,，、/|+-]+", selection.strip()) if token]
        if len(tokens) <= 1:
            compact = "".join(tokens) if tokens else selection.strip()
            tokens = list(compact)
        invalid = [token for token in tokens if token not in zodiacs]
        if invalid or not tokens:
            raise InvalidSelectionError(f"无法解析平特一肖生肖：{selection}")
        duplicates = sorted(
            {token for token in tokens if tokens.count(token) > 1},
            key=ZODIAC_SEQUENCE.index,
        )
        if duplicates:
            raise InvalidSelectionError(f"平特一肖生肖重复：{','.join(duplicates)}")
        if len(tokens) != 1:
            raise InvalidSelectionError("平特一肖每条明细必须恰好一个生肖")
        zodiac = tokens[0]
        main = is_main_zodiac(self._zodiac_year, zodiac)
        if normalized_type == PINGTE_MAIN_ZODIAC and not main:
            raise InvalidSelectionError(
                f"{self._zodiac_year}年主肖为{get_main_zodiac(self._zodiac_year)}，"
                f"不能按主肖结算：{zodiac}"
            )
        if normalized_type == PINGTE_ZODIAC and main:
            raise InvalidSelectionError(
                f"{self._zodiac_year}年主肖为{zodiac}，必须使用「平特一肖带主肖」独立赔率"
            )
        return zodiac

    def _normalize_six_special_zodiac_selection(self, selection: str) -> str:
        zodiacs = set(get_zodiac_number_map(self._zodiac_year))
        tokens = [token for token in re.split(r"[\s,，、/|+-]+", selection.strip()) if token]
        if len(tokens) <= 1:
            compact = "".join(tokens) if tokens else selection.strip()
            tokens = list(compact)
        invalid = [token for token in tokens if token not in zodiacs]
        if invalid:
            raise InvalidSelectionError(f"无法解析六肖中特生肖列表：{selection}")
        unique_tokens = list(dict.fromkeys(tokens))
        if len(unique_tokens) != 6:
            raise InvalidSelectionError(f"六肖中特需要 6 个不同生肖：{selection}")
        return ",".join(unique_tokens)

    def _normalize_tail_group_selection(self, selection: str) -> str:
        tokens = self._split_tail_tokens(selection)
        tails: list[str] = []
        for token in tokens:
            tail = token.replace("尾", "")
            if not re.fullmatch(r"[0-9]", tail):
                raise InvalidSelectionError(f"无效尾数：{selection}")
            tails.append(tail)
        unique_tails = list(dict.fromkeys(tails))
        if not unique_tails:
            raise InvalidSelectionError("连尾投注内容不能为空")
        return ",".join(unique_tails)

    def _normalize_ping_tail_selection(self, selection: str, original_bet_type: str) -> str:
        tokens = self._split_tail_tokens(selection)
        tails: list[str] = []
        for token in tokens:
            tail = token.replace("尾", "")
            if not re.fullmatch(r"[0-9]", tail):
                raise InvalidSelectionError(f"无效平尾尾数：{selection}")
            tails.append(tail)
        if not tails:
            raise InvalidSelectionError("平尾投注内容不能为空")
        duplicates = [tail for tail in dict.fromkeys(tails) if tails.count(tail) > 1]
        if duplicates:
            raise InvalidSelectionError(f"平尾尾数重复：{','.join(duplicates)}")
        if len(tails) != 1:
            raise InvalidSelectionError("平尾每条明细必须恰好一个尾数")
        if original_bet_type == "平特0尾" and tails[0] != "0":
            raise InvalidSelectionError("平特0尾的投注内容必须为0")
        return tails[0]

    def _split_tail_tokens(self, selection: str) -> list[str]:
        text = selection.strip()
        tokens = [token for token in re.split(r"[\s,，、/|+]+", text) if token]
        if len(tokens) > 1:
            return tokens
        compact = re.sub(r"[\s,，、/|+]+", "", text)
        if re.search(r"(?:尾[0-9]{2,}|[0-9]{2,}尾)", compact):
            raise InvalidSelectionError(f"无效尾数：{selection}")
        matches = list(re.finditer(r"尾[0-9]|[0-9]尾|[0-9]", compact))
        if not matches or "".join(match.group(0) for match in matches) != compact:
            raise InvalidSelectionError(f"无法解析连尾尾数：{selection}")
        return [match.group(0) for match in matches]

    def _normalize_package_half_wave_selection(self, selection: str) -> str:
        tokens = self._split_package_half_wave_tokens(selection)
        invalid = [token for token in tokens if token not in PACKAGE_HALF_WAVE_SELECTIONS]
        if invalid:
            raise InvalidSelectionError(f"无效包半波：{selection}")
        unique_tokens = list(dict.fromkeys(tokens))
        if not unique_tokens:
            raise InvalidSelectionError("包半波投注内容不能为空")
        return ",".join(unique_tokens)

    def _normalize_lianma_groups(self, selection: str, group_size: int) -> str:
        text = selection.strip()
        bracket_matches = list(re.finditer(r"\(([^()]*)\)", text))
        if bracket_matches:
            leftover = re.sub(r"\([^()]*\)", "", text).strip()
            if re.sub(r"[\-\s,，、]+", "", leftover):
                raise InvalidSelectionError(f"连码组合格式无效：{selection}")
            groups = [self._normalize_lianma_group(match.group(1), group_size) for match in bracket_matches]
        else:
            groups = [self._normalize_lianma_group(text, group_size)]
        if not groups:
            raise InvalidSelectionError("连码组合不能为空")
        return "-".join("(" + "-".join(group) + ")" for group in groups)

    def _normalize_lianma_group(self, group_text: str, group_size: int) -> tuple[str, ...]:
        tokens = [token for token in re.split(r"[\s,，、\-]+", group_text.strip()) if token]
        if len(tokens) != group_size:
            raise InvalidSelectionError(f"连码每组必须 {group_size} 个号码：{group_text}")
        try:
            numbers = tuple(normalize_number(token) for token in tokens)
        except InvalidNumberError as exc:
            raise InvalidSelectionError(f"无效连码号码：{group_text}") from exc
        if len(set(numbers)) != len(numbers):
            raise InvalidSelectionError(f"连码单组内不能重复号码：{group_text}")
        return numbers

    def _normalize_number_fuxuan_selection(self, selection: str, *, note: str | None = None) -> str:
        fuxuan_type = self._extract_fuxuan_type(selection, note)
        if fuxuan_type is None:
            raise UnsupportedBetTypeError(FUXUAN_UNSUPPORTED_REASON)
        number_selection = selection.split("|", 1)[1] if "|" in selection else selection
        numbers = self._normalize_number_group_selection(number_selection)
        k = int(fuxuan_type[1:])
        if k not in {2, 3}:
            raise UnsupportedBetTypeError(FUXUAN_UNSUPPORTED_REASON)
        selected_numbers = [token for token in numbers.split(",") if token]
        if k > len(selected_numbers):
            raise InvalidSelectionError(f"复选数量{fuxuan_type}不能大于号码个数 {len(selected_numbers)}")
        if k < 2:
            raise InvalidSelectionError(f"复选数量必须至少为 2：{fuxuan_type}")
        # Touch the combinations here so invalid boundaries are caught during normalization.
        tuple(combinations(selected_numbers, k))
        return f"{fuxuan_type}|{numbers}"

    def _extract_fuxuan_type(self, selection: str, note: str | None) -> str | None:
        for text in (selection, note or ""):
            match = re.search(r"复\s*([2-9]\d*)", text)
            if match:
                return f"复{int(match.group(1))}"
        return None

    def _split_package_half_wave_tokens(self, selection: str) -> list[str]:
        text = selection.strip()
        tokens = [token for token in re.split(r"[\s,，、/|+]+", text) if token]
        if len(tokens) > 1:
            return tokens
        compact = re.sub(r"[\s,，、/|+]+", "", text)
        matches = list(re.finditer(r"[红蓝绿][单双大小]", compact))
        if not matches or "".join(match.group(0) for match in matches) != compact:
            raise InvalidSelectionError(f"无法解析包半波：{selection}")
        return [match.group(0) for match in matches]

    def _looks_like_number_selection(self, selection: str) -> bool:
        tokens = [token for token in re.split(r"[\s,，、/|+-]+", selection.strip()) if token]
        return bool(tokens) and all(token.isdigit() for token in tokens)

    def _is_zodiac(self, value: str) -> bool:
        return value in get_zodiac_number_map(self._zodiac_year)

    def _is_half_wave(self, value: str) -> bool:
        if len(value) < 2:
            return False
        return value in {"红单", "红双", "蓝单", "蓝双", "绿单", "绿双"}

    def _is_tail(self, value: str) -> bool:
        return bool(re.fullmatch(r"(尾[0-9]|[0-9]尾)", value))

    def _is_head(self, value: str) -> bool:
        return bool(re.fullmatch(r"([0-4]头|头[0-4])", value))
