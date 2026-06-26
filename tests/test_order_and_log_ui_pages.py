from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QItemSelectionModel
from PySide6.QtWidgets import QApplication

from models import Order, SettlementRecord
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.log_service import LogService
from services.order_service import OrderService
from services.settlement_service import SettlementService
from services.settings_service import SettingsService
from ui.app_events import app_events
from ui.pages.operation_log_page import OperationLogPage
from ui.pages.order_detail_page import OrderDetailPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(service: OrderService, *, customer: str = "张三", region: str = "澳门", channel: str = "微信"):
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel=channel,
            region=region,
            raw_text="1各10\n2各20",
            source="test",
            items=[
                OrderItemCreate(bet_type="特码", selection="1", amount="10"),
                OrderItemCreate(bet_type="特码", selection="2", amount="20"),
            ],
        )
    )


def create_single_item_order(
    service: OrderService,
    *,
    selection: str,
    customer: str,
    region: str = "澳门",
):
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel="测试渠道",
            region=region,
            raw_text=f"特码 {selection} 各10",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection=selection, amount="10")],
        )
    )


def create_typed_order(
    service: OrderService,
    *,
    bet_type: str,
    selection: str,
    customer: str,
    region: str = "澳门",
):
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel="测试渠道",
            region=region,
            raw_text=f"{bet_type} {selection} 10",
            source="test",
            items=[OrderItemCreate(bet_type=bet_type, selection=selection, amount="10")],
        )
    )


def create_settlement_draw(session_factory, *, region: str = "澳门", issue: str = "UI-162"):
    return DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region=region,
            issue_number=issue,
            draw_date=date(2026, 6, 24),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="01",
            source="test",
        )
    )


def table_winning_status(page: OrderDetailPage, order_no: str) -> str:
    for row in range(page._table.rowCount()):
        if page._table.item(row, 6).text() == order_no:
            return page._table.item(row, 8).text()
    raise AssertionError(f"order not found in table: {order_no}")


def select_order_row(page: OrderDetailPage, order_no: str) -> None:
    for row in range(page._table.rowCount()):
        if page._table.item(row, 6).text() == order_no:
            page._table.selectRow(row)
            return
    raise AssertionError(f"order not found in table: {order_no}")


def test_order_detail_page_empty_state(session_factory) -> None:
    app()
    page = OrderDetailPage(order_service=OrderService(session_factory), log_service=LogService(session_factory))
    page.reload_data()
    assert page._table.rowCount() == 0
    assert "暂无订单数据" in page._status_label.text()
    assert all(not button.isEnabled() for button in page.findChildren(type(page._btn_prev)) if button.objectName() == "toolBtn")


def test_order_detail_page_loads_filters_and_details(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    result = create_order(service)
    create_order(service, customer="李四", region="香港", channel="现金")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))

    assert page._table.rowCount() == 2
    page._cmb_declarer.setCurrentText("张三")
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 7).text() == "张三"
    assert page._table.item(0, 4).text() == "30.00"

    page._table.selectRow(0)
    page._on_selection_changed()
    assert result.order_no in page._detail_info.text()
    assert page._item_table.rowCount() == 2
    assert page._item_table.item(0, 2).text() == "10.00"
    assert LogService(session_factory).count_logs(module="订单详情", action="查看订单") == 1


def test_order_detail_declarer_filter_merges_settings_and_history(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    create_order(order_service, customer="历史申报人")
    settings_service = SettingsService(session_factory)
    plan = settings_service.ensure_default_plan()
    settings_service.add_declarer("配置申报人", plan.id)

    page = OrderDetailPage(
        order_service=order_service,
        log_service=LogService(session_factory),
        settings_service=settings_service,
    )

    options = [page._cmb_declarer.itemText(index) for index in range(page._cmb_declarer.count())]
    assert options == ["不限申报人", "配置申报人", "历史申报人"]


def test_order_detail_declarer_filter_empty_sources_is_safe(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        settings_service=SettingsService(session_factory),
    )

    assert page._cmb_declarer.count() == 1
    assert page._cmb_declarer.currentText() == "不限申报人"
    assert page._table.rowCount() == 0


def test_order_detail_declarer_filter_refreshes_on_settings_changed(session_factory) -> None:
    app()
    settings_service = SettingsService(session_factory)
    plan = settings_service.ensure_default_plan()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        settings_service=settings_service,
    )
    assert page._cmb_declarer.findText("新增申报人") < 0

    settings_service.add_declarer("新增申报人", plan.id)
    app_events.settings_changed.emit()

    assert page._cmb_declarer.findText("新增申报人") >= 0


