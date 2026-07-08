from __future__ import annotations

import os
from decimal import Decimal

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QRadioButton, QSpinBox

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService
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
            customer_name="页面测试",
            channel="pytest",
            region=region,
            raw_text=f"{bet_type} {selection} {amount}",
            source="test",
            items=[OrderItemCreate(bet_type=bet_type, selection=selection, amount=amount)],
        )
    )


def headers(table) -> list[str]:
    return [table.horizontalHeaderItem(column).text() for column in range(table.columnCount())]


def button_texts(page) -> set[str]:
    return {button.text() for button in page.findChildren(QPushButton)}


def radio_texts(page) -> set[str]:
    return {radio.text() for radio in page.findChildren(QRadioButton)}


def label_text(page) -> str:
    return "\n".join(label.text() for label in page.findChildren(QLabel))


def test_special_adjust_page_creates_with_required_layout(session_factory) -> None:
    app()
    page = SpecialOrderPage(order_service=OrderService(session_factory))

    assert headers(page._summary_table) == ["号码", "下注数", "盈亏", "ID"]
    assert page._summary_table.rowCount() == 49
    assert len(page._original_edits) == 49
    assert len(page._adjust_edits) == 49
    assert len(page._total_edits) == 49
    assert page.findChild(QSpinBox, "specialAdjustmentZodiacYearSpin") is not None
    assert {"只看澳门", "只看香港"}.issubset(radio_texts(page))
    assert {
        "保存本次调整",
        "调整为10的倍数",
        "清空当前调单",
        "清空输出框",
        "重置所有数据",
        "结码总奖",
        "打开扩展",
        "调整记录",
    }.issubset(button_texts(page))
    text = label_text(page)
    assert "原特码数据" in text
    assert "调整后数据" in text
    assert "最大亏损" in text
    assert "调整额" in text


def test_special_adjust_page_refreshes_order_summary_and_input(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, selection="01", amount="100")
    create_order(service, selection="25-37-49各20", amount="20")
    page = SpecialOrderPage(order_service=service)

    by_number = {
        page._summary_table.item(row, 0).text()[-2:]: Decimal(page._summary_table.item(row, 1).text())
        for row in range(page._summary_table.rowCount())
    }
    assert by_number["01"] == Decimal("100.00")
    assert by_number["25"] == Decimal("20.00")
    assert page._original_edits["49"].text() == "20.00"

    page._adjustment_input.setText("12=100,25=50")
    page._on_apply_adjustment_input()

    assert page._adjust_edits["12"].text() == "100.00"
    assert page._adjust_edits["25"].text() == "50.00"
    assert page._total_edits["25"].text() == "70.00"


def test_lianxiao_adjust_page_creates_with_required_layout(session_factory) -> None:
    app()
    page = LianxiaoOrderPage(order_service=OrderService(session_factory))

    assert headers(page._summary_table) == ["生肖组", "下注数", "盈亏"]
    assert page._summary_table.rowCount() == 1
    assert page._summary_table.item(0, 0).text() == "暂无数据"
    assert len(page._tables) == 5
    for table in page._tables:
        assert headers(table) == ["生肖组", "下注数", "盈亏"]
    assert page.findChild(QSpinBox, "lianxiaoAdjustmentZodiacYearSpin") is not None
    assert {"只看澳门", "只看香港"}.issubset(radio_texts(page))
    assert {
        "打印连肖调整",
        "清空输出框",
        "重置调整",
        "打开扩展",
        "调整记录",
    }.issubset(button_texts(page))
    text = label_text(page)
    assert "原连肖数据" in text
    assert "调整后数据" in text
    assert "连肖必须有“连”字在其中" in text


def test_lianxiao_adjust_page_refreshes_summary_and_prints(session_factory) -> None:
    app()
    service = OrderService(session_factory)
    create_order(service, bet_type="连肖", selection="狗羊猴", amount="200")
    create_order(service, bet_type="连肖", selection="龙羊猴鸡", amount="50")
    page = LianxiaoOrderPage(order_service=service)

    assert page._summary_table.rowCount() == 2
    amounts = {
        page._summary_table.item(row, 0).text(): Decimal(page._summary_table.item(row, 1).text())
        for row in range(page._summary_table.rowCount())
    }
    assert Decimal("200.00") in amounts.values()
    assert Decimal("50.00") in amounts.values()

    page._adjustment_input.setText("狗羊猴=100")
    page._on_apply_adjustment_input()
    page._on_print_adjustment()

    output = page._output.toPlainText()
    assert "连肖调整" in output
    assert "调整后" in output
