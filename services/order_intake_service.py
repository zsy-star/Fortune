"""Order intake adapter: parser output → OrderCreate → OrderService."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.orm import Session

from core.database import SessionLocal
from domain.exceptions import DomainError
from schemas.order_intake_schema import IntakeMetadata, OrderIntakePreview, OrderIntakeSaveResult
from schemas.order_intake_schema import IntakeItemPreview
from schemas.order_schema import OrderCreate, OrderItemCreate, OrderResult
from services.order_intake_mapper import (
    IntakeConversionError,
    RegionConflictError,
    convert_parse_result,
    resolve_region,
    to_decimal_amount,
)
from services.order_parser import parse_lines
from services.order_service import OrderService
from settlement.bet_normalizer import BetTypeNormalizer


class OrderIntakeService:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        order_service: OrderService | None = None,
        normalizer: BetTypeNormalizer | None = None,
    ):
        self._session_factory = session_factory
        self._order_service = order_service or OrderService(session_factory)
        self._normalizer = normalizer or BetTypeNormalizer()

    def preview_raw_text(
        self,
        raw_text: str,
        *,
        customer_name: str | None = None,
        channel: str | None = None,
        region: str | None = None,
        source: str = "record_window",
    ) -> OrderIntakePreview:
        metadata = IntakeMetadata(
            customer_name=customer_name,
            channel=channel,
            region=region,
            source=source,
            raw_text=raw_text,
        )
        parsed_results = parse_lines(raw_text)
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

    def save_preview(self, preview: OrderIntakePreview) -> OrderIntakeSaveResult:
        if not preview.can_save:
            return OrderIntakeSaveResult(
                success=False,
                preview=preview,
                error="预览结果不可保存：" + "; ".join(preview.errors) if preview.errors else "预览不可保存",
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
            region=preview.region,
            raw_text=preview.raw_text,
            source=preview.source,
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
        channel: str | None = None,
        region: str | None = None,
        source: str = "record_window",
    ) -> OrderIntakeSaveResult:
        preview = self.preview_raw_text(
            raw_text,
            customer_name=customer_name,
            channel=channel,
            region=region,
            source=source,
        )
        if not preview.can_save:
            return OrderIntakeSaveResult(
                success=False,
                preview=preview,
                error="; ".join(preview.errors) if preview.errors else "预览不可保存",
            )
        return self.save_preview(preview)

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
        )

        if not metadata.raw_text.strip():
            preview.errors.append("输入为空")
            return preview

        resolved_regions: list[str] = []
        all_previews: list = []
        all_order_items: list[OrderItemCreate] = []
        total_amount = Decimal("0")

        for index, result in enumerate(parsed_results):
            source_line = source_lines[index] if index < len(source_lines) else metadata.raw_text.strip()
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
            preview.warnings.append("客户名称为空")
        if not preview.channel:
            preview.warnings.append("渠道为空")

        preview.can_save = (
            not preview.errors
            and preview.invalid_items == 0
            and preview.region is not None
            and preview.order_items
            and preview.total_amount > 0
        )
        return preview
