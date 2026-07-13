"""订单文本解析服务 — 将自然语言订单展开为六合彩号码列表（2026 年马年起始）。

支持格式: <类别>各数<金额>  或  <连肖关键词><生肖列表>各数<金额>
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal

from domain.non_hit_rules import (
    NON_HIT_MAX_COUNT,
    NON_HIT_MIN_COUNT,
    format_non_hit_count_chinese,
    parse_non_hit_count_label,
)
from domain.zodiac_config import (
    ZODIAC_SEQUENCE,
    get_default_zodiac_year,
    get_zodiac_number_map,
    validate_zodiac_year,
)

# ======================================================================
# 工具函数
# ======================================================================


def _digit_root(n: int) -> int:
    """合数根值：各位相加，若 ≥10 则继续，直到 1-9。"""
    while n >= 10:
        n = sum(int(d) for d in str(n))
    return n


# ======================================================================
# 生肖数据（含别名映射）
# ======================================================================

_ZODIAC_ALIASES: tuple[tuple[str, ...], ...] = (
    ("午马", "午", "马"),
    ("巳蛇", "巳", "蛇"),
    ("辰龙", "辰", "龙"),
    ("卯兔", "卯", "兔"),
    ("寅虎", "寅", "虎"),
    ("丑牛", "丑", "牛"),
    ("子鼠", "子", "鼠"),
    ("亥猪", "亥", "猪"),
    ("戌狗", "戌", "狗"),
    ("酉鸡", "酉", "鸡"),
    ("申猴", "申", "猴"),
    ("未羊", "未", "羊"),
)
_ZODIAC_ALIAS_BY_NAME = {aliases[-1]: aliases for aliases in _ZODIAC_ALIASES}
_ZODIAC_ENTRIES: tuple[tuple[tuple[str, ...], tuple[int, ...]], ...] = ()
_active_zodiac_year = 0

# 标识符 → 号码 快速查找
_zodiac_by_id: dict[str, tuple[int, ...]] = {}

# 标识符按长度降序（最长匹配优先）
_ZODIAC_IDS_BY_LEN: list[str] = []

# 标识符 → 标准名（单字全名）
_zodiac_name: dict[str, str] = {}

# 号码 → 标准生肖名（反向查询）
_number_to_zodiac: dict[int, str] = {}

# ======================================================================
# 类别规则
# ======================================================================


@dataclass(frozen=True)
class CategoryRule:
    """一个类别规则：多个别名 → 号码列表 + 标准名称 + 优先级（越小越先匹配）。"""

    aliases: tuple[str, ...]
    numbers: tuple[int, ...]
    name: str
    priority: int


# ── 构建规则列表 ──

_RULES: list[CategoryRule] = []

# 1) 生肖（priority=1，最高优先）
for _aliases, _nums in _ZODIAC_ENTRIES:
    _RULES.append(CategoryRule(_aliases, _nums, _aliases[2], 1))

# 2) 波色（priority=2）
_WAVE_RED = (1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46)
_WAVE_BLUE = (3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48)
_WAVE_GREEN = (5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49)
_RULES.append(CategoryRule(("红波", "红", "红波色"), _WAVE_RED, "红波", 2))
_RULES.append(CategoryRule(("蓝波", "蓝", "蓝波色"), _WAVE_BLUE, "蓝波", 2))
_RULES.append(CategoryRule(("绿波", "绿", "绿波色"), _WAVE_GREEN, "绿波", 2))

# 3) 半波（priority=3）— 新增
_HALF_RED_ODD = (1, 7, 13, 19, 23, 29, 35, 45)
_HALF_RED_EVEN = (2, 8, 12, 18, 24, 30, 34, 40, 46)
_HALF_BLUE_ODD = (3, 9, 15, 25, 31, 37, 41, 47)
_HALF_BLUE_EVEN = (4, 10, 14, 20, 26, 36, 42, 48)
_HALF_GREEN_ODD = (5, 11, 17, 21, 27, 33, 39, 43, 49)
_HALF_GREEN_EVEN = (6, 16, 22, 28, 32, 38, 44)
_RULES.append(CategoryRule(("红单", "红单半波"), _HALF_RED_ODD, "红单", 3))
_RULES.append(CategoryRule(("红双", "红双半波"), _HALF_RED_EVEN, "红双", 3))
_RULES.append(CategoryRule(("蓝单", "蓝单半波"), _HALF_BLUE_ODD, "蓝单", 3))
_RULES.append(CategoryRule(("蓝双", "蓝双半波"), _HALF_BLUE_EVEN, "蓝双", 3))
_RULES.append(CategoryRule(("绿单", "绿单半波"), _HALF_GREEN_ODD, "绿单", 3))
_RULES.append(CategoryRule(("绿双", "绿双半波"), _HALF_GREEN_EVEN, "绿双", 3))

# 4) 大小（priority=4）
_RULES.append(CategoryRule(("大", "大号", "大数"), tuple(range(25, 50)), "大", 4))
_RULES.append(CategoryRule(("小", "小号", "小数"), tuple(range(1, 25)), "小", 4))

# 5) 单双（priority=5）
_RULES.append(
    CategoryRule(
        ("单", "单数", "奇数"),
        tuple(n for n in range(1, 50) if n % 2 == 1),
        "单",
        5,
    )
)
_RULES.append(
    CategoryRule(
        ("双", "双数", "偶数"),
        tuple(n for n in range(1, 50) if n % 2 == 0),
        "双",
        5,
    )
)

# 6) 尾数（priority=6）
for _tail in range(10):
    _tail_nums = tuple(n for n in range(1, 50) if n % 10 == _tail)
    _aliases_tail = (f"尾{_tail}", f"{_tail}尾", f"尾数{_tail}")
    _RULES.append(CategoryRule(_aliases_tail, _tail_nums, f"尾{_tail}", 6))

# 7) 头数（priority=7）
for _head in range(1, 5):
    _lo, _hi = _head * 10, _head * 10 + 9
    if _hi > 49:
        _hi = 49
    _head_nums = tuple(range(_lo, _hi + 1))
    _aliases_head = (f"{_head}头", f"头{_head}", f"{_head}字头")
    _RULES.append(CategoryRule(_aliases_head, _head_nums, f"{_head}头", 7))

# 8) 合数单双（priority=8）— 使用显式列表
_HE_DAN = (1, 3, 5, 7, 9, 10, 12, 14, 16, 18, 21, 23, 25, 27, 29,
           30, 32, 34, 36, 38, 41, 43, 45, 47, 49)
_HE_SHUANG = (2, 4, 6, 8, 11, 13, 15, 17, 19, 20, 22, 24, 26, 28,
              31, 33, 35, 37, 39, 40, 42, 44, 46, 48)
_RULES.append(CategoryRule(("合单", "合数单"), _HE_DAN, "合单", 8))
_RULES.append(CategoryRule(("合双", "合数双"), _HE_SHUANG, "合双", 8))

# 9) 合数大小（priority=9）
_he_xiao = tuple(n for n in range(1, 50) if _digit_root(n) <= 4)
_he_da = tuple(n for n in range(1, 50) if _digit_root(n) >= 5)
_RULES.append(CategoryRule(("合小", "合数小"), _he_xiao, "合小", 9))
_RULES.append(CategoryRule(("合大", "合数大"), _he_da, "合大", 9))

# 10) 五行（priority=10）— 新增
_WUXING_JIN = (3, 4, 11, 12, 25, 26, 33, 34, 41, 42)
_WUXING_MU = (7, 8, 15, 16, 23, 24, 37, 38, 45, 46)
_WUXING_SHUI = (13, 14, 21, 22, 29, 30, 43, 44)
_WUXING_HUO = (1, 2, 9, 10, 17, 18, 31, 32, 39, 40, 47, 48)
_WUXING_TU = (5, 6, 19, 20, 27, 28, 35, 36, 49)
_RULES.append(CategoryRule(("金", "五行金"), _WUXING_JIN, "金", 10))
_RULES.append(CategoryRule(("木", "五行木"), _WUXING_MU, "木", 10))
_RULES.append(CategoryRule(("水", "五行水"), _WUXING_SHUI, "水", 10))
_RULES.append(CategoryRule(("火", "五行火"), _WUXING_HUO, "火", 10))
_RULES.append(CategoryRule(("土", "五行土"), _WUXING_TU, "土", 10))

# 11) 全包（priority=11，最低）
_RULES.append(
    CategoryRule(
        ("全包", "全部", "所有号码", "全部号"),
        tuple(range(1, 50)),
        "全包",
        11,
    )
)

_RULES.sort(key=lambda r: r.priority)


def _zodiac_entries_for_year(year: int) -> tuple[tuple[tuple[str, ...], tuple[int, ...]], ...]:
    mapping = get_zodiac_number_map(validate_zodiac_year(year))
    return tuple(
        (_ZODIAC_ALIAS_BY_NAME[zodiac], tuple(int(number) for number in numbers))
        for zodiac, numbers in mapping.items()
    )


def _configure_zodiac_year(year: int | None) -> int:
    """Refresh parser zodiac lookup tables for the selected lottery year."""
    global _ZODIAC_ENTRIES, _ZODIAC_IDS_BY_LEN, _active_zodiac_year

    selected_year = validate_zodiac_year(year or get_default_zodiac_year())
    if selected_year == _active_zodiac_year:
        return selected_year

    _ZODIAC_ENTRIES = _zodiac_entries_for_year(selected_year)
    _zodiac_by_id.clear()
    _zodiac_name.clear()
    _number_to_zodiac.clear()

    for aliases, nums in _ZODIAC_ENTRIES:
        std = aliases[-1]
        for alias in aliases:
            _zodiac_by_id[alias] = nums
            _zodiac_name[alias] = std
        for number in nums:
            _number_to_zodiac[number] = std

    _ZODIAC_IDS_BY_LEN = sorted(_zodiac_by_id.keys(), key=len, reverse=True)

    non_zodiac_rules = [rule for rule in _RULES if rule.priority != 1]
    zodiac_rules = [CategoryRule(aliases, nums, aliases[-1], 1) for aliases, nums in _ZODIAC_ENTRIES]
    _RULES[:] = sorted([*zodiac_rules, *non_zodiac_rules], key=lambda r: r.priority)
    _active_zodiac_year = selected_year
    return selected_year


_configure_zodiac_year(get_default_zodiac_year())

# ======================================================================
# 连肖关键词
# ======================================================================

_LIANXIAO_KEYWORDS: tuple[str, ...] = ("连肖", "连", "拖", "托", "有", "友", "胆")

# 「数字 + 连肖关键词」格式: 生肖们 + 可选中文数字 + 连/拖/托/有/友
_CN_DIGIT_MAP: dict[str, int] = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_CN_DIGIT_CHARS: str = "".join(_CN_DIGIT_MAP.keys())
# 剩余部分必须完全匹配: 可选中文数字 + 任一连肖关键词
_TUO_TAIL_PATTERN = re.compile(rf"^([{_CN_DIGIT_CHARS}]?)(连肖|[拖托连有友])$")

# ======================================================================
# 解析结果
# ======================================================================


@dataclass
class ParseResult:
    """单条订单解析结果。"""

    success: bool
    category: str = ""  # 标准化类别名
    numbers: tuple[int, ...] = ()  # 展开后的号码（已排序，所有生肖合并）
    amount: float = 0.0  # 每注金额
    total: float = 0.0  # 总金额
    error: str = ""  # 失败时的错误信息
    region: str = ""  # 地域标签: "香港"/"澳门"/""
    original_text: str = ""  # 原始输入文本（调用方可回填）
    # 多生肖时每项为 (生肖名, 号码元组)；单类别为空列表
    zodiac_groups: list[tuple[str, tuple[int, ...]]] = field(default_factory=list)
    # 复试连肖专用：用户指定的连数列表，如 (3, 4, 5)
    fushi_lian_sizes: tuple[int, ...] = ()
    # 复选类玩法专用：复2、复3、复4 等
    fuxuan_type: str = ""
    # 连码类玩法专用：((1, 2), (3, 4)) 等括号组合
    lianma_groups: tuple[tuple[int, ...], ...] = ()
    # 平尾专用：标准尾数列表，如 (1, 3, 4, 6)
    pingwei_tails: tuple[int, ...] = ()
    # 解析阶段提示：用于共计校验、排除说明、暂不支持结算等非阻断信息。
    warnings: list[str] = field(default_factory=list)
    # 保存到预览/订单备注的补充信息。
    note: str = ""
    # 归一化后的源片段，便于预览表显示多单拆分来源。
    normalized_text: str = ""
    # “生肖各数”口径：按生肖下号码展开，而不是按连肖整组保存。
    zodiac_number_mode: bool = False


@dataclass(frozen=True)
class ParseOptions:
    """Optional record-window parsing switches.

    These flags are intentionally opt-in so order import and split-order flows
    keep their historical parsing behavior.
    """

    special_zodiac_mode: bool = False
    age_writing: bool = False
    zodiac_each_mode: bool = False
    zodiac_year: int | None = None


# ======================================================================
# 金额提取
# ======================================================================

_AMOUNT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:元|块|蚊)?$")
_CN_AMOUNT_CHARS = "零〇一二两三四五六七八九十百千万"
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９．", "0123456789.")


def _cn_amount_to_number(raw: str) -> Decimal | None:
    """把常见中文金额转为数字，支持十、三十五、一百二十等口语写法。"""
    text = raw.strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return Decimal(text)
    digit_map = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    unit_map = {"十": 10, "百": 100, "千": 1000}
    total = 0
    section = 0
    number = 0
    for char in text:
        if char in digit_map:
            number = digit_map[char]
            continue
        if char in unit_map:
            unit = unit_map[char]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
            continue
        if char == "万":
            section += number
            total += section * 10000
            section = 0
            number = 0
            continue
        return None
    value = total + section + number
    return Decimal(value) if value > 0 else None


def _format_decimal_plain(value: Decimal) -> str:
    if value == value.to_integral():
        return str(int(value))
    return format(value.normalize(), "f").rstrip("0").rstrip(".")


def _normalize_chinese_amounts(text: str) -> str:
    amount_word = rf"[{_CN_AMOUNT_CHARS}]+"

    def marker_repl(match: re.Match[str]) -> str:
        value = _cn_amount_to_number(match.group(2))
        if value is None:
            return match.group(0)
        return f"{match.group(1)}{_format_decimal_plain(value)}"

    text = re.sub(rf"((?:各组|各数|各号|每注|每数|各|每|打|买)\s*)({amount_word})", marker_repl, text)

    def suffix_repl(match: re.Match[str]) -> str:
        value = _cn_amount_to_number(match.group(1))
        if value is None:
            return match.group(0)
        return f"{_format_decimal_plain(value)}{match.group(2)}"

    return re.sub(rf"({amount_word})(元|块|蚊)", suffix_repl, text)


def _normalize_smart_text(text: str) -> str:
    """第一阶段智能录单归一化：只处理输入形态，不改变玩法/结算口径。"""
    t = text.strip().translate(_FULLWIDTH_DIGITS)
    t = _normalize_chinese_amounts(t)

    # 只归一金额尾部的“各包/每个包”，避免影响包半波、全包等玩法名。
    t = re.sub(
        r"(?:各|每个)\s*(?:包\s*)?(\d+(?:\.\d+)?)\s*(?=(?:元|块|蚊)?$)",
        r"各\1",
        t,
    )

    # 01号一10元 / 26号1 0块 这类口语里，“一/1”是“各”的近音。
    t = re.sub(r"一\s*(\d+(?:\.\d+)?)\s*(元|块|蚊)", r"各\1", t)
    t = re.sub(r"(?<=号)\s*1\s+(\d)\s*(元|块|蚊)", r"各1\1", t)

    def collapse_spaced_digits(match: re.Match[str]) -> str:
        return re.sub(r"\s+", "", match.group(1))

    t = re.sub(r"(?<!\d)((?:\d\s+){1,4}\d)(?=\s*(?:号|元|块|蚊|$))", collapse_spaced_digits, t)
    t = re.sub(r"(\d)\s+(?=\d号)", r"\1", t)
    t = re.sub(r"(\d)\s+(?=\d(?:元|块|蚊))", r"\1", t)

    # 常见参考软件别名。
    t = t.replace("平肖", "平特一肖")
    t = t.replace("特肖", "平特一肖")
    t = re.sub(r"平特(?=$|[，,。；;\s])", "平特一肖", t)
    t = re.sub(r"^(.+?)(各组|各数|各号|每注|每数|各|每|打|买)(\d+(?:\.\d+)?)(?:平特|平特一肖)$", r"\1平特一肖\2\3", t)
    t = re.sub(rf"^([{''.join(sorted(set(_zodiac_name.values())))}]+)数各", r"\1各数", t)
    t = re.sub(rf"^([{''.join(sorted(set(_zodiac_name.values())))}]+)数(?=(?:每|打|买))", r"\1", t)
    t = re.sub(rf"^([{''.join(sorted(set(_zodiac_name.values())))}]+)平(?=\d|各|每|打|买)", r"\1平特一肖", t)

    # “36号48号各数25”需要在去“号”之前插入号码分隔符。
    t = re.sub(r"(\d{1,2})号(?=\s*\d{1,2}号)", r"\1,", t)
    t = re.sub(r"(\d{1,2})号\s*(?=(?:各组|各数|各号|每注|每数|各|每|打|买))", r"\1", t)
    t = re.sub(r"(\d{1,2})号\s*(\d+(?:\.\d+)?)(?:元|块|蚊)?(?=$|[，,。；;\s])", r"\1各\2", t)
    t = re.sub(r"(\d{1,2})号(?:码)?", r"\1", t)
    t = re.sub(r"(\d)(?:元|块|蚊)", r"\1", t)
    return t.strip()


def _extract_amount(text: str) -> tuple[float, str]:
    """从文本末尾提取金额数字，返回 (金额, 去除金额后的剩余文本)。"""
    m = _AMOUNT_PATTERN.search(text)
    if not m:
        return 0.0, text
    amount = float(m.group(1))
    remaining = text[: m.start()].strip()
    return amount, remaining


# ======================================================================
# 连肖解析
# ======================================================================


def _parse_lianxiao_zodiacs(text: str) -> list[int]:
    """贪心最长生肖名匹配。返回去重并排序的号码列表。"""
    pos = 0
    numbers: list[int] = []
    while pos < len(text):
        matched = False
        for zid in _ZODIAC_IDS_BY_LEN:
            if text.startswith(zid, pos):
                numbers.extend(_zodiac_by_id[zid])
                pos += len(zid)
                matched = True
                break
        if not matched:
            # 无法继续匹配，停止
            break
    return sorted(set(numbers))


# ── 纯数字列表解析 ──
_NUMBER_SPLIT_PATTERN = re.compile(r"[,，\-—、\s]+")


def _parse_number_list(text: str) -> tuple[int, ...] | None:
    """尝试将文本解析为 1-49 的号码列表。

    支持分隔符: 空格、逗号、中文逗号、减号、顿号。

    Returns:
        去重排序后的号码元组；无法解析则返回 None。
    """
    # 拒绝负数号（如 "1,-2,3"）——分隔符替换前先检测
    if re.search(r'(?:^|[,，\-—、\s])-\d', text):
        return None

    cleaned = _NUMBER_SPLIT_PATTERN.sub(" ", text).strip()
    if not cleaned:
        return None

    tokens = cleaned.split()
    numbers: list[int] = []
    for token in tokens:
        try:
            n = int(token)
        except ValueError:
            return None  # 含非数字字符 → 不是号码列表
        if n < 1 or n > 49:
            return None  # 超出范围 → 不是有效号码
        numbers.append(n)

    if not numbers:
        return None
    return tuple(sorted(set(numbers)))


def _apply_exclusion(result: ParseResult, exclude_nums: set[int]) -> None:
    """从结果中移除排除的号码，重新计算 total。"""
    if not exclude_nums or not result.success or not result.numbers:
        return
    excluded_str = ",".join(f"{n:02d}" for n in sorted(exclude_nums))
    filtered = tuple(n for n in result.numbers if n not in exclude_nums)
    if not filtered:
        result.success = False
        result.error = f"排除 {excluded_str} 后无剩余号码"
        result.numbers = ()
        result.total = 0.0
        return
    result.numbers = filtered
    if f"排除号码={excluded_str}" not in result.note:
        result.note = ";".join(part for part in (result.note, f"排除号码={excluded_str}") if part)
    result.warnings.append(f"已排除号码：{excluded_str}")
    if result.category == "N不中" or _is_lianxiao_result_category(result.category):
        result.total = result.amount
    else:
        result.total = result.amount * len(filtered)


def _parse_zodiac_groups(text: str) -> list[tuple[str, tuple[int, ...]]]:
    """贪心解析连续生肖名，返回 [(标准名, 号码元组), ...]。"""
    pos = 0
    groups: list[tuple[str, tuple[int, ...]]] = []
    while pos < len(text):
        matched = False
        for zid in _ZODIAC_IDS_BY_LEN:
            if text.startswith(zid, pos):
                groups.append((_zodiac_name[zid], _zodiac_by_id[zid]))
                pos += len(zid)
                matched = True
                break
        if not matched:
            break
    return groups


def _parse_exact_zodiac_selection(text: str) -> list[tuple[str, tuple[int, ...]]]:
    """Parse a selection made only of zodiac names, allowing common separators."""
    normalized = re.sub(r"[,，、/\-\s]+", "", text.strip())
    if not normalized:
        return []
    groups = _parse_zodiac_groups(normalized)
    if groups and _zodiac_consume_len(normalized) == len(normalized):
        return groups
    return []


def _lianxiao_category(keyword: str) -> str:
    if keyword in {"连", "连肖"}:
        return "连肖"
    return f"{keyword}肖"


def _is_lianxiao_result_category(category: str) -> bool:
    return category in {"连肖", "拖肖", "托肖", "有肖", "友肖", "胆肖"}


def _build_lianxiao_result(
    *,
    region: str,
    category: str,
    groups: list[tuple[str, tuple[int, ...]]],
    amount: float | Decimal,
) -> ParseResult:
    amount_decimal = _decimal_amount(amount)
    zodiac_order = {zodiac: index for index, zodiac in enumerate(ZODIAC_SEQUENCE)}
    groups = sorted(groups, key=lambda group: zodiac_order[group[0]])
    all_nums = tuple(sorted({n for _, ns in groups for n in ns}))
    return ParseResult(
        region=region,
        success=True,
        category=category,
        numbers=all_nums,
        amount=amount_decimal,
        total=amount_decimal,
        zodiac_groups=groups,
    )


_AGE_WRITING_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*岁")


def _apply_age_writing(text: str, options: ParseOptions) -> tuple[str, str | None]:
    """Normalize NN岁 tokens into lottery number tokens when enabled."""
    if not options.age_writing:
        return text, None

    error: str | None = None

    def repl(match: re.Match[str]) -> str:
        nonlocal error
        raw = match.group(1)
        n = int(raw)
        if n < 1 or n > 49:
            error = f"岁写法号码 {raw} 超出范围 (1-49)"
            return raw
        return f"{n:02d}"

    normalized = _AGE_WRITING_PATTERN.sub(repl, text)
    return normalized, error


def _build_special_zodiac_result(
    *,
    region: str,
    groups: list[tuple[str, tuple[int, ...]]],
    amount: float,
) -> ParseResult:
    all_nums = tuple(sorted({n for _, ns in groups for n in ns}))
    return ParseResult(
        region=region,
        success=True,
        category="平特一肖",
        numbers=all_nums,
        amount=amount,
        total=amount * len(groups),
        zodiac_groups=groups,
    )


def _starts_with_lianxiao(text: str) -> bool:
    """检查文本是否以连肖关键词开头。"""
    for kw in _LIANXIAO_KEYWORDS:
        if text.startswith(kw):
            return True
    return False


def _get_lianxiao_keyword(text: str) -> str:
    """获取开头的连肖关键词（最长的那个）。"""
    found = ""
    for kw in _LIANXIAO_KEYWORDS:
        if text.startswith(kw) and len(kw) > len(found):
            found = kw
    return found


def _try_parse_tuo_zodiacs(text: str) -> list[tuple[str, tuple[int, ...]]] | None:
    """检测「生肖们 + 可选中文数字 + 连/拖/托/有/友」格式。

    例: "猪羊马三托" → 生肖=猪羊马, 数字=三, 关键词=托
         "鼠牛虎二连" → 生肖=鼠牛虎, 数字=二, 关键词=连
         "马虎有"     → 生肖=马虎,   数字=无,  关键词=有

    返回生肖分组列表，不匹配则返回 None。
    """
    # 1. 从开头贪心解析生肖名
    groups = _parse_zodiac_groups(text)
    if not groups:
        return None

    consumed = _zodiac_consume_len(text)
    if consumed == 0 or consumed >= len(text):
        return None

    remaining = text[consumed:]
    m = _TUO_TAIL_PATTERN.match(remaining)
    if not m:
        return None

    # 匹配成功：m.group(1) 是可选中文数字，m.group(2) 是 托/拖
    return groups


# ======================================================================
# 主解析
# ======================================================================


# ── "各" / "各数" 分隔符正则 ──
_SEP_PATTERN = re.compile(r"各组|各数|各号|每注|每数|各|每|打|买")

# ── 复试连肖格式: "牛鸡猪狗虎复试3.4.5连各组50" ──
_FUSHI_PATTERN = re.compile(
    r"^(.+?)复试(\d+(?:[\.。]\d+)*)连各组(\d+(?:\.\d+)?)$"
)

# ── bet 类型中缀: 可出现在类别名后面的投注类型关键词 ──
_BET_TYPE_INFIX: list[str] = sorted(
    ["平特一肖", "平特一尾", "特码波色", "特码两面",
     "包半波", "六肖中特", "二中特", "N不中", "特码", "特串", "平码", "连尾", "不中"],
    key=len, reverse=True,  # 长优先
)

_NON_HIT_COUNT_CHARS = "零〇一二两三四五六七八九十"
_NON_HIT_PREFIX_PATTERN = re.compile(
    rf"^(?P<label>(?:[Nn])|(?:\d+)|(?:[{_NON_HIT_COUNT_CHARS}]+))?不中\s*"
)
_NON_HIT_SUFFIX_PATTERN = re.compile(
    rf"(?P<label>(?:[Nn])|(?:\d+)|(?:[{_NON_HIT_COUNT_CHARS}]+))?不中$"
)
_RANKED_LIANXIAO_PATTERN = re.compile(
    r"^(?:(?P<prefix>[二三四五])连肖\s*(?P<prefix_selection>.+?)|"
    r"(?P<suffix_selection>.+?)\s*(?P<suffix>[二三四五])连肖)$"
)
_FUXUAN_TOKEN_PATTERN = re.compile(r"复\s*(\d+)")
_LIANMA_TYPES: dict[str, int] = {"二中二": 2, "三中三": 3, "三中二": 3}


def _strip_bet_type_infix(category_text: str) -> tuple[str, str]:
    """从类别文本末尾剥离投注类型关键词。返回 (剩余类别名, bet_type)。"""
    non_hit_match = _NON_HIT_SUFFIX_PATTERN.search(category_text)
    if non_hit_match:
        remaining = category_text[:non_hit_match.start()].strip()
        if remaining:
            return remaining, non_hit_match.group(0)
    for bt in _BET_TYPE_INFIX:
        if category_text.endswith(bt):
            remaining = category_text[:-len(bt)].strip()
            if remaining:  # 剥离后还有内容（如 "蛇"、"红波"）
                return remaining, bt
    return category_text, ""


def _parse_ranked_lianxiao_category(
    *,
    region: str,
    category_text: str,
    amount: float | Decimal,
) -> ParseResult | None:
    match = _RANKED_LIANXIAO_PATTERN.fullmatch(category_text.strip())
    if match is None:
        return None
    rank_text = match.group("prefix") or match.group("suffix")
    selection_text = match.group("prefix_selection") or match.group("suffix_selection") or ""
    rank = int(parse_non_hit_count_label(rank_text) or 0)
    compact_selection = re.sub(r"[,，、/\-\s]+", "", selection_text)
    groups = _parse_zodiac_groups(compact_selection)
    consumed = _zodiac_consume_len(compact_selection)
    if consumed != len(compact_selection):
        return ParseResult(
            region=region,
            success=False,
            error=f"无法解析连肖生肖列表：{selection_text}",
        )
    names = [name for name, _ in groups]
    duplicates = sorted(
        {name for name in names if names.count(name) > 1},
        key=ZODIAC_SEQUENCE.index,
    )
    if duplicates:
        unique_count = len(set(names))
        return ParseResult(
            region=region,
            success=False,
            error=(
                f"连肖生肖重复：{','.join(duplicates)}；连肖阶数与生肖数量不匹配："
                f"{rank_text}连肖需要{rank}个不同生肖，实际{unique_count}个不同生肖"
            ),
        )
    if len(groups) != rank:
        return ParseResult(
            region=region,
            success=False,
            error=(
                f"连肖阶数与生肖数量不匹配：{rank_text}连肖需要{rank}个生肖，"
                f"实际{len(groups)}个"
            ),
        )
    return _build_lianxiao_result(
        region=region,
        category="连肖",
        groups=groups,
        amount=amount,
    )


def _parse_non_hit_numbers(
    selection_text: str,
    expected_count: int | None,
) -> tuple[tuple[int, ...] | None, str | None]:
    text = selection_text.strip()
    range_match = re.fullmatch(r"(\d{1,2})\s*[-至]\s*(\d{1,2})", text)
    raw_numbers: list[int] = []
    if range_match:
        lower, upper = int(range_match.group(1)), int(range_match.group(2))
        if not (1 <= lower <= upper <= 49):
            return None, f"N不中号码范围无效：{selection_text}（号码必须为01-49）"
        raw_numbers = list(range(lower, upper + 1))
    else:
        if re.search(r"(?:^|[,，、/\.\s])-\d", text):
            return None, f"N不中号码格式无效：{selection_text}"
        tokens = [token for token in re.split(r"[,，、/\.\-—\s]+", text) if token]
        if not tokens:
            return None, "N不中号码列表不能为空"
        for token in tokens:
            if not token.isdigit():
                return None, f"N不中号码格式无效：{selection_text}"
            number = int(token)
            if number < 1 or number > 49:
                return None, f"N不中号码 {token} 超出范围 (01-49)"
            raw_numbers.append(number)

    duplicate_numbers = sorted({number for number in raw_numbers if raw_numbers.count(number) > 1})
    if duplicate_numbers:
        duplicate_text = ",".join(f"{number:02d}" for number in duplicate_numbers)
        return None, f"N不中号码重复：{duplicate_text}"

    actual_count = len(raw_numbers)
    effective_count = expected_count if expected_count is not None else actual_count
    if effective_count < NON_HIT_MIN_COUNT or effective_count > NON_HIT_MAX_COUNT:
        return None, (
            f"N不中选择号码数量必须为{NON_HIT_MIN_COUNT}-{NON_HIT_MAX_COUNT}个，"
            f"实际{actual_count}个"
        )
    if actual_count != effective_count:
        label = format_non_hit_count_chinese(effective_count)
        return None, (
            f"N不中阶数与号码数量不匹配：{label}不中需要{effective_count}个不同号码，"
            f"实际{actual_count}个"
        )
    return tuple(sorted(raw_numbers)), None


def _decimal_amount(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _parse_tail_digit_list(text: str) -> tuple[int, ...] | str:
    if re.search(r"(^|[,，、\s])-+\d", text.strip()):
        return f"平尾尾数无效：{text}"
    tokens = [token for token in re.split(r"[,，、\-\s]+", text.strip()) if token]
    if not tokens:
        return "平尾尾数不能为空"
    tails: list[int] = []
    for token in tokens:
        if not token.isdigit():
            return f"平尾尾数格式无效：{text}"
        tail = int(token)
        if tail < 0 or tail > 9:
            return f"平尾尾数 {token} 超出范围 (0-9)"
        tails.append(tail)
    return tuple(sorted(set(tails)))


def _parse_pingwei_category(
    *,
    region: str,
    category_text: str,
    amount: float | Decimal,
) -> ParseResult | None:
    text = category_text.strip()
    if not text:
        return None

    selection_text = ""
    if text.startswith("平尾"):
        selection_text = text[len("平尾"):].strip()
    elif text.endswith("平尾"):
        selection_text = text[: -len("平尾")].strip()
    else:
        return None

    parsed = _parse_tail_digit_list(selection_text)
    if isinstance(parsed, str):
        return ParseResult(region=region, success=False, error=parsed)
    amount_decimal = _decimal_amount(amount)
    return ParseResult(
        region=region,
        success=True,
        category="平尾",
        numbers=parsed,
        amount=amount_decimal,
        total=amount_decimal * len(parsed),
        pingwei_tails=parsed,
    )


def _format_lianma_selection(groups: tuple[tuple[int, ...], ...]) -> str:
    return "-".join("(" + "-".join(f"{number:02d}" for number in group) + ")" for group in groups)


def _parse_lianma_group_text(group_text: str, group_size: int) -> tuple[int, ...] | str:
    raw_tokens = [token for token in re.split(r"[,，、\-\s]+", group_text.strip()) if token]
    if len(raw_tokens) != group_size:
        return f"连码每组必须 {group_size} 个号码：{group_text}"
    numbers: list[int] = []
    for token in raw_tokens:
        if not token.isdigit():
            return f"连码号码格式无效：{group_text}"
        number = int(token)
        if number < 1 or number > 49:
            return f"连码号码 {token} 超出范围 (01-49)"
        numbers.append(number)
    if len(set(numbers)) != len(numbers):
        return f"连码单组内不能重复号码：{group_text}"
    return tuple(numbers)


def _parse_lianma_drag_group_text(group_text: str) -> tuple[int, ...] | str:
    raw_tokens = [token for token in re.split(r"[,，、\-\s]+", group_text.strip()) if token]
    if not raw_tokens:
        return f"拖式号码组不能为空：{group_text}"
    numbers: list[int] = []
    for token in raw_tokens:
        if not token.isdigit():
            return f"拖式号码格式无效：{group_text}"
        number = int(token)
        if number < 1 or number > 49:
            return f"拖式号码 {token} 超出范围 (01-49)"
        numbers.append(number)
    if len(set(numbers)) != len(numbers):
        return f"拖式同组内不能重复号码：{group_text}"
    return tuple(numbers)


def _parse_lianma_drag_groups(selection_text: str, group_size: int) -> tuple[tuple[int, ...], ...] | str | None:
    text = selection_text.strip()
    if group_size != 2:
        return None

    if "拖" in text:
        pieces = [piece.strip() for piece in text.split("拖")]
        if len(pieces) != 2 or not pieces[0] or not pieces[1]:
            return f"二中二拖式格式无效：{selection_text}"
    elif "/" in text:
        pieces = [piece.strip() for piece in text.split("/")]
        if len(pieces) != 2 or not pieces[0] or not pieces[1]:
            return f"二中二分组格式无效：{selection_text}"
    else:
        return None

    left = _parse_lianma_drag_group_text(pieces[0])
    if isinstance(left, str):
        return left
    right = _parse_lianma_drag_group_text(pieces[1])
    if isinstance(right, str):
        return right
    if set(left) & set(right):
        return "二中二拖式两组号码不能重复"

    groups: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for left_number in left:
        for right_number in right:
            group = tuple(sorted((left_number, right_number)))
            if group in seen:
                continue
            seen.add(group)
            groups.append(group)
    if not groups:
        return f"二中二拖式没有生成有效组合：{selection_text}"
    return tuple(groups)


def _parse_lianma_groups(
    selection_text: str,
    group_size: int,
    *,
    fushi_mode: bool = False,
) -> tuple[tuple[int, ...], ...] | str:
    text = selection_text.strip()
    if not text:
        return "连码投注内容不能为空"

    explicit_fushi = "复式" in text
    if explicit_fushi:
        text = text.replace("复式", " ").strip()

    drag_groups = _parse_lianma_drag_groups(text, group_size)
    if drag_groups is not None:
        return drag_groups

    bracket_matches = list(re.finditer(r"\(([^()]*)\)", text))
    if bracket_matches:
        leftover = re.sub(r"\([^()]*\)", "", text).strip()
        if re.sub(r"[\-—,，、\s]+", "", leftover):
            return f"连码括号组合格式无效：{selection_text}"
        groups: list[tuple[int, ...]] = []
        for match in bracket_matches:
            parsed = _parse_lianma_group_text(match.group(1), group_size)
            if isinstance(parsed, str):
                return parsed
            groups.append(parsed)
        return tuple(groups)

    numbers = _parse_number_list(text)
    if numbers is not None and (explicit_fushi or fushi_mode):
        if len(numbers) < group_size:
            return f"连码复式号码数量不能少于 {group_size} 个：{selection_text}"
        return tuple(tuple(group) for group in itertools.combinations(numbers, group_size))

    parsed = _parse_lianma_group_text(text, group_size)
    if isinstance(parsed, str):
        return parsed
    return (parsed,)


def _parse_lianma_category(
    *,
    region: str,
    category_text: str,
    amount: float | Decimal,
    fushi_mode: bool = False,
) -> ParseResult | None:
    text = category_text.strip()
    if not text:
        return None

    bet_type = ""
    selection_text = ""
    for candidate in sorted(_LIANMA_TYPES, key=len, reverse=True):
        if text.startswith(candidate):
            bet_type = candidate
            selection_text = text[len(candidate):].strip()
            break
        if text.endswith(candidate):
            bet_type = candidate
            selection_text = text[: -len(candidate)].strip()
            break
    if not bet_type:
        return None

    group_size = _LIANMA_TYPES[bet_type]
    groups = _parse_lianma_groups(selection_text, group_size, fushi_mode=fushi_mode)
    if isinstance(groups, str):
        return ParseResult(region=region, success=False, error=groups)

    amount_decimal = _decimal_amount(amount)
    flattened = tuple(sorted({number for group in groups for number in group}))
    return ParseResult(
        region=region,
        success=True,
        category=bet_type,
        numbers=flattened,
        amount=amount_decimal,
        total=amount_decimal * len(groups),
        lianma_groups=groups,
    )


def _unique_zodiac_groups(
    groups: list[tuple[str, tuple[int, ...]]],
) -> list[tuple[str, tuple[int, ...]]]:
    seen: set[str] = set()
    unique: list[tuple[str, tuple[int, ...]]] = []
    for name, numbers in groups:
        if name in seen:
            continue
        seen.add(name)
        unique.append((name, numbers))
    return unique


def _build_fuxuan_result(
    *,
    region: str,
    category: str,
    numbers: tuple[int, ...],
    amount: float | Decimal,
    k: int,
    zodiac_groups: list[tuple[str, tuple[int, ...]]] | None = None,
) -> ParseResult:
    count = len(zodiac_groups) if zodiac_groups is not None else len(numbers)
    combo_count = math.comb(count, k)
    amount_decimal = _decimal_amount(amount)
    return ParseResult(
        region=region,
        success=True,
        category=category,
        numbers=numbers,
        amount=amount_decimal,
        total=amount_decimal * combo_count,
        zodiac_groups=zodiac_groups or [],
        fuxuan_type=f"复{k}",
    )


def _parse_fuxuan_category(
    *,
    region: str,
    category_text: str,
    amount: float | Decimal,
) -> ParseResult | None:
    text = category_text.strip()
    if not text:
        return None

    explicit_type = ""
    for prefix, category in (
        ("几中几复选", "几中几复选"),
        ("复式组合", "几中几复选"),
        ("连肖复选", "连肖复选"),
    ):
        if text.startswith(prefix):
            explicit_type = category
            text = text[len(prefix):].strip()
            break

    matches = list(_FUXUAN_TOKEN_PATTERN.finditer(text))
    if not matches:
        return None
    if len(matches) > 1:
        return ParseResult(region=region, success=False, error=f"复选格式只能包含一个复选类型：{category_text}")

    match = matches[0]
    k = int(match.group(1))
    selection_text = f"{text[:match.start()]} {text[match.end():]}".strip()
    if k < 2:
        return ParseResult(region=region, success=False, error=f"复选数量必须至少为 2：复{k}")
    if not selection_text:
        return ParseResult(region=region, success=False, error=f"复选投注内容不能为空：{category_text}")

    if explicit_type != "连肖复选":
        numbers = _parse_number_list(selection_text)
        if numbers is not None:
            if k > len(numbers):
                return ParseResult(
                    region=region,
                    success=False,
                    error=f"复选数量复{k}不能大于号码个数 {len(numbers)}",
                )
            return _build_fuxuan_result(
                region=region,
                category="几中几复选",
                numbers=numbers,
                amount=amount,
                k=k,
            )
        if explicit_type == "几中几复选":
            return ParseResult(region=region, success=False, error=f"无法解析几中几复选号码列表：{selection_text}")

    if explicit_type != "几中几复选":
        groups = _unique_zodiac_groups(_parse_exact_zodiac_selection(selection_text))
        if groups:
            if k > len(groups):
                return ParseResult(
                    region=region,
                    success=False,
                    error=f"复选数量复{k}不能大于生肖个数 {len(groups)}",
                )
            all_numbers = tuple(sorted({n for _, nums in groups for n in nums}))
            return _build_fuxuan_result(
                region=region,
                category="连肖复选",
                numbers=all_numbers,
                amount=amount,
                k=k,
                zodiac_groups=groups,
            )
        if explicit_type == "连肖复选":
            return ParseResult(region=region, success=False, error=f"无法解析连肖复选生肖列表：{selection_text}")

    return ParseResult(region=region, success=False, error=f"无法解析复选投注内容：{selection_text}")


def _resolve_parse_options(
    options: ParseOptions | None,
    *,
    special_zodiac_mode: bool = False,
    age_writing: bool = False,
    zodiac_each_mode: bool = False,
    zodiac_year: int | None = None,
) -> ParseOptions:
    if options is not None:
        if options.zodiac_year is None and zodiac_year is not None:
            return ParseOptions(
                special_zodiac_mode=options.special_zodiac_mode,
                age_writing=options.age_writing,
                zodiac_each_mode=options.zodiac_each_mode,
                zodiac_year=zodiac_year,
            )
        return options
    return ParseOptions(
        special_zodiac_mode=special_zodiac_mode,
        age_writing=age_writing,
        zodiac_each_mode=zodiac_each_mode,
        zodiac_year=zodiac_year,
    )


def parse_order(
    text: str,
    *,
    options: ParseOptions | None = None,
    special_zodiac_mode: bool = False,
    age_writing: bool = False,
    zodiac_each_mode: bool = False,
    zodiac_year: int | None = None,
) -> ParseResult:
    """解析一行订单文本，返回展开结果。

    Args:
        text: 订单文本，如 "兔各20"、"兔各数20"、"连兔龙蛇各20"、"兔龙蛇各20"

    Returns:
        ParseResult — 成功时包含号码列表和金额；失败时 success=False。
    """
    options = _resolve_parse_options(
        options,
        special_zodiac_mode=special_zodiac_mode,
        age_writing=age_writing,
        zodiac_each_mode=zodiac_each_mode,
        zodiac_year=zodiac_year,
    )
    _configure_zodiac_year(options.zodiac_year)
    text = _normalize_smart_text(text.strip())
    if not text:
        return ParseResult(success=False, error="输入为空")

    text, age_error = _apply_age_writing(text, options)
    if age_error:
        return ParseResult(success=False, error=age_error)

    # ── 提取排除号码: "兔各30 不要04,16" → 排除 04,16 ──
    exclude_nums: set[int] = set()
    _EXCLUDE_PATTERN = re.compile(r"\s+(?:不要|除了|排除|去掉|除)\s*(.+)$")
    exclude_m = _EXCLUDE_PATTERN.search(text)
    if exclude_m:
        exclude_text = exclude_m.group(1)
        parsed_ex = _parse_number_list(exclude_text)
        if parsed_ex:
            exclude_nums = set(parsed_ex)
        text = text[:exclude_m.start()].strip()

    # ── 提取地域前缀 ──
    region = ""
    for prefix, full_name in (("澳门", "澳门"), ("澳", "澳门"), ("奥", "澳门"), ("香港", "香港"), ("港", "香港")):
        if text.startswith(prefix):
            region = full_name
            text = text[len(prefix):].strip()
            break

    # ── 投注类型前缀（覆盖默认类别）──
    bet_type_override = ""
    non_hit_expected_count: int | None = None
    non_hit_prefix = _NON_HIT_PREFIX_PATTERN.match(text)
    if non_hit_prefix:
        bet_type_override = "N不中"
        try:
            non_hit_expected_count = parse_non_hit_count_label(non_hit_prefix.group("label") or "")
        except ValueError as exc:
            return ParseResult(region=region, success=False, error=str(exc))
        if non_hit_expected_count is not None and not (
            NON_HIT_MIN_COUNT <= non_hit_expected_count <= NON_HIT_MAX_COUNT
        ):
            return ParseResult(
                region=region,
                success=False,
                error=f"N不中阶数必须为{NON_HIT_MIN_COUNT}-{NON_HIT_MAX_COUNT}",
            )
        text = text[non_hit_prefix.end():].strip()

    _BET_PREFIXES = [
        ("平特一肖", "平特一肖"),
        ("特肖", "平特一肖"),
        ("平特一尾", "平特一尾"),
        ("特码波色", "特码波色"),
        ("特码两面", "特码两面"),
        ("六肖中特", "六肖中特"),
        ("二中特", "二中特"),
        ("包半波", "包半波"),
        ("特串", "特串"),
        ("平码", "平码"),
        ("连尾", "连尾"),
        ("特码", "特码"),
    ]  # 长优先，避免 "特码" 截胡 "特码波色"
    if not bet_type_override:
        for prefix, bt in _BET_PREFIXES:
            if text.startswith(prefix):
                bet_type_override = bt
                text = text[len(prefix):].strip()
                break

    # ── 0. 斜杠简写: <号码>/<金额>  最高优先级 ──
    slash_m = re.match(r"^(\d{1,2})/(\d+)$", text)
    if slash_m:
        num = int(slash_m.group(1))
        amount = float(slash_m.group(2))
        if 1 <= num <= 49:
            result = ParseResult(region=region,
                success=True,
                category="单号投注",
                numbers=(num,),
                amount=amount,
                total=amount,
            )
            _apply_exclusion(result, exclude_nums)
            return result
        else:
            return ParseResult(region=region,
                success=False,
                error=f"号码 {num} 超出范围 (1-49)",
            )

    # ── 0b. 复试连肖: 牛鸡猪狗虎复试3.4.5连各组50 ──
    fushi_m = _FUSHI_PATTERN.match(text)
    if fushi_m:
        zodiac_text = fushi_m.group(1)
        lian_str = fushi_m.group(2)
        amount = float(fushi_m.group(3))

        if amount <= 0:
            return ParseResult(region=region,
                success=False,
                error=f"复试金额必须大于 0，当前: {amount}",
            )

        groups = _parse_zodiac_groups(zodiac_text)
        if not groups:
            return ParseResult(region=region,
                success=False,
                error=f"复试格式中无法识别生肖: 「{zodiac_text}」",
            )

        lian_sizes = [int(s) for s in re.split(r"[\.。]", lian_str) if s]
        zc = len(groups)
        for n in lian_sizes:
            if n < 2 or n > zc:
                return ParseResult(region=region,
                    success=False,
                    error=f"复试连数 {n} 无效（最少2连，最多{zc}连，当前{len(groups)}个生肖）",
                )

        total_combos = sum(
            len(list(itertools.combinations(groups, n))) for n in lian_sizes
        )
        all_nums = tuple(sorted({n for _, ns in groups for n in ns}))

        return ParseResult(
            region=region,
            success=True,
            category="连肖复选",
            numbers=all_nums,
            amount=amount,
            total=amount * total_combos,
            zodiac_groups=groups,
            fushi_lian_sizes=tuple(lian_sizes),
            fuxuan_type="复" + ".".join(str(size) for size in lian_sizes),
            note=f"复试连数={','.join(str(size) for size in lian_sizes)};组合数={total_combos}",
        )

    # ── 1. 查找 "各/各数/每/每注" 分隔符 ──
    sep_m = _SEP_PATTERN.search(text)
    if not sep_m:
        # 无分隔符：尝试末尾金额（旧格式兜底 / 省略「各」的快捷格式「兔10」）
        amount, category_text = _extract_amount(text)
        category_text, infix_bt = _strip_bet_type_infix(category_text)
        if infix_bt and not bet_type_override:
            if infix_bt.endswith("不中"):
                bet_type_override = "N不中"
                try:
                    non_hit_expected_count = parse_non_hit_count_label(infix_bt)
                except ValueError as exc:
                    return ParseResult(region=region, success=False, error=str(exc))
            else:
                bet_type_override = infix_bt
        # 清理末尾残留的分隔关键字（"蛇打" → "蛇"）
        category_text = re.sub(r'(打|各|各数|每|每注)$', '', category_text).strip()
        if amount == 0:
            return ParseResult(region=region,
                success=False,
                error=f"未找到「各/每/打」分隔符，且无法提取末尾金额: {text}",
            )
    else:
        category_text = text[: sep_m.start()].strip()

        # ── 检查 bet 类型中缀（如 "蛇平特一肖打1000"）──
        category_text, infix_bt = _strip_bet_type_infix(category_text)
        if infix_bt and not bet_type_override:
            if infix_bt.endswith("不中"):
                bet_type_override = "N不中"
                try:
                    non_hit_expected_count = parse_non_hit_count_label(infix_bt)
                except ValueError as exc:
                    return ParseResult(region=region, success=False, error=str(exc))
            else:
                bet_type_override = infix_bt

        amount_str = text[sep_m.end() :].strip()
        # 去除可选的 "元" 后缀
        amount_str = re.sub(r"(元|块|蚊)$", "", amount_str).strip()
        # 金额倍数: *N（如「兔各10*3」→ 30）
        mult_m = re.match(r"(\d+(?:\.\d+)?)\s*\*\s*(\d+)\s*$", amount_str)
        if mult_m:
            amount_str = mult_m.group(1)
            amount = float(amount_str) * float(mult_m.group(2))
        else:
            try:
                amount = float(amount_str)
            except ValueError:
                return ParseResult(region=region,
                    success=False,
                    error=f"金额格式无效: 「{sep_m.group()}」后的 '{amount_str}' 无法转为数字",
                )

    if amount <= 0:
        return ParseResult(region=region, success=False, error=f"金额必须大于 0，当前: {amount}")

    if not category_text:
        return ParseResult(region=region, success=False, error="未找到类别描述（分隔符之前为空）")

    if non_hit_expected_count is not None and not (
        NON_HIT_MIN_COUNT <= non_hit_expected_count <= NON_HIT_MAX_COUNT
    ):
        return ParseResult(
            region=region,
            success=False,
            error=f"N不中阶数必须为{NON_HIT_MIN_COUNT}-{NON_HIT_MAX_COUNT}",
        )

    ranked_lianxiao_result = _parse_ranked_lianxiao_category(
        region=region,
        category_text=category_text,
        amount=amount,
    )
    if ranked_lianxiao_result is not None:
        return ranked_lianxiao_result

    pingwei_result = _parse_pingwei_category(
        region=region,
        category_text=category_text,
        amount=amount,
    )
    if pingwei_result is not None:
        return pingwei_result

    lianma_result = _parse_lianma_category(
        region=region,
        category_text=category_text,
        amount=amount,
        fushi_mode=bool(sep_m and sep_m.group() == "各组"),
    )
    if lianma_result is not None:
        return lianma_result

    fuxuan_result = _parse_fuxuan_category(
        region=region,
        category_text=category_text,
        amount=amount,
    )
    if fuxuan_result is not None:
        return fuxuan_result

    # ── 2-4. 类别匹配（支持前缀剥离，如「张三 兔」→ 忽略「张三」匹配「兔」）──

    def _try_match(cat: str, amt: float) -> ParseResult | None:
        """尝试所有匹配策略，成功返回 ParseResult，失败返回 None。"""
        groups_for_special = _parse_exact_zodiac_selection(cat)
        use_zodiac_each = (
            options.zodiac_each_mode
            and sep_m is not None
            and sep_m.group() == "各"
            and len(groups_for_special) >= 1
        )
        zodiac_number_mode = bool(sep_m and sep_m.group() in {"各数", "每数"})
        if (
            groups_for_special
            and (bet_type_override == "平特一肖" or use_zodiac_each or options.special_zodiac_mode)
        ):
            return _build_special_zodiac_result(
                region=region,
                groups=groups_for_special,
                amount=amt,
            )

        # 0. 特殊投注类型处理
        if bet_type_override in {"二中特", "特串"}:
            num_list = _parse_number_list(cat)
            if num_list is not None:
                return ParseResult(region=region,
                    success=True,
                    category=bet_type_override,
                    numbers=num_list,
                    amount=amt,
                    total=amt,
                    warnings=[f"{bet_type_override}可录入预览，正式结算暂不支持"],
                )
            return ParseResult(region=region,
                success=False,
                error=f"无法解析{bet_type_override}号码列表：{cat}",
            )

        if bet_type_override == "N不中":
            num_list, non_hit_error = _parse_non_hit_numbers(cat, non_hit_expected_count)
            if non_hit_error:
                return ParseResult(region=region, success=False, error=non_hit_error)
            assert num_list is not None
            return ParseResult(
                region=region,
                success=True,
                category="N不中",
                numbers=num_list,
                amount=amt,
                total=amt,
                note=f"N不中阶数={len(num_list)}",
            )

        if bet_type_override in ("连尾", "平特一尾"):
            # 尾数列表: 所有尾数为指定值的号码展开
            tail_nums = _parse_number_list(cat)
            if tail_nums is not None:
                all_nums: list[int] = []
                for t in tail_nums:
                    if 0 <= t <= 9:
                        all_nums.extend(n for n in range(1, 50) if n % 10 == t)
                if all_nums:
                    return ParseResult(region=region,
                        success=True,
                        category=bet_type_override,  # "连尾" 或 "平特一尾"
                        numbers=tuple(sorted(set(all_nums))),
                        amount=amt,
                        total=amt * len(all_nums),
                    )
            return None

        # 2. 显式连肖（以连/拖/托/有/友/胆开头）
        if _starts_with_lianxiao(cat):
            kw = _get_lianxiao_keyword(cat)
            zodiac_text = cat[len(kw):]
            # 去除中间的关键词（如「胆马拖兔」→ 马兔）
            for kw2 in _LIANXIAO_KEYWORDS:
                zodiac_text = zodiac_text.replace(kw2, "")
            groups_inner = _parse_exact_zodiac_selection(zodiac_text)
            if groups_inner:
                return _build_lianxiao_result(
                    region=region,
                    category=_lianxiao_category(kw),
                    groups=groups_inner,
                    amount=amt,
                )
            return None  # 连肖关键词后无有效生肖

        # 2b. 「生肖们 + 可选数字 + 连/拖/托/有/友」格式
        tuo_groups = _try_parse_tuo_zodiacs(cat)
        if tuo_groups is not None:
            remaining_inner = cat[_zodiac_consume_len(cat):]
            kw_m = _TUO_TAIL_PATTERN.match(remaining_inner)
            suffix = kw_m.group(2) if kw_m else "连"
            return _build_lianxiao_result(
                region=region,
                category=_lianxiao_category(suffix),
                groups=tuo_groups,
                amount=amt,
            )

        # 3. 精确别名匹配
        for rule in _RULES:
            if cat in rule.aliases:
                return ParseResult(region=region,
                    success=True,
                    category=rule.name,
                    numbers=rule.numbers,
                    amount=amt,
                    total=amt * len(rule.numbers),
                )

        # 3b. 纯数字号码列表
        num_list = _parse_number_list(cat)
        if num_list is not None:
            return ParseResult(region=region,
                success=True,
                category="纯数字",
                numbers=num_list,
                amount=amt,
                total=amt * len(num_list),
            )

        # 4. 多生肖 / 单生肖自动识别
        groups_inner = _parse_zodiac_groups(cat)
        if len(groups_inner) >= 2 and _zodiac_consume_len(cat) == len(cat):
            all_nums = tuple(sorted({n for _, ns in groups_inner for n in ns}))
            return ParseResult(region=region,
                success=True,
                category="多生肖",
                numbers=all_nums,
                amount=amt,
                total=amt * (len(all_nums) if zodiac_number_mode else len(groups_inner)),
                zodiac_groups=groups_inner,
                zodiac_number_mode=zodiac_number_mode,
            )
        if len(groups_inner) == 1 and _zodiac_consume_len(cat) == len(cat):
            name, nums = groups_inner[0]
            return ParseResult(region=region,
                success=True,
                category=name,
                numbers=nums,
                amount=amt,
                total=amt * len(nums),
                zodiac_groups=groups_inner,
            )

        return None

    # 先尝试完整类别文本，失败则逐词剥离前缀重试
    ct = category_text
    while True:
        result = _try_match(ct, amount)
        if result is not None:
            if bet_type_override:
                result.category = bet_type_override
            _apply_exclusion(result, exclude_nums)
            return result
        if " " not in ct:
            break
        _, ct = ct.split(" ", 1)

    # ── 5. 无匹配 ──
    return ParseResult(region=region,
        success=False,
        error=f"无法识别的类别: 「{category_text}」",
    )


def _zodiac_consume_len(text: str) -> int:
    """返回从文本开头连续匹配生肖标识符所消费的总字符数。"""
    pos = 0
    while pos < len(text):
        matched = False
        for zid in _ZODIAC_IDS_BY_LEN:
            if text.startswith(zid, pos):
                pos += len(zid)
                matched = True
                break
        if not matched:
            break
    return pos


# ======================================================================
# 多行解析
# ======================================================================


def _normalize_line(text: str) -> str | None:
    """清洗一行自然语言口语订单，转换为标准格式。无法识别返回 None。

    >>> _normalize_line("张二，澳门码，09号，45号，以上二个数各5元")
    '澳门09,45各5'
    >>> _normalize_line("01号一10元")
    '01各10'
    >>> _normalize_line("共计40")
    None
    """
    t = _normalize_smart_text(text)
    if not t:
        return None

    # 丢弃仅有"共计NN"的行
    if re.match(r'^(?:共计|合计|总计)\s*\d+(?:\.\d+)?$', t):
        return None

    # 去掉开头的「人名，」/「人名、」（2-3个中文字 + 中文逗号）
    t = re.sub(r'^[^\d\s澳门香港澳奥港各每打买连复试]{2,4}[，,]\s*', '', t)

    # 地区口语：澳门码 / 香港码 → 澳门 / 香港
    t = re.sub(r'(澳门|香港)码', r'\1', t)

    # "，N号不要" / "，N,N号除外" → " 不要 N,N"（翻转给后续排除逻辑用）
    t = re.sub(
        r'(?:^|[，,]\s*)(\d{1,2}(?:[，,]\d{1,2})*)号(不要|除外|排除|去掉|除了)',
        r' \2 \1',
        t,
    )

    # "以上N个数各X元" / "以上N个各X元" → 各X
    # 先转中文数字：五→5, 六→6, 七→7, 八→8, 九→9, 十→10
    for cn, nb in [("五", "5"), ("六", "6"), ("七", "7"), ("八", "8"), ("九", "9"), ("十", "10")]:
        t = t.replace(f'以上{cn}个', f'以上{nb}个')
    t = re.sub(r'以上(\d+)个(?:数)?各(\d+(?:\.\d+)?)', r'各\2', t)

    # "各X元" / "每X元" → "各X"
    t = re.sub(r'(各组|各数|各号|每注|每数|各|每|打|买)(\d+(?:\.\d+)?)(元|块|蚊)', r'\1\2', t)

    # "一X元" → "各X"  (口语 "01号一10元" → "01各10")
    t = re.sub(r'一(\d+(?:\.\d+)?)(元|块|蚊)', r'各\1', t)

    # 中文逗号、顿号 → 英文逗号（号码分隔）
    t = t.replace('，', ',').replace('、', ',')

    # 去掉首尾逗号（"澳门,09,45,各5" 保留逗号；",09,45,各5" 清理首部逗号）
    t = re.sub(r'^[,\s]+', '', t)
    t = re.sub(r'[,\s]+$', '', t)
    t = re.sub(r',\s*,', ',', t)  # 双逗号合并

    # 残留的"元"字清理
    t = re.sub(r'(\d)元', r'\1', t)

    t = t.strip()
    if not t:
        return None

    return t


def _extract_declared_total(text: str) -> tuple[str, Decimal | None]:
    text = _normalize_chinese_amounts(text.translate(_FULLWIDTH_DIGITS))
    total: Decimal | None = None

    def repl(match: re.Match[str]) -> str:
        nonlocal total
        value = _cn_amount_to_number(match.group(1))
        if value is None:
            return ""
        total = value
        return ""

    cleaned = re.sub(
        rf"(?:共计|合计|总计)\s*(\d+(?:\.\d+)?|[{_CN_AMOUNT_CHARS}]+)\s*(?:元|块|蚊)?",
        repl,
        text,
    )
    return cleaned, total


def _strip_region_marker(text: str) -> tuple[str, str]:
    t = text.strip()
    region = ""
    for marker, full_name in (
        ("澳门码", "澳门"),
        ("澳门", "澳门"),
        ("澳", "澳门"),
        ("奥", "澳门"),
        ("香港码", "香港"),
        ("香港", "香港"),
        ("港", "香港"),
    ):
        if t.startswith(marker):
            return t[len(marker):].strip(), full_name
    for marker, full_name in (
        ("澳门码", "澳门"),
        ("澳门", "澳门"),
        ("澳", "澳门"),
        ("奥", "澳门"),
        ("香港码", "香港"),
        ("香港", "香港"),
        ("港", "香港"),
    ):
        if t.endswith(marker):
            return t[: -len(marker)].strip(), full_name
    return t, region


def _with_region(segment: str, region: str) -> str:
    if not region:
        return segment.strip()
    segment = segment.strip()
    if segment.startswith(("澳门", "澳", "奥", "香港", "港")):
        return segment
    return region + segment


def _is_exclusion_clause(text: str) -> bool:
    return bool(re.search(r"(不要|除了|排除|去掉|除外|除)", text))


def _normalize_exclusion_clause(text: str) -> str:
    cleaned = re.sub(r"(不要|除了|排除|去掉|除外|除)", "", text)
    cleaned = cleaned.replace("号", "")
    nums = _parse_number_list(cleaned)
    if nums:
        return " 不要 " + ",".join(f"{n:02d}" for n in nums)
    return " " + text.strip()


def _looks_like_amount_clause(text: str) -> bool:
    if re.search(_SEP_PATTERN, text):
        return True
    zodiacs = "".join(sorted(set(_zodiac_name.values())))
    if re.fullmatch(rf"[{zodiacs}]+(?:平特一肖|平)\d+(?:\.\d+)?", text.strip()):
        return True
    if re.fullmatch(rf"[{zodiacs}]+[{_CN_DIGIT_CHARS}]?(?:连肖|连|拖|托|有|友|胆)\d+(?:\.\d+)?", text.strip()):
        return True
    if re.fullmatch(r"\d{1,2}号\d+(?:\.\d+)?", text.strip()):
        return True
    return False


def _split_comma_clauses(line: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[，,]", line) if part.strip()]
    if len(parts) < 2:
        return [line]

    combined: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if _is_exclusion_clause(part) and combined:
            combined[-1] += _normalize_exclusion_clause(part)
        elif (
            re.fullmatch(r"\d{1,2}", part)
            and index + 1 < len(parts)
            and re.match(r"\d{1,2}(?:各组|各数|各号|每注|每数|各|每|打|买)", parts[index + 1])
        ):
            combined.append(part + "," + parts[index + 1])
            index += 1
        else:
            combined.append(part)
        index += 1

    amount_like_count = sum(1 for part in combined if _looks_like_amount_clause(part))
    numeric_only_count = sum(1 for part in combined if re.fullmatch(r"\d{1,2}", part))
    if amount_like_count >= 2 and numeric_only_count < len(combined) - 1:
        return combined
    return [line]


def _split_repeated_number_amount_groups(line: str) -> list[str] | None:
    body, region = _strip_region_marker(line)
    compact = re.sub(r"\s+", "", body)
    if not compact or not re.fullmatch(r"[\d/,\-—十各.]+", compact):
        return None
    if compact.count("各") < 2:
        return None

    def parse_group_numbers(group_text: str) -> tuple[list[int], int] | None:
        nums = [token for token in re.split(r"[/,，\-—十]+", group_text.strip("/,，-—十")) if token]
        if not nums:
            return None
        parsed: list[int] = []
        for token in nums:
            if not token.isdigit():
                return None
            number = int(token)
            if number < 1 or number > 49:
                return None
            parsed.append(number)
        return parsed, len(nums[0])

    segments: list[str] = []
    start = 0
    while start < len(compact):
        marker = compact.find("各", start)
        if marker < 0:
            return None
        parsed_group = parse_group_numbers(compact[start:marker])
        if parsed_group is None:
            return None
        parsed, _ = parsed_group

        amount_start = marker + 1
        if amount_start >= len(compact) or not compact[amount_start].isdigit():
            return None

        next_marker_exists = "各" in compact[amount_start:]
        amount_end: int | None = None
        if not next_marker_exists:
            tail = compact[amount_start:]
            if not re.fullmatch(r"\d+(?:\.\d+)?", tail):
                return None
            amount_end = len(compact)
        else:
            candidates: list[tuple[int, int]] = []
            for end in range(amount_start + 1, min(len(compact), amount_start + 6) + 1):
                amount_text = compact[amount_start:end]
                if not re.fullmatch(r"\d+(?:\.\d+)?", amount_text):
                    continue
                next_marker = compact.find("各", end)
                if next_marker < 0:
                    continue
                next_group = parse_group_numbers(compact[end:next_marker])
                if next_group is None:
                    continue
                _, first_token_len = next_group
                candidates.append((0 if first_token_len == 2 else 1, end))
            if not candidates:
                return None
            candidates.sort()
            amount_end = candidates[0][1]

        amount_text = compact[amount_start:amount_end]
        segment = ",".join(f"{number:02d}" for number in parsed) + f"各{amount_text}"
        segments.append(_with_region(segment, region))
        start = amount_end
    return segments


def _split_pair_amount_groups(line: str) -> list[str] | None:
    body, region = _strip_region_marker(line)
    body = body.strip()
    number_matches = list(re.finditer(r"(?<!\d)(\d{1,2})(?:号)?\s+(\d+(?:\.\d+)?)(?!\d)", body))
    if len(number_matches) >= 2:
        leftover = body
        for match in number_matches:
            leftover = leftover.replace(match.group(0), " ", 1)
        if not leftover.strip():
            return [_with_region(f"{int(m.group(1)):02d}各{m.group(2)}", region) for m in number_matches]

    for prefix, target_prefix in (("平特一肖", "平特一肖"), ("连肖", "连肖")):
        if body.startswith(prefix):
            selection_body = body[len(prefix):].strip()
            matches = list(re.finditer(rf"([{''.join(sorted(set(_zodiac_name.values())))}]+)\s*(\d+(?:\.\d+)?)", selection_body))
            if len(matches) < 2:
                return None
            leftover = selection_body
            for match in matches:
                leftover = leftover.replace(match.group(0), " ", 1)
            if leftover.strip():
                return None
            if target_prefix == "平特一肖":
                return [_with_region(f"{m.group(1)}平特一肖打{m.group(2)}", region) for m in matches]
            return [_with_region(f"连肖{m.group(1)}打{m.group(2)}", region) for m in matches]
    return None


def _split_space_order_chunks(line: str) -> list[str] | None:
    body, region = _strip_region_marker(line)
    chunks = [chunk.strip() for chunk in re.split(r"\s{2,}", body) if chunk.strip()]
    if len(chunks) < 2:
        return None
    if all(_looks_like_amount_clause(chunk) for chunk in chunks):
        return [_with_region(chunk, region) for chunk in chunks]
    return None


def _split_smart_segments(line: str) -> list[str]:
    repeated = _split_repeated_number_amount_groups(line)
    if repeated:
        return repeated
    pair_amounts = _split_pair_amount_groups(line)
    if pair_amounts:
        return pair_amounts
    space_chunks = _split_space_order_chunks(line)
    if space_chunks:
        return [part for chunk in space_chunks for part in _split_smart_segments(chunk)]

    pieces: list[str] = []
    for comma_clause in _split_comma_clauses(line):
        pair_clause = _split_pair_amount_groups(comma_clause)
        if pair_clause:
            pieces.extend(pair_clause)
        else:
            pieces.append(comma_clause)
    return pieces


def parse_lines(
    text: str,
    *,
    options: ParseOptions | None = None,
    special_zodiac_mode: bool = False,
    age_writing: bool = False,
    zodiac_each_mode: bool = False,
    zodiac_year: int | None = None,
) -> list[ParseResult]:
    """解析多行文本，支持上下文标题行和口语自然语言清洗。

    标题行格式: [地域]投注类型   如 "澳平特一肖"、"港特码"
    数据行自动继承标题行的地域和投注类型。

    口语清洗示例:
        张二，澳门码，09号，45号，以上二个数各5元  →  澳门09,45各5
        01号一10元                                    →  01各10
        共计40                                        →  (丢弃)
    """
    options = _resolve_parse_options(
        options,
        special_zodiac_mode=special_zodiac_mode,
        age_writing=age_writing,
        zodiac_each_mode=zodiac_each_mode,
        zodiac_year=zodiac_year,
    )
    _configure_zodiac_year(options.zodiac_year)
    text, declared_total = _extract_declared_total(text)
    results: list[ParseResult] = []
    ctx_region = ""
    ctx_bet_type = ""

    # 所有可作为标题的投注类型（长优先匹配）
    _ALL_BT = sorted(
        {"平特一肖", "平特一尾", "特码波色", "特码两面",
         "包半波", "六肖中特", "特码", "平码", "不中", "连尾"},
        key=len, reverse=True,
    )

    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        # ── 按句号分号拆子句，逐条清洗 ──
        sub_lines: list[str] = []
        for sub in re.split(r'[。；;]', raw_line):
            normalized = _normalize_line(sub)
            if normalized:
                sub_lines.append(normalized)
        if not sub_lines:
            continue

        for line in sub_lines:

            # ── 尝试解析为标题行 ──
            h_region = ""
            h_bt = ""
            remaining = line
            for prefix, full_name in (("澳门", "澳门"), ("澳", "澳门"), ("奥", "澳门"), ("香港", "香港"), ("港", "香港")):
                if remaining.startswith(prefix):
                    h_region = full_name
                    remaining = remaining[len(prefix):].strip()
                    break
            for bt in _ALL_BT:
                if remaining.startswith(bt):
                    h_bt = bt
                    remaining = remaining[len(bt):].strip()
                    break

            if h_bt and not remaining:
                # 纯标题行：更新上下文，不产生输出
                ctx_region = h_region or ctx_region
                ctx_bet_type = h_bt
                continue

            # ── 数据行：继承上下文 ──
            if ctx_region and not any(line.startswith(p) for p in ("澳门", "香港", "澳", "港")):
                line = ctx_region + line
            if ctx_bet_type and not any(line.startswith(bt) for bt in _ALL_BT):
                # 投注类型要紧挨地域之后（parse_order 先剥地域再剥投注类型）
                inserted = False
                for prefix in ("澳门", "香港", "澳", "奥", "港"):
                    if line.startswith(prefix):
                        line = prefix + ctx_bet_type + line[len(prefix):]
                        inserted = True
                        break
                if not inserted:
                    line = ctx_bet_type + line

            # ── 一行多单：按参考软件式口语规则拆成独立订单片段 ──
            trailing_region = ""
            stripped_line, trailing_region = _strip_region_marker(line)
            if trailing_region:
                line = _with_region(stripped_line, trailing_region)
            sub_parts = _split_smart_segments(line)
            for sub in sub_parts:
                sub = sub.strip()
                if sub:
                    r = parse_order(sub, options=options)
                    r.original_text = sub.strip()
                    r.normalized_text = sub.strip()
                    results.append(r)

    if declared_total is not None and results:
        calculated_total = sum((Decimal(str(r.total)) for r in results if r.success), Decimal("0"))
        if calculated_total == declared_total:
            message = f"共计校验通过：{_format_decimal_plain(declared_total)}"
        else:
            message = (
                f"共计校验不一致：输入{_format_decimal_plain(declared_total)}，"
                f"解析{_format_decimal_plain(calculated_total)}"
            )
        for result in results:
            if result.success:
                result.warnings.append(message)
                break
    return results


# ======================================================================
# 输出格式化
# ======================================================================


def _fmt_nums(nums: tuple[int, ...]) -> str:
    """号码列表用逗号拼接，如 04,16,28,40。"""
    return ",".join(f"{n:02d}" for n in nums)


def _reverse_zodiac(numbers: tuple[int, ...]) -> str:
    """反向查询：号码列表 → 生肖标注。"""
    zodiacs: dict[str, list[int]] = {}
    for n in numbers:
        name = _number_to_zodiac.get(n, "?")
        zodiacs.setdefault(name, []).append(n)

    parts: list[str] = []
    for name, nums in zodiacs.items():
        parts.append(f"{name}({_fmt_nums(nums)})")
    return " ".join(parts)


def _format_fushi(result: ParseResult, amount_display: str) -> str:
    """格式化复试连肖结果，展示组合明细。"""
    groups = result.zodiac_groups
    zodiac_names = [name for name, _ in groups]
    all_nums = list(result.numbers)  # sorted
    lian_sizes = list(result.fushi_lian_sizes) if result.fushi_lian_sizes else []

    # 计算每个连数的组合数
    lian_breakdown: list[tuple[int, int]] = []  # [(连数, 组合数), ...]
    total_combos = 0
    for n in lian_sizes:
        cnt = len(list(itertools.combinations(groups, n)))
        lian_breakdown.append((n, cnt))
        total_combos += cnt

    zc = len(groups)
    lian_label = ".".join(str(n) for n in lian_sizes)
    lines = [
        f"复试连肖: {' '.join(zodiac_names)}  ({zc}个生肖, {lian_label}连)",
        f"号码: {' '.join(f'{n:02d}' for n in all_nums)}",
        "",
    ]
    for n, cnt in lian_breakdown:
        sub_total = cnt * result.amount
        sub_display = f"{sub_total:g}" if sub_total != int(sub_total) else f"{int(sub_total)}"
        lines.append(f"  {n}连: {cnt}组 × {amount_display}元 = {sub_display}元")
    lines.append("")
    total_display = f"{result.total:g}" if result.total != int(result.total) else f"{int(result.total)}"
    lines.append(f"  合计: {total_combos}组, 总{total_display}元")
    return "\n".join(lines)


def format_result(result: ParseResult) -> str:
    """将单条解析结果格式化为输出文本。

    多生肖时每个生肖单独一行；单类别时所有号码一行。
    纯数字类别自动附加反向生肖查询。
    """
    if not result.success:
        return f"[错误] {result.error}"

    amount_display = f"{result.amount:g}" if result.amount != int(result.amount) else f"{int(result.amount)}"
    prefix = f"{result.region}：特码：" if result.region else ""

    # ── 复试连肖专用展示 ──
    if result.fushi_lian_sizes and result.zodiac_groups:
        return _format_fushi(result, amount_display)

    groups = result.zodiac_groups
    if result.category == "平特一肖" and groups:
        names = "、".join(name for name, _ in groups)
        total_display = f"{result.total:g}" if result.total != int(result.total) else f"{int(result.total)}"
        return f"{prefix}平特一肖：{names} 各{amount_display}元，合计{total_display}元"

    if len(groups) >= 2:
        # 多生肖：每个生肖一行，均加前缀
        lines = [f"{prefix}{_fmt_nums(nums)} 各{amount_display}元" for _, nums in groups]
        return "\n".join(lines)

    # 单类别 / 单个生肖 / 无分组
    line = f"{prefix}{_fmt_nums(result.numbers)} 各{amount_display}元"
    # 纯数字列表：附加反向生肖查询
    if result.category == "纯数字" and result.numbers:
        line += f"\n→ {_reverse_zodiac(result.numbers)}"
    return line


def format_results(results: list[ParseResult]) -> str:
    """将多条解析结果格式化为输出文本，条之间空行分隔。"""
    blocks: list[str] = []
    for r in results:
        blocks.append(format_result(r))
    return "\n\n".join(blocks)
