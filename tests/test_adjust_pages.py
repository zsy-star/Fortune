from __future__ import annotations

import os
from decimal import Decimal

from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton
from sqlalchemy import func, select

from models import Order
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService
import ui.pages.lianxiao_order_page as lianxiao_module
import ui.pages.special_order_page as special_module
from ui.pages.lianxiao_order_page import LianxiaoOrderPage
from ui.pages.special_order_page import SpecialOrderPage


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_order(
    service: OrderService,
    *,
    region: str = "澳门",
    bet_type: str = "特码",
    selection: str = "01",
    amount: str = "10",
):
    return service.create_order(
        OrderCreate(
            customer_name="调单测试",
            channel="测试渠道",
            region=region,
            raw_text=f"{bet_type} {selection} {amount}",
            source="test",
            items=[OrderItemCreate(bet_type=bet_type, selection=selection, amount=amount)],
        )
    )


def count_orders(session_factory) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count(Order.id))) or 0)


def test_special_order_page_creates_and_shows_empty_state(session_factory) -> None:
    app()
    page = SpecialOrderPage(order_service=OrderService(session_factory))

    assert page._summary_table.rowCount() == 49
    assert len(page._adjust_edits) == 49
    assert len(page._total_edits) == 49
    assert "暂无数据" in page._output.toPlainText()


def test_special_order_page_reads_existing_special_order_summary(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, selection="01,02", amount="10")
    create_order(service, selection="01", amount="5")
    create_order(service, bet_type="连肖", selection="牛,马", amount="100")

    page = SpecialOrderPage(order_service=service)

    rows = {
        page._summary_table.item(row, 0).text(): Decimal(page._summary_table.item(row, 1).text())
        for row in range(page._summary_table.rowCount())
    }
    assert rows["01"] == Decimal("15.00")
    assert rows["02"] == Decimal("10.00")
    assert "特码总额：25.00" in page._lbl_special_total.text()


def test_special_order_page_low_and_high_risk_buttons_are_in_memory_only(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, selection="01", amount="11")
    before = count_orders(session_factory)
    page = SpecialOrderPage(order_service=service)

    page._on_round_to_tens()
    assert page._adjust_edits["01"].text() == "9.00"
    page._on_save_adjustment()
    page._on_reset_all_data()
    page._on_special_settlement()
    page._on_open_extension()
    page._on_adjust_records()
    assert count_orders(session_factory) == before
    output = page._output.toPlainText()
    assert "页面内临时调整" in output
    assert "数据库未被修改" in output
    assert "不计算赔付" in output
    assert "打开拓展" in output
    assert "调整记录" in output


def test_special_order_page_export_text_and_buttons(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, selection="01", amount="10")
    page = SpecialOrderPage(order_service=service)

    assert page._btn_copy_summary.text() == "复制当前汇总"
    assert page._btn_export_summary.text() == "导出当前汇总"

    text = page._build_export_text()
    assert "特码调单汇总" in text
    assert "当前筛选区域：全部" in text
    assert "号码\t下注数\t盈亏\tID" in text
    assert "号码\t原金额\t调整\t总计" in text
    assert "未写数据库" in text


def test_special_order_page_copy_and_export_summary_are_readonly(
    session_factory, tmp_path, monkeypatch
) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, selection="01", amount="10")
    before = count_orders(session_factory)
    page = SpecialOrderPage(order_service=service)

    page._btn_copy_summary.click()
    assert "特码调单汇总" in QApplication.clipboard().text()
    assert "已复制特码调单汇总到剪贴板" in page._output.toPlainText()

    monkeypatch.setattr(
        special_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("", ""),
    )
    page._on_export_summary()
    assert "已取消导出" in page._output.toPlainText()

    export_path = tmp_path / "special_summary.txt"
    monkeypatch.setattr(
        special_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(export_path), "Text Files (*.txt)"),
    )
    page._on_export_summary()
    assert export_path.read_text(encoding="utf-8").startswith("特码调单汇总")
    assert "已导出特码调单汇总" in page._output.toPlainText()

    monkeypatch.setattr(
        special_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(tmp_path), "Text Files (*.txt)"),
    )
    page._on_export_summary()
    assert "导出特码调单汇总失败" in page._output.toPlainText()
    assert count_orders(session_factory) == before


