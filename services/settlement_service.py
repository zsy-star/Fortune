"""Read-only settlement preview service."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.database import SessionLocal
from models import LotteryDraw, Order
from schemas.settlement_schema import OrderSettlementCommitResult, OrderSettlementPreview
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
        order.status = ORDER_STATUS_SETTLED
        description = (
            f"确认结算订单 {order.order_no}，开奖 {draw.region} {draw.issue_number}，"
            f"中奖 {preview.winning_items}，未中奖 {preview.losing_items}"
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

        return OrderSettlementCommitResult(
            order_id=order.id,
            draw_id=draw.id,
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
