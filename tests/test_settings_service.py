from __future__ import annotations

from decimal import Decimal

import pytest

from schemas.settings_schema import OddsRebateItemUpdate
from services.log_service import LogService
from services.settings_service import SettingsService


def test_default_plan_is_created_once_and_persisted(session_factory) -> None:
    service = SettingsService(session_factory)

    first = service.ensure_default_plan()
    second = SettingsService(session_factory).ensure_default_plan()

    assert first.id == second.id
    assert first.name == "默认方案"
    assert first.is_default
    assert len(service.list_plans()) == 1


def test_plan_add_default_and_delete_safety(session_factory) -> None:
    service = SettingsService(session_factory)
    default = service.ensure_default_plan()
    custom = service.create_plan("47倍4水")

    assert [plan.name for plan in service.list_plans()] == ["默认方案", "47倍4水"]
    with pytest.raises(ValueError, match="默认配置方案不能删除"):
        service.delete_plan(default.id)

    service.set_default_plan(custom.id)
    service.delete_plan(default.id)
    remaining = service.list_plans()
    assert len(remaining) == 1
    assert remaining[0].name == "47倍4水"
    with pytest.raises(ValueError, match="至少保留一个"):
        service.delete_plan(custom.id)


def test_rate_item_add_edit_validation_and_persistence(session_factory) -> None:
    service = SettingsService(session_factory)
    plan = service.ensure_default_plan()
    item = service.add_item(plan.id, "特码", "47", "4")

    saved = SettingsService(session_factory).list_plans()[0].items[0]
    assert saved.bet_type == "特码"
    assert saved.odds == Decimal("47.0000")
    assert saved.rebate == Decimal("4.00")

    service.update_items(
        plan.id,
        [OddsRebateItemUpdate(id=item.id, odds="48.5", rebate="3.5")],
    )
    updated = SettingsService(session_factory).list_plans()[0].items[0]
    assert updated.odds == Decimal("48.5000")
    assert updated.rebate == Decimal("3.50")

    with pytest.raises(ValueError, match="赔率必须大于"):
        service.add_item(plan.id, "平码", "0", "1")
    with pytest.raises(ValueError, match="赔率必须是有效数字"):
        service.add_item(plan.id, "连肖", "", "1")
    with pytest.raises(ValueError, match="返水必须是有效数字"):
        service.add_item(plan.id, "连尾", "10", "")
    with pytest.raises(ValueError, match="0 到 100"):
        service.add_item(plan.id, "连肖", "10", "101")
    with pytest.raises(ValueError, match="已存在"):
        service.add_item(plan.id, "特码", "49", "2")


def test_declarer_add_bind_duplicate_and_plan_delete_safety(session_factory) -> None:
    service = SettingsService(session_factory)
    default = service.ensure_default_plan()
    custom = service.create_plan("46倍6水")
    declarer = service.add_declarer("林林", default.id)

    assert declarer.plan_name == "默认方案"
    rebound = service.update_declarer_plan(declarer.id, custom.id)
    assert rebound.plan_id == custom.id
    assert SettingsService(session_factory).list_declarers()[0].plan_name == "46倍6水"
    with pytest.raises(ValueError, match="不能重复"):
        service.add_declarer("林林", default.id)
    with pytest.raises(ValueError, match="已绑定申报人"):
        service.delete_plan(custom.id)

    service.delete_declarer(declarer.id)
    service.delete_plan(custom.id)
    assert service.list_declarers() == []


def test_secret_settings_save_reload_and_do_not_log_values(session_factory) -> None:
    service = SettingsService(session_factory)
    saved = service.save_secret_settings("import-secret", "export-secret")
    reloaded = SettingsService(session_factory).get_secret_settings()

    assert saved == reloaded
    assert reloaded.import_key == "import-secret"
    assert reloaded.export_key == "export-secret"
    logs = LogService(session_factory).list_logs(module="settings", action="save_file_keys")
    assert len(logs) == 1
    assert "import-secret" not in logs[0].description
    assert "export-secret" not in logs[0].description
