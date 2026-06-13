from __future__ import annotations

import inspect
import os
from pathlib import Path

import matplotlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton

from services.log_service import LogService
from services.order_service import OrderService
from ui.matplotlib_setup import configure_matplotlib
from ui.pages.lianxiao_order_page import LianxiaoOrderPage
from ui.pages.number_catalog_page import NumberCatalogPage
from ui.pages.operation_log_page import OperationLogPage
from ui.pages.order_analysis_page import OrderAnalysisPage
from ui.pages.order_detail_page import OrderDetailPage
from ui.pages.overview_page import OverviewPage
from ui.pages.special_order_page import SpecialOrderPage
from ui.windows.record_order_window import RecordOrderWindow
from ui.windows.split_order_window import SplitOrderWindow


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _texts(widget, cls) -> list[str]:
    return [child.text() for child in widget.findChildren(cls)]


def test_matplotlib_chinese_font_configuration_is_callable() -> None:
    configure_matplotlib(use_qt_backend=False)

    assert matplotlib.rcParams["axes.unicode_minus"] is False
    assert matplotlib.rcParams["font.sans-serif"]


def test_overview_and_order_analysis_pages_create_offscreen(session_factory) -> None:
    app()

    overview = OverviewPage(order_service=OrderService(session_factory))
    analysis = OrderAnalysisPage(order_service=OrderService(session_factory))

    assert overview._recent_orders_view.toPlainText()
    assert analysis._report_view.toPlainText()


def test_lianxiao_order_page_is_reserved_without_fake_business_data() -> None:
    app()
    page = LianxiaoOrderPage()
    source = inspect.getsource(LianxiaoOrderPage)
    labels = "\n".join(_texts(page, QLabel))

    assert "当前测试版暂未开放连肖调单持久化功能" in labels
    assert "不参与正式记账、结算、导出" in labels
    assert "猴羊龙" not in labels
    assert "猴羊龙" not in source
    assert all(not button.isEnabled() for button in page.findChildren(QPushButton))


def test_special_order_page_is_reserved_without_fake_business_data() -> None:
    app()
    page = SpecialOrderPage()
    labels = "\n".join(_texts(page, QLabel))

    assert "当前测试版暂未开放调单持久化功能" in labels
    assert "本页仅为后续连码调单功能预留" in labels
    assert "不参与正式记账、结算、导出" in labels
    assert all(not button.isEnabled() for button in page.findChildren(QPushButton))


def test_split_order_window_marks_feature_unavailable() -> None:
    app()
    window = SplitOrderWindow()

    assert "拆单助手当前测试版暂未开放" in window._scope_hint.text()
    assert not window._btn_split.isEnabled()
    assert not window._btn_style.isEnabled()
    assert not window._btn_save.isEnabled()


def test_order_detail_page_keeps_supported_actions_and_hides_unopened_buttons(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )
    button_texts = set(_texts(page, QPushButton))
    label_texts = "\n".join(_texts(page, QLabel))

    assert "查询" in button_texts
    assert "导出 Excel" in button_texts
    assert page._btn_preview.text() == "结算预览"
    assert page._btn_void.text() == "作废订单"
    assert "更多批量处理和兑奖功能暂未开放" in label_texts
    for unopened in ("清空订单", "删除过滤订单", "导入订单", "过滤兑奖", "综合兑奖", "重置开奖"):
        assert unopened not in button_texts


def test_operation_log_page_does_not_expose_clear_log_button(session_factory) -> None:
    app()
    page = OperationLogPage(log_service=LogService(session_factory))
    button_texts = set(_texts(page, QPushButton))

    assert "查询" in button_texts
    assert "导出 Excel" in button_texts
    assert "清空日志" not in button_texts


def test_number_catalog_shows_static_reference_notice() -> None:
    app()
    page = NumberCatalogPage()
    text = page._content.toPlainText()

    assert "静态号码参考表" in text
    assert "当前版本不会自动随年份更新" in text
    assert "请以实际开奖年份配置为准" in text


def test_record_order_window_marks_unimplemented_options_and_footer_scope() -> None:
    app()
    window = RecordOrderWindow()
    window._parse_timer.stop()
    checkboxes = {checkbox.text(): checkbox for checkbox in window.findChildren(QCheckBox)}

    for label in ("识别地区", "智能纠错", "特肖模式", "抄写法", "各->各肖"):
        assert label in checkboxes
        assert not checkboxes[label].isEnabled()
        assert checkboxes[label].toolTip() == "暂未开放"
    assert "当前测试版重点支持特码类录入和结算" in window.findChild(QLabel, "footerHint").text()
    assert "全面支持" not in window.findChild(QLabel, "footerHint").text()
    assert "三中三" not in window.findChild(QLabel, "footerHint").text()
    window.close()
    window.deleteLater()


def test_readme_and_scope_document_describe_commercial_test_scope() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    scope = Path("docs/commercial_test_scope.md").read_text(encoding="utf-8")

    for heading in ("当前测试版已完成", "当前测试版暂未开放", "后续规划"):
        assert heading in readme
    assert "录单窗口尚未接入数据库" not in readme
    assert "订单详情、数据总览、订单分析仍未读取真实订单数据" not in readme
    assert "商用测试版范围" in scope
    assert "不显示假业务数据" in scope


def test_order_analysis_dead_demo_code_removed() -> None:
    import ui.pages.order_analysis_page as module

    source = inspect.getsource(module)
    assert "_build_macau_rows" not in source
    assert "_REPORT_HTML" not in source
