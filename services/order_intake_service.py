"""Order intake adapter: parser output → OrderCreate → OrderService."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from core.database import SessionLocal
from domain.bet_types import normalize_bet_type, normalize_region
from domain.exceptions import DomainError
from domain.number_rules import normalize_number
from domain.zodiac_config import get_default_zodiac_year
from schemas.order_intake_schema import IntakeMetadata, IntakeTableRow, OrderIntakePreview, OrderIntakeSaveResult
from schemas.order_intake_schema import IntakeItemPreview
from schemas.order_schema import OrderCreate, OrderItemCreate, OrderResult
from services.order_intake_mapper import (
    IntakeConversionError,
    RegionConflictError,
    convert_parse_result,
    resolve_region,
    to_decimal_amount,
)
from services.order_parser import ParseOptions, parse_lines
from services.order_service import OrderService
from settlement.bet_normalizer import BetTypeNormalizer
from settlement.bet_normalizer import (
    SPECIAL_COLOR,
    SPECIAL_HALF_WAVE,
    SPECIAL_NUMBER,
    SPECIAL_PARITY,
    SPECIAL_SIZE,
)
from settlement.exceptions import InvalidSelectionError, UnsupportedBetTypeError
from services.settlement_support_service import SettlementSupportService

_CENT = Decimal("0.01")
_NORMALIZED_TO_ORDER_BET_TYPE = {
    SPECIAL_COLOR: "特码波色",
    SPECIAL_HALF_WAVE: "包半波",
    SPECIAL_SIZE: "特码两面",
    SPECIAL_PARITY: "特码两面",
}


class OrderIntakeService:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        order_service: OrderService | None = None,
        normalizer: BetTypeNormalizer | None = None,
        settlement_support_service: SettlementSupportService | None = None,
    ):
        self._session_factory = session_factory
        self._order_service = order_service or OrderService(session_factory)
        self._normalizer = normalizer or BetTypeNormalizer()
        self._settlement_support_service = settlement_support_service or SettlementSupportService(
            self._normalizer
        )

    def preview_raw_text(
        self,
        raw_text: str,
        *,
        customer_name: str | None = None,
        config_plan_name: str | None = None,
        channel: str | None = None,
        region: str | None = None,
        source: str = "record_window",
        parse_options: ParseOptions | None = None,
        zodiac_year: int | None = None,
    ) -> OrderIntakePreview:
        selected_zodiac_year = zodiac_year or (parse_options.zodiac_year if parse_options else None) or get_default_zodiac_year()
        metadata = IntakeMetadata(
            customer_name=customer_name,
            config_plan_name=config_plan_name,
            channel=channel,
            region=region,
            source=source,
            raw_text=raw_text,
            zodiac_year=selected_zodiac_year,
        )
        parsed_results = parse_lines(raw_text, options=parse_options, zodiac_year=selected_zodiac_year)
        return self.convert_parsed_result(parsed_results, metadata)

    def convert_parsed_result(
        self,
        parsed_result,
        metadata: IntakeMetadata,
    ) -> OrderIntakePreview:
        if isinstance(parsed_result, list):
            lines = [line.strip() for line in metadata.raw_text.splitlines() if line.strip()]
            if len(lines) != len(parsed_result):
                lines = lines or [metadata.raw_text.strip()]
            return self._convert_many(parsed_result, lines, metadata)

        return self._convert_many([parsed_result], [metadata.raw_text.strip()], metadata)

    def preview_table_rows(
        self,
        rows: list[IntakeTableRow],
        metadata: IntakeMetadata,
    ) -> OrderIntakePreview:
        preview = OrderIntakePreview(
            raw_text=(metadata.raw_text or "").strip() or self._raw_text_from_table_rows(rows),
            region=None,
            customer_name=(metadata.customer_name or None) and metadata.customer_name.strip() or None,
            channel=(metadata.channel or None) and metadata.channel.strip() or None,
            source=(metadata.source or "record_window_adjusted").strip() or "record_window_adjusted",
            config_plan_name=(metadata.config_plan_name or None)
            and metadata.config_plan_name.strip()
            or None,
            zodiac_year=metadata.zodiac_year,
        )
        if not rows:
            preview.errors.append("表格没有可保存的订单明细")
            return preview

        resolved_regions: list[str] = []
        total_amount = Decimal("0")

        for row in rows:
            row_preview, order_items, row_region = self._convert_table_row(row, metadata)
            preview.items.append(row_preview)
            if row_region:
                resolved_regions.append(row_region)
            if not row_preview.is_valid:
                preview.errors.append(row_preview.error or f"第 {row.row_number} 行数据不合法")
                continue
            preview.order_items.extend(order_items)
            total_amount += sum(item.amount for item in order_items)
            if row_preview.warning:
                preview.warnings.append(row_preview.warning)

        unique_regions = set(resolved_regions)
        if len(unique_regions) > 1:
            preview.errors.append(f"表格地区不一致：{', '.join(sorted(unique_regions))}")
        elif unique_regions:
            preview.region = next(iter(unique_regions))

        preview.total_amount = total_amount
        preview.valid_items = sum(1 for item in preview.items if item.is_valid)
        preview.invalid_items = sum(1 for item in preview.items if not item.is_valid)

        if not preview.customer_name:
            preview.warnings.append("申报人未设置")
        if not preview.channel:
            preview.warnings.append("渠道为空")

        preview.can_save = (
            not preview.errors
            and preview.invalid_items == 0
            and preview.region is not None
            and preview.order_items
            and preview.total_amount > 0
        )
        self._annotate_settlement_support(preview)
        return preview

    def save_preview(
        self,
        preview: OrderIntakePreview,
        *,
        allow_partial: bool = False,
    ) -> OrderIntakeSaveResult:
        if not preview.can_save:
            return OrderIntakeSaveResult(
                success=False,
                preview=preview,
                error="预览结果不可保存：" + "; ".join(preview.errors) if preview.errors else "预览不可保存",
            )
        if preview.invalid_items and not allow_partial:
            return OrderIntakeSaveResult(
                success=False,
                preview=preview,
                error="预览存在识别失败项；必须明确确认后才能只保存成功项",
            )
        if not preview.region:
            return OrderIntakeSaveResult(
                success=False,
                preview=preview,
                error="订单地区未确定",
            )
        if not preview.order_items:
            return OrderIntakeSaveResult(
                success=False,
                preview=preview,
                error="没有可保存的订单明细",
            )

        expected_total = sum(item.amount for item in preview.order_items)
        if expected_total != preview.total_amount:
            return OrderIntakeSaveResult(
                success=False,
                preview=preview,
                error=f"预览总金额 {preview.total_amount} 与明细合计 {expected_total} 不一致",
            )

        order_create = OrderCreate(
            customer_name=preview.customer_name,
            channel=preview.channel,
            config_plan_name=preview.config_plan_name,
            region=preview.region,
            raw_text=preview.raw_text,
            source=preview.source,
            zodiac_year=preview.zodiac_year,
            items=list(preview.order_items),
        )
        try:
            order = self._order_service.create_order(order_create)
        except (DomainError, ValueError, TypeError) as exc:
            return OrderIntakeSaveResult(success=False, preview=preview, error=str(exc))
        except Exception as exc:
            return OrderIntakeSaveResult(success=False, preview=preview, error=f"保存失败：{exc}")

        return OrderIntakeSaveResult(success=True, order=order, preview=preview)

    def parse_and_save(
        self,
        raw_text: str,
        *,
        customer_name: str | None = None,
        config_plan_name: str | None = None,
        channel: str | None = None,
        region: str | None = None,
        source: str = "record_window",
        parse_options: ParseOptions | None = None,
        zodiac_year: int | None = None,
    ) -> OrderIntakeSaveResult:
        preview = self.preview_raw_text(
            raw_text,
            customer_name=customer_name,
            config_plan_name=config_plan_name,
            channel=channel,
            region=region,
            source=source,
            parse_options=parse_options,
            zodiac_year=zodiac_year,
        )
        if not preview.can_save:
            return OrderIntakeSaveResult(
                success=False,
                preview=preview,
                error="; ".join(preview.errors) if preview.errors else "预览不可保存",
            )
        return self.save_preview(preview)

    def _convert_table_row(
        self,
        row: IntakeTableRow,
        metadata: IntakeMetadata,
    ) -> tuple[IntakeItemPreview, list[OrderItemCreate], str | None]:
        source_line = row.source_line or self._format_table_row_source(row)
        original_bet_type = str(row.bet_type or "").strip()
        original_selection = str(row.selection or "").strip()
        row_region: str | None = None

        try:
            row_region = normalize_region(str(row.region or metadata.region or "").strip())
            total_amount = self._table_amount(row.total_amount, row.row_number, "金额")
            order_bet_type, normalized_selection, normalized_type, warning = self._normalize_table_bet(
                original_bet_type,
                original_selection,
                row.row_number,
            )
            order_items = self._build_table_order_items(
                row=row,
                order_bet_type=order_bet_type,
                normalized_selection=normalized_selection,
                normalized_type=normalized_type,
                total_amount=total_amount,
            )
        except (ValueError, TypeError, DomainError, IntakeConversionError, InvalidSelectionError, UnsupportedBetTypeError) as exc:
            return (
                IntakeItemPreview(
                    source_line=source_line,
                    original_bet_type=original_bet_type,
                    normalized_bet_type=None,
                    original_selection=original_selection,
                    normalized_selection=None,
                    amount=None,
                    is_valid=False,
                    error=str(exc),
                ),
                [],
                row_region,
            )

        preview = IntakeItemPreview(
            source_line=source_line,
            original_bet_type=original_bet_type,
            normalized_bet_type=normalized_type,
            original_selection=original_selection,
            normalized_selection=normalized_selection,
            amount=sum(item.amount for item in order_items),
            is_valid=True,
            warning=warning,
            order_bet_type=order_bet_type,
            order_selection=normalized_selection,
        )
        return preview, order_items, row_region

    def _normalize_table_bet(
        self,
        bet_type: str,
        selection: str,
        row_number: int,
    ) -> tuple[str, str, str | None, str | None]:
        if not bet_type:
            raise ValueError(f"第 {row_number} 行投注类型不能为空")
        if not selection:
            raise ValueError(f"第 {row_number} 行投注内容不能为空")

        try:
            normalized = self._normalizer.normalize(bet_type, selection)
        except UnsupportedBetTypeError:
            order_bet_type = normalize_bet_type(bet_type)
            warning = f"第 {row_number} 行玩法「{order_bet_type}」可保存，但当前结算预览暂不支持"
            return order_bet_type, selection.strip(), None, warning

        if normalized.normalized_bet_type == SPECIAL_NUMBER:
            return "特码", normalized.selection, normalized.normalized_bet_type, None

        order_bet_type = _NORMALIZED_TO_ORDER_BET_TYPE.get(normalized.normalized_bet_type)
        if order_bet_type is None:
            order_bet_type = normalize_bet_type(bet_type)
        return order_bet_type, normalized.selection, normalized.normalized_bet_type, None

    def _build_table_order_items(
        self,
        *,
        row: IntakeTableRow,
        order_bet_type: str,
        normalized_selection: str,
        normalized_type: str | None,
        total_amount: Decimal,
    ) -> list[OrderItemCreate]:
        note = (row.note or None) and row.note.strip() or None
        if normalized_type == SPECIAL_NUMBER or order_bet_type in {"特码", "号码"}:
            numbers = [
                normalize_number(token.strip())
                for token in normalized_selection.replace("，", ",").replace("、", ",").replace("/", ",").split(",")
                if token.strip()
            ]
            if not numbers:
                raise ValueError(f"第 {row.row_number} 行投注号码不能为空")
            per_amount = self._per_item_amount(row, total_amount, len(numbers))
            return [
                OrderItemCreate(bet_type="特码", selection=number, amount=per_amount, note=note)
                for number in numbers
            ]

        return [
            OrderItemCreate(
                bet_type=order_bet_type,
                selection=normalized_selection,
                amount=total_amount,
                note=note,
            )
        ]

    def _per_item_amount(self, row: IntakeTableRow, total_amount: Decimal, count: int) -> Decimal:
        if count <= 0:
            raise ValueError(f"第 {row.row_number} 行投注内容不能为空")
        if count == 1:
            return total_amount

        if row.per_item_amount not in (None, ""):
            per_amount = self._table_amount(row.per_item_amount, row.row_number, "每号金额")
            if per_amount * count == total_amount:
                return per_amount

        per_amount = (total_amount / Decimal(count)).quantize(_CENT)
        if per_amount * count != total_amount:
            raise ValueError(f"第 {row.row_number} 行金额 {total_amount} 无法平均分配到 {count} 个号码")
        return per_amount

    def _table_amount(self, value, row_number: int, label: str) -> Decimal:
        try:
            amount = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, TypeError, AttributeError):
            raise ValueError(f"第 {row_number} 行{label}不是有效数字：{value}") from None
        if not amount.is_finite():
            raise ValueError(f"第 {row_number} 行{label}不是有效数字：{value}")
        if amount <= 0:
            raise ValueError(f"第 {row_number} 行{label}必须大于 0")
        return amount

    def _format_table_row_source(self, row: IntakeTableRow) -> str:
        return f"{row.region} {row.bet_type} {row.selection} {row.total_amount}"

    def _raw_text_from_table_rows(self, rows: list[IntakeTableRow]) -> str:
        return "\n".join(self._format_table_row_source(row) for row in rows).strip()

    def _convert_many(
        self,
        parsed_results: list,
        source_lines: list[str],
        metadata: IntakeMetadata,
    ) -> OrderIntakePreview:
        preview = OrderIntakePreview(
            raw_text=metadata.raw_text,
            region=None,
            customer_name=(metadata.customer_name or None) and metadata.customer_name.strip() or None,
            channel=(metadata.channel or None) and metadata.channel.strip() or None,
            source=(metadata.source or "record_window").strip() or "record_window",
            config_plan_name=(metadata.config_plan_name or None)
            and metadata.config_plan_name.strip()
            or None,
            zodiac_year=metadata.zodiac_year,
        )

        if not metadata.raw_text.strip():
            preview.errors.append("输入为空")
            return preview

        resolved_regions: list[str] = []
        all_previews: list = []
        all_order_items: list[OrderItemCreate] = []
        total_amount = Decimal("0")

        for index, result in enumerate(parsed_results):
            source_line = (
                getattr(result, "normalized_text", None)
                or getattr(result, "original_text", None)
                or (source_lines[index] if index < len(source_lines) else metadata.raw_text.strip())
            )
            try:
                line_region = resolve_region(
                    text_region=result.region,
                    param_region=metadata.region,
                )
            except RegionConflictError as exc:
                message = str(exc)
                preview.errors.append(message)
                all_previews.append(
                    IntakeItemPreview(
                        source_line=source_line,
                        original_bet_type=result.category if result.success else "",
                        normalized_bet_type=None,
                        original_selection=source_line,
                        normalized_selection=None,
                        amount=None,
                        is_valid=False,
                        error=message,
                    )
                )
                continue
            except IntakeConversionError as exc:
                preview.errors.append(str(exc))
                continue

            resolved_regions.append(line_region)
            item_previews, order_items, warnings, errors = convert_parse_result(
                result,
                source_line,
                normalizer=self._normalizer,
            )
            all_previews.extend(item_previews)
            preview.warnings.extend(warnings)
            preview.errors.extend(errors)
            for item in order_items:
                all_order_items.append(item)
                total_amount += item.amount

        if not resolved_regions and preview.errors:
            preview.items = [p for p in all_previews if p is not None]
            preview.invalid_items = len(preview.items)
            return preview

        unique_regions = set(resolved_regions)
        if len(unique_regions) > 1:
            preview.errors.append(
                f"多行订单地区不一致：{', '.join(sorted(unique_regions))}"
            )
        elif unique_regions:
            preview.region = next(iter(unique_regions))

        preview.items = all_previews
        preview.order_items = all_order_items
        preview.total_amount = total_amount
        preview.valid_items = sum(1 for item in preview.items if item.is_valid)
        preview.invalid_items = sum(1 for item in preview.items if not item.is_valid)

        if not preview.customer_name:
            preview.warnings.append("申报人未设置")
        if not preview.channel:
            preview.warnings.append("渠道为空")

        if preview.invalid_items and preview.order_items:
            preview.warnings.append(
                f"本次识别有 {preview.invalid_items} 个失败项；确认后仅保存 {preview.valid_items} 个成功项"
            )

        preview.can_save = (
            preview.region is not None
            and preview.order_items
            and preview.total_amount > 0
        )
        self._annotate_settlement_support(preview)
        return preview

    def _annotate_settlement_support(self, preview: OrderIntakePreview) -> None:
        seen_warnings: set[str] = set(preview.warnings)
        order_items = iter(preview.order_items)
        for item_preview in preview.items:
            if not item_preview.is_valid:
                continue
            order_item = next(order_items, None)
            bet_type = (
                getattr(order_item, "bet_type", None)
                or item_preview.order_bet_type
                or item_preview.original_bet_type
            )
            selection = (
                getattr(order_item, "selection", None)
                or item_preview.order_selection
                or item_preview.normalized_selection
                or item_preview.original_selection
            )
            result = self._settlement_support_service.check_item(
                bet_type,
                selection,
                note=getattr(order_item, "note", None),
            )
            item_preview.settlement_support_status = result.status
            item_preview.settlement_support_message = result.message
            item_preview.settlement_support_suggestion = result.suggestion
            if not result.is_supported:
                warning = (
                    f"{result.message}。{result.suggestion}"
                )
                if warning not in seen_warnings:
                    preview.warnings.append(warning)
                    seen_warnings.add(warning)
