from __future__ import annotations

import os
from datetime import date
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.draw_service import DrawService
from services.log_service import LogService
from services.order_service import OrderService
from services.settlement_service import SettlementService
from ui.dialogs.settlement_preview_dialog import SettlementPreviewDialog
from ui.pages.order_detail_page import OrderDetailPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(
    service: OrderService,
    *,
    customer: str = "张三",
    region: str = "澳门",
    channel: str = "微信",
    items: list[OrderItemCreate] | None = None,
):
    if items is None:
        items = [
            OrderItemCreate(bet_type="特码", selection="01", amount="10.00"),
            OrderItemCreate(bet_type="特码", selection="02", amount="20.00"),
            OrderItemCreate(bet_type="连肖", selection="马蛇", amount="30.00"),
        ]
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel=channel,
            region=region,
            raw_text="preview test",
            source="test",
            items=items,
        )
    )


def create_draw(
    service: DrawService,
    *,
    region: str = "澳门",
    issue: str = "162",
    special: str = "01",
):
    return service.create_draw(
        LotteryDrawCreate(
            region=region,
            issue_number=issue,
            draw_date=date(2026, 6, 11),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number=special,
            source="test_source",
        )
    )


def open_preview_dialog(session_factory, order_id: int) -> SettlementPreviewDialog:
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    settlement_service = SettlementService(session_factory)
    dialog = SettlementPreviewDialog(
        order_id,
        order_service=order_service,
        draw_service=draw_service,
        settlement_service=settlement_service,
    )
    return dialog