def test_lianxiao_order_page_creates_and_shows_empty_state(session_factory) -> None:
    app()
    page = LianxiaoOrderPage(order_service=OrderService(session_factory))

    assert page._summary_table.rowCount() == 1
    assert page._summary_table.item(0, 0).text() == "暂无数据"
    assert len(page._tables) == 4
    assert [page._summary_table.horizontalHeaderItem(column).text() for column in range(3)] == [
        "生肖组",
        "下注数",
        "盈亏",
    ]
    for table in page._tables:
        assert [table.horizontalHeaderItem(column).text() for column in range(3)] == [
            "生肖组",
            "下注数",
            "盈亏",
        ]
    labels = "\n".join(label.text() for label in page.findChildren(QLabel))
    assert "原金额" not in labels
    assert "总计" not in labels
    assert "原连肖数据" in labels
    assert "调整后数据" in labels
    assert not page.findChildren(QLineEdit)
    button_texts = {button.text() for button in page.findChildren(QPushButton)}
    assert "保存本次调整" not in button_texts
    assert "调整成为 10 的倍数" not in button_texts
    assert "清空当前调整" not in button_texts
    assert "连肖兑奖" not in button_texts
    assert page._btn_print.text() == "打印连肖调整"
    assert page._btn_copy_summary.text() == "复制当前汇总"
    assert page._btn_export_summary.text() == "导出当前汇总"
    assert page._btn_clear_output.text() == "清空输出框"
    assert page._btn_reset.text() == "重置调整"
    assert "暂无数据" in page._output.toPlainText()


def test_lianxiao_order_page_reads_existing_lianxiao_summary(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, bet_type="连肖", selection="牛,马", amount="100")
    create_order(service, bet_type="连肖", selection="牛,马", amount="50")
    create_order(service, bet_type="特码", selection="01", amount="10")

    page = LianxiaoOrderPage(order_service=service)

    assert page._summary_table.rowCount() == 1
    assert page._summary_table.item(0, 0).text() == "牛,马"
    assert page._summary_table.item(0, 1).text() == "150.00"
    assert page._tables[0].rowCount() == 1
    assert page._tables[0].item(0, 0).text() == "牛,马"
    assert page._tables[0].item(0, 1).text() == "150.00"
    assert "连肖总额：150.00" in page._lbl_lianxiao_total.text()


def test_lianxiao_order_page_actions_are_readonly(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, bet_type="连肖", selection="牛,马", amount="100")
    before = count_orders(session_factory)
    page = LianxiaoOrderPage(order_service=service)

    page._on_print_adjustment()
    page._on_reset_adjustment()

    assert count_orders(session_factory) == before
    output = page._output.toPlainText()
    assert "当前版本未调用打印机" in output
    assert "数据库订单未被修改" in output


def test_lianxiao_order_page_export_text_and_copy_export_behaviors(
    session_factory, tmp_path, monkeypatch
) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, bet_type="连肖", selection="牛,马", amount="100")
    before = count_orders(session_factory)
    page = LianxiaoOrderPage(order_service=service)

    text = page._build_export_text()
    assert "连肖调单汇总" in text
    assert "当前筛选区域：全部" in text
    assert "生肖组\t下注数\t盈亏" in text
    assert "第 1 列表" in text
    assert "未写数据库" in text

    page._btn_copy_summary.click()
    assert "连肖调单汇总" in QApplication.clipboard().text()
    assert "已复制连肖调单汇总到剪贴板" in page._output.toPlainText()

    monkeypatch.setattr(
        lianxiao_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("", ""),
    )
    page._on_export_summary()
    assert "已取消导出" in page._output.toPlainText()

    export_path = tmp_path / "lianxiao_summary.txt"
    monkeypatch.setattr(
        lianxiao_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(export_path), "Text Files (*.txt)"),
    )
    page._on_export_summary()
    assert export_path.read_text(encoding="utf-8").startswith("连肖调单汇总")
    assert "已导出连肖调单汇总" in page._output.toPlainText()

    monkeypatch.setattr(
        lianxiao_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(tmp_path), "Text Files (*.txt)"),
    )
    page._on_export_summary()
    assert "导出连肖调单汇总失败" in page._output.toPlainText()
    assert count_orders(session_factory) == before
