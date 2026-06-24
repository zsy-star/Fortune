"""Persistence helpers for local settings-center data."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from models import AppMeta, DeclarerSetting, OddsRebateItem, OddsRebatePlan


class SettingsRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_plans(self) -> list[OddsRebatePlan]:
        stmt = (
            select(OddsRebatePlan)
            .options(selectinload(OddsRebatePlan.items), selectinload(OddsRebatePlan.declarers))
            .order_by(OddsRebatePlan.is_default.desc(), OddsRebatePlan.id.asc())
        )
        return list(self.session.scalars(stmt))

    def get_plan(self, plan_id: int) -> OddsRebatePlan | None:
        stmt = (
            select(OddsRebatePlan)
            .options(selectinload(OddsRebatePlan.items), selectinload(OddsRebatePlan.declarers))
            .where(OddsRebatePlan.id == plan_id)
        )
        return self.session.scalars(stmt).first()

    def get_plan_by_name(self, name: str) -> OddsRebatePlan | None:
        stmt = select(OddsRebatePlan).where(OddsRebatePlan.name == name)
        return self.session.scalars(stmt).first()

    def count_plans(self) -> int:
        return int(self.session.scalar(select(func.count(OddsRebatePlan.id))) or 0)

    def add_plan(self, plan: OddsRebatePlan) -> OddsRebatePlan:
        self.session.add(plan)
        return plan

    def delete_plan(self, plan: OddsRebatePlan) -> None:
        self.session.delete(plan)

    def clear_default_plans(self) -> None:
        self.session.execute(update(OddsRebatePlan).values(is_default=False))

    def get_item(self, item_id: int) -> OddsRebateItem | None:
        return self.session.get(OddsRebateItem, item_id)

    def get_item_by_bet_type(self, plan_id: int, bet_type: str) -> OddsRebateItem | None:
        stmt = select(OddsRebateItem).where(
            OddsRebateItem.plan_id == plan_id,
            OddsRebateItem.bet_type == bet_type,
        )
        return self.session.scalars(stmt).first()

    def add_item(self, item: OddsRebateItem) -> OddsRebateItem:
        self.session.add(item)
        return item

    def delete_item(self, item: OddsRebateItem) -> None:
        self.session.delete(item)

    def list_declarers(self) -> list[DeclarerSetting]:
        stmt = (
            select(DeclarerSetting)
            .options(selectinload(DeclarerSetting.plan))
            .order_by(DeclarerSetting.id.asc())
        )
        return list(self.session.scalars(stmt))

    def get_declarer(self, declarer_id: int) -> DeclarerSetting | None:
        stmt = (
            select(DeclarerSetting)
            .options(selectinload(DeclarerSetting.plan))
            .where(DeclarerSetting.id == declarer_id)
        )
        return self.session.scalars(stmt).first()

    def get_declarer_by_name(self, name: str) -> DeclarerSetting | None:
        stmt = select(DeclarerSetting).where(DeclarerSetting.name == name)
        return self.session.scalars(stmt).first()

    def add_declarer(self, declarer: DeclarerSetting) -> DeclarerSetting:
        self.session.add(declarer)
        return declarer

    def delete_declarer(self, declarer: DeclarerSetting) -> None:
        self.session.delete(declarer)

    def get_meta(self, key: str) -> AppMeta | None:
        stmt = select(AppMeta).where(AppMeta.key == key)
        return self.session.scalars(stmt).first()

    def set_meta(self, key: str, value: str) -> AppMeta:
        meta = self.get_meta(key)
        if meta is None:
            meta = AppMeta(key=key, value=value)
            self.session.add(meta)
        else:
            meta.value = value
        return meta
