"""Display-only formatting for record-order intake parse results."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


_SPECIAL_DISPLAY_CATEGORIES = {
    "特码号码",
    "特码生肖",
    "特码波色",
    "特码半波",
    "特码大小",
    "特码单双",
    "特码尾数",
    "特码头数",
    "特码合数单双",
    "特码合数大小",
    "特码五行",
    "单号投注",
    "纯数字",
    "多生肖",
}

_DIRECT_SPECIAL_SELECTIONS = {
    "红波",
    "蓝波",
    "绿波",
    "红单",
    "红双",
    "蓝单",
    "蓝双",
    "绿单",
    "绿双",
    "大",
    "小",
    "单",
    "双",
    "合单",
    "合双",
    "合大",
    "合小",
    "金",
    "木",
    "水",
    "火",
    "土",
    "全包",
}

_ZODIAC_NAMES = {"鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"}


@dataclass(frozen=True, slots=True)
class OrderIntakeDisplayItem:
    """Small DTO for testing and non-parser callers of the display formatter."""

    region: str | None
    bet_type: str
    selection: str
    amount: Decimal | int | float | str | None
    original_text: str = ""
    error: str | None = None
    warning: str | None = None


def normalize_display_region(region: str | None, default_region: str | None = None) -> str:
    raw = (region or default_region or "澳门").strip()
    lowered = raw.lower().replace(" ", "")
    if lowered in {"macau", "macao"} or raw in {"澳门", "澳"}:
        return "澳门"
    if lowered in {"hongkong", "hk"} or raw in {"香港", "港"}:
        return "香港"
    return raw or "澳门"


def simplify_display_bet_type(bet_type: str | None) -> str:
    raw = (bet_type or "特码").strip()
    if raw in _SPECIAL_DISPLAY_CATEGORIES:
        return "特码"
    if raw in _DIRECT_SPECIAL_SELECTIONS:
        return "特码"
    if raw in _ZODIAC_NAMES:
        return "特码"
    if re.fullmatch(r"尾\d", raw) or re.fullmatch(r"\d头", raw):
        return "特码"
    return raw or "特码"


def format_display_amount(amount: Decimal | int | float | str | None) -> str:
    if amount is None:
        return "0"
    try:
        decimal = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return str(amount).strip()
    if decimal == decimal.to_integral_value():
        return str(int(decimal))
    return format(decimal.normalize(), "f")


def _split_selection(selection: str) -> list[str]:
    compact = selection.strip()
    if not compact:
        return []
    compact = re.sub(r"\s+", " ", compact)
    parts = re.split(r"[-,，、./|+]+|\s+", compact)
    return [part.strip() for part in parts if part.strip()]


def format_display_selection(selection: str | None) -> str:
    raw = (selection or "").strip()
    if not raw:
        return ""
    return "-".join(_split_selection(raw)) or raw


def _format_line(region: str | None, bet_type: str | None, selection: str, amount: Any) -> str:
    display_region = normalize_display_region(region)
    display_bet_type = simplify_display_bet_type(bet_type)
    display_selection = format_display_selection(selection)
    display_amount = format_display_amount(amount)
    return f"{display_region}: {display_bet_type}: {display_selection} 各数 {display_amount}"


def _source_text(item: Any) -> str:
    return (
        str(getattr(item, "original_text", "") or "")
        or str(getattr(item, "source_line", "") or "")
        or str(getattr(item, "selection", "") or "")
    ).strip()


def _should_show_unsupported(warning: str | None) -> bool:
    text = (warning or "").strip().lower()
    return bool(text and ("不支持" in text or "暂不支持" in text or "unsupported" in text))


def format_display_item(item: OrderIntakeDisplayItem, default_region: str | None = None) -> str:
    if item.error:
        raw = item.original_text or item.selection
        return f"无法识别: {raw}，原因：{item.error}"

    line = _format_line(
        normalize_display_region(item.region, default_region),
        item.bet_type,
        item.selection,
        item.amount,
    )
    if _should_show_unsupported(item.warning):
        return f"不支持结算: {line}，原因：{item.warning}"
    return line


def format_intake_item(item: Any, default_region: str | None = None) -> str:
    if getattr(item, "error", None):
        return f"无法识别: {_source_text(item)}，原因：{getattr(item, 'error')}"

    selection = (
        getattr(item, "order_selection", None)
        or getattr(item, "normalized_selection", None)
        or getattr(item, "original_selection", None)
        or ""
    )
    bet_type = (
        getattr(item, "order_bet_type", None)
        or getattr(item, "normalized_bet_type", None)
        or getattr(item, "original_bet_type", None)
        or "特码"
    )
    line = _format_line(default_region, bet_type, str(selection), getattr(item, "amount", None))
    warning = getattr(item, "warning", None)
    if _should_show_unsupported(warning):
        return f"不支持结算: {line}，原因：{warning}"
    return line


def _amount_marker_prefix(text: str, category: str) -> str:
    if category == "单号投注" and "/" in text:
        return text.split("/", 1)[0]
    match = re.search(r"(?:各组|各数|各号|每注|每数|各|每|打|买)", text)
    return text[: match.start()] if match else text


def _number_selection_from_result(result: Any) -> str:
    numbers = tuple(getattr(result, "numbers", ()) or ())
    source = str(getattr(result, "original_text", "") or getattr(result, "normalized_text", "") or "")
    prefix = _amount_marker_prefix(source, str(getattr(result, "category", "") or ""))
    tokens = re.findall(r"\d{1,2}", prefix)
    if len(tokens) >= len(numbers) and numbers:
        return "-".join(tokens[: len(numbers)])
    if len(numbers) == 1:
        return str(numbers[0])
    return "-".join(f"{int(number):02d}" for number in numbers)


def _selection_from_parse_result(result: Any) -> str:
    lianma_groups = tuple(getattr(result, "lianma_groups", ()) or ())
    if lianma_groups:
        return "-".join(
            "(" + "-".join(f"{int(number):02d}" for number in group) + ")"
            for group in lianma_groups
        )
    pingwei_tails = tuple(getattr(result, "pingwei_tails", ()) or ())
    if pingwei_tails:
        return "-".join(f"{int(tail)}尾" for tail in pingwei_tails)
    groups = list(getattr(result, "zodiac_groups", []) or [])
    if groups:
        return "-".join(str(name) for name, _numbers in groups)

    category = str(getattr(result, "category", "") or "")
    numbers = tuple(getattr(result, "numbers", ()) or ())
    if category in {"单号投注", "纯数字"} and numbers:
        return _number_selection_from_result(result)
    if numbers and not category:
        return _number_selection_from_result(result)
    return category or _number_selection_from_result(result)


def format_parse_result(result: Any, default_region: str | None = None) -> str:
    if not getattr(result, "success", False):
        raw = _source_text(result)
        reason = str(getattr(result, "error", "") or "未说明")
        return f"无法识别: {raw}，原因：{reason}"

    region = normalize_display_region(getattr(result, "region", None), default_region)
    category = str(getattr(result, "category", None) or "特码")
    selection = _selection_from_parse_result(result)
    amount = format_display_amount(getattr(result, "amount", None))
    total = format_display_amount(getattr(result, "total", None))
    lianma_groups = tuple(getattr(result, "lianma_groups", ()) or ())
    if lianma_groups:
        line = (
            f"{region}: {category}: {selection} "
            f"每组 {amount}，组合数 {len(lianma_groups)}，合计 {total}"
        )
    elif category == "四肖":
        line = f"{region}: 四肖: {selection} 整组 {amount}，合计 {total}"
    elif re.fullmatch(r"(?:[大小])?[红蓝绿][单双]", category):
        line = (
            f"{region}: {category}: {format_display_selection(selection)} "
            f"每号 {amount}，号码数 {len(tuple(getattr(result, 'numbers', ()) or ())) }，合计 {total}"
        )
    else:
        line = _format_line(region, category, selection, amount)
    warnings = list(getattr(result, "warnings", []) or [])
    unsupported = next((warning for warning in warnings if _should_show_unsupported(warning)), None)
    if unsupported:
        return f"不支持结算: {line}，原因：{unsupported}"
    return line


def format_parse_results(results: list[Any], default_region: str | None = None) -> list[str]:
    return [format_parse_result(result, default_region=default_region) for result in results]
