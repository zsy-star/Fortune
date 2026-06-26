from __future__ import annotations

import inspect
import os
from pathlib import Path

import matplotlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QLineEdit, QPushButton

from services.log_service import LogService
from services.draw_service import DrawService
from services.order_service import OrderService
from ui.main_window import MainWindow
from ui.matplotlib_setup import configure_matplotlib
from ui.pages.lianxiao_order_page import LianxiaoOrderPage
from ui.pages.draw_history_page import DrawHistoryPage
from ui.pages.number_catalog_page import NumberCatalogPage
from ui.pages.operation_log_page import OperationLogPage
from ui.pages.order_analysis_page import OrderAnalysisPage
from ui.pages.order_detail_page import OrderDetailPage
from ui.pages.overview_page import OverviewPage
from ui.pages.settlement_ledger_page import SettlementLedgerPage
from ui.pages.special_order_page import SpecialOrderPage
from ui.widgets.nav_hover_menu import NavHoverMenuButton
from ui.windows.record_order_window import RecordOrderWindow
from ui.windows.split_order_window import SplitOrderWindow
from ui.unavailable import UNAVAILABLE_TOOLTIP


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


def test_lianxiao_order_page_first_stage_is_readonly(session_factory) -> None:
    app()
    page = LianxiaoOrderPage(order_service=OrderService(session_factory))

    labels = "\n".join(_texts(page, QLabel))
    assert "原金额" not in labels
    assert "总计" not in labels
    assert "原连肖数据" in labels
    assert "调整后数据" in labels
    assert page._summary_table.rowCount() == 1
    assert len(page._tables) == 4
    assert not page.findChildren(QLineEdit)
    assert "暂无数据" in page._output.toPlainText()
    button_texts = {button.text() for button in page.findChildren(QPushButton)}
    assert "保存本次调整" not in button_texts
    assert "调整成为 10 的倍数" not in button_texts
    assert "清空当前调整" not in button_texts
    assert "连肖兑奖" not in button_texts
    assert page._btn_print.isEnabled()
    assert page._btn_reset.isEnabled()
    assert page._btn_clear_output.isEnabled()
    page._on_print_adjustment()
    page._on_reset_adjustment()
    assert "请先复制或导出当前汇总后打印" in page._output.toPlainText()
    assert "数据库订单未被修改" in page._output.toPlainText()


def test_special_order_page_is_tema_readonly_first_stage(session_factory) -> None:
    app()
    page = SpecialOrderPage(order_service=OrderService(session_factory))
    labels = "\n".join(_texts(page, QLabel))

    assert "特码调单" in labels
    assert "第一阶段只读汇总" in labels
    assert "连码调单" not in labels
    assert page._summary_table.rowCount() == 49
    assert len(page._adjust_edits) == 49
    assert page._btn_open_extension.isEnabled()
    assert page._btn_adjust_records.isEnabled()
    assert "暂无数据" in page._output.toPlainText()
    page._on_save_adjustment()
    page._on_reset_all_data()
    page._on_special_settlement()
    output = page._output.toPlainText()
    assert "调整保存功能后续开放" in output
    assert "高风险功能暂未开放" in output
    assert "不计算赔付" in output


def test_main_window_tema_nav_direct_and_hover_only_lianxiao() -> None:
    app()
    window = MainWindow()
    try:
        all_text = "\n".join(_texts(window, QPushButton))
        assert "连码调单" not in all_text
        assert window._adjust_nav is not None
        assert window._adjust_nav.main_button().text() == "特码调单"
        assert window._adjust_nav.menu_button().text() == "▾"
        assert [button.text() for button in window._adjust_nav._option_buttons] == ["连肖调单"]

        window._adjust_nav.main_button().click()
        assert isinstance(window._stack.currentWidget(), SpecialOrderPage)

        window._adjust_nav._option_buttons[0].click()
        assert isinstance(window._stack.currentWidget(), LianxiaoOrderPage)
    finally:
        window.close()
        window.deleteLater()


def test_tema_hover_menu_uses_delayed_stable_hide_instead_of_immediate_hide() -> None:
    source = inspect.getsource(NavHoverMenuButton)

    assert "_hide_popup_if_cursor_left" in source
    assert "Qt.WindowType.ToolTip" in source
    assert "Qt.WindowType.Popup" not in source
    assert "self._hide_timer.timeout.connect(self._popup.hide)" not in source


