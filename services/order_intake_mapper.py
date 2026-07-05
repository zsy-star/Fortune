"""Map order_parser.ParseResult into OrderCreate-oriented intake previews."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from domain.bet_types import REGION_MACAU, normalize_bet_type, normalize_region
from domain.exceptions import InvalidBetTypeError, InvalidNumberError, InvalidRegionError
from domain.number_rules import normalize_number
from domain.zodiac_config import get_default_zodiac_year, get_zodiac_number_map
from schemas.order_intake_schema import IntakeItemPreview
from schemas.order_schema import OrderItemCreate
from services.order_parser import ParseResult
from settlement.bet_normalizer import BetTypeNormalizer
from settlement.exceptions import InvalidSelectionError, UnsupportedBetTypeError

_SINGLE_ITEM_CATEGORIES: dict[str, tuple[str, str]] = {
    "红波": ("特码波色", "红波"),
    "蓝波": ("特码波色", "蓝波"),
    "绿波": ("特码波色", "绿波"),
    "红单": ("包半波", "红单"),
    "红双": ("包半波", "红双"),
    "蓝单": ("包半波", "蓝单"),
    "蓝双": ("包半波", "蓝双"),
    "绿单": ("包半波", "绿单"),
    "绿双": ("包半波", "绿双"),
    "大": ("特码两面", "大"),
    "小": ("特码两面", "小"),
    "单": ("特码两面", "单"),
    "双": ("特码两面", "双"),
}

_EXPAND_NUMBER_CATEGORIES = frozenset({"单号投注", "纯数字"})
_ZODIAC_NAMES = frozenset(get_zodiac_number_map(get_default_zodiac_year()))
_ELEMENTS = frozenset({"金", "木", "水", "火", "土"})
_SUM_LABELS = frozenset({"合单", "合双", "合大", "合小"})
_TAIL_PATTERN = re.compile(r"^尾[0-9]$")
_HEAD_PATTERN = re.compile(r"^[0-4]头$")
_UNSUPPORTED_SAVE_CATEGORIES = frozenset({"全包"})
_LIANMA_CATEGORIES = frozenset({"二中二", "三中三", "三中二"})
_UNSUPPORTED_SETTLEMENT_GROUP_CATEGORIES = frozenset({"二中特", "特串"})


class IntakeConversionError(Exception):
    """Raised when intake conversion cannot proceed."""


class RegionConflictError(IntakeConversionError):
    """Text region disagrees with caller-supplied region."""


def to_decimal_amount(value: float | int | str | Decimal) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise IntakeConversionError(f"非法金额：{value!r}") from None
    if not amount.is_finite():
        raise IntakeConversionError(f"非法金额：{value!r}")
    if amount <= 0:
        raise IntakeConversionError(f"金额必须大于 0：{amount}")
    return amount


def resolve_region(
    *,
    text_region: str,
    param_region: str | None,
    default_region: str = REGION_MACAU,
) -> str:
    normalized_param = normalize_region(param_region) if param_region else None
    normalized_text = normalize_region(text_region) if text_region else None

    if normalized_text and normalized_param and normalized_text != normalized_param:
        raise RegionConflictError(
            f"文本地区 {normalized_text} 与参数地区 {normalized_param} 不一致"
        )
    if normalized_text:
        return normalized_text
    if normalized_param:
        return normalized_param
    return normalize_region(default_region)


def _is_single_zodiac(result: ParseResult) -> bool:
    if result.category not in _ZODIAC_NAMES:
        return False
    if len(result.zodiac_groups) == 1:
        return result.category == result.zodiac_groups[0][0]
    return not result.category.endswith("肖")


def _is_lianxiao_category(result: ParseResult) -> bool:
    if getattr(result, "zodiac_number_mode", False):
        return False
    if result.category == "多生肖":
        return True
    if result.category.endswith("肖") and not _is_single_zodiac(result):
        return True
    return False


def _is_expand_category(category: str) -> bool:
    if category in _EXPAND_NUMBER_CATEGORIES:
        return True
    if category in _ZODIAC_NAMES:
        return True
    if category in _ELEMENTS or category in _SUM_LABELS:
        return True
    if _TAIL_PATTERN.fullmatch(category) or _HEAD_PATTERN.fullmatch(category):
        return True
    return False


def _normalize_preview_fields(
    normalizer: BetTypeNormalizer,
    preview_bet_type: str,
    selection: str,
) -> tuple[str | None, str | None, str | None]:
    try:
        normalized = normalizer.normalize(preview_bet_type, selection)
        return normalized.normalized_bet_type, normalized.selection, None
    except UnsupportedBetTypeError:
        return None, None, None
    except InvalidSelectionError as exc:
        return None, None, str(exc)


def _build_item_preview(
    *,
    source_line: str,
    original_bet_type: str,
    original_selection: str,
    amount: Decimal | None,
    order_bet_type: str | None,
    order_selection: str | None,
    normalizer: BetTypeNormalizer,
    preview_bet_type: str | None = None,
    preview_selection: str | None = None,
    warning: str | None = None,
    error: str | None = None,
) -> IntakeItemPreview:
    normalized_bet_type: str | None = None
    normalized_selection: str | None = None
    if order_bet_type and order_selection and error is None:
        norm_type = preview_bet_type or order_bet_type
        norm_selection = preview_selection or order_selection
        normalized_bet_type, normalized_selection, norm_error = _normalize_preview_fields(
            normalizer, norm_type, norm_selection
        )
        if norm_error:
            error = norm_error
            order_bet_type = None
            order_selection = None

    is_valid = error is None and order_bet_type is not None and order_selection is not None and amount is not None
    return IntakeItemPreview(
        source_line=source_line,
        original_bet_type=original_bet_type,
        normalized_bet_type=normalized_bet_type,
        original_selection=original_selection,
        normalized_selection=normalized_selection,
        amount=amount,
        is_valid=is_valid,
        warning=warning,
        error=error,
        order_bet_type=order_bet_type,
        order_selection=order_selection,
    )


def _format_lianma_selection(groups: tuple[tuple[int, ...], ...]) -> str:
    return "-".join("(" + "-".join(f"{number:02d}" for number in group) + ")" for group in groups)


def convert_parse_result(
    result: ParseResult,
    source_line: str,
    *,
    normalizer: BetTypeNormalizer | None = None,
) -> tuple[list[IntakeItemPreview], list[OrderItemCreate], list[str], list[str]]:
    normalizer = normalizer or BetTypeNormalizer()
    warnings: list[str] = list(getattr(result, "warnings", []) or [])
    errors: list[str] = []
    previews: list[IntakeItemPreview] = []
    order_items: list[OrderItemCreate] = []

    if not result.success:
        message = result.error or "解析失败"
        previews.append(
            IntakeItemPreview(
                source_line=source_line,
                original_bet_type="",
                normalized_bet_type=None,
                original_selection=source_line,
                normalized_selection=None,
                amount=None,
                is_valid=False,
                error=message,
            )
        )
        errors.append(message)
        return previews, order_items, warnings, errors

    try:
        per_amount = to_decimal_amount(result.amount)
        expected_total = to_decimal_amount(result.total)
    except IntakeConversionError as exc:
        previews.append(
            IntakeItemPreview(
                source_line=source_line,
                original_bet_type=result.category,
                normalized_bet_type=None,
                original_selection=source_line,
                normalized_selection=None,
                amount=None,
                is_valid=False,
                error=str(exc),
            )
        )
        errors.append(str(exc))
        return previews, order_items, warnings, errors

    category = result.category

    if category in _UNSUPPORTED_SETTLEMENT_GROUP_CATEGORIES:
        selection = ",".join(f"{number:02d}" for number in result.numbers)
        warning = f"玩法「{category}」可保存，但当前结算预览暂不支持"
        warnings.append(warning)
        try:
            normalize_bet_type(category)
        except InvalidBetTypeError as exc:
            message = str(exc)
            previews.append(
                _build_item_preview(
                    source_line=source_line,
                    original_bet_type=category,
                    original_selection=selection,
                    amount=expected_total,
                    order_bet_type=None,
                    order_selection=None,
                    normalizer=normalizer,
                    warning=warning,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        preview = _build_item_preview(
            source_line=source_line,
            original_bet_type=category,
            original_selection=selection,
            amount=expected_total,
            order_bet_type=category,
            order_selection=selection,
            normalizer=normalizer,
            warning=warning,
        )
        previews.append(preview)
        if preview.is_valid:
            order_items.append(
                OrderItemCreate(
                    bet_type=category,
                    selection=selection,
                    amount=expected_total,
                    note=(result.note or "结算规则待确认"),
                )
            )
        else:
            errors.append(preview.error or f"{category}映射失败")
        return previews, order_items, warnings, errors

    if category in _UNSUPPORTED_SAVE_CATEGORIES:
        message = f"玩法「{category}」当前无法保存到订单系统"
        previews.append(
            IntakeItemPreview(
                source_line=source_line,
                original_bet_type=category,
                normalized_bet_type=None,
                original_selection=",".join(f"{n:02d}" for n in result.numbers),
                normalized_selection=None,
                amount=expected_total,
                is_valid=False,
                error=message,
            )
        )
        errors.append(message)
        return previews, order_items, warnings, errors

    if category in _SINGLE_ITEM_CATEGORIES:
        bet_type, selection = _SINGLE_ITEM_CATEGORIES[category]
        try:
            normalize_bet_type(bet_type)
        except InvalidBetTypeError as exc:
            message = str(exc)
            previews.append(
                _build_item_preview(
                    source_line=source_line,
                    original_bet_type=category,
                    original_selection=selection,
                    amount=expected_total,
                    order_bet_type=None,
                    order_selection=None,
                    normalizer=normalizer,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        preview = _build_item_preview(
            source_line=source_line,
            original_bet_type=category,
            original_selection=selection,
            amount=expected_total,
            order_bet_type=bet_type,
            order_selection=selection,
            preview_bet_type=category,
            normalizer=normalizer,
        )
        previews.append(preview)
        if preview.is_valid:
            order_items.append(
                OrderItemCreate(bet_type=bet_type, selection=selection, amount=expected_total)
            )
        else:
            errors.append(preview.error or "类别映射失败")
        return previews, order_items, warnings, errors

    if category == "平特一肖" and result.zodiac_groups:
        selection = ",".join(name for name, _ in result.zodiac_groups)
        try:
            normalize_bet_type("平特一肖")
        except InvalidBetTypeError as exc:
            message = str(exc)
            previews.append(
                _build_item_preview(
                    source_line=source_line,
                    original_bet_type=category,
                    original_selection=selection,
                    amount=expected_total,
                    order_bet_type=None,
                    order_selection=None,
                    normalizer=normalizer,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        preview = _build_item_preview(
            source_line=source_line,
            original_bet_type=category,
            original_selection=selection,
            amount=expected_total,
            order_bet_type="平特一肖",
            order_selection=selection,
            preview_bet_type=category,
            normalizer=normalizer,
        )
        previews.append(preview)
        if preview.is_valid:
            order_items.append(
                OrderItemCreate(bet_type="平特一肖", selection=selection, amount=expected_total)
            )
        else:
            errors.append(preview.error or "平特一肖映射失败")
        return previews, order_items, warnings, errors

    if category == "N不中":
        selection = ",".join(f"{number:02d}" for number in result.numbers)
        try:
            normalize_bet_type("N不中")
        except InvalidBetTypeError as exc:
            message = str(exc)
            previews.append(
                _build_item_preview(
                    source_line=source_line,
                    original_bet_type=category,
                    original_selection=selection,
                    amount=expected_total,
                    order_bet_type=None,
                    order_selection=None,
                    normalizer=normalizer,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        preview = _build_item_preview(
            source_line=source_line,
            original_bet_type=category,
            original_selection=selection,
            amount=expected_total,
            order_bet_type="N不中",
            order_selection=selection,
            normalizer=normalizer,
        )
        previews.append(preview)
        if preview.is_valid:
            order_items.append(
                OrderItemCreate(bet_type="N不中", selection=selection, amount=expected_total)
            )
        else:
            errors.append(preview.error or "N不中映射失败")
        return previews, order_items, warnings, errors

    if category == "平尾":
        warning = None
        tails = result.pingwei_tails or result.numbers
        selection = ",".join(str(tail) for tail in tails)
        note = f"平尾尾数个数={len(tails)}" if tails else None
        try:
            normalize_bet_type("平尾")
        except InvalidBetTypeError as exc:
            message = str(exc)
            previews.append(
                _build_item_preview(
                    source_line=source_line,
                    original_bet_type=category,
                    original_selection=selection,
                    amount=expected_total,
                    order_bet_type=None,
                    order_selection=None,
                    normalizer=normalizer,
                    warning=warning,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        preview = _build_item_preview(
            source_line=source_line,
            original_bet_type=category,
            original_selection=selection,
            amount=expected_total,
            order_bet_type="平尾",
            order_selection=selection,
            normalizer=normalizer,
            warning=warning,
        )
        previews.append(preview)
        if preview.is_valid:
            order_items.append(
                OrderItemCreate(
                    bet_type="平尾",
                    selection=selection,
                    amount=expected_total,
                    note=note,
                )
            )
        else:
            errors.append(preview.error or "平尾映射失败")
        return previews, order_items, warnings, errors

    if category in _LIANMA_CATEGORIES:
        warning = None
        groups = result.lianma_groups
        selection = _format_lianma_selection(groups) if groups else ",".join(f"{number:02d}" for number in result.numbers)
        group_size = len(groups[0]) if groups else 0
        is_drag_group = category == "二中二" and ("拖" in source_line or "/" in source_line)
        note_prefix = "拖式组合数" if is_drag_group else "连码组合数"
        note = f"{note_prefix}={len(groups)};连码组大小={group_size}" if groups else None
        try:
            normalize_bet_type(category)
        except InvalidBetTypeError as exc:
            message = str(exc)
            previews.append(
                _build_item_preview(
                    source_line=source_line,
                    original_bet_type=category,
                    original_selection=selection,
                    amount=expected_total,
                    order_bet_type=None,
                    order_selection=None,
                    normalizer=normalizer,
                    warning=warning,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        preview = _build_item_preview(
            source_line=source_line,
            original_bet_type=category,
            original_selection=selection,
            amount=expected_total,
            order_bet_type=category,
            order_selection=selection,
            normalizer=normalizer,
            warning=warning,
        )
        previews.append(preview)
        if preview.is_valid:
            order_items.append(
                OrderItemCreate(
                    bet_type=category,
                    selection=selection,
                    amount=expected_total,
                    note=note,
                )
            )
        else:
            errors.append(preview.error or f"{category}映射失败")
        return previews, order_items, warnings, errors

    if category in {"几中几复选", "连肖复选"}:
        warning = "复选类玩法可保存，但正式结算规则待确认" if category == "连肖复选" else None
        if warning:
            warnings.append(warning)
        if category == "连肖复选":
            selection = ",".join(name for name, _ in result.zodiac_groups)
        else:
            selection = ",".join(f"{number:02d}" for number in result.numbers)
        fuxuan_notes: list[str] = []
        if result.fuxuan_type:
            fuxuan_notes.append(f"复选类型={result.fuxuan_type}")
        if result.fushi_lian_sizes:
            combo_count = int(Decimal(str(result.total)) / Decimal(str(result.amount))) if Decimal(str(result.amount)) else 0
            fuxuan_notes.append(
                "复试连数="
                + ",".join(str(size) for size in result.fushi_lian_sizes)
                + f";组合数={combo_count}"
            )
        if result.note:
            fuxuan_notes.append(result.note)
        fuxuan_note = ";".join(dict.fromkeys(fuxuan_notes)) or None
        try:
            normalize_bet_type(category)
        except InvalidBetTypeError as exc:
            message = str(exc)
            previews.append(
                _build_item_preview(
                    source_line=source_line,
                    original_bet_type=category,
                    original_selection=selection,
                    amount=expected_total,
                    order_bet_type=None,
                    order_selection=None,
                    normalizer=normalizer,
                    warning=warning,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        preview = _build_item_preview(
            source_line=source_line,
            original_bet_type=category,
            original_selection=selection,
            amount=expected_total,
            order_bet_type=category,
            order_selection=selection,
            normalizer=normalizer,
            preview_selection=f"{result.fuxuan_type}|{selection}" if category == "几中几复选" and result.fuxuan_type else None,
            warning=warning,
        )
        previews.append(preview)
        if preview.is_valid:
            order_items.append(
                OrderItemCreate(
                    bet_type=category,
                    selection=selection,
                    amount=expected_total,
                    note=fuxuan_note,
                )
            )
        else:
            errors.append(preview.error or f"{category}映射失败")
        return previews, order_items, warnings, errors

    if _is_lianxiao_category(result):
        warning = "连肖按整组金额保存，当前结算仍为简化口径"
        warnings.append(warning)
        selection = ",".join(name for name, _ in result.zodiac_groups)
        if not selection:
            selection = category
        try:
            normalize_bet_type("连肖")
        except InvalidBetTypeError as exc:
            message = str(exc)
            previews.append(
                _build_item_preview(
                    source_line=source_line,
                    original_bet_type=category,
                    original_selection=selection,
                    amount=expected_total,
                    order_bet_type=None,
                    order_selection=None,
                    normalizer=normalizer,
                    warning=warning,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        preview = _build_item_preview(
            source_line=source_line,
            original_bet_type=category,
            original_selection=selection,
            amount=expected_total,
            order_bet_type="连肖",
            order_selection=selection,
            preview_bet_type=category,
            normalizer=normalizer,
            warning=warning,
        )
        previews.append(preview)
        if preview.is_valid:
            order_items.append(
                OrderItemCreate(bet_type="连肖", selection=selection, amount=expected_total)
            )
        else:
            errors.append(preview.error or "连肖映射失败")
        return previews, order_items, warnings, errors

    if _is_expand_category(category) or _is_single_zodiac(result) or getattr(result, "zodiac_number_mode", False):
        numbers = result.numbers
        if not numbers:
            message = f"类别「{category}」未展开出有效号码"
            previews.append(
                IntakeItemPreview(
                    source_line=source_line,
                    original_bet_type=category,
                    normalized_bet_type=None,
                    original_selection="",
                    normalized_selection=None,
                    amount=None,
                    is_valid=False,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        original_selection = ",".join(f"{n:02d}" for n in numbers)
        computed_total = per_amount * len(numbers)
        if computed_total != expected_total:
            message = (
                f"金额不一致：解析器 total={expected_total}，"
                f"按每号 {per_amount} × {len(numbers)} 计算为 {computed_total}"
            )
            previews.append(
                IntakeItemPreview(
                    source_line=source_line,
                    original_bet_type=category,
                    normalized_bet_type=None,
                    original_selection=original_selection,
                    normalized_selection=None,
                    amount=expected_total,
                    is_valid=False,
                    error=message,
                )
            )
            errors.append(message)
            return previews, order_items, warnings, errors

        line_warning: str | None = None
        if category not in _EXPAND_NUMBER_CATEGORIES:
            line_warning = f"玩法「{category}」按号码展开保存为特码，结算预览按特码号码判定"

        is_single_zodiac_line = _is_single_zodiac(result)
        zodiac_preview_selection = (
            (result.zodiac_groups[0][0] if result.zodiac_groups else result.category)
            if is_single_zodiac_line
            else None
        )

        for number in numbers:
            try:
                selection = normalize_number(number)
            except InvalidNumberError as exc:
                message = str(exc)
                previews.append(
                    IntakeItemPreview(
                        source_line=source_line,
                        original_bet_type=category,
                        normalized_bet_type=None,
                        original_selection=original_selection,
                        normalized_selection=None,
                        amount=None,
                        is_valid=False,
                        error=message,
                    )
                )
                errors.append(message)
                return previews, order_items, warnings, errors

            if category in _EXPAND_NUMBER_CATEGORIES:
                preview_type = "特码"
                preview_selection = selection
                original_selection = str(number)
            elif is_single_zodiac_line and zodiac_preview_selection:
                preview_type = category
                preview_selection = zodiac_preview_selection
                original_selection = zodiac_preview_selection
            elif (
                category in _ELEMENTS
                or category in _SUM_LABELS
                or _TAIL_PATTERN.fullmatch(category)
                or _HEAD_PATTERN.fullmatch(category)
            ):
                preview_type = category
                preview_selection = category
                original_selection = category
            else:
                preview_type = "特码"
                preview_selection = selection
                original_selection = str(number)

            preview = _build_item_preview(
                source_line=source_line,
                original_bet_type=category,
                original_selection=original_selection,
                amount=per_amount,
                order_bet_type="特码",
                order_selection=selection,
                preview_bet_type=preview_type,
                preview_selection=preview_selection,
                normalizer=normalizer,
                warning=line_warning,
            )
            previews.append(preview)
            if preview.is_valid:
                order_items.append(
                    OrderItemCreate(
                        bet_type="特码",
                        selection=selection,
                        amount=per_amount,
                        note=(result.note or None),
                    )
                )
            else:
                errors.append(preview.error or f"号码 {number} 转换失败")

        if line_warning:
            warnings.append(line_warning)
        return previews, order_items, warnings, errors

    message = f"无法识别的解析类别：{category}"
    previews.append(
        IntakeItemPreview(
            source_line=source_line,
            original_bet_type=category,
            normalized_bet_type=None,
            original_selection=source_line,
            normalized_selection=None,
            amount=expected_total,
            is_valid=False,
            error=message,
        )
    )
    errors.append(message)
    return previews, order_items, warnings, errors
