"""订单文本解析服务 — 将自然语言订单展开为六合彩号码列表（2026 年马年起始）。

支持格式: <类别>各数<金额>  或  <连肖关键词><生肖列表>各数<金额>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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

# 2026 年马年起始
_ZODIAC_ENTRIES: tuple[tuple[tuple[str, ...], tuple[int, ...]], ...] = (
    (("午马", "午", "马"), (1, 13, 25, 37, 49)),
    (("巳蛇", "巳", "蛇"), (2, 14, 26, 38)),
    (("辰龙", "辰", "龙"), (3, 15, 27, 39)),
    (("卯兔", "卯", "兔"), (4, 16, 28, 40)),
    (("寅虎", "寅", "虎"), (5, 17, 29, 41)),
    (("丑牛", "丑", "牛"), (6, 18, 30, 42)),
    (("子鼠", "子", "鼠"), (7, 19, 31, 43)),
    (("亥猪", "亥", "猪"), (8, 20, 32, 44)),
    (("戌狗", "戌", "狗"), (9, 21, 33, 45)),
    (("酉鸡", "酉", "鸡"), (10, 22, 34, 46)),
    (("申猴", "申", "猴"), (11, 23, 35, 47)),
    (("未羊", "未", "羊"), (12, 24, 36, 48)),
)

# 标识符 → 号码 快速查找
_zodiac_by_id: dict[str, tuple[int, ...]] = {}
for _aliases, _nums in _ZODIAC_ENTRIES:
    for _a in _aliases:
        _zodiac_by_id[_a] = _nums

# 标识符按长度降序（最长匹配优先）
_ZODIAC_IDS_BY_LEN: list[str] = sorted(_zodiac_by_id.keys(), key=len, reverse=True)

# 标识符 → 标准名（单字全名）
_zodiac_name: dict[str, str] = {}
for _aliases, _ in _ZODIAC_ENTRIES:
    _std = _aliases[-1]  # 最后一个别名是单字全名
    for _a in _aliases:
        _zodiac_name[_a] = _std

# 号码 → 标准生肖名（反向查询）
_number_to_zodiac: dict[int, str] = {}
for _aliases, _nums in _ZODIAC_ENTRIES:
    for _n in _nums:
        _number_to_zodiac[_n] = _aliases[-1]

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

# ======================================================================
# 连肖关键词
# ======================================================================

_LIANXIAO_KEYWORDS: tuple[str, ...] = ("连", "拖", "托", "有", "友", "胆")

# 「数字 + 连肖关键词」格式: 生肖们 + 可选中文数字 + 连/拖/托/有/友
_CN_DIGIT_MAP: dict[str, int] = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_CN_DIGIT_CHARS: str = "".join(_CN_DIGIT_MAP.keys())
# 剩余部分必须完全匹配: 可选中文数字 + 任一连肖关键词
_TUO_TAIL_PATTERN = re.compile(rf"^([{_CN_DIGIT_CHARS}]?)([拖托连有友])$")

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


# ======================================================================
# 金额提取
# ======================================================================

_AMOUNT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:元)?$")


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
    filtered = tuple(n for n in result.numbers if n not in exclude_nums)
    if not filtered:
        excluded_str = ",".join(f"{n:02d}" for n in sorted(exclude_nums))
        result.success = False
        result.error = f"排除 {excluded_str} 后无剩余号码"
        result.numbers = ()
        result.total = 0.0
        return
    result.numbers = filtered
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
_SEP_PATTERN = re.compile(r"(?:各|每)(?:数|注)?")


def parse_order(text: str) -> ParseResult:
    """解析一行订单文本，返回展开结果。

    Args:
        text: 订单文本，如 "兔各20"、"兔各数20"、"连兔龙蛇各20"、"兔龙蛇各20"

    Returns:
        ParseResult — 成功时包含号码列表和金额；失败时 success=False。
    """
    text = text.strip()
    if not text:
        return ParseResult(success=False, error="输入为空")

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
    for prefix in ("澳门", "香港"):
        if text.startswith(prefix):
            region = prefix
            text = text[len(prefix):].strip()
            break

    # ── 投注类型前缀（覆盖默认类别）──
    bet_type_override = ""
    _BET_PREFIXES = [
        ("平特一肖", "平特一肖"),
        ("平特一尾", "平特一尾"),
        ("平码", "平码"),
        ("不中", "不中"),
        ("连尾", "连尾"),
    ]
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

    # ── 1. 查找 "各/各数/每/每注" 分隔符 ──
    sep_m = _SEP_PATTERN.search(text)
    if not sep_m:
        # 无分隔符：尝试末尾金额（旧格式兜底 / 省略「各」的快捷格式「兔10」）
        amount, category_text = _extract_amount(text)
        if amount == 0:
            return ParseResult(region=region,
                success=False,
                error=f"未找到「各/每」分隔符，且无法提取末尾金额: {text}",
            )
    else:
        category_text = text[: sep_m.start()].strip()
        amount_str = text[sep_m.end() :].strip()
        # 去除可选的 "元" 后缀
        amount_str = re.sub(r"元$", "", amount_str).strip()
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

    # ── 2-4. 类别匹配（支持前缀剥离，如「张三 兔」→ 忽略「张三」匹配「兔」）──

    def _try_match(cat: str, amt: float) -> ParseResult | None:
        """尝试所有匹配策略，成功返回 ParseResult，失败返回 None。"""
        # 0. 特殊投注类型处理
        if bet_type_override == "不中":
            # 不中范围: 5-24 或 5至24
            range_m = re.match(r"^(\d{1,2})\s*[-至]\s*(\d{1,2})$", cat)
            if range_m:
                lo, hi = int(range_m.group(1)), int(range_m.group(2))
                if 1 <= lo <= hi <= 49:
                    nums = tuple(range(lo, hi + 1))
                    return ParseResult(region=region,
                        success=True,
                        category="不中",
                        numbers=nums,
                        amount=amt,
                        total=amt * len(nums),
                    )
            return None

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
            groups_inner = _parse_zodiac_groups(zodiac_text)
            if groups_inner:
                all_nums = tuple(sorted({n for _, ns in groups_inner for n in ns}))
                return ParseResult(region=region,
                    success=True,
                    category=f"{kw}肖",
                    numbers=all_nums,
                    amount=amt,
                    total=amt * len(all_nums),
                    zodiac_groups=groups_inner,
                )
            return None  # 连肖关键词后无有效生肖

        # 2b. 「生肖们 + 可选数字 + 连/拖/托/有/友」格式
        tuo_groups = _try_parse_tuo_zodiacs(cat)
        if tuo_groups is not None:
            remaining_inner = cat[_zodiac_consume_len(cat):]
            kw_m = _TUO_TAIL_PATTERN.match(remaining_inner)
            suffix = kw_m.group(2) if kw_m else "连"
            all_nums = tuple(sorted({n for _, ns in tuo_groups for n in ns}))
            return ParseResult(region=region,
                success=True,
                category=f"{suffix}肖",
                numbers=all_nums,
                amount=amt,
                total=amt * len(all_nums),
                zodiac_groups=tuo_groups,
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
                total=amt * len(all_nums),
                zodiac_groups=groups_inner,
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


def parse_lines(text: str) -> list[ParseResult]:
    """解析多行文本，每行独立解析。空行忽略。

    支持一行多单：逗号/中文逗号分隔，且两侧都有「各/每」时才拆分。
    """
    results: list[ParseResult] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 一行多单：兔各10，马各20 → 拆为两单
        sub_lines = [line]
        if "各" in line or "每" in line:
            parts = re.split(r"[，,]", line)
            if len(parts) >= 2 and all(
                re.search(r"(?:各|每)(?:数|注)?", p) for p in parts
            ):
                sub_lines = parts
        for sub in sub_lines:
            sub = sub.strip()
            if sub:
                results.append(parse_order(sub))
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


def format_result(result: ParseResult) -> str:
    """将单条解析结果格式化为输出文本。

    多生肖时每个生肖单独一行；单类别时所有号码一行。
    纯数字类别自动附加反向生肖查询。
    """
    if not result.success:
        return f"[错误] {result.error}"

    amount_display = f"{result.amount:g}" if result.amount != int(result.amount) else f"{int(result.amount)}"
    prefix = f"{result.region}：特码：" if result.region else ""

    groups = result.zodiac_groups
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