def test_split_order_window_opens_first_stage_text_tools() -> None:
    app()
    window = SplitOrderWindow()

    assert "拆单助手第一阶段仅用于文本整理" in window._scope_hint.text()
    assert window._btn_split.isEnabled()
    assert window._btn_style.isEnabled()
    assert window._btn_copy.isEnabled()
    assert window._btn_save.isEnabled()
    assert "不会保存订单" in window._scope_hint.text()


def test_split_order_first_stage_handlers_are_not_silent() -> None:
    app()
    window = SplitOrderWindow()

    window._input_text.setPlainText("兔各10，马各5")
    window._on_start_split()
    assert window._result_text.toPlainText() == "兔各10\n马各5"
    window._on_toggle_numbered_style()
    assert window._result_text.toPlainText() == "1. 兔各10\n2. 马各5"


def test_order_detail_page_keeps_supported_actions_and_disables_unopened_buttons(session_factory) -> None:
    app()
    page = OrderDetailPage(
        order_service=OrderService(session_factory),
        log_service=LogService(session_factory),
    )
    button_texts = set(_texts(page, QPushButton))
    assert "搜索" in button_texts
    assert "刷新" in button_texts
    assert "导出订单" in button_texts
    assert page._btn_preview.text() == "结算预览"
    assert page._btn_void.text() == "作废订单"
    unopened_buttons = (
        page._btn_clear_orders,
        page._btn_import_orders,
        page._btn_reset_draw,
    )
    assert all(button.text() in button_texts for button in unopened_buttons)
    assert all(not button.isEnabled() for button in unopened_buttons)
    assert all("暂未开放" in button.toolTip() for button in unopened_buttons)
    assert page._btn_filter_prize.text() == "过滤结算结果"
    assert page._btn_filter_prize.isEnabled()
    assert page._btn_combined_prize.text() == "综合结算摘要"
    assert page._btn_combined_prize.isEnabled()
    assert page._btn_expand_prize.text() == "扩大兑奖框"
    assert page._btn_expand_prize.isEnabled()


def test_operation_log_page_does_not_expose_clear_log_button(session_factory) -> None:
    app()
    page = OperationLogPage(log_service=LogService(session_factory))
    button_texts = set(_texts(page, QPushButton))

    assert "查询" in button_texts
    assert "导出 Excel" in button_texts
    assert "清空日志" not in button_texts
    assert "清空日志等高风险维护功能暂未开放" in "\n".join(_texts(page, QLabel))


def test_high_risk_handler_is_explicit_and_snapshot_detail_is_read_only(session_factory) -> None:
    app()
    log_page = OperationLogPage(log_service=LogService(session_factory))
    log_page._on_clear_disabled()
    assert "当前测试版暂未开放：清空操作日志" in log_page._lbl_total.text()
    assert "审计策略" in log_page._lbl_total.text()

    ledger_page = SettlementLedgerPage(order_service=OrderService(session_factory))
    assert ledger_page._btn_snapshot_detail.isEnabled()
    assert ledger_page._btn_snapshot_detail.text() == "查看结算快照详情"
    assert "快照详情直接展示正式结算保存时的数据" in ledger_page._lbl_readonly.text()


def test_draw_history_manual_maintenance_is_opened_safely(session_factory) -> None:
    app()
    page = DrawHistoryPage(draw_service=DrawService(session_factory))

    assert page._btn_manual_add.text() == "手工新增开奖"
    assert page._btn_manual_add.isEnabled()
    assert page._btn_manual_edit.text() == "修正选中开奖"
    assert not page._btn_manual_edit.isEnabled()
    assert page._btn_sync_latest.isEnabled()
    assert page._btn_sync_history.isEnabled()


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
    assert checkboxes["识别地区"].isEnabled()
    assert checkboxes["智能纠错"].isEnabled()
    for label in ("特肖模式", "抄写法", "各->各肖"):
        assert not checkboxes[label].isEnabled()
        assert "需要" in checkboxes[label].toolTip()
    assert "当前测试版重点支持特码类录入和结算" in window.findChild(QLabel, "footerHint").text()
    assert "未开放选项已禁用" in window.findChild(QLabel, "footerHint").text()
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