def test_order_detail_filters_exact_declarer_and_combines_conditions(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    exact = create_order(service, customer="张", region="澳门")
    create_order(service, customer="张三", region="澳门")
    hk = create_order(service, customer="李四", region="香港")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))

    page._cmb_declarer.setCurrentText("张")
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 6).text() == exact.order_no
    assert page._table.item(0, 7).text() == "张"

    page._cmb_region.setCurrentText("香港")
    page._cmb_declarer.setCurrentText("李四")
    page._edit_order_no.setText(hk.order_no)
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 6).text() == hk.order_no

    page._on_reset()
    assert page._cmb_declarer.currentIndex() == 0
    assert page._cmb_declarer.currentText() == "不限申报人"
    assert page._table.rowCount() == 3


def test_order_detail_business_layout_and_core_entries(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )

    headers = [page._table.horizontalHeaderItem(index).text() for index in range(page._table.columnCount())]
    assert headers == [
        "订单信息",
        "复式类型",
        "计算方式",
        "金额",
        "订单总额",
        "是否自定义",
        "订单序号",
        "申报人",
        "中奖情况",
        "中奖金额",
        "备注",
    ]
    assert page._btn_query.isEnabled()
    assert page._btn_refresh.isEnabled()
    assert page._btn_export_excel.isEnabled()
    assert not page._btn_preview.isEnabled()
    assert not page._btn_void.isEnabled()


def test_order_detail_remaining_unavailable_actions_are_explicitly_disabled(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )

    buttons = [
        page._btn_clear_orders,
        page._btn_reset_draw,
    ]
    assert all(not button.isEnabled() for button in buttons)
    assert all("暂未开放" in button.toolTip() for button in buttons)
    assert page._btn_import_orders.isEnabled()
    assert page._btn_import_orders.text() == "导入订单"
    assert "预览" in page._btn_import_orders.toolTip()
    assert page._btn_filter_prize.isEnabled()
    assert page._btn_filter_prize.text() == "过滤结算结果"
    assert page._btn_combined_prize.isEnabled()
    assert page._btn_combined_prize.text() == "综合结算摘要"
    assert page._btn_expand_prize.isEnabled()
    assert page._cmb_bet_type.isEnabled()
    assert page._cmb_winning.isEnabled()
    assert page._cmb_toolbar_placeholder.isEnabled()


def test_order_detail_bet_type_filter_loads_and_filters_real_items(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    special = create_typed_order(service, bet_type="特码", selection="01", customer="特码客户")
    create_typed_order(service, bet_type="特码波色", selection="红波", customer="波色客户")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))

    options = [page._cmb_bet_type.itemText(index) for index in range(page._cmb_bet_type.count())]
    assert options[0] == "不限投注类型"
    assert "特码" in options
    assert "特码波色" in options

    page._cmb_bet_type.setCurrentText("特码")
    page._on_query()

    assert page._table.rowCount() == 1
    assert page._table.item(0, 6).text() == special.order_no

    page._on_reset()
    assert page._cmb_bet_type.currentText() == "不限投注类型"
    assert page._table.rowCount() == 2


def test_order_detail_selected_and_current_totals(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, customer="甲")
    create_order(service, customer="乙")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))

    assert page._lbl_current_total.text() == "当前订单总额：60.00"
    page._table.selectRow(0)
    selection = page._table.selectionModel()
    selection.select(
        page._table.model().index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )

    assert page._lbl_selected_total.text() == "选中总额：60.00"
    assert page._lbl_order_state.text() == "订单状态：未结算"


def test_order_detail_draw_area_has_empty_placeholders(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )

    for region in ("澳门", "香港"):
        placeholder = page._draw_widgets[region]["placeholder"]
        assert placeholder.text() == "暂无开奖数据"


def test_order_detail_draw_area_refreshes_on_draws_changed(session_factory) -> None:
    app()
    draw_service = DrawService(session_factory)
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        draw_service=draw_service,
    )
    assert page._draw_widgets["澳门"]["placeholder"].text() == "暂无开奖数据"

    draw_service.create_draw(
        LotteryDrawCreate(
            region="澳门",
            issue_number="AUTO-1",
            draw_date=date(2026, 6, 25),
            regular_numbers=["01", "02", "03", "04", "05", "06"],
            special_number="07",
            source="test",
        )
    )
    app_events.draws_changed.emit()

    assert "AUTO-1" in page._draw_widgets["澳门"]["title"].text()
    assert page._draw_widgets["澳门"]["placeholder"].isHidden()


def test_order_detail_unsettled_order_keeps_amount_unavailable(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    order = create_single_item_order(service, selection="01", customer="未结算")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))

    assert table_winning_status(page, order.order_no) == "未结算"
    row = next(row for row in range(page._table.rowCount()) if page._table.item(row, 6).text() == order.order_no)
    assert page._table.item(row, 9).text() == "—"
    select_order_row(page, order.order_no)
    assert page._macau_result.toPlainText() == "当前订单未结算，暂无兑奖结果。"
    assert page._combined_result.toPlainText() == "当前订单未结算，暂无兑奖结果。"


