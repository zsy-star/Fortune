from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QWidget

from models import OperationLog, Order
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.log_service import LogService
from services.order_service import OrderService
from ui.pages.settlement_ledger_page import SettlementLedgerPage


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(
    service: OrderService,
    *,
    customer: str = "客户",
    region: str = "澳门",
    channel: str = "微信",
    amount: str = "10",
):
    return service.create_order(
        OrderCreate(
            customer_name=customer,
            channel=channel,
            region=region,
            raw_text=f"{customer}{amount}",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount=amount)],
        )
    )


def settle_order(
    session_factory,
    order_id: int,
    order_no: str,
    *,
    settled_at: datetime | None = None,
) -> None:
    settled_at = settled_at or datetime.now()
    log = LogService(session_factory).create_log(
        module="settlement",
        action="commit",
        description=f"确认结算订单 {order_no}，中奖 1，未中奖 0",
        related_type="order",
        related_id=order_id,
    )
    with session_factory() as session:
        order = session.get(Order, order_id)
        saved_log = session.get(OperationLog, log.id)
        assert order is not None
        assert saved_log is not None
        order.status = "settled"
        order.updated_at = settled_at
        saved_log.created_at = settled_at
        session.commit()


def make_page(session_factory) -> SettlementLedgerPage:
    return SettlementLedgerPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )


def test_settlement_ledger_page_empty_database_shows_empty_state(session_factory) -> None:
    app()
    page = make_page(session_factory)

    assert page._table.rowCount() == 0
    assert page._lbl_total.text() == "暂无结算记录"
    assert not page._btn_prev.isEnabled()
    assert not page._btn_next.isEnabled()


def test_settlement_ledger_page_lists_only_settled_orders_with_log_summary(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    settled = create_order(order_service, customer="已结算客户", region="澳门", amount="10")
    active = create_order(order_service, customer="未结算客户", region="香港", amount="20")
    settle_order(session_factory, settled.id, settled.order_no)

    page = make_page(session_factory)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == str(settled.id)
    assert page._table.item(0, 1).text() == settled.order_no
    assert page._table.item(0, 2).text() == "已结算客户"
    assert page._table.item(0, 3).text() == "澳门"
    assert page._table.item(0, 4).text() == "settled"
    assert page._table.item(0, 5).text() == "10.00"
    assert page._table.item(0, 7).text() == "-"
    assert settled.order_no in page._table.item(0, 8).toolTip()
    assert active.order_no not in [page._table.item(row, 1).text() for row in range(page._table.rowCount())]


def test_settlement_ledger_page_filters_by_region_and_date(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    old_day = datetime(2026, 6, 1, 9, 0, 0)
    new_day = datetime(2026, 6, 5, 9, 0, 0)
    macau = create_order(order_service, customer="澳门客户", region="澳门", amount="10")
    hong_kong = create_order(order_service, customer="香港客户", region="香港", amount="20")
    settle_order(session_factory, macau.id, macau.order_no, settled_at=old_day)
    settle_order(session_factory, hong_kong.id, hong_kong.order_no, settled_at=new_day)

    page = make_page(session_factory)
    page._cmb_region.setCurrentText("香港")
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 1).text() == hong_kong.order_no

    page._cmb_region.setCurrentText("全部")
    page._start_date.setDate(QDate(2026, 6, 1))
    page._end_date.setDate(QDate(2026, 6, 1))
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 1).text() == macau.order_no


def test_settlement_ledger_page_searches_by_order_id_or_order_no(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    first = create_order(order_service, customer="一号客户", region="澳门", amount="10")
    second = create_order(order_service, customer="二号客户", region="澳门", amount="20")
    settle_order(session_factory, first.id, first.order_no)
    settle_order(session_factory, second.id, second.order_no)

    page = make_page(session_factory)
    page._keyword.setText(str(first.id))
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 1).text() == first.order_no

    page._keyword.setText(second.order_no[-6:])
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 1).text() == second.order_no


def test_settlement_ledger_page_pagination_and_refresh(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    for idx in range(21):
        order = create_order(order_service, customer=f"分页客户{idx}", region="澳门", amount="10")
        settle_order(session_factory, order.id, order.order_no, settled_at=datetime.now() + timedelta(seconds=idx))

    page = make_page(session_factory)
    assert page._table.rowCount() == 20
    assert page._btn_next.isEnabled()
    page._next_page()
    assert page._table.rowCount() == 1
    page.reload_data()
    assert page._table.rowCount() == 1
    page._on_reset()
    assert page._page == 1
    assert page._table.rowCount() == 20


def test_order_service_settlement_ledger_read_only_query(session_factory) -> None:
    service = OrderService(session_factory)
    settled = create_order(service, customer="已结算", region="澳门", amount="10")
    active = create_order(service, customer="未结算", region="香港", amount="20")
    old_time = datetime.now() - timedelta(days=3)
    settle_order(session_factory, settled.id, settled.order_no, settled_at=old_time)

    assert service.count_settlement_ledger() == 1
    assert service.list_settlement_ledger()[0].id == settled.id
    assert service.count_settlement_ledger(region="澳门") == 1
    assert service.count_settlement_ledger(region="香港") == 0
    assert service.count_settlement_ledger(keyword=str(settled.id)) == 1
    assert service.count_settlement_ledger(keyword=active.order_no) == 0
    assert service.count_settlement_ledger(start_date=datetime.now() - timedelta(days=1)) == 0
    assert service.list_settlement_ledger(limit=1, offset=1) == []
    assert service.get_order(active.id).status == "active"


def test_settlement_ledger_page_is_read_only_and_uses_services_only() -> None:
    source = inspect.getsource(SettlementLedgerPage)

    for forbidden in ("Session", "Repository", "sqlite", "OrderRepository", "LogRepository"):
        assert forbidden not in source
    assert "commit_order_settlement" not in source
    assert "SettlementService" not in source


def test_main_window_registers_settlement_ledger_without_real_services(monkeypatch) -> None:
    app()
    import ui.main_window as main_window

    class DummyPage(QWidget):
        pass

    monkeypatch.setattr(
        main_window,
        "_STACK_PAGE_CLASSES",
        [DummyPage for _ in main_window._STACK_PAGE_CLASSES],
    )
    window = main_window.MainWindow()

    assert any(button.text() == "结算历史" for button in window._nav_group.buttons())
    assert window._stack.count() == len(main_window._STACK_PAGE_CLASSES)