def test_dialog_shows_order_info(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    order = create_order(order_service, customer="预览客户", channel="现金")
    dialog = open_preview_dialog(session_factory, order.id)

    assert dialog._lbl_order_no.text() == order.order_no
    assert dialog._lbl_region.text() == "澳门"
    assert dialog._lbl_total.text() == "60.00"
    assert dialog._lbl_customer.text() == "预览客户"
    assert dialog._lbl_channel.text() == "现金"
    assert dialog._lbl_status.text() == "active"
    assert "2026" in dialog._lbl_created.text()


def test_dialog_loads_only_order_region_draws(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = create_order(order_service, region="澳门")
    create_draw(draw_service, region="澳门", issue="162", special="32")
    create_draw(draw_service, region="香港", issue="100", special="11")

    dialog = open_preview_dialog(session_factory, order.id)

    assert dialog._cmb_draw.count() == 1
    assert "162" in dialog._cmb_draw.currentText()
    assert "香港" not in dialog._cmb_draw.currentText()


def test_dialog_default_draw_without_auto_preview(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = create_order(order_service)
    create_draw(draw_service, issue="163", special="32")
    create_draw(draw_service, issue="162", special="01")

    dialog = open_preview_dialog(session_factory, order.id)

    assert dialog._cmb_draw.currentIndex() == 0
    assert "163" in dialog._cmb_draw.currentText()
    assert dialog._lbl_total_items.text() == "—"
    assert dialog._result_table.rowCount() == 0


def test_dialog_no_draws_disables_preview(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    order = create_order(order_service)

    dialog = open_preview_dialog(session_factory, order.id)

    assert not dialog._lbl_no_draws.isHidden()
    assert not dialog._btn_preview.isEnabled()
    assert not dialog._cmb_draw.isEnabled()
    assert dialog._cmb_draw.count() == 0


def test_dialog_invalid_order_rejects(session_factory) -> None:
    app()
    dialog = open_preview_dialog(session_factory, 999999)
    assert not dialog.is_valid()
    assert not hasattr(dialog, "_order_detail")


def test_draw_detail_updates_on_issue_change(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = create_order(order_service)
    create_draw(draw_service, issue="162", special="01")
    create_draw(draw_service, issue="163", special="32")

    dialog = open_preview_dialog(session_factory, order.id)
    assert "163" in dialog._cmb_draw.itemText(0)
    dialog._cmb_draw.setCurrentIndex(1)

    assert dialog._lbl_special.text() == "01"
    assert "162" in dialog._cmb_draw.currentText()
    assert dialog._lbl_regular.text() == "02 03 04 05 06 07"
    assert dialog._lbl_draw_date.text() == "2026-06-11"
    assert dialog._lbl_source.text() == "test_source"


def test_refresh_draws_reads_database_only(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = create_order(order_service)
    create_draw(draw_service, issue="162")

    dialog = open_preview_dialog(session_factory, order.id)
    with patch("requests.get") as get_mock:
        dialog._reload_draws()
        get_mock.assert_not_called()
    assert dialog._cmb_draw.count() == 1


def test_preview_supported_winning_losing_and_unsupported(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = create_order(order_service)
    create_draw(draw_service, issue="162", special="01")

    dialog = open_preview_dialog(session_factory, order.id)
    dialog._on_start_preview()

    assert dialog._lbl_total_items.text() == "3"
    assert dialog._lbl_supported.text() == "2"
    assert dialog._lbl_unsupported.text() == "1"
    assert dialog._lbl_winning.text() == "1"
    assert dialog._lbl_losing.text() == "1"
    assert dialog._result_table.rowCount() == 3

    assert dialog._result_table.item(0, 4).text() == "中奖"
    assert dialog._result_table.item(1, 4).text() == "未中奖"
    assert dialog._result_table.item(2, 4).text() == "暂不支持"
    assert dialog._result_table.item(2, 3).text() == "否"
    assert dialog._result_table.item(0, 2).text() == "10.00"
    assert dialog._result_table.item(0, 5).text() == "01"
    assert dialog._result_table.item(1, 5).text() == "—"
    assert dialog._result_table.item(0, 6).toolTip() == dialog._result_table.item(0, 6).text()


def test_preview_does_not_modify_order_or_logs(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    log_service = LogService(session_factory)
    order = create_order(order_service)
    draw = create_draw(draw_service)

    before_order = order_service.get_order(order.id)
    before_logs = log_service.count_logs()
    before_draws = draw_service.count_draws()

    dialog = open_preview_dialog(session_factory, order.id)
    dialog._on_start_preview()
    dialog.close()

    after_order = order_service.get_order(order.id)
    assert before_order.status == after_order.status == "active"
    assert before_order.total_amount == after_order.total_amount
    assert log_service.count_logs() == before_logs
    assert draw_service.count_draws() == before_draws


def test_commit_without_draw_warns_and_does_not_call_service(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    order = create_order(order_service, items=[OrderItemCreate(bet_type="特码", selection="01", amount="10.00")])
    dialog = open_preview_dialog(session_factory, order.id)

    with (
        patch.object(dialog._settlement_service, "commit_order_settlement") as commit,
        patch("ui.dialogs.settlement_preview_dialog.QMessageBox.warning") as warning,
    ):
        dialog._on_commit_settlement()

    commit.assert_not_called()
    warning.assert_called_once()
    assert "请先选择开奖并完成结算预览" in warning.call_args.args[2]


def test_commit_without_preview_warns_and_does_not_call_service(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = create_order(order_service, items=[OrderItemCreate(bet_type="特码", selection="01", amount="10.00")])
    create_draw(draw_service)
    dialog = open_preview_dialog(session_factory, order.id)

    with (
        patch.object(dialog._settlement_service, "commit_order_settlement") as commit,
        patch("ui.dialogs.settlement_preview_dialog.QMessageBox.warning") as warning,
    ):
        dialog._on_commit_settlement()

    commit.assert_not_called()
    warning.assert_called_once()
    assert "请先开始预览" in warning.call_args.args[2]


def test_commit_with_unsupported_preview_is_blocked(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    log_service = LogService(session_factory)
    order = create_order(order_service)
    create_draw(draw_service)
    dialog = open_preview_dialog(session_factory, order.id)
    dialog._on_start_preview()

    with (
        patch.object(dialog._settlement_service, "commit_order_settlement") as commit,
        patch("ui.dialogs.settlement_preview_dialog.QMessageBox.warning") as warning,
    ):
        dialog._on_commit_settlement()

    commit.assert_not_called()
    warning.assert_called_once()
    assert "存在暂不支持玩法" in warning.call_args.args[2]
    assert order_service.get_order(order.id).status == "active"
    assert log_service.count_logs(module="settlement", action="commit") == 0


def test_commit_cancel_confirmation_does_not_call_service(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = create_order(order_service, items=[OrderItemCreate(bet_type="特码", selection="01", amount="10.00")])
    create_draw(draw_service)
    dialog = open_preview_dialog(session_factory, order.id)
    dialog._on_start_preview()

    with (
        patch(
            "ui.dialogs.settlement_preview_dialog.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question,
        patch.object(dialog._settlement_service, "commit_order_settlement") as commit,
    ):
        dialog._on_commit_settlement()

    question.assert_called_once()
    commit.assert_not_called()
    assert dialog._lbl_status.text() == "active"
    assert order_service.get_order(order.id).status == "active"


def test_commit_confirm_calls_service_and_persists_status_and_log(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    log_service = LogService(session_factory)
    order = create_order(
        order_service,
        items=[
            OrderItemCreate(bet_type="特码", selection="01", amount="10.00"),
            OrderItemCreate(bet_type="特码", selection="02", amount="20.00"),
        ],
    )
    draw = create_draw(draw_service, special="01")
    dialog = open_preview_dialog(session_factory, order.id)
    dialog._on_start_preview()

    assert dialog._btn_commit.isEnabled()
    with (
        patch(
            "ui.dialogs.settlement_preview_dialog.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as question,
        patch("ui.dialogs.settlement_preview_dialog.QMessageBox.information") as info,
        patch.object(
            dialog._settlement_service,
            "commit_order_settlement",
            wraps=dialog._settlement_service.commit_order_settlement,
        ) as commit,
    ):
        dialog._on_commit_settlement()

    question.assert_called_once()
    assert "订单号 / 订单ID" in question.call_args.args[2]
    assert "中奖数量：1" in question.call_args.args[2]
    commit.assert_called_once_with(order.id, draw.id)
    info.assert_called_once()
    assert "结算成功" in info.call_args.args[2]
    assert "操作日志ID" in info.call_args.args[2]
    assert dialog.settlement_committed()
    assert dialog._lbl_status.text() == "settled"
    assert not dialog._btn_commit.isEnabled()
    assert order_service.get_order(order.id).status == "settled"
    assert log_service.count_logs(module="settlement", action="commit") == 1


def test_commit_settled_order_repeat_click_shows_friendly_warning(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    log_service = LogService(session_factory)
    order = create_order(order_service, items=[OrderItemCreate(bet_type="特码", selection="01", amount="10.00")])
    create_draw(draw_service)
    dialog = open_preview_dialog(session_factory, order.id)
    dialog._on_start_preview()

    with (
        patch(
            "ui.dialogs.settlement_preview_dialog.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch("ui.dialogs.settlement_preview_dialog.QMessageBox.information"),
    ):
        dialog._on_commit_settlement()

    with (
        patch.object(dialog._settlement_service, "commit_order_settlement") as commit,
        patch("ui.dialogs.settlement_preview_dialog.QMessageBox.warning") as warning,
    ):
        dialog._on_commit_settlement()

    commit.assert_not_called()
    warning.assert_called_once()
    assert "该订单已结算，不能重复结算" in warning.call_args.args[2]
    assert log_service.count_logs(module="settlement", action="commit") == 1


def test_commit_failure_shows_error_without_crashing(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    draw_service = DrawService(session_factory)
    order = create_order(order_service, items=[OrderItemCreate(bet_type="特码", selection="01", amount="10.00")])
    create_draw(draw_service)
    dialog = open_preview_dialog(session_factory, order.id)
    dialog._on_start_preview()

    with (
        patch(
            "ui.dialogs.settlement_preview_dialog.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch.object(dialog._settlement_service, "commit_order_settlement", side_effect=RuntimeError("boom")),
        patch("ui.dialogs.settlement_preview_dialog.QMessageBox.warning") as warning,
    ):
        dialog._on_commit_settlement()

    warning.assert_called_once()
    assert "结算失败" in warning.call_args.args[2]
    assert "boom" in warning.call_args.args[2]
    assert order_service.get_order(order.id).status == "active"
    assert not dialog.settlement_committed()


def test_order_detail_preview_button_states(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    log_service = LogService(session_factory)
    order = create_order(order_service)
    page = OrderDetailPage(
        order_service=order_service,
        log_service=log_service,
        draw_service=DrawService(session_factory),
        settlement_service=SettlementService(session_factory),
    )
    page.reload_data()

    assert not page._btn_preview.isEnabled()
    page._table.selectRow(0)
    page._on_selection_changed()
    assert page._btn_preview.isEnabled()

    with patch("ui.pages.order_detail_page.SettlementPreviewDialog") as dialog_cls:
        dialog_cls.return_value.settlement_committed.return_value = False
        page._on_settlement_preview()
        dialog_cls.assert_called_once_with(
            order.id,
            parent=page,
            order_service=page._order_service,
            draw_service=page._draw_service,
            settlement_service=page._settlement_service,
        )
        dialog_cls.return_value.exec.assert_called_once()


def test_order_detail_empty_state_and_existing_features(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        draw_service=DrawService(session_factory),
        settlement_service=SettlementService(session_factory),
    )
    page.reload_data()
    assert page._table.rowCount() == 0
    assert "暂无订单数据" in page._status_label.text()
    assert not page._btn_preview.isEnabled()

    service = OrderService(session_factory)
    for idx in range(21):
        create_order(service, customer=f"客户{idx}")
    page.reload_data()
    assert page._table.rowCount() == 20
    page._cmb_declarer.setCurrentText("客户1")
    page._on_query()
    assert page._table.rowCount() >= 1
    page._table.selectRow(0)
    page._on_selection_changed()
    assert page._item_table.rowCount() == 3
