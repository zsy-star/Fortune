"""Normalize parser/order bet labels into settlement rule types."""

from __future__ import annotations

import re
from dataclasses import dataclass

from domain.color_rules import FIVE_ELEMENT_NUMBERS, WAVE_NUMBERS
from domain.exceptions import InvalidNumberError
from domain.number_rules import normalize_number
from domain.zodiac_rules import get_zodiac_map
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
LINKED_TAIL = "linked_tail"
NON_HIT_NUMBER = "non_hit_number"
SIX_SPECIAL_ZODIAC = "six_special_zodiac"
REGULAR_NUMBER = "regular_number"
PACKAGE_HALF_WAVE = "package_half_wave"

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
    LINKED_TAIL,
    NON_HIT_NUMBER,
    SIX_SPECIAL_ZODIAC,
    REGULAR_NUMBER,
    PACKAGE_HALF_WAVE,
}

UNSUPPORTED_BET_TYPES = {
    "胆拖",
    "拖码",
    "组选",
    "复式组合",
    "全包",
    "平码一肖",
    "三中一",
    "二中二",
    "三中二",
    "二中特",
    "特串",
}

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
    SPECIAL_ZODIAC_GROUP: {"连肖", "多生肖"},
    LINKED_TAIL: {"连尾"},
    NON_HIT_NUMBER: {"不中", "N不中"},
    SIX_SPECIAL_ZODIAC: {"六肖中特"},
    REGULAR_NUMBER: {"平码"},
    PACKAGE_HALF_WAVE: {"包半波"},
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

    def normalize(self, bet_type: str, selection: str) -> NormalizedBet:
        original_bet_type = (bet_type or "").strip()
        raw_selection = (selection or "").strip()
        if not original_bet_type:
            raise UnsupportedBetTypeError("投注类型不能为空")
        if not raw_selection:
            raise InvalidSelectionError("投注内容不能为空")

        if original_bet_type in UNSUPPORTED_BET_TYPES:
            raise UnsupportedBetTypeError(f"暂不支持玩法：{original_bet_type}")

        normalized_type = self._normalize_type(original_bet_type, raw_selection)
        normalized_selection = self._normalize_selection(normalized_type, raw_selection)
        return NormalizedBet(original_bet_type, normalized_type, normalized_selection)

    def _normalize_type(self, bet_type: str, selection: str) -> str:
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

    def _normalize_selection(self, normalized_type: str, selection: str) -> str:
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
        if normalized_type == SPECIAL_ZODIAC_GROUP:
            return self._normalize_zodiac_group_selection(selection)
        if normalized_type == LINKED_TAIL:
            return self._normalize_tail_group_selection(selection)
        if normalized_type == NON_HIT_NUMBER:
            return self._normalize_number_group_selection(selection)
        if normalized_type == SIX_SPECIAL_ZODIAC:
            return self._normalize_six_special_zodiac_selection(selection)
        if normalized_type == REGULAR_NUMBER:
            return self._normalize_number_group_selection(selection)
        if normalized_type == PACKAGE_HALF_WAVE:
            return self._normalize_package_half_wave_selection(selection)
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

    def _normalize_number_group_selection(self, selection: str) -> str:
        numbers = self._split_numbers(selection)
        try:
            return ",".join(dict.fromkeys(normalize_number(number) for number in numbers))
        except InvalidNumberError as exc:
            raise InvalidSelectionError(f"无效号码：{selection}") from exc

    def _split_numbers(self, selection: str) -> list[str]:
        tokens = [token for token in re.split(r"[\s,，、/|+-]+", selection.strip()) if token]
        if not tokens:
            raise InvalidSelectionError("号码投注内容不能为空")
        return tokens

    def _normalize_zodiac_group_selection(self, selection: str) -> str:
        zodiacs = set(get_zodiac_map(2026))
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
        if len(unique_tokens) < 2:
            raise InvalidSelectionError(f"生肖列表至少需要 2 个不同生肖：{selection}")
        return ",".join(unique_tokens)

    def _normalize_six_special_zodiac_selection(self, selection: str) -> str:
        zodiacs = set(get_zodiac_map(2026))
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
        return value in get_zodiac_map(2026)

    def _is_half_wave(self, value: str) -> bool:
        if len(value) < 2:
            return False
        return value in {"红单", "红双", "蓝单", "蓝双", "绿单", "绿双"}

    def _is_tail(self, value: str) -> bool:
        return bool(re.fullmatch(r"(尾[0-9]|[0-9]尾)", value))

    def _is_head(self, value: str) -> bool:
        return bool(re.fullmatch(r"([0-4]头|头[0-4])", value))
