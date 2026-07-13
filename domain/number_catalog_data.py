"""Structured data and derived groups for the static number catalog.

This module is presentation data only.  In particular, the 2026 five-element
reference and the folk classifications below must not be used by settlement.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from domain.color_rules import WAVE_NUMBERS
from domain.zodiac_config import get_zodiac_number_map

ALL_NUMBERS: tuple[int, ...] = tuple(range(1, 50))

WAVE_TEXT_COLORS: dict[str, str] = {
    "红波": "#D93025",
    "蓝波": "#1565C0",
    "绿波": "#138A36",
}

FIVE_ELEMENT_TEXT_COLORS: dict[str, str] = {
    "金": "#B8860B",
    "木": "#228B22",
    "水": "#1565C0",
    "火": "#D93025",
    "土": "#8B7355",
}

# The supplied 2026 static reference differs from domain.color_rules, which is
# already used by order/settlement code.  Keep the distinction explicit.
REFERENCE_FIVE_ELEMENT_NUMBERS_2026: dict[str, tuple[int, ...]] = {
    "金": (4, 5, 12, 13, 26, 27, 34, 35, 42, 43),
    "木": (8, 9, 16, 17, 24, 25, 38, 39, 46, 47),
    "水": (1, 14, 15, 22, 23, 30, 31, 44, 45),
    "火": (2, 3, 10, 11, 18, 19, 32, 33, 40, 41, 48, 49),
    "土": (6, 7, 20, 21, 28, 29, 36, 37),
}

ZODIAC_ATTRIBUTES: tuple[tuple[str, str], ...] = (
    ("家禽", "牛、马、羊、鸡、狗、猪"),
    ("野兽", "鼠、虎、兔、龙、蛇、猴"),
    ("吉美", "兔、龙、蛇、马、羊、鸡"),
    ("凶丑", "鼠、牛、虎、猴、狗、猪"),
    ("阴性", "鼠、龙、蛇、马、狗、猪"),
    ("阳性", "牛、虎、兔、羊、猴、鸡"),
    ("天肖", "兔、马、猴、猪、牛、龙"),
    ("地肖", "蛇、羊、鸡、狗、鼠、虎"),
    ("单笔", "鼠、龙、马、蛇、鸡、猪"),
    ("双笔", "虎、猴、狗、兔、羊、牛"),
    ("白边", "鼠、牛、虎、鸡、狗、猪"),
    ("黑中", "兔、龙、蛇、马、羊、猴"),
    ("日肖", "兔、龙、蛇、马、羊、猴"),
    ("夜肖", "鼠、牛、虎、鸡、狗、猪"),
    ("前肖", "鼠、牛、虎、兔、龙、蛇"),
    ("后肖", "马、羊、猴、鸡、狗、猪"),
    ("大肖", "牛、虎、马、羊、狗、猪"),
    ("小肖", "鼠、兔、龙、蛇、猴、鸡"),
    ("左边肖", "鼠、牛、龙、蛇、猴、鸡"),
    ("右边肖", "虎、兔、马、羊、狗、猪"),
    ("三合", "鼠龙猴、牛蛇鸡、虎马狗、兔羊猪"),
    ("男肖", "鼠、牛、虎、龙、马、猴、狗"),
    ("女肖", "兔、蛇、羊、鸡、猪（五宫肖）"),
    ("六合", "鼠牛、龙鸡、虎猪、蛇猴、兔狗、马羊"),
    ("琴", "兔蛇鸡"),
    ("棋", "鼠牛狗"),
    ("书", "虎龙马"),
    ("画", "羊猴猪"),
    ("五福肖", "鼠、虎、兔、蛇、猴[龙]。"),
)

COLORED_ZODIAC_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("红肖", "马、兔、鼠、鸡", "#D93025"),
    ("蓝肖", "蛇、虎、猪、猴", "#1565C0"),
    ("绿肖", "羊、龙、牛、狗", "#138A36"),
)

FIXED_NUMBER_GROUP_SECTIONS: tuple[
    tuple[str, tuple[tuple[str, tuple[int, ...]], ...]], ...
] = (
    (
        "门数（固定不变）",
        (
            ("1门", tuple(range(1, 10))),
            ("2门", tuple(range(10, 19))),
            ("3门", tuple(range(19, 28))),
            ("4门", tuple(range(28, 38))),
            ("5门", tuple(range(38, 50))),
        ),
    ),
    (
        "段位（固定不变）",
        tuple((f"{index + 1}段", tuple(range(start, start + 7))) for index, start in enumerate(range(1, 50, 7))),
    ),
    (
        "前后落码（静态参考）",
        (
            ("前落码", (1, 2, 3, 4, 5, 6, 7, 8, 17, 18, 19, 20, 21, 22, 23, 24, 33, 34, 35, 36, 37, 38, 39, 40)),
            ("后落码", (9, 10, 11, 12, 13, 14, 15, 16, 25, 26, 27, 28, 29, 30, 31, 32, 41, 42, 43, 44, 45, 46, 47, 48, 49)),
        ),
    ),
    (
        "内外围码（静态参考）",
        (
            ("内围码", (9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 23, 24, 25, 26, 27, 30, 31, 32, 33, 34, 37, 38, 39, 40, 41)),
            ("外围码", (1, 2, 3, 4, 5, 6, 7, 8, 14, 15, 21, 22, 28, 29, 35, 36, 42, 43, 44, 45, 46, 47, 48, 49)),
        ),
    ),
    (
        "楼上楼下码（静态参考）",
        (
            ("楼上码", (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 25, 26, 27, 28)),
            ("楼下码", (22, 23, 24, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49)),
        ),
    ),
    (
        "左右边码（静态参考）",
        (
            ("左边码", (1, 2, 3, 4, 8, 9, 10, 11, 15, 16, 17, 18, 22, 23, 24, 29, 30, 31, 36, 37, 38, 43, 44, 45)),
            ("右边码", (5, 6, 7, 12, 13, 14, 19, 20, 21, 25, 26, 27, 28, 32, 33, 34, 35, 39, 40, 41, 42, 46, 47, 48, 49)),
        ),
    ),
    (
        "高底码（静态参考）",
        (
            ("高码", (1, 4, 7, 9, 10, 12, 17, 18, 19, 25, 26, 27, 28, 29, 30, 34, 35, 36, 37, 39, 44, 45, 47, 48)),
            ("底码", (2, 3, 5, 6, 8, 11, 13, 14, 15, 16, 20, 21, 22, 23, 24, 31, 32, 33, 38, 40, 41, 42, 43, 46, 49)),
        ),
    ),
    (
        "天玄地机码（静态参考）",
        (
            ("天玄码", (1, 4, 7, 9, 10, 11, 14, 17, 19, 20, 21, 24, 27, 29, 30, 31, 34, 37, 39, 40, 41, 44, 47, 49)),
            ("地机码", (2, 3, 5, 6, 8, 12, 13, 15, 16, 18, 22, 23, 25, 26, 28, 32, 33, 35, 36, 38, 42, 43, 45, 46, 48)),
        ),
    ),
)

NINE_STAR_GROUPS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("一白", (47, 10, 22, 45, 8, 20, 44, 19, 6, 18, 30, 5, 17, 28, 3, 15, 14, 13, 24, 48)),
    ("二黑", (11, 10, 9, 33, 45, 20, 32, 44, 19, 18, 5, 17, 29, 4, 40, 27, 2, 26, 13, 25, 48)),
    ("三碧", (35, 10, 46, 21, 20, 44, 19, 6, 18, 5, 29, 41, 4, 15, 2, 14, 38, 13, 25, 12, 24, 48)),
    ("四绿", (23, 35, 10, 22, 34, 33, 45, 8, 20, 44, 19, 43, 6, 18, 5, 41, 4, 3, 39, 2, 26, 38, 13, 25, 12)),
    ("五黄", (11, 35, 10, 33, 20, 44, 7, 31, 43, 6, 18, 42, 41, 40, 3, 39, 2, 49, 24)),
    ("六白", (23, 35, 10, 33, 8, 20, 7, 6, 5, 17, 4, 28, 40, 3, 15, 27, 2, 26, 38, 1, 37, 12, 24)),
    ("七赤", (23, 35, 10, 34, 46, 9, 32, 43, 42, 5, 17, 29, 40, 3, 27, 38, 13, 25, 37, 24, 36)),
    ("八白", (23, 47, 10, 9, 8, 44, 7, 31, 18, 30, 17, 41, 4, 40, 3, 15, 27, 26, 1, 37, 48)),
    ("九紫", (11, 23, 35, 47, 22, 33, 44, 19, 18, 42, 17, 4, 40, 3, 27, 14, 26, 1, 13, 12, 24)),
)

REFERENCE_TEXT_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "生肖的五行属性",
        ("【金肖】猴鸡  【木肖】虎兔  【水肖】鼠猪  【火肖】蛇马  【土肖】牛羊龙狗",),
    ),
    (
        "生肖身份分类",
        ("两大君王：龙 虎", "两大恶人：鼠 猴", "四大美女：兔 蛇 羊 鸡", "四大家臣：牛 马 猪 狗"),
    ),
    (
        "月份（民间参考）",
        (
            "01月；鼠，羊，虎，蛇。 02月；牛，马，兔，鼠。",
            "03月；虎，蛇，龙，牛。 04月；兔，龙，蛇，猴。",
            "05月；龙，兔，马，兔。 06月；蛇，虎，羊，狗。",
            "07月；马，牛，猴，猪。 08月；羊，鼠，鸡，马。",
            "09月；猴，猪，狗，羊。 10月；鸡，狗，猪，虎。",
            "11月；狗，鸡，鼠，鸡。 12月；猪，猴，牛，龙。",
        ),
    ),
    (
        "一年四季生肖所在的位置（民间参考）",
        (
            "春天生肖（东方31---------42）：兔、虎、龙。",
            "夏天生肖（南方19---------30）：马、蛇、羊。",
            "秋天生肖（西方07---------18）：鸡、猴、狗。",
            "冬天生肖（北方01-06. 43-49）：鼠、猪、牛。",
            "虎，兔，[龙]。。。。春。。。东方。。。木。。青色",
            "蛇，马，[羊]。。。。夏。。。南方。。。火。。赤色",
            "猴，鸡，[狗]。。。。秋。。。西方。。。金。。白色",
            "猪，鼠，[牛]。。。。冬。。。北方。。。水。。黑色",
            "龙 [立春]，羊 [立夏]，狗 [立秋]，牛 [立东]",
            "。。。中央。。。土。。黄色",
        ),
    ),
    ("方位的生肖排位（民间参考）", ("东：虎，兔，龙。", "南：马，蛇，羊。", "西：鸡，猴，狗。", "北：鼠，猪，牛。")),
    (
        "民间十二生肖所属时间",
        (
            "01.鼠 04岁（23---01时，三更）",
            "02.牛 03岁（01---03时，四更）",
            "03.虎 02岁（03---05时，五更）",
            "04.兔 01岁（05---07时，六更）",
            "05.龙 12岁（07---09时，七更）",
            "06.蛇 11岁（09---11时，八更）",
            "07.马 10岁（11---13时，九更）",
            "08.羊 09岁（13---15时，10更）",
            "09.猴 08岁（15---17时，11更）",
            "10.鸡 07岁（17---19时，12更）",
            "11.狗 06岁（19---21时，一更）",
            "12.猪 05岁（21---23时，二更）",
        ),
    ),
    (
        "八卦的生肖排位（民间参考）",
        ("乾（离）马兔;", "巽（坤）羊猴;", "坎（兑）鸡;", "艮（乾）狗猪;", "坤（坎）鼠;", "震（艮）牛虎，", "离（震）兔，", "兑（巽）龙蛇。"),
    ),
    (
        "六合地基 / 天干（民间参考）",
        (
            "六合地基:正月虎;二月兔;三月龙;四月蛇;五月马;六月羊;",
            "六合天干:正月狗;二月猪;三月鼠;四月牛;五月虎;六月兔;",
            "六合地基:七月猴;八月鸡;九月狗;十月猪;十一月鼠;十二月牛.",
            "六合天干:七月龙;八月马;九月蛇;十月羊;十一月猴;十二月鸡.",
        ),
    ),
    (
        "五行之间的关系（静态参考）",
        (
            "相生：木生火、火生土、土生金、金生水、水生木",
            "相克：木克土、土克水、水克火、火克金、金克木",
            "五行规律：金生水--克木 水生木--克火 木生火--克土 火生土--克金 土生金--克水",
        ),
    ),
)


def half_wave_groups() -> dict[str, tuple[int, ...]]:
    groups: dict[str, tuple[int, ...]] = {}
    for wave_name in ("红波", "蓝波", "绿波"):
        prefix = wave_name.removesuffix("波")
        numbers = WAVE_NUMBERS[wave_name]
        groups[f"{prefix}双"] = tuple(number for number in ALL_NUMBERS if number in numbers and number % 2 == 0)
        groups[f"{prefix}单"] = tuple(number for number in ALL_NUMBERS if number in numbers and number % 2 == 1)
    return groups


def sum_parity_groups() -> dict[str, tuple[int, ...]]:
    return {
        "合数单": tuple(number for number in ALL_NUMBERS if digit_sum(number) % 2 == 1),
        "合数双": tuple(number for number in ALL_NUMBERS if digit_sum(number) % 2 == 0),
    }


def size_groups() -> dict[str, tuple[int, ...]]:
    return {"小": tuple(range(1, 25)), "大": tuple(range(25, 50))}


def middle_edge_groups() -> dict[str, tuple[int, ...]]:
    return {"中数": tuple(range(13, 38)), "边数": tuple(range(1, 13)) + tuple(range(38, 50))}


def digit_sum_groups() -> dict[str, tuple[int, ...]]:
    return {f"{total:02d}合": tuple(number for number in ALL_NUMBERS if digit_sum(number) == total) for total in range(1, 14)}


def head_groups() -> dict[str, tuple[int, ...]]:
    return {f"{head}头": tuple(number for number in ALL_NUMBERS if number // 10 == head) for head in range(5)}


def composite_size_reference_groups() -> dict[str, tuple[int, ...]]:
    """Return the supplied static-reference split (direct digit sum, not digit root)."""
    return {
        "合小": tuple(number for number in ALL_NUMBERS if digit_sum(number) <= 6),
        "合大": tuple(number for number in ALL_NUMBERS if digit_sum(number) >= 7),
    }


def tail_size_groups() -> dict[str, tuple[int, ...]]:
    return {
        "尾小": tuple(number for number in ALL_NUMBERS if number % 10 <= 4),
        "尾大": tuple(number for number in ALL_NUMBERS if number % 10 >= 5),
    }


def size_parity_groups() -> dict[str, tuple[int, ...]]:
    return {
        f"{size}{parity}": tuple(
            number
            for number in ALL_NUMBERS
            if (number < 25) == (size == "小") and (number % 2 == 1) == (parity == "单")
        )
        for size in ("小", "大")
        for parity in ("单", "双")
    }


def sum_tail_groups() -> dict[str, tuple[int, ...]]:
    return {f"{tail}合尾": tuple(number for number in ALL_NUMBERS if digit_sum(number) % 10 == tail) for tail in range(10)}


def head_parity_groups() -> dict[str, tuple[int, ...]]:
    return {
        f"{head}头{parity}": tuple(
            number for number in ALL_NUMBERS if number // 10 == head and (number % 2 == 1) == (parity == "单")
        )
        for parity in ("单", "双")
        for head in range(5)
    }


def modulo_groups(modulus: int) -> dict[str, tuple[int, ...]]:
    if modulus < 2:
        raise ValueError("模数必须大于或等于 2")
    return {f"{modulus}余{remainder}": tuple(number for number in ALL_NUMBERS if number % modulus == remainder) for remainder in range(modulus)}


def digit_sum(number: int) -> int:
    return number // 10 + number % 10


def validate_number_group(name: str, numbers: Iterable[int]) -> tuple[int, ...]:
    values = tuple(numbers)
    invalid = sorted({number for number in values if not isinstance(number, int) or not 1 <= number <= 49}, key=str)
    if invalid:
        raise ValueError(f"{name} 包含超出 01-49 的号码：{invalid}")
    duplicates = sorted(number for number in set(values) if values.count(number) > 1)
    if duplicates:
        raise ValueError(f"{name} 包含重复号码：{duplicates}")
    return values


def validate_partition(name: str, groups: Mapping[str, Iterable[int]]) -> None:
    seen: dict[int, str] = {}
    for group_name, numbers in groups.items():
        for number in validate_number_group(f"{name}/{group_name}", numbers):
            if number in seen:
                raise ValueError(f"{name} 的号码 {number:02d} 同时出现在 {seen[number]} 和 {group_name}")
            seen[number] = group_name
    missing = sorted(set(ALL_NUMBERS) - set(seen))
    if missing:
        rendered = "、".join(f"{number:02d}" for number in missing)
        raise ValueError(f"{name} 未覆盖号码：{rendered}")


def validate_catalog_data(year: int = 2026) -> None:
    zodiac = {name: tuple(int(number) for number in numbers) for name, numbers in get_zodiac_number_map(year).items()}
    validate_partition(f"{year}生肖", zodiac)
    validate_partition("波色", WAVE_NUMBERS)
    validate_partition("2026静态参考五行", REFERENCE_FIVE_ELEMENT_NUMBERS_2026)
    validate_partition("半波", half_wave_groups())
    validate_partition("合数单双", sum_parity_groups())
    validate_partition("大小", size_groups())
    validate_partition("中边数", middle_edge_groups())
    validate_partition("合数", digit_sum_groups())
    validate_partition("头数", head_groups())
    validate_partition("合大合小静态参考", composite_size_reference_groups())
    validate_partition("尾大尾小", tail_size_groups())
    validate_partition("半单双", size_parity_groups())
    validate_partition("合尾", sum_tail_groups())
    validate_partition("头数单双", head_parity_groups())
    for modulus in range(3, 8):
        validate_partition(f"模{modulus}数", modulo_groups(modulus))
    for title, groups in FIXED_NUMBER_GROUP_SECTIONS:
        validate_partition(title, dict(groups))
    for name, numbers in NINE_STAR_GROUPS:
        validate_number_group(f"九星/{name}", numbers)


validate_catalog_data()
