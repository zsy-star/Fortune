from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from models import OperationLog, Order, SettlementRecord
from schemas.draw_schema import LotteryDrawCreate
from schemas.order_schema import OrderCreate, OrderItemCreate
from schemas.settlement_schema import SettlementLedgerResult
from services.draw_service import DrawService
from services.log_service import LogService
from services.order_service import OrderService
from services.settlement_service import SettlementService
import ui.pages.settlement_ledger_page as settlement_ledger_module
from ui.pages.settlement_ledger_page import _SettlementSnapshotDialog
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
    issue_number: str | None = None,
) -> None:
    settled_at = settled_at or datetime.now()
    issue_number = issue_number or str(100000 + order_id)
    detail = OrderService(session_factory).get_order(order_id)
    assert detail is not None
    draw = DrawService(session_factory).create_draw(
        LotteryDrawCreate(
            region=detail.region,
            issue_number=issue_number,
            draw_date=settled_at.date(),
            regular_numbers=["02", "03", "04", "05", "06", "07"],
            special_number="01",
        )
    )
    SettlementService(session_factory).commit_order_settlement(order_id, draw.id)
    with session_factory() as session:
        order = session.get(Order, order_id)
        record = session.query(SettlementRecord).filter_by(order_id=order_id).one()
        saved_log = session.get(OperationLog, record.operation_log_id)
        assert order is not None
        assert saved_log is not None
        record.settled_at = settled_at
        order.updated_at = settled_at
        saved_log.created_at = settled_at
        session.commit()


def make_page(session_factory) -> SettlementLedgerPage:
    return SettlementLedgerPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
        settlement_service=SettlementService(session_factory),
    )


def make_ledger_result(snapshot) -> SettlementLedgerResult:
    now = datetime(2026, 6, 12, 10, 30, 0)
    return SettlementLedgerResult(
        id=9,
        order_id=101,
        draw_id=202,
        operation_log_id=None,
        order_no="ORD-SNAPSHOT",
        customer_name="客户",
        region="澳门",
        order_status="settled",
        total_amount=Decimal("60.00"),
        settled_at=now,
        issue_number="162",
        total_items=3,
        hit_count=1,
        miss_count=1,
        unsupported_count=1,
        result_snapshot=snapshot,
        order_created_at=now,
        order_updated_at=now,
        operation_log_description=None,
    )


def test_settlement_ledger_page_empty_database_shows_empty_state(session_factory) -> None:
    app()
    page = make_page(session_factory)

    assert page._table.rowCount() == 0
    assert page._lbl_total.text() == "暂无结算记录"
    assert not page._btn_prev.isEnabled()
    assert not page._btn_next.isEnabled()


def test_settlement_ledger_page_exposes_snapshot_detail_entry(session_factory) -> None:
    app()
    page = make_page(session_factory)

    assert page._btn_snapshot_detail.text() == "查看结算快照详情"
    assert page._btn_snapshot_detail.isEnabled()


def test_settlement_ledger_snapshot_detail_requires_selected_record(session_factory, monkeypatch) -> None:
    app()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    page = make_page(session_factory)

    page._on_snapshot_detail()

    assert page._lbl_total.text() == "请先选择一条结算记录。"


def test_settlement_ledger_snapshot_detail_opens_selected_record(session_factory, monkeypatch) -> None:
    app()
    order_service = OrderService(session_factory)
    order = create_order(order_service, customer="快照客户", region="澳门", amount="10")
    settle_order(session_factory, order.id, order.order_no)
    opened: list[SettlementLedgerResult] = []

    class FakeSnapshotDialog:
        def __init__(self, record, parent=None):
            opened.append(record)

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(settlement_ledger_module, "_SettlementSnapshotDialog", FakeSnapshotDialog)

    page = make_page(session_factory)
    page._table.selectRow(0)
    page._on_snapshot_detail()

    assert len(opened) == 1
    assert opened[0].order_id == order.id
    assert opened[0].result_snapshot["items"][0]["selection"] == "01"


def test_settlement_snapshot_dialog_displays_hit_miss_and_unsupported_items() -> None:
    app()
    dialog = _SettlementSnapshotDialog(
        make_ledger_result(
            {
                "items": [
                    {
                        "bet_type": "特码",
                        "selection": "01",
                        "amount": "10.00",
                        "is_supported": True,
                        "is_winner": True,
                        "matched_number": "01",
                        "reason": "特码 01 命中号码 01",
                    },
                    {
                        "bet_type": "特码",
                        "selection": "02",
                        "amount": "20.00",
                        "is_supported": True,
                        "is_winner": False,
                        "matched_number": None,
                        "reason": "特码 01 未命中号码 02",
                    },
                    {
                        "bet_type": "连肖",
                        "selection": "马,蛇",
                        "amount": "30.00",
                        "is_supported": False,
                        "is_winner": None,
                        "matched_number": None,
                        "reason": "暂不支持玩法",
                    },
                ]
            }
        )
    )

    assert "订单 ID：101" in dialog._summary_label.text()
    assert "draw_id：202" in dialog._summary_label.text()
    assert dialog._items_table.rowCount() == 3
    assert dialog._items_table.item(0, 3).text() == "命中"
    assert dialog._items_table.item(1, 3).text() == "未中"
    assert dialog._items_table.item(2, 3).text() == "不支持"
    assert dialog._items_table.item(2, 5).text() == "暂不支持玩法"
    assert '"selection": "01"' in dialog._raw_snapshot.toPlainText()


def test_settlement_snapshot_dialog_handles_empty_or_malformed_snapshot() -> None:
    app()
    dialog = _SettlementSnapshotDialog(make_ledger_result({}))

    assert dialog._items_table.rowCount() == 0
    assert "快照数据为空或格式不完整" in dialog._empty_label.text()
    assert "快照数据为空或格式不完整" in dialog._raw_snapshot.toPlainText()


def test_settlement_ledger_page_lists_only_settled_orders_with_log_summary(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    settled = create_order(order_service, customer="已结算客户", region="澳门", amount="10")
    active = create_order(order_service, customer="未结算客户", region="香港", amount="20")
    settle_order(session_factory, settled.id, settled.order_no)

    page = make_page(session_factory)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 1).text() == str(settled.id)
    assert page._table.item(0, 2).text() == settled.order_no
    assert page._table.item(0, 3).text() == "已结算客户"
    assert page._table.item(0, 4).text() == "澳门"
    assert page._table.item(0, 5).text() == "settled"
    assert page._table.item(0, 6).text() == "10.00"
    assert page._table.item(0, 8).text() != "-"
    assert page._table.item(0, 9).text() == "中1 / 未0 / 不支持0"
    assert settled.order_no in page._table.item(0, 10).toolTip()
    assert active.order_no not in [page._table.item(row, 2).text() for row in range(page._table.rowCount())]


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
    assert page._table.item(0, 2).text() == hong_kong.order_no

    page._cmb_region.setCurrentText("全部")
    page._start_date.setDate(QDate(2026, 6, 1))
    page._end_date.setDate(QDate(2026, 6, 1))
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == macau.order_no


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
    assert page._table.item(0, 2).text() == first.order_no

    page._keyword.setText(second.order_no[-6:])
    page._on_query()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == second.order_no


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
    assert service.list_settlement_ledger()[0].order_id == settled.id
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
    assert "SettlementRecordRepository" not in source


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
