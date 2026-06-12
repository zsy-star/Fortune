"""Read-only settlement preview service."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.database import SessionLocal
from models import LotteryDraw, Order
from settlement.exceptions import SettlementDataError
from settlement.settlement_engine import SettlementEngine


class SettlementService:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        engine: SettlementEngine | None = None,
    ):
        self._session_factory = session_factory
        self._engine = engine or SettlementEngine()

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

    def _get_order(self, session: Session, order_id: int) -> Order:
        stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        order = session.scalars(stmt).first()
        if order is None:
            raise SettlementDataError(f"未找到订单：{order_id}")
        return order