def test_order_detail_uses_persisted_counts_for_winning_statuses(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    hit = create_single_item_order(service, selection="01", customer="命中")
    miss = create_single_item_order(service, selection="02", customer="未中")
    partial = create_order(service, customer="部分命中")
    unsupported = create_single_item_order(service, selection="01", customer="含不支持")
    draw = create_settlement_draw(session_factory)
    settlement_service = SettlementService(session_factory)
    for order in (hit, miss, partial, unsupported):
        settlement_service.commit_order_settlement(order.id, draw.id)

    with session_factory() as session:
        record = session.query(SettlementRecord).filter_by(order_id=unsupported.id).one()
        record.unsupported_count = 1
        record.total_items = 2
        record.result_snapshot = {
            "items": [
                {
                    "bet_type": "特码",
                    "selection": "01",
                    "is_supported": True,
                    "is_winner": True,
                },
                {
                    "bet_type": "连肖",
                    "selection": "马,蛇",
                    "is_supported": False,
                    "is_winner": None,
                },
            ]
        }
        session.commit()

    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))
    assert table_winning_status(page, hit.order_no) == "命中"
    assert table_winning_status(page, miss.order_no) == "未中"
    assert table_winning_status(page, partial.order_no) == "部分命中"
    assert table_winning_status(page, unsupported.order_no) == "含不支持"


def test_order_detail_winning_filter_uses_persisted_settlement_counts(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    unsettled = create_single_item_order(service, selection="01", customer="未结算")
    hit = create_single_item_order(service, selection="01", customer="命中")
    miss = create_single_item_order(service, selection="02", customer="未中")
    partial = create_order(service, customer="部分命中")
    unsupported = create_single_item_order(service, selection="01", customer="含不支持")
    draw = create_settlement_draw(session_factory)
    settlement_service = SettlementService(session_factory)
    for order in (hit, miss, partial, unsupported):
        settlement_service.commit_order_settlement(order.id, draw.id)

    with session_factory() as session:
        record = session.query(SettlementRecord).filter_by(order_id=unsupported.id).one()
        record.unsupported_count = 1
        record.total_items = 2
        record.result_snapshot = {
            "items": [
                {"bet_type": "特码", "selection": "01", "is_supported": True, "is_winner": True},
                {"bet_type": "连肖", "selection": "马,蛇", "is_supported": False, "is_winner": None},
            ]
        }
        session.commit()

    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))
    cases = {
        "未结算": unsettled.order_no,
        "命中": hit.order_no,
        "未中": miss.order_no,
        "部分命中": partial.order_no,
        "含不支持": unsupported.order_no,
    }
    for winning_filter, expected_order_no in cases.items():
        page._cmb_winning.setCurrentText(winning_filter)
        page._on_query()
        assert page._table.rowCount() == 1
        assert page._table.item(0, 6).text() == expected_order_no

    page._cmb_winning.setCurrentText("已结算")
    page._on_query()
    assert page._table.rowCount() == 4

    page._on_reset()
    assert page._cmb_winning.currentText() == "不限中奖"
    assert page._table.rowCount() == 5


def test_order_detail_winning_filter_does_not_recalculate_settlement(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_single_item_order(service, selection="01", customer="未结算")
    settlement_service = SettlementService(session_factory)

    with patch.object(settlement_service, "preview_order", side_effect=AssertionError("should not recalculate")):
        page = OrderDetailPage(
            order_service=service,
            log_service=LogService(session_factory),
            settlement_service=settlement_service,
        )
        page._cmb_winning.setCurrentText("未结算")
        page._on_query()

    assert page._table.rowCount() == 1


def test_order_detail_filter_and_combined_settlement_summary_are_readonly(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, customer="未结算")
    hit = create_single_item_order(service, selection="01", customer="命中")
    draw = create_settlement_draw(session_factory)
    SettlementService(session_factory).commit_order_settlement(hit.id, draw.id)
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))
    log_count_before = LogService(session_factory).count_logs()

    with patch("ui.pages.order_detail_page.QMessageBox.information") as info:
        page._on_filter_settlement_results()
        page._on_combined_settlement_summary()

    assert info.call_count == 2
    assert "订单数：2" in page._combined_result.toPlainText()
    assert "中奖金额：—" in page._combined_result.toPlainText()
    assert LogService(session_factory).count_logs() == log_count_before


