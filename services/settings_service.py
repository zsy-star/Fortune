"""Validated read/write service for the local configuration center."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models import DeclarerSetting, OddsRebateItem, OddsRebatePlan
from repositories.settings_repository import SettingsRepository
from schemas.settings_schema import (
    DeclarerSettingResult,
    OddsRebateItemResult,
    OddsRebateItemUpdate,
    OddsRebatePlanResult,
    SecretSettingsResult,
)
from services.log_service import LogService

IMPORT_KEY_META = "settings.import_file_key"
EXPORT_KEY_META = "settings.export_file_key"


class SettingsService:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory
        self._log_service = LogService(session_factory)

    def ensure_default_plan(self) -> OddsRebatePlanResult:
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            plans = repo.list_plans()
            if not plans:
                plan = OddsRebatePlan(name="默认方案", is_default=True)
                repo.add_plan(plan)
                session.flush()
                self._log(session, "create_plan", "创建初始默认赔率/返水配置方案", plan.id)
                session.commit()
                return self._to_plan(plan)
            default = next((plan for plan in plans if plan.is_default), None)
            if default is None:
                plans[0].is_default = True
                self._log(session, "set_default_plan", f"设置默认配置方案：{plans[0].name}", plans[0].id)
                session.commit()
                default = plans[0]
            return self._to_plan(default)

    def list_plans(self) -> list[OddsRebatePlanResult]:
        with self._session_factory() as session:
            return [self._to_plan(plan) for plan in SettingsRepository(session).list_plans()]

    def create_plan(self, name: str, *, make_default: bool = False) -> OddsRebatePlanResult:
        name = self._validate_name(name, "配置方案名称")
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            if repo.get_plan_by_name(name) is not None:
                raise ValueError("配置方案名称不能重复")
            is_first = repo.count_plans() == 0
            if make_default or is_first:
                repo.clear_default_plans()
            plan = OddsRebatePlan(name=name, is_default=make_default or is_first)
            repo.add_plan(plan)
            session.flush()
            self._log(session, "create_plan", f"新增赔率/返水配置方案：{name}", plan.id)
            result = self._to_plan(plan)
            session.commit()
            return result

    def delete_plan(self, plan_id: int) -> None:
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            plan = repo.get_plan(plan_id)
            if plan is None:
                raise ValueError("配置方案不存在")
            if repo.count_plans() <= 1:
                raise ValueError("至少保留一个配置方案")
            if plan.is_default:
                raise ValueError("默认配置方案不能删除，请先设置其他默认方案")
            if plan.declarers:
                raise ValueError("该配置方案已绑定申报人，不能删除")
            name = plan.name
            repo.delete_plan(plan)
            self._log(session, "delete_plan", f"删除赔率/返水配置方案：{name}", plan_id)
            session.commit()

    def set_default_plan(self, plan_id: int) -> OddsRebatePlanResult:
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            plan = repo.get_plan(plan_id)
            if plan is None:
                raise ValueError("配置方案不存在")
            repo.clear_default_plans()
            plan.is_default = True
            self._log(session, "set_default_plan", f"设置默认配置方案：{plan.name}", plan.id)
            session.flush()
            result = self._to_plan(plan)
            session.commit()
            return result

    def add_item(
        self,
        plan_id: int,
        bet_type: str,
        odds: Decimal | int | float | str,
        rebate: Decimal | int | float | str,
    ) -> OddsRebateItemResult:
        bet_type = self._validate_name(bet_type, "投注类型")
        odds_value = self._validate_odds(odds)
        rebate_value = self._validate_rebate(rebate)
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            plan = repo.get_plan(plan_id)
            if plan is None:
                raise ValueError("配置方案不存在")
            if repo.get_item_by_bet_type(plan_id, bet_type) is not None:
                raise ValueError("当前方案已存在该投注类型")
            item = OddsRebateItem(
                plan_id=plan_id,
                bet_type=bet_type,
                odds=odds_value,
                rebate=rebate_value,
            )
            repo.add_item(item)
            session.flush()
            self._log(session, "add_rate_item", f"方案 {plan.name} 新增配置项：{bet_type}", item.id)
            result = self._to_item(item)
            session.commit()
            return result

    def update_items(
        self,
        plan_id: int,
        updates: list[OddsRebateItemUpdate],
    ) -> OddsRebatePlanResult:
        validated = [
            (update.id, self._validate_odds(update.odds), self._validate_rebate(update.rebate))
            for update in updates
        ]
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            plan = repo.get_plan(plan_id)
            if plan is None:
                raise ValueError("配置方案不存在")
            for item_id, odds, rebate in validated:
                item = repo.get_item(item_id)
                if item is None or item.plan_id != plan_id:
                    raise ValueError("配置项不存在或不属于当前方案")
                item.odds = odds
                item.rebate = rebate
            self._log(session, "save_rate_items", f"保存方案配置项：{plan.name}", plan.id)
            session.flush()
            result = self._to_plan(plan)
            session.commit()
            return result

    def delete_item(self, plan_id: int, item_id: int) -> None:
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            item = repo.get_item(item_id)
            if item is None or item.plan_id != plan_id:
                raise ValueError("配置项不存在或不属于当前方案")
            bet_type = item.bet_type
            repo.delete_item(item)
            self._log(session, "delete_rate_item", f"删除赔率/返水配置项：{bet_type}", item_id)
            session.commit()

    def list_declarers(self) -> list[DeclarerSettingResult]:
        with self._session_factory() as session:
            return [self._to_declarer(row) for row in SettingsRepository(session).list_declarers()]

    def add_declarer(self, name: str, plan_id: int) -> DeclarerSettingResult:
        name = self._validate_name(name, "申报人名称")
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            plan = repo.get_plan(plan_id)
            if plan is None:
                raise ValueError("赔率配置方案不存在")
            if repo.get_declarer_by_name(name) is not None:
                raise ValueError("申报人名称不能重复")
            declarer = DeclarerSetting(name=name, plan_id=plan_id)
            repo.add_declarer(declarer)
            session.flush()
            declarer.plan = plan
            self._log(session, "add_declarer", f"新增申报人：{name}", declarer.id)
            result = self._to_declarer(declarer)
            session.commit()
            return result

    def update_declarer_plan(self, declarer_id: int, plan_id: int) -> DeclarerSettingResult:
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            declarer = repo.get_declarer(declarer_id)
            plan = repo.get_plan(plan_id)
            if declarer is None:
                raise ValueError("申报人不存在")
            if plan is None:
                raise ValueError("赔率配置方案不存在")
            declarer.plan_id = plan_id
            declarer.plan = plan
            self._log(session, "bind_declarer_plan", f"申报人 {declarer.name} 绑定方案：{plan.name}", declarer.id)
            session.flush()
            result = self._to_declarer(declarer)
            session.commit()
            return result

    def delete_declarer(self, declarer_id: int) -> None:
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            declarer = repo.get_declarer(declarer_id)
            if declarer is None:
                raise ValueError("申报人不存在")
            name = declarer.name
            repo.delete_declarer(declarer)
            self._log(session, "delete_declarer", f"删除申报人：{name}", declarer_id)
            session.commit()

    def get_secret_settings(self) -> SecretSettingsResult:
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            import_meta = repo.get_meta(IMPORT_KEY_META)
            export_meta = repo.get_meta(EXPORT_KEY_META)
            return SecretSettingsResult(
                import_key=import_meta.value or "" if import_meta else "",
                export_key=export_meta.value or "" if export_meta else "",
            )

    def save_secret_settings(self, import_key: str, export_key: str) -> SecretSettingsResult:
        import_key = str(import_key)
        export_key = str(export_key)
        if len(import_key) > 512 or len(export_key) > 512:
            raise ValueError("秘钥长度不能超过 512 个字符")
        with self._session_factory() as session:
            repo = SettingsRepository(session)
            repo.set_meta(IMPORT_KEY_META, import_key)
            repo.set_meta(EXPORT_KEY_META, export_key)
            self._log(session, "save_file_keys", "保存导入/导出秘钥配置（未记录秘钥内容）")
            session.commit()
        return SecretSettingsResult(import_key=import_key, export_key=export_key)

    def _validate_name(self, value: str, label: str) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{label}不能为空")
        if len(text) > 128:
            raise ValueError(f"{label}不能超过 128 个字符")
        return text

    def _to_decimal(self, value, label: str) -> Decimal:
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f"{label}必须是有效数字") from None
        if not result.is_finite():
            raise ValueError(f"{label}必须是有效数字")
        return result

    def _validate_odds(self, value) -> Decimal:
        odds = self._to_decimal(value, "赔率")
        if odds <= 0:
            raise ValueError("赔率必须大于 0")
        return odds

    def _validate_rebate(self, value) -> Decimal:
        rebate = self._to_decimal(value, "返水")
        if rebate < 0 or rebate > 100:
            raise ValueError("返水必须在 0 到 100 之间")
        return rebate

    def _to_item(self, item: OddsRebateItem) -> OddsRebateItemResult:
        return OddsRebateItemResult(
            id=item.id,
            plan_id=item.plan_id,
            bet_type=item.bet_type,
            odds=Decimal(item.odds),
            rebate=Decimal(item.rebate),
        )

    def _to_plan(self, plan: OddsRebatePlan) -> OddsRebatePlanResult:
        return OddsRebatePlanResult(
            id=plan.id,
            name=plan.name,
            is_default=plan.is_default,
            items=tuple(self._to_item(item) for item in plan.items),
        )

    def _to_declarer(self, declarer: DeclarerSetting) -> DeclarerSettingResult:
        return DeclarerSettingResult(
            id=declarer.id,
            name=declarer.name,
            plan_id=declarer.plan_id,
            plan_name=declarer.plan.name,
        )

    def _log(
        self,
        session: Session,
        action: str,
        description: str,
        related_id: int | None = None,
    ) -> None:
        self._log_service.create_log(
            module="settings",
            action=action,
            description=description,
            related_type="settings",
            related_id=related_id,
            session=session,
        )
