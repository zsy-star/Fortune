from __future__ import annotations

import inspect
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from models import Order
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.log_service import LogService
from services.order_service import OrderService
from ui.pages.order_detail_page import OrderDetailPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(service: OrderService, *, customer: str = "void-ui", status: str | None = None):
    order = service.create_order(
        OrderCreate(
            customer_name=customer,
            channel="test",
            region="澳门",
            raw_text=f"{customer} 10",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )
    if status is not None:
        with service._session_factory() as session:
            saved = session.get(Order, order.id)
            assert saved is not None
            saved.status = status
            session.commit()
    return order


def make_page(session_factory) -> OrderDetailPage:
    return OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )


def load_order(page: OrderDetailPage, order_id: int) -> None:
    page._load_detail(order_id)


def test_order_detail_page_void_button_initially_disabled(session_factory) -> None:
    app()
    page = make_page(session_factory)

    assert not page._btn_void.isEnabled()
    assert page._table.rowCount() == 0


def test_active_and_pending_orders_enable_void_button(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    active = create_order(service, customer="active")
    pending = create_order(service, customer="pending", status="pending")
    page = make_page(session_factory)

    load_order(page, active.id)
    assert page._btn_void.isEnabled()

    load_order(page, pending.id)
    assert page._btn_void.isEnabled()


def test_settled_and_voided_orders_disable_void_button(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    settled = create_order(service, customer="settled", status="settled")
    voided = create_order(service, customer="voided", status="voided")
    page = make_page(session_factory)

    load_order(page, settled.id)
    assert not page._btn_void.isEnabled()

    load_order(page, voided.id)
    assert not page._btn_void.isEnabled()


def test_void_cancel_reason_input_does_not_call_service(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    order = create_order(service)
    page = make_page(session_factory)
    load_order(page, order.id)

    with (
        patch("ui.pages.order_detail_page.QInputDialog.getMultiLineText", return_value=("", False)),
        patch.object(page._order_service, "void_order", wraps=page._order_service.void_order) as void_order,
    ):
        page._on_void_order()

    void_order.assert_not_called()
    assert page._order_service.get_order(order.id).status == "active"


def test_void_blank_reason_warns_and_does_not_call_service(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    order = create_order(service)
    page = make_page(session_factory)
    load_order(page, order.id)

    with (
        patch("ui.pages.order_detail_page.QInputDialog.getMultiLineText", return_value=("   ", True)),
        patch("ui.pages.order_detail_page.QMessageBox.warning") as warning,
        patch.object(page._order_service, "void_order", wraps=page._order_service.void_order) as void_order,
    ):
        page._on_void_order()

    void_order.assert_not_called()
    warning.assert_called_once()
    assert "请输入作废原因" in warning.call_args.args[2]
    assert page._order_service.get_order(order.id).status == "active"


def test_void_cancel_confirmation_does_not_call_service(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    order = create_order(service)
    page = make_page(session_factory)
    load_order(page, order.id)

    with (
        patch("ui.pages.order_detail_page.QInputDialog.getMultiLineText", return_value=("entered wrong", True)),
        patch(
            "ui.pages.order_detail_page.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question,
        patch.object(page._order_service, "void_order", wraps=page._order_service.void_order) as void_order,
    ):
        page._on_void_order()

    question.assert_called_once()
    assert "订单ID / 订单号" in question.call_args.args[2]
    assert "作废后订单不会被删除" in question.call_args.args[2]
    assert "该操作会写入操作日志" in question.call_args.args[2]
    void_order.assert_not_called()
    assert page._order_service.get_order(order.id).status == "active"


def test_void_confirm_calls_service_persists_status_log_and_disables_button(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    log_service = LogService(session_factory)
    order = create_order(service)
    page = OrderDetailPage(order_service=service, log_service=log_service)
    load_order(page, order.id)

    with (
        patch("ui.pages.order_detail_page.QInputDialog.getMultiLineText", return_value=("entered wrong", True)),
        patch(
            "ui.pages.order_detail_page.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as question,
        patch("ui.pages.order_detail_page.QMessageBox.information") as info,
        patch.object(page._order_service, "void_order", wraps=page._order_service.void_order) as void_order,
    ):
        page._on_void_order()

    question.assert_called_once()
    void_order.assert_called_once_with(order.id, "entered wrong", operator="system")
    info.assert_called_once()
    assert "订单作废成功" in info.call_args.args[2]
    assert "操作日志ID" in info.call_args.args[2]
    assert page._order_service.get_order(order.id).status == "voided"
    assert "状态：voided" in page._detail_info.text()
    assert not page._btn_void.isEnabled()
    assert log_service.count_logs(module="order", action="void") == 1


def test_void_failure_shows_error_without_crashing(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    order = create_order(service)
    page = make_page(session_factory)
    load_order(page, order.id)

    with (
        patch("ui.pages.order_detail_page.QInputDialog.getMultiLineText", return_value=("entered wrong", True)),
        patch(
            "ui.pages.order_detail_page.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch.object(page._order_service, "void_order", side_effect=RuntimeError("boom")),
        patch("ui.pages.order_detail_page.QMessageBox.warning") as warning,
    ):
        page._on_void_order()

    warning.assert_called_once()
    assert "订单作废失败" in warning.call_args.args[2]
    assert "boom" in warning.call_args.args[2]
    assert page._order_service.get_order(order.id).status == "active"
    assert page._btn_void.isEnabled()


def test_order_void_ui_uses_service_only() -> None:
    source = inspect.getsource(OrderDetailPage)

    for forbidden in ("Session", "Repository", "sqlite", "OrderRepository", "LogRepository", "data/fortune.db"):
        assert forbidden not in source
    assert "void_order(" in source
    assert "delete" not in source.lower()