def test_order_detail_expand_and_collapse_result_panel(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )

    assert page._macau_result.maximumHeight() == 82
    page._on_toggle_result_panel_size()
    assert page._btn_expand_prize.text() == "收起兑奖框"
    assert page._macau_result.maximumHeight() > 82
    page._on_toggle_result_panel_size()
    assert page._btn_expand_prize.text() == "扩大兑奖框"
    assert page._macau_result.maximumHeight() == 82


def test_order_detail_business_action_combo_has_no_silent_entries(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )

    actions = [
        page._cmb_toolbar_placeholder.itemData(index)
        for index in range(1, page._cmb_toolbar_placeholder.count())
    ]
    assert actions == ["detail", "preview", "void"]

    page._on_business_action_selected(page._cmb_toolbar_placeholder.findData("detail"))
    assert "请先选择订单" in page._status_label.text()


def test_order_detail_selected_settlement_summary_uses_snapshot(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    order = create_order(service, customer="摘要客户")
    draw = create_settlement_draw(session_factory)
    SettlementService(session_factory).commit_order_settlement(order.id, draw.id)
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))

    select_order_row(page, order.order_no)

    macau_text = page._macau_result.toPlainText()
    assert f"订单 ID：{order.id}" in macau_text
    assert "地区：澳门" in macau_text
    assert "期号：UI-162" in macau_text
    assert "命中数：1" in macau_text
    assert "未命中数：1" in macau_text
    assert "不支持数：0" in macau_text
    assert "总明细数：2" in macau_text
    assert "总金额：30.00" in macau_text
    assert "特码/01：命中" in macau_text
    assert "特码/02：未中" in macau_text
    assert "订单 ID" not in page._hong_kong_result.toPlainText()
    assert page._combined_result.toPlainText() == macau_text


def test_order_detail_historical_settled_order_without_record(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    order = create_single_item_order(service, selection="01", customer="历史订单")
    with session_factory() as session:
        saved = session.get(Order, order.id)
        assert saved is not None
        saved.status = "settled"
        session.commit()

    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))
    select_order_row(page, order.order_no)

    expected = "该订单为历史已结算订单，但暂无结算快照记录。"
    assert table_winning_status(page, order.order_no) == "已结算"
    assert page._macau_result.toPlainText() == expected
    assert page._combined_result.toPlainText() == expected


def test_order_detail_malformed_snapshot_does_not_crash(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    order = create_single_item_order(service, selection="01", customer="坏快照")
    draw = create_settlement_draw(session_factory)
    SettlementService(session_factory).commit_order_settlement(order.id, draw.id)
    with session_factory() as session:
        record = session.query(SettlementRecord).filter_by(order_id=order.id).one()
        record.result_snapshot = {"items": "not-a-list"}
        session.commit()

    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))
    select_order_row(page, order.order_no)

    assert "快照数据为空或格式不完整" in page._macau_result.toPlainText()
    assert "快照数据为空或格式不完整" in page._combined_result.toPlainText()


def test_order_detail_page_pagination_state(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    for idx in range(21):
        create_order(service, customer=f"客户{idx}")
    page = OrderDetailPage(order_service=service, log_service=LogService(session_factory))
    assert page._table.rowCount() == 20
    assert not page._btn_prev.isEnabled()
    assert page._btn_next.isEnabled()
    page._next_page()
    assert page._table.rowCount() == 1


def test_operation_log_page_empty_state(session_factory) -> None:
    app()
    page = OperationLogPage(log_service=LogService(session_factory))
    assert page._table.rowCount() == 0
    assert page._lbl_total.text() == "暂无操作日志"


def test_operation_log_page_loads_filters_reset_and_paging(session_factory) -> None:
    app()
    service = LogService(session_factory)
    for idx in range(22):
        service.create_log(
            module="draw_sync" if idx % 2 == 0 else "order",
            action="success",
            description=f"同步日志 {idx}",
            related_type="draw",
            related_id=idx,
        )
    page = OperationLogPage(log_service=service)
    assert page._table.rowCount() == 20
    assert "17203" not in page._lbl_total.text()
    assert page._btn_next.isEnabled()
    page._module.setText("draw")
    page._on_query()
    assert page._total == 11
    page._keyword.setText("日志 2")
    page._on_query()
    assert page._total >= 1
    page._on_reset()
    assert page._total == 22
    assert page._table.item(0, 3).toolTip()


def test_operation_log_page_date_validation_and_clear_disabled(session_factory) -> None:
    app()
    page = OperationLogPage(log_service=LogService(session_factory))
    page._start_date.setDate(QDate(2026, 1, 2))
    page._end_date.setDate(QDate(2026, 1, 1))
    page.reload_data()
    assert "开始日期不能晚于结束日期" in page._lbl_total.text()
    page._on_clear_disabled()
    assert "暂未开放" in page._lbl_total.text()
