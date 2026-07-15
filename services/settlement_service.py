"""Read-only settlement preview service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.database import SessionLocal
from domain.bet_types import normalize_region
from domain.play_rules import FORTUNE_RULESET_2026_V2, is_v2_ruleset
from domain.non_hit_rules import (
    format_non_hit_count_chinese,
    non_hit_odds_bet_type_candidates,
)
from domain.zodiac_rules import get_zodiac
from domain.zodiac_config import get_default_zodiac_year, validate_zodiac_year
from models import LotteryDraw, Order, SettlementRecord
from repositories.settings_repository import SettingsRepository
from repositories.settlement_record_repository import SettlementRecordRepository
from schemas.settlement_schema import (
    ItemSettlementResult,
    OrderSettlementCommitResult,
    OrderSettlementPreview,
    SettlementLedgerResult,
)
from settlement.exceptions import SettlementDataError
from settlement.bet_normalizer import (
    LINKED_TAIL,
    LIANMA_THREE_THREE,
    LIANMA_THREE_TWO,
    LIANMA_TWO_TWO,
    LIANXIAO_ZODIAC,
    NON_HIT_NUMBER,
    NUMBER_FUXUAN,
    PACKAGE_HALF_WAVE,
    PINGTE_MAIN_ZODIAC,
    PINGTE_ZODIAC,
    PING_TAIL,
    REGULAR_NUMBER,
    SPECIAL_COLOR,
    SPECIAL_ELEMENT,
    SPECIAL_HALF_WAVE,
    SPECIAL_HEAD,
    SPECIAL_NUMBER,
    SPECIAL_PARITY,
    SPECIAL_SIZE,
    SPECIAL_SUM_PARITY,
    SPECIAL_SUM_SIZE,
    SPECIAL_TAIL,
    SPECIAL_ZODIAC,
    SPECIAL_ZODIAC_GROUP,
    SIX_SPECIAL_ZODIAC,
)
from settlement.settlement_engine import SettlementEngine
from services.log_service import LogService
from services.settlement_support_service import SettlementSupportResult, SettlementSupportService

ORDER_STATUS_SETTLED = "settled"
CENT = Decimal("0.01")
PINGTE_ZODIAC_TYPES = frozenset({PINGTE_ZODIAC, PINGTE_MAIN_ZODIAC})
REQUIRED_ODDS_TYPES = PINGTE_ZODIAC_TYPES | frozenset(
    {SPECIAL_NUMBER, PING_TAIL, LIANXIAO_ZODIAC}
)

ODDS_CANDIDATES: dict[str, tuple[str, ...]] = {
    SPECIAL_NUMBER: ("特码号码", "特码", "号码", "特号", "单号投注", "纯数字"),
    SPECIAL_ZODIAC: ("特码生肖", "生肖", "平特一肖", "一肖"),
    SPECIAL_COLOR: ("波色", "特码波色", "色波"),
    SPECIAL_HALF_WAVE: ("半波", "包半波", "特码半波"),
    SPECIAL_SIZE: ("大小", "特码大小", "特码两面"),
    SPECIAL_PARITY: ("单双", "特码单双", "特码两面"),
    SPECIAL_TAIL: ("尾数", "特码尾数"),
    SPECIAL_HEAD: ("头数", "特码头数"),
    SPECIAL_SUM_PARITY: ("合数", "合数单双", "特码合数单双"),
    SPECIAL_SUM_SIZE: ("合数", "合数大小", "特码合数大小"),
    SPECIAL_ELEMENT: ("五行", "特码五行"),
    LIANXIAO_ZODIAC: ("连肖",),
    PINGTE_ZODIAC: ("平特一肖", "平肖", "生肖"),
    PINGTE_MAIN_ZODIAC: ("平特一肖带主肖", "平特一肖主肖", "平肖主肖"),
    LINKED_TAIL: ("连尾", "尾数"),
    PING_TAIL: ("平尾",),
    LIANMA_TWO_TWO: ("二中二",),
    LIANMA_THREE_THREE: ("三中三",),
    LIANMA_THREE_TWO: ("三中二",),
    NUMBER_FUXUAN: ("几中几复选",),
    NON_HIT_NUMBER: ("N不中", "不中"),
    SIX_SPECIAL_ZODIAC: ("六肖中特",),
    REGULAR_NUMBER: ("平码",),
    PACKAGE_HALF_WAVE: ("半波", "包半波", "特码半波"),
}


class SettlementService:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        engine: SettlementEngine | None = None,
    ):
        self._session_factory = session_factory
        self._engine = engine or SettlementEngine()
        self._log_service = LogService(session_factory)
        self._support_service = SettlementSupportService()

    def preview_order(self, order_id: int, draw_id: int):
        with self._session_factory() as session:
            order = self._get_order(session, order_id)
            draw = session.get(LotteryDraw, draw_id)
            if draw is None:
                raise SettlementDataError(f"鏈壘鍒板紑濂栬褰曪細{draw_id}")
            engine, _warning = self._engine_for_order(order)
            preview = engine.evaluate_order(order, draw)
            return self._apply_payouts(session, order, preview)

    def preview_order_by_issue(self, order_id: int, region: str, issue_number: str):
        with self._session_factory() as session:
            order = self._get_order(session, order_id)
            stmt = select(LotteryDraw).where(
                LotteryDraw.region == region,
                LotteryDraw.issue_number == str(issue_number),
            )
            draw = session.scalars(stmt).first()
            if draw is None:
                raise SettlementDataError(f"鏈壘鍒板紑濂栬褰曪細{region} {issue_number}")
            engine, _warning = self._engine_for_order(order)
            preview = engine.evaluate_order(order, draw)
            return self._apply_payouts(session, order, preview)

    def preview_order_data(self, order_result, lottery_draw_result):
        engine, _warning = self._engine_for_order(order_result)
        return engine.evaluate_order(order_result, lottery_draw_result)

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

    def check_order_support(self, order_id: int) -> list[SettlementSupportResult]:
        with self._session_factory() as session:
            order = self._get_order(session, order_id)
            return self._support_service.check_order_items(
                order.items,
                ruleset_version=order.ruleset_version,
                zodiac_year=order.zodiac_year,
                require_zodiac_year=True,
            )


    def commit_order_settlement(self, order_id: int, draw_id: int) -> OrderSettlementCommitResult:
        with self._session_factory() as session:
            try:
                order = self._get_order(session, order_id)
                draw = session.get(LotteryDraw, draw_id)
                if draw is None:
                    raise SettlementDataError(f"\u672a\u627e\u5230\u5f00\u5956\u8bb0\u5f55\uff1a{draw_id}")
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

        ruleset_support = self._support_service.check_ruleset_version(order.ruleset_version)
        if not ruleset_support.is_supported:
            raise SettlementDataError(
                "订单规则版本不允许正式结算："
                f"{ruleset_support.reason}"
            )

        if order.zodiac_year is None and any(
            item.bet_type in {"平特一肖", "平特一肖带主肖", "连肖", "多生肖"}
            for item in order.items
        ):
            raise SettlementDataError("平特一肖正式结算需要订单保存的生肖年份")

        unsupported_before_preview = self._support_service.unsupported_results(
            order.items,
            ruleset_version=order.ruleset_version,
            zodiac_year=order.zodiac_year,
            require_zodiac_year=True,
        )
        if unsupported_before_preview:
            raise SettlementDataError(
                "存在暂不支持玩法，暂不能正式结算：" + self._format_unsupported_support(unsupported_before_preview)
            )

        engine, zodiac_warning = self._engine_for_order(order)
        preview: OrderSettlementPreview = self._apply_payouts(
            session,
            order,
            engine.evaluate_order(order, draw),
        )
        if preview.unsupported_items:
            unsupported = [
                f"{item.bet_type}/{item.selection}: {item.reason}"
                for item in preview.results
                if not item.is_supported
            ]
            raise SettlementDataError(
                "存在暂不支持玩法，暂不能正式结算：" + "; ".join(unsupported)
            )
        missing_required_odds = [item for item in preview.results if item.missing_odds]
        if missing_required_odds:
            raise SettlementDataError(self._missing_required_odds_error(order, missing_required_odds))

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
            result_snapshot=self._build_result_snapshot(
                order,
                draw,
                preview,
                settled_at,
                zodiac_year=engine.zodiac_year,
                warnings=[zodiac_warning] if zodiac_warning else [],
            ),
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
            warnings=[zodiac_warning] if zodiac_warning else [],
            operation_log_id=log.id,
            total_bet_amount=preview.total_bet_amount,
            total_payout_amount=preview.total_payout_amount,
            total_rebate_amount=preview.total_rebate_amount,
            statistic_net_amount=preview.statistic_net_amount,
        )

    def _apply_payouts(
        self,
        session: Session,
        order: Order,
        preview: OrderSettlementPreview,
    ) -> OrderSettlementPreview:
        plan, odds_source = self._resolve_odds_plan(session, order)
        plan_name = getattr(plan, "name", None) if plan is not None else None
        plan_items = list(getattr(plan, "items", []) or []) if plan is not None else []
        results = [
            self._apply_item_payout(item, plan_items, plan_name, odds_source)
            for item in preview.results
        ]
        results = [
            self._apply_item_rebate(item, plan_items, plan_name, odds_source)
            for item in results
        ]
        blocking_reasons = tuple(
            dict.fromkeys(
                item.blocking_reason
                for item in results
                if item.blocking_reason
            )
        )
        total_bet = sum((item.amount for item in results), Decimal("0.00")).quantize(CENT)
        total_payout = sum((item.payout_amount for item in results), Decimal("0.00")).quantize(CENT)
        total_rebate = sum((item.rebate_amount for item in results), Decimal("0.00")).quantize(CENT)
        statistic_net = (total_payout + total_rebate - total_bet).quantize(CENT)
        return replace(
            preview,
            results=results,
            total_bet_amount=total_bet,
            total_payout_amount=total_payout,
            total_rebate_amount=total_rebate,
            statistic_net_amount=statistic_net,
            settlement_ready=not blocking_reasons,
            blocking_reasons=blocking_reasons,
        )

    def _resolve_odds_plan(self, session: Session, order: Order):
        repo = SettingsRepository(session)
        customer_name = (getattr(order, "customer_name", None) or "").strip()
        if customer_name:
            declarer = repo.get_declarer_by_name(customer_name)
            if declarer is not None:
                plan = repo.get_plan(declarer.plan_id)
                if plan is not None:
                    return plan, "申报人绑定方案"
        plans = repo.list_plans()
        default_plan = next((plan for plan in plans if plan.is_default), None)
        if default_plan is not None:
            return default_plan, "默认方案"
        return None, "未配置"

    def _apply_item_payout(
        self,
        item: ItemSettlementResult,
        plan_items: list[Any],
        plan_name: str | None,
        odds_source: str,
    ) -> ItemSettlementResult:
        if item.is_supported is False:
            return replace(
                item,
                payout_amount=Decimal("0.00"),
                odds_source="未配置",
                payout_note="不支持玩法，不计算中奖金额",
            )
        if item.normalized_bet_type in REQUIRED_ODDS_TYPES:
            item = self._mark_required_odds_readiness(
                item,
                plan_items,
                plan_name,
                odds_source,
            )
            if item.missing_odds:
                return item
        if item.is_winner is not True:
            return replace(
                item,
                payout_amount=Decimal("0.00"),
                odds_source="未配置",
                payout_note="未命中，不计算中奖金额",
            )
        if not plan_items:
            return replace(
                item,
                payout_amount=Decimal("0.00"),
                odds_plan_name=plan_name,
                odds_source="未配置",
                payout_note="未配置赔率",
            )
        odds_item = self._find_odds_item(item, plan_items)
        if odds_item is None:
            return replace(
                item,
                payout_amount=Decimal("0.00"),
                odds_plan_name=plan_name,
                odds_source=odds_source,
                payout_note="未找到赔率配置",
            )
        odds = Decimal(odds_item.odds)
        payout = (item.amount * odds).quantize(CENT, rounding=ROUND_HALF_UP)
        return replace(
            item,
            odds=odds,
            payout_amount=payout,
            odds_plan_name=plan_name,
            odds_source=odds_source,
            odds_key_used=str(odds_item.bet_type).strip(),
            payout_note=f"中奖金额 = 投注金额 {_decimal_money(item.amount)} x 赔率 {_decimal_odds(odds)}",
        )

    def _mark_required_odds_readiness(
        self,
        item: ItemSettlementResult,
        plan_items: list[Any],
        plan_name: str | None,
        odds_source: str,
    ) -> ItemSettlementResult:
        candidates = self._odds_candidates_for_item(item)
        odds_item = self._find_odds_item(item, plan_items) if plan_items else None
        invalid_odds_key: str | None = None
        if odds_item is not None:
            try:
                configured_odds = Decimal(odds_item.odds)
            except (InvalidOperation, TypeError, ValueError):
                configured_odds = None
            if configured_odds is None or not configured_odds.is_finite() or configured_odds <= 0:
                invalid_odds_key = str(odds_item.bet_type).strip()

        if odds_item is not None and invalid_odds_key is None:
            return replace(item, odds_key_candidates=candidates)

        attempted_keys = "、".join(candidates) or "无"
        odds_label = self._required_odds_label(item)
        if invalid_odds_key is not None:
            blocking_reason = (
                f"{odds_label}键「{invalid_odds_key}」赔率值无效"
                f"（已尝试：{attempted_keys}）；请到设置中心补齐有效赔率后再正式结算"
            )
        else:
            blocking_reason = (
                f"缺少{odds_label}配置（已尝试：{attempted_keys}）；"
                "请到设置中心补齐赔率后再正式结算"
            )
        outcome = "命中" if item.is_winner is True else "未命中"
        preview_note = f"{outcome}，{blocking_reason}；当前结果仅供核对，不能正式结算"
        return replace(
            item,
            odds=None,
            payout_amount=Decimal("0.00"),
            odds_plan_name=plan_name,
            odds_source=odds_source if plan_items else "未配置",
            odds_key_used=None,
            odds_key_candidates=candidates,
            missing_odds=True,
            settlement_ready=False,
            blocking_reason=blocking_reason,
            payout_note=preview_note,
            reason=f"{item.reason}；{preview_note}",
        )

    @staticmethod
    def _missing_required_odds_error(order: Order, items: list[ItemSettlementResult]) -> str:
        details = "; ".join(
            (
                f"{item.bet_type}/{item.selection}"
                f"（{SettlementService._required_item_kind(item)}；"
                f"已尝试赔率键：{'、'.join(item.odds_key_candidates) or '无'}；"
                f"{item.blocking_reason or '缺少适用赔率'}）"
            )
            for item in items
        )
        return (
            f"订单 {order.order_no} 存在赔率配置不完整的受管控明细，不能正式结算：{details}。"
            "请到设置中心补齐赔率后重新预览并结算"
        )

    @staticmethod
    def _required_item_kind(item: ItemSettlementResult) -> str:
        if item.normalized_bet_type == SPECIAL_NUMBER:
            return "特码号码"
        if item.normalized_bet_type == PINGTE_MAIN_ZODIAC:
            return "主肖"
        if item.normalized_bet_type == PINGTE_ZODIAC:
            return "普通生肖"
        if item.normalized_bet_type == PING_TAIL:
            return "0尾" if item.selection == "0" else "普通平尾"
        if item.normalized_bet_type == LIANXIAO_ZODIAC:
            return "连肖"
        return "受管控玩法"

    @staticmethod
    def _required_odds_label(item: ItemSettlementResult) -> str:
        if item.normalized_bet_type == SPECIAL_NUMBER:
            return "特码号码赔率"
        if item.normalized_bet_type == PINGTE_MAIN_ZODIAC:
            return "主肖专用赔率"
        if item.normalized_bet_type == PINGTE_ZODIAC:
            return "平特一肖赔率"
        if item.normalized_bet_type == PING_TAIL:
            return "0尾专用赔率" if item.selection == "0" else "平尾赔率"
        if item.normalized_bet_type == LIANXIAO_ZODIAC:
            return "连肖赔率"
        return "赔率"

    def _engine_for_order(self, order: Any) -> tuple[SettlementEngine, str | None]:
        raw_ruleset = getattr(order, "ruleset_version", FORTUNE_RULESET_2026_V2)
        if not is_v2_ruleset(raw_ruleset):
            value = str(raw_ruleset or "未设置").strip() or "未设置"
            raise SettlementDataError(
                f"订单规则版本 {value} 不受V2结算支持，禁止自动按V2解释"
            )
        raw_year = getattr(order, "zodiac_year", None)
        if raw_year is None:
            year = get_default_zodiac_year()
            return (
                SettlementEngine(
                    zodiac_year=year,
                    ruleset_version=FORTUNE_RULESET_2026_V2,
                ),
                f"订单未记录生肖年份，使用默认年份 {year} 兼容",
            )
        return (
            SettlementEngine(
                zodiac_year=validate_zodiac_year(raw_year),
                ruleset_version=FORTUNE_RULESET_2026_V2,
            ),
            None,
        )

    def _apply_item_rebate(
        self,
        item: ItemSettlementResult,
        plan_items: list[Any],
        plan_name: str | None,
        odds_source: str,
    ) -> ItemSettlementResult:
        if not plan_items:
            return replace(
                item,
                rebate_rate=Decimal("0.00"),
                rebate_amount=Decimal("0.00"),
                rebate_note="未配置返水，按 0 计算",
            )
        rebate_item = self._find_rebate_item(item, plan_items)
        if rebate_item is None:
            return replace(
                item,
                rebate_rate=Decimal("0.00"),
                rebate_amount=Decimal("0.00"),
                rebate_note="未找到返水配置，按 0 计算",
            )
        rebate_percent = Decimal(rebate_item.rebate)
        rebate_rate = (rebate_percent / Decimal("100")).quantize(Decimal("0.0001"))
        rebate_amount = (item.amount * rebate_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        note = (
            f"返水金额 = 投注金额 {_decimal_money(item.amount)} x 返水比例 "
            f"{_decimal_odds(rebate_percent)}%"
        )
        return replace(
            item,
            rebate_rate=rebate_rate,
            rebate_amount=rebate_amount,
            rebate_key_used=str(rebate_item.bet_type).strip(),
            rebate_note=f"{odds_source} / {plan_name or '未配置方案'}：{note}",
        )

    def _find_odds_item(self, item: ItemSettlementResult, plan_items: list[Any]):
        candidates = self._odds_candidates_for_item(item)
        item_by_name = {str(config.bet_type).strip(): config for config in plan_items}
        if item.normalized_bet_type == PING_TAIL and item.selection == "0":
            for candidate in candidates:
                config = item_by_name.get(candidate)
                if config is not None:
                    return config
            return None
        if item.normalized_bet_type in {
            NON_HIT_NUMBER,
            SPECIAL_ZODIAC_GROUP,
            LIANXIAO_ZODIAC,
            PINGTE_ZODIAC,
            PINGTE_MAIN_ZODIAC,
        }:
            for candidate in candidates:
                config = item_by_name.get(candidate)
                if config is not None:
                    return config
        exact = item_by_name.get(str(item.bet_type).strip())
        if exact is not None:
            return exact
        for candidate in candidates:
            config = item_by_name.get(candidate)
            if config is not None:
                return config
        return None

    def _find_rebate_item(self, item: ItemSettlementResult, plan_items: list[Any]):
        item_by_name = {str(config.bet_type).strip(): config for config in plan_items}
        if item.normalized_bet_type in {
            PINGTE_ZODIAC,
            PINGTE_MAIN_ZODIAC,
            PING_TAIL,
            LIANXIAO_ZODIAC,
        }:
            for candidate in self._odds_candidates_for_item(item):
                config = item_by_name.get(candidate)
                if config is not None:
                    return config
        exact = item_by_name.get(str(item.bet_type).strip())
        if exact is not None:
            return exact
        for generic in ("全部", "统一返水", "默认返水"):
            config = item_by_name.get(generic)
            if config is not None:
                return config
        return self._find_odds_item(item, plan_items)

    def _odds_candidates_for_item(self, item: ItemSettlementResult) -> tuple[str, ...]:
        normalized_type = item.normalized_bet_type
        if normalized_type == LIANXIAO_ZODIAC:
            return ("连肖",)
        if normalized_type == SPECIAL_ZODIAC_GROUP:
            count = len(item.selected_zodiacs or ())
            specific = (
                (
                    f"{format_non_hit_count_chinese(count)}连肖",
                    f"{count}连肖",
                )
                if 2 <= count <= 5
                else ()
            )
            if item.bet_type == "多生肖":
                return (*specific, "多生肖", "连肖", "生肖")
            return (*specific, "连肖", "多生肖", "生肖")
        if normalized_type == NUMBER_FUXUAN:
            if item.fuxuan_type == "复2":
                return ("几中几复选", "二中二")
            if item.fuxuan_type == "复3":
                return ("几中几复选", "三中三")
            return ("几中几复选",)
        if normalized_type == NON_HIT_NUMBER:
            count = len(item.selected_numbers or ())
            if count:
                return non_hit_odds_bet_type_candidates(count)
        if normalized_type == PING_TAIL and item.selection == "0":
            return ("平特0尾", "平尾0尾", "0尾")
        return ODDS_CANDIDATES.get(normalized_type or "", ())

    def _validate_limit_offset(self, limit: int, offset: int) -> tuple[int, int]:
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        if offset < 0:
            offset = 0
        return limit, offset

    def _format_unsupported_support(self, results: list[SettlementSupportResult]) -> str:
        return "; ".join(
            f"{result.play_type}/{result.selection}: {result.reason}；{result.suggestion}"
            for result in results
        )

    def _build_result_snapshot(
        self,
        order: Order,
        draw: LotteryDraw,
        preview: OrderSettlementPreview,
        settled_at: datetime,
        *,
        zodiac_year: int,
        warnings: list[str],
    ) -> dict[str, Any]:
        item_snapshots = [self._snapshot_item(item) for item in preview.results]
        snapshot = {
            "ruleset_version": order.ruleset_version,
            "order": {
                "id": order.id,
                "order_no": order.order_no,
                "region": order.region,
                "total_amount": str(order.total_amount),
                "status_before": order.status,
                "zodiac_year": order.zodiac_year,
                "ruleset_version": order.ruleset_version,
            },
            "draw": {
                "id": draw.id,
                "region": draw.region,
                "issue_number": draw.issue_number,
                "draw_date": draw.draw_date.isoformat(),
                "regular_numbers": list(draw.regular_numbers),
                "special_number": draw.special_number,
                "special_zodiac": get_zodiac(draw.special_number, year=zodiac_year),
                "zodiac_year": zodiac_year,
            },
            "warnings": warnings,
            "summary": {
                "total_bet_amount": _decimal_money(preview.total_bet_amount),
                "total_payout_amount": _decimal_money(preview.total_payout_amount),
                "total_rebate_amount": _decimal_money(preview.total_rebate_amount),
                "statistic_net_amount": _decimal_money(preview.statistic_net_amount),
            },
            "settlement": {
                "settled_at": settled_at.isoformat(sep=" "),
                "total_items": preview.total_items,
                "supported_items": preview.supported_items,
                "unsupported_items": preview.unsupported_items,
                "hit_count": preview.winning_items,
                "miss_count": preview.losing_items,
                "total_bet_amount": _decimal_money(preview.total_bet_amount),
                "total_payout_amount": _decimal_money(preview.total_payout_amount),
                "total_rebate_amount": _decimal_money(preview.total_rebate_amount),
                "statistic_net_amount": _decimal_money(preview.statistic_net_amount),
            },
            "items": item_snapshots,
        }
        pingte_items = [
            item
            for item in item_snapshots
            if item["normalized_type"] in {PINGTE_ZODIAC, PINGTE_MAIN_ZODIAC}
        ]
        if pingte_items:
            item_results = [item["item_results"][0] for item in pingte_items]
            hit_items = [item for item in pingte_items if item["is_winner"] is True]
            hit_stake_amount = sum(
                (Decimal(item["stake_amount"]) for item in item_results if item["is_winner"] is True),
                Decimal("0.00"),
            )
            snapshot["pingte_zodiac"] = {
                "zodiac_year": zodiac_year,
                "drawn_numbers": list(pingte_items[0]["drawn_numbers"]),
                "drawn_zodiacs": list(pingte_items[0]["drawn_zodiacs"]),
                "item_results": item_results,
                "hit_selection_count": len(hit_items),
                "missed_selection_count": len(pingte_items) - len(hit_items),
                "hit_stake_amount": _decimal_money(hit_stake_amount),
                "total_winning_amount": _decimal_money(
                    sum((Decimal(item["winning_amount"]) for item in item_results), Decimal("0.00"))
                ),
                "total_rebate_amount": _decimal_money(
                    sum((Decimal(item["rebate_amount"]) for item in item_results), Decimal("0.00"))
                ),
            }
        lianxiao_items = [
            item for item in item_snapshots if item["normalized_type"] == LIANXIAO_ZODIAC
        ]
        if lianxiao_items:
            item_results = [item["item_results"][0] for item in lianxiao_items]
            hit_items = [item for item in item_results if item["is_winner"] is True]
            hit_stake_amount = sum(
                (Decimal(item["stake_amount"]) for item in hit_items),
                Decimal("0.00"),
            )
            total_winning_amount = sum(
                (Decimal(item["winning_amount"]) for item in item_results),
                Decimal("0.00"),
            )
            total_rebate_amount = sum(
                (Decimal(item["rebate_amount"]) for item in item_results),
                Decimal("0.00"),
            )
            total_stake_amount = sum(
                (Decimal(item["stake_amount"]) for item in item_results),
                Decimal("0.00"),
            )
            snapshot["lianxiao"] = {
                "zodiac_year": zodiac_year,
                "drawn_numbers": list(lianxiao_items[0]["drawn_numbers"]),
                "drawn_zodiacs": list(lianxiao_items[0]["drawn_zodiacs"]),
                "item_results": item_results,
                "hit_group_count": len(hit_items),
                "missed_group_count": len(item_results) - len(hit_items),
                "hit_stake_amount": _decimal_money(hit_stake_amount),
                "total_winning_amount": _decimal_money(total_winning_amount),
                "total_rebate_amount": _decimal_money(total_rebate_amount),
                "statistical_settlement_amount": _decimal_money(
                    total_winning_amount + total_rebate_amount - total_stake_amount
                ),
            }
        ping_tail_items = [
            item for item in item_snapshots if item["normalized_type"] == PING_TAIL
        ]
        if ping_tail_items:
            item_results = [item["item_results"][0] for item in ping_tail_items]
            hit_items = [item for item in item_results if item["is_winner"] is True]
            hit_stake_amount = sum(
                (Decimal(item["stake_amount"]) for item in hit_items),
                Decimal("0.00"),
            )
            total_winning_amount = sum(
                (Decimal(item["winning_amount"]) for item in item_results),
                Decimal("0.00"),
            )
            total_rebate_amount = sum(
                (Decimal(item["rebate_amount"]) for item in item_results),
                Decimal("0.00"),
            )
            total_stake_amount = sum(
                (Decimal(item["stake_amount"]) for item in item_results),
                Decimal("0.00"),
            )
            snapshot["ping_tail"] = {
                "selected_tails": [item["selected_tail"] for item in item_results],
                "drawn_numbers": list(ping_tail_items[0]["drawn_numbers"]),
                "drawn_tails": list(ping_tail_items[0]["drawn_tails"]),
                "item_results": item_results,
                "hit_tail_count": len(hit_items),
                "missed_tail_count": len(item_results) - len(hit_items),
                "hit_stake_amount": _decimal_money(hit_stake_amount),
                "total_winning_amount": _decimal_money(total_winning_amount),
                "total_rebate_amount": _decimal_money(total_rebate_amount),
                "statistical_settlement_amount": _decimal_money(
                    total_winning_amount + total_rebate_amount - total_stake_amount
                ),
            }
        return snapshot

    def _snapshot_item(self, item: ItemSettlementResult) -> dict[str, Any]:
        result = (
            "unsupported"
            if item.is_supported is False
            else "hit"
            if item.is_winner is True
            else "miss"
            if item.is_winner is False
            else None
        )
        snapshot = {
            "order_item_id": item.order_item_id,
            "bet_type": item.bet_type,
            "normalized_bet_type": item.normalized_bet_type,
            "normalized_type": item.normalized_bet_type,
            "selection": item.selection,
            "amount": str(item.amount),
            "result": result,
            "is_supported": item.is_supported,
            "is_winner": item.is_winner,
            "matched_number": item.matched_number,
            "reason": item.reason,
            "draw_special_number": item.draw_special_number,
            "draw_special_zodiac": item.draw_special_zodiac,
            "draw_numbers": list(item.draw_numbers),
            "draw_tails": list(item.draw_tails),
            "draw_regular_numbers": list(item.draw_regular_numbers),
            "selected_zodiacs": list(item.selected_zodiacs),
            "missing_zodiacs": list(item.missing_zodiacs),
            "matched_zodiac": item.matched_zodiac,
            "selected_tails": list(item.selected_tails),
            "matched_tails": list(item.matched_tails),
            "selected_tail": item.selected_tail,
            "is_zero_tail": item.is_zero_tail,
            "selected_numbers": list(item.selected_numbers),
            "hit_numbers": list(item.hit_numbers),
            "matched_numbers": list(item.matched_numbers),
            "selected_groups": list(item.selected_groups),
            "matched_groups": list(item.matched_groups),
            "fuxuan_type": item.fuxuan_type,
            "draw_special_wave": item.draw_special_wave,
            "draw_special_odd_even": item.draw_special_odd_even,
            "draw_special_big_small": item.draw_special_big_small,
            "selected_halfwaves": list(item.selected_halfwaves),
            "matched_halfwave": item.matched_halfwave,
            "unsupported_reason": item.unsupported_reason,
            "odds": _decimal_odds(item.odds) if item.odds is not None else None,
            "payout_amount": _decimal_money(item.payout_amount),
            "odds_plan_name": item.odds_plan_name,
            "odds_source": item.odds_source,
            "payout_note": item.payout_note,
            "rebate_rate": _decimal_odds(item.rebate_rate) if item.rebate_rate is not None else None,
            "rebate_amount": _decimal_money(item.rebate_amount),
            "rebate_note": item.rebate_note,
            "ruleset_version": item.ruleset_version,
            "zodiac_year": item.zodiac_year,
            "matcher_id": item.matcher_id,
            "matcher_version": item.matcher_version,
            "odds_key_used": item.odds_key_used,
            "odds_key_candidates": list(item.odds_key_candidates),
            "missing_odds": item.missing_odds,
            "settlement_ready": item.settlement_ready,
            "blocking_reason": item.blocking_reason,
            "rebate_key_used": item.rebate_key_used,
            "payout_tier": item.payout_tier,
            "selection_unit": item.selection_unit,
            "draw_scope": item.draw_scope,
            "duplicate_policy": item.duplicate_policy,
        }
        if item.normalized_bet_type == NON_HIT_NUMBER:
            snapshot.update(
                {
                    "regular_numbers": list(item.regular_numbers),
                    "special_number": item.special_number,
                    "hit_regular_numbers": list(item.hit_regular_numbers),
                }
            )
        if item.normalized_bet_type in {PINGTE_ZODIAC, PINGTE_MAIN_ZODIAC}:
            item_result = {
                "selected_zodiac": item.selected_zodiac,
                "matched_numbers": list(item.matched_numbers),
                "is_winner": item.is_winner,
                "stake_amount": _decimal_money(item.amount),
                "odds": _decimal_odds(item.odds) if item.odds is not None else None,
                "winning_amount": _decimal_money(item.payout_amount),
                "is_main_zodiac": item.is_main_zodiac,
                "odds_key_used": item.odds_key_used,
                "odds_key_candidates": list(item.odds_key_candidates),
                "rebate_key_used": item.rebate_key_used,
                "rebate_amount": _decimal_money(item.rebate_amount),
                "reason": item.reason,
            }
            snapshot.update(
                {
                    "drawn_numbers": list(item.draw_numbers),
                    "drawn_zodiacs": list(item.drawn_zodiacs),
                    "selected_zodiac": item.selected_zodiac,
                    "is_main_zodiac": item.is_main_zodiac,
                    "item_results": [item_result],
                    "hit_selection_count": 1 if item.is_winner is True else 0,
                    "hit_stake_amount": _decimal_money(
                        item.amount if item.is_winner is True else Decimal("0.00")
                    ),
                }
            )
        if item.normalized_bet_type == LIANXIAO_ZODIAC:
            item_result = {
                "selected_zodiacs": list(item.selected_zodiacs),
                "drawn_zodiacs": list(item.drawn_zodiacs),
                "missing_zodiacs": list(item.missing_zodiacs),
                "matched_numbers": list(item.matched_numbers),
                "is_winner": item.is_winner,
                "stake_amount": _decimal_money(item.amount),
                "odds": _decimal_odds(item.odds) if item.odds is not None else None,
                "winning_amount": _decimal_money(item.payout_amount),
                "odds_key_candidates": list(item.odds_key_candidates),
                "odds_key_used": item.odds_key_used,
                "rebate_key_used": item.rebate_key_used,
                "rebate_amount": _decimal_money(item.rebate_amount),
                "missing_odds": item.missing_odds,
                "settlement_ready": item.settlement_ready,
                "reason": item.reason,
            }
            snapshot.update(
                {
                    "drawn_numbers": list(item.draw_numbers),
                    "drawn_zodiacs": list(item.drawn_zodiacs),
                    "selected_zodiacs": list(item.selected_zodiacs),
                    "missing_zodiacs": list(item.missing_zodiacs),
                    "item_results": [item_result],
                    "hit_group_count": 1 if item.is_winner is True else 0,
                    "hit_stake_amount": _decimal_money(
                        item.amount if item.is_winner is True else Decimal("0.00")
                    ),
                }
            )
        if item.normalized_bet_type == PING_TAIL:
            item_result = {
                "selected_tail": item.selected_tail,
                "matched_numbers": list(item.matched_numbers),
                "is_winner": item.is_winner,
                "stake_amount": _decimal_money(item.amount),
                "odds": _decimal_odds(item.odds) if item.odds is not None else None,
                "winning_amount": _decimal_money(item.payout_amount),
                "is_zero_tail": item.is_zero_tail,
                "odds_key_candidates": list(item.odds_key_candidates),
                "odds_key_used": item.odds_key_used,
                "rebate_key_used": item.rebate_key_used,
                "rebate_amount": _decimal_money(item.rebate_amount),
                "missing_odds": item.missing_odds,
                "settlement_ready": item.settlement_ready,
                "reason": item.reason,
            }
            snapshot.update(
                {
                    "drawn_numbers": list(item.draw_numbers),
                    "drawn_tails": list(item.draw_tails),
                    "selected_tail": item.selected_tail,
                    "is_zero_tail": item.is_zero_tail,
                    "item_results": [item_result],
                    "hit_tail_count": 1 if item.is_winner is True else 0,
                    "hit_stake_amount": _decimal_money(
                        item.amount if item.is_winner is True else Decimal("0.00")
                    ),
                }
            )
        return snapshot

    def _to_ledger_result(self, record: SettlementRecord) -> SettlementLedgerResult:
        order = record.order
        log = record.operation_log
        total_payout_amount = self._snapshot_total_payout(record.result_snapshot)
        total_rebate_amount = self._snapshot_total_rebate(record.result_snapshot)
        statistic_net_amount = self._snapshot_statistic_net(record.result_snapshot, total_payout_amount, total_rebate_amount, record.total_amount)
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
            total_payout_amount=total_payout_amount,
            total_rebate_amount=total_rebate_amount,
            statistic_net_amount=statistic_net_amount,
        )


    def _snapshot_total_payout(self, snapshot: object) -> Decimal:
        if isinstance(snapshot, dict):
            summary = snapshot.get("summary")
            if isinstance(summary, dict) and summary.get("total_payout_amount") not in (None, ""):
                try:
                    return Decimal(str(summary["total_payout_amount"])).quantize(CENT)
                except Exception:
                    return Decimal("0.00")
            settlement = snapshot.get("settlement")
            if isinstance(settlement, dict) and settlement.get("total_payout_amount") not in (None, ""):
                try:
                    return Decimal(str(settlement["total_payout_amount"])).quantize(CENT)
                except Exception:
                    return Decimal("0.00")
            items = snapshot.get("items")
            if isinstance(items, list):
                total = Decimal("0.00")
                for item in items:
                    if isinstance(item, dict) and item.get("payout_amount") not in (None, ""):
                        try:
                            total += Decimal(str(item["payout_amount"]))
                        except Exception:
                            continue
                return total.quantize(CENT)
        return Decimal("0.00")

    def _snapshot_total_rebate(self, snapshot: object) -> Decimal:
        if isinstance(snapshot, dict):
            summary = snapshot.get("summary")
            if isinstance(summary, dict) and summary.get("total_rebate_amount") not in (None, ""):
                try:
                    return Decimal(str(summary["total_rebate_amount"])).quantize(CENT)
                except Exception:
                    return Decimal("0.00")
            settlement = snapshot.get("settlement")
            if isinstance(settlement, dict) and settlement.get("total_rebate_amount") not in (None, ""):
                try:
                    return Decimal(str(settlement["total_rebate_amount"])).quantize(CENT)
                except Exception:
                    return Decimal("0.00")
            items = snapshot.get("items")
            if isinstance(items, list):
                total = Decimal("0.00")
                found = False
                for item in items:
                    if isinstance(item, dict) and item.get("rebate_amount") not in (None, ""):
                        found = True
                        try:
                            total += Decimal(str(item["rebate_amount"]))
                        except Exception:
                            continue
                if found:
                    return total.quantize(CENT)
        return Decimal("0.00")

    def _snapshot_statistic_net(
        self,
        snapshot: object,
        total_payout: Decimal,
        total_rebate: Decimal,
        total_amount: Decimal,
    ) -> Decimal:
        if isinstance(snapshot, dict):
            summary = snapshot.get("summary")
            if isinstance(summary, dict) and summary.get("statistic_net_amount") not in (None, ""):
                try:
                    return Decimal(str(summary["statistic_net_amount"])).quantize(CENT)
                except Exception:
                    return Decimal("0.00")
            settlement = snapshot.get("settlement")
            if isinstance(settlement, dict) and settlement.get("statistic_net_amount") not in (None, ""):
                try:
                    return Decimal(str(settlement["statistic_net_amount"])).quantize(CENT)
                except Exception:
                    return Decimal("0.00")
        return (Decimal(total_payout) + Decimal(total_rebate) - Decimal(total_amount)).quantize(CENT)


def _decimal_money(value: Decimal) -> str:
    return f"{Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP):.2f}"


def _decimal_odds(value: Decimal) -> str:
    return str(Decimal(value).normalize())
