"""Read-only settlement preview service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.database import SessionLocal
from domain.bet_types import normalize_region
from domain.zodiac_rules import get_zodiac
from models import LotteryDraw, Order, SettlementRecord
from repositories.settlement_record_repository import SettlementRecordRepository
from schemas.settlement_schema import (
    ItemSettlementResult,
    OrderSettlementCommitResult,
    OrderSettlementPreview,
    SettlementLedgerResult,
)
from settlement.exceptions import SettlementDataError
from settlement.settlement_engine import SettlementEngine
from services.log_service import LogService

ORDER_STATUS_SETTLED = "settled"


class SettlementService:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        engine: SettlementEngine | None = None,
    ):
        self._session_factory = session_factory
        self._engine = engine or SettlementEngine()
        self._log_service = LogService(session_factory)

    def preview_order(self, order_id: int, draw_id: int):
        with self._session_factory() as session:
            order = self._get_order(session, order_id)
            draw = session.get(LotteryDraw, draw_id)
            if draw is None:
                raise SettlementDataError(f"未找到开奖记录：{draw_id}")
            return self._engine.evaluate_order(order, draw)

    def preview_order_by_issue(self, order_id: int, region: str, issue_number: str):
        with self._session_factory() as session:
            order = self._get_order(session, order_id)
            stmt = select(LotteryDraw).where(
                LotteryDraw.region == region,
                LotteryDraw.issue_number == str(issue_number),
            )
            draw = session.scalars(stmt).first()
            if draw is None:
                raise SettlementDataError(f"未找到开奖记录：{region} {issue_number}")
            return self._engine.evaluate_order(order, draw)

    def preview_order_data(self, order_result, lottery_draw_result):
        return self._engine.evaluate_order(order_result, lottery_draw_result)

    def list_settlement_records(
        self,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SettlementLedgerResult]:
        limit, offset = self._validate_limit_offset(limit, offset)
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            rows = SettlementRecordRepository(session).list(
                region=region,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )
            return [self._to_ledger_result(record) for record in rows]

    def count_settlement_records(
        self,
        *,
        region: str | None = None,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        if region is not None:
            region = normalize_region(region)
        with self._session_factory() as session:
            return SettlementRecordRepository(session).count(
                region=region,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
            )

    def get_settlement_record_by_order_id(self, order_id: int) -> SettlementLedgerResult | None:
        with self._session_factory() as session:
            record = SettlementRecordRepository(session).get_by_order_id(order_id)
            return self._to_ledger_result(record) if record else None

    def get_settlement_records_by_order_ids(
        self,
        order_ids: list[int],
    ) -> dict[int, SettlementLedgerResult]:
        """Return persisted settlement summaries without evaluating orders again."""
        with self._session_factory() as session:
            records = SettlementRecordRepository(session).get_by_order_ids(order_ids)
            results: dict[int, SettlementLedgerResult] = {}
            for record in records:
                results.setdefault(record.order_id, self._to_ledger_result(record))
            return results

    def get_settlement_record(self, record_id: int) -> SettlementLedgerResult | None:
        with self._session_factory() as session:
            record = SettlementRecordRepository(session).get(record_id)
            return self._to_ledger_result(record) if record else None

    def commit_order_settlement(self, order_id: int, draw_id: int) -> OrderSettlementCommitResult:
        with self._session_factory() as session:
            try:
                order = self._get_order(session, order_id)
                draw = session.get(LotteryDraw, draw_id)
                if draw is None:
                    raise SettlementDataError(f"未找到开奖记录：{draw_id}")
                result = self._commit_loaded(session, order, draw)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise

    def commit_order_settlement_by_issue(
        self,
        order_id: int,
        region: str,
        issue_number: str,
    ) -> OrderSettlementCommitResult:
        with self._session_factory() as session:
            try:
                order = self._get_order(session, order_id)
                stmt = select(LotteryDraw).where(
                    LotteryDraw.region == region,
                    LotteryDraw.issue_number == str(issue_number),
                )
                draw = session.scalars(stmt).first()
                if draw is None:
                    raise SettlementDataError(f"未找到开奖记录：{region} {issue_number}")
                result = self._commit_loaded(session, order, draw)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise

    def _get_order(self, session: Session, order_id: int) -> Order:
        stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        order = session.scalars(stmt).first()
        if order is None:
            raise SettlementDataError(f"未找到订单：{order_id}")
        return order

    def _commit_loaded(
        self,
        session: Session,
        order: Order,
        draw: LotteryDraw,
    ) -> OrderSettlementCommitResult:
        if order.status == ORDER_STATUS_SETTLED:
            raise SettlementDataError(f"订单已结算，不能重复结算：{order.order_no}")

        record_repo = SettlementRecordRepository(session)
        if record_repo.get_by_order_id(order.id) is not None:
            raise SettlementDataError(f"订单已有结算记录，不能重复结算：{order.order_no}")

        preview: OrderSettlementPreview = self._engine.evaluate_order(order, draw)
        if preview.unsupported_items:
            unsupported = [
                f"{item.bet_type}/{item.selection}: {item.reason}"
                for item in preview.results
                if not item.is_supported
            ]
            raise SettlementDataError(
                "存在暂不支持玩法，暂不能正式结算：" + "; ".join(unsupported)
            )

        status_before = order.status
        settled_at = datetime.now()
        record = SettlementRecord(
            order_id=order.id,
            draw_id=draw.id,
            region=order.region,
            issue_number=draw.issue_number,
            settled_at=settled_at,
            total_items=preview.total_items,
            hit_count=preview.winning_items,
            miss_count=preview.losing_items,
            unsupported_count=preview.unsupported_items,
            total_amount=Decimal(order.total_amount),
            result_snapshot=self._build_result_snapshot(order, draw, preview, settled_at),
        )
        record_repo.add(record)
        session.flush()

        order.status = ORDER_STATUS_SETTLED
        order.updated_at = settled_at
        description = (
            f"确认结算订单 {order.order_no}，开奖 {draw.region} {draw.issue_number}，"
            f"结算记录 {record.id}，中奖 {preview.winning_items}，未中奖 {preview.losing_items}"
        )
        log = self._log_service.create_log(
            module="settlement",
            action="commit",
            description=description,
            related_type="order",
            related_id=order.id,
            session=session,
        )
        session.flush()
        record.operation_log_id = log.id
        session.flush()

        return OrderSettlementCommitResult(
            order_id=order.id,
            draw_id=draw.id,
            settlement_record_id=record.id,
            region=order.region,
            issue_number=draw.issue_number,
            total_items=preview.total_items,
            supported_items=preview.supported_items,
            unsupported_items=preview.unsupported_items,
            win_count=preview.winning_items,
            lose_count=preview.losing_items,
            order_status_before=status_before,
            order_status_after=order.status,
            results=preview.results,
            warnings=[],
            operation_log_id=log.id,
        )

    def _validate_limit_offset(self, limit: int, offset: int) -> tuple[int, int]:
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        if offset < 0:
            offset = 0
        return limit, offset

    def _build_result_snapshot(
        self,
        order: Order,
        draw: LotteryDraw,
        preview: OrderSettlementPreview,
        settled_at: datetime,
    ) -> dict[str, Any]:
        return {
            "order": {
                "id": order.id,
                "order_no": order.order_no,
                "region": order.region,
                "total_amount": str(order.total_amount),
                "status_before": order.status,
            },
            "draw": {
                "id": draw.id,
                "region": draw.region,
                "issue_number": draw.issue_number,
                "draw_date": draw.draw_date.isoformat(),
                "regular_numbers": list(draw.regular_numbers),
                "special_number": draw.special_number,
                "special_zodiac": get_zodiac(draw.special_number),
            },
            "settlement": {
                "settled_at": settled_at.isoformat(sep=" "),
                "total_items": preview.total_items,
                "supported_items": preview.supported_items,
                "unsupported_items": preview.unsupported_items,
                "hit_count": preview.winning_items,
                "miss_count": preview.losing_items,
            },
            "items": [self._snapshot_item(item) for item in preview.results],
        }

    def _snapshot_item(self, item: ItemSettlementResult) -> dict[str, Any]:
        return {
            "order_item_id": item.order_item_id,
            "bet_type": item.bet_type,
            "normalized_bet_type": item.normalized_bet_type,
            "selection": item.selection,
            "amount": str(item.amount),
            "is_supported": item.is_supported,
            "is_winner": item.is_winner,
            "matched_number": item.matched_number,
            "reason": item.reason,
            "draw_special_number": item.draw_special_number,
            "draw_special_zodiac": item.draw_special_zodiac,
            "selected_zodiacs": list(item.selected_zodiacs),
            "matched_zodiac": item.matched_zodiac,
            "unsupported_reason": item.unsupported_reason,
        }

    def _to_ledger_result(self, record: SettlementRecord) -> SettlementLedgerResult:
        order = record.order
        log = record.operation_log
        return SettlementLedgerResult(
            id=record.id,
            order_id=record.order_id,
            draw_id=record.draw_id,
            operation_log_id=record.operation_log_id,
            order_no=order.order_no,
            customer_name=order.customer_name,
            region=record.region,
            order_status=order.status,
            total_amount=record.total_amount,
            settled_at=record.settled_at,
            issue_number=record.issue_number,
            total_items=record.total_items,
            hit_count=record.hit_count,
            miss_count=record.miss_count,
            unsupported_count=record.unsupported_count,
            result_snapshot=record.result_snapshot,
            order_created_at=order.created_at,
            order_updated_at=order.updated_at,
            operation_log_description=log.description if log else None,
        )
