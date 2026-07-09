from __future__ import annotations

import inspect
import os
import subprocess
from pathlib import Path

import matplotlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QLineEdit, QPushButton, QRadioButton, QSpinBox

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.adjustment_record_service import AdjustmentRecordService
from services.log_service import LogService
from services.draw_service import DrawService
from services.order_import_service import OrderImportService
from services.order_intake_service import OrderIntakeService
from services.order_service import OrderService
from services.settings_service import SettingsService
from services.settlement_service import SettlementService
from ui.dialogs.adjustment_record_dialog import AdjustmentRecordDialog
from ui.dialogs.order_import_dialog import OrderImportDialog
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.settlement_preview_dialog import SettlementPreviewDialog
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
from ui.pages.today_draw_page import TodayDrawPage
from ui.pages.tools_page import ToolsPage
from ui.widgets.nav_hover_menu import NavHoverMenuButton
from ui.windows.record_order_window import RecordOrderWindow
from ui.windows.split_order_window import SplitOrderWindow
from ui.unavailable import UNAVAILABLE_TOOLTIP


class EmptySettingsService:
    def list_declarers(self):
        return []


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


def test_commercial_test_version_main_pages_and_dialogs_create_offscreen(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    order = order_service.create_order(
        OrderCreate(
            customer_name="集成验收",
            channel="测试",
            region="澳门",
            raw_text="01各10",
            source="test",
            items=[OrderItemCreate(bet_type="特码", selection="01", amount="10")],
        )
    )

    widgets = [
        MainWindow(),
        OverviewPage(order_service=order_service),
        OrderAnalysisPage(order_service=order_service),
        SpecialOrderPage(order_service=order_service),
        LianxiaoOrderPage(order_service=order_service),
        TodayDrawPage(draw_service=DrawService(session_factory)),
        DrawHistoryPage(draw_service=DrawService(session_factory)),
        OrderDetailPage(order_service=order_service, log_service=LogService(session_factory)),
        SettlementLedgerPage(order_service=order_service),
        OperationLogPage(log_service=LogService(session_factory)),
        NumberCatalogPage(),
        ToolsPage(),
        SettingsDialog(settings_service=SettingsService(session_factory)),
        RecordOrderWindow(settings_service=EmptySettingsService()),
        SplitOrderWindow(settings_service=EmptySettingsService()),
        OrderImportDialog(
            import_service=OrderImportService(OrderIntakeService(session_factory)),
            settings_service=EmptySettingsService(),
        ),
        AdjustmentRecordDialog(service=AdjustmentRecordService(session_factory)),
        SettlementPreviewDialog(
            order.id,
            order_service=order_service,
            draw_service=DrawService(session_factory),
            settlement_service=SettlementService(session_factory),
        ),
    ]

    assert all(widget is not None for widget in widgets)
    assert widgets[0].windowTitle()
    assert widgets[-1].is_valid()
    for widget in widgets:
        close = getattr(widget, "close", None)
        if callable(close):
            close()
        delete_later = getattr(widget, "deleteLater", None)
        if callable(delete_later):
            delete_later()


def test_lianxiao_order_page_first_stage_is_readonly(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    page = LianxiaoOrderPage(order_service=order_service)
    before_order_count = order_service.count_orders()
    before_settlement_count = order_service.count_settlement_ledger()

    labels = "\n".join(_texts(page, QLabel))
    assert "原金额" not in labels
    assert "总计" not in labels
    assert "原连肖数据" in labels
    assert "调整后数据" in labels
    assert page._summary_table.rowCount() == 1
    assert len(page._tables) == 5
    for table in (page._summary_table, *page._tables):
        assert [table.horizontalHeaderItem(index).text() for index in range(table.columnCount())] == [
            "生肖组",
            "持有",
            "盈亏",
        ]
    assert {"只看澳门", "只看香港"}.issubset({radio.text() for radio in page.findChildren(QRadioButton)})
    assert page._adjustment_input in page.findChildren(QLineEdit)
    button_texts = {button.text() for button in page.findChildren(QPushButton)}
    assert "打印连肖调整" in button_texts
    assert "清空输出框" in button_texts
    assert "重置调整" in button_texts
    assert "保存本次调整" in button_texts
    assert "打开扩展" in button_texts
    assert "调整记录" in button_texts
    assert "调整成为 10 的倍数" not in button_texts
    assert "清空当前调整" not in button_texts
    assert "连肖兑奖" not in button_texts
    assert page._btn_save_adjustment.isEnabled()
    assert page._btn_print.isEnabled()
    assert page._btn_reset.isEnabled()
    assert page._btn_clear_output.isEnabled()
    assert page._btn_adjust_records.isEnabled()
    page._on_print_adjustment()
    assert "连肖调整" in page._output.toPlainText()
    page._on_reset_adjustment()
    assert "保留原始订单汇总" in page._output.toPlainText()
    assert order_service.count_orders() == before_order_count
    assert order_service.count_settlement_ledger() == before_settlement_count


def test_special_order_page_is_tema_readonly_first_stage(session_factory) -> None:
    app()
    order_service = OrderService(session_factory)
    page = SpecialOrderPage(order_service=order_service)
    before_order_count = order_service.count_orders()
    before_settlement_count = order_service.count_settlement_ledger()
    labels = "\n".join(_texts(page, QLabel))

    assert {"只看澳门", "只看香港"}.issubset({radio.text() for radio in page.findChildren(QRadioButton)})
    assert [page._summary_table.horizontalHeaderItem(index).text() for index in range(page._summary_table.columnCount())] == [
        "号码",
        "下注数",
        "盈亏",
        "ID",
    ]
    for expected in ("号码", "原特码数据", "调整后数据", "最大亏损", "调整额"):
        assert expected in labels
    assert "连码调单" not in labels
    assert page._summary_table.rowCount() == 49
    assert len(page._adjust_edits) == 49
    button_texts = {button.text() for button in page.findChildren(QPushButton)}
    for expected in (
        "保存本次调整",
        "调整为10的倍数",
        "清空当前调单",
        "清空输出框",
        "重置所有数据",
        "结码总奖",
        "打开扩展",
        "调整记录",
    ):
        assert expected in button_texts
    assert page._btn_adjust_records.isEnabled()
    page._on_save_adjustment()
    page._on_reset_all_data()
    page._on_special_settlement()
    output = page._output.toPlainText()
    assert "当前没有调整内容，无需保存" in output
    assert "重新从订单数据计算原始汇总" in output
    assert "不执行结算入账" in output
    assert order_service.count_orders() == before_order_count
    assert order_service.count_settlement_ledger() == before_settlement_count


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
    window = SplitOrderWindow(settings_service=EmptySettingsService())

    assert "可预览拆分结果并确认保存成功行" in window._scope_hint.text()
    assert window._btn_split.isEnabled()
    assert window._btn_style.isEnabled()
    assert window._btn_copy.isEnabled()
    assert window._btn_save.isEnabled()
    assert window._btn_preview_orders.isEnabled()
    assert not window._btn_confirm_save.isEnabled()
    assert "不会结算" in window._scope_hint.text()


def test_split_order_first_stage_handlers_are_not_silent() -> None:
    app()
    window = SplitOrderWindow(settings_service=EmptySettingsService())

    window._input_text.setPlainText("兔各10，马各5")
    window._on_start_split()
    assert window._result_text.toPlainText() == "兔各10\n马各5"
    window._on_toggle_numbered_style()
    assert window._result_text.toPlainText() == "1. 兔各10\n2. 马各5"


def test_order_detail_page_keeps_supported_actions_and_guards_high_risk_buttons(session_factory) -> None:
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
    high_risk_buttons = (
        page._btn_clear_orders,
        page._btn_bulk_delete_orders,
        page._btn_reset_draw,
    )
    assert all(button.text() in button_texts for button in high_risk_buttons)
    assert page._btn_clear_orders.isEnabled()
    assert page._btn_clear_orders.objectName() == "dangerAction"
    assert "自动备份" in page._btn_clear_orders.toolTip()
    assert not page._btn_bulk_delete_orders.isEnabled()
    assert page._btn_bulk_delete_orders.objectName() == "dangerAction"
    assert page._btn_reset_draw.isEnabled()
    assert page._btn_reset_draw.objectName() == "dangerAction"
    assert "无结算记录" in page._btn_reset_draw.toolTip()
    assert page._btn_import_orders.text() == "导入订单"
    assert page._btn_import_orders.isEnabled()
    assert "预览" in page._btn_import_orders.toolTip()
    assert page._btn_filter_prize.text() == "过滤结算结果"
    assert page._btn_filter_prize.isEnabled()
    assert page._btn_combined_prize.text() == "综合结算摘要"
    assert page._btn_combined_prize.isEnabled()
    assert page._btn_expand_prize.text() == "扩大兑奖框"
    assert page._btn_expand_prize.isEnabled()


def test_operation_log_page_exposes_guarded_clear_log_button(session_factory) -> None:
    app()
    page = OperationLogPage(log_service=LogService(session_factory))
    button_texts = set(_texts(page, QPushButton))

    assert "查询" in button_texts
    assert "导出表格" in button_texts
    assert "清空日志" in button_texts
    assert page._btn_clear_logs.isEnabled()
    assert page._btn_clear_logs.objectName() == "dangerAction"
    assert "归档当前日志" in page._btn_clear_logs.toolTip()
    assert "备份数据库" in "\n".join(_texts(page, QLabel))


def test_high_risk_handler_is_explicit_and_snapshot_detail_is_read_only(session_factory) -> None:
    app()
    log_page = OperationLogPage(log_service=LogService(session_factory))
    assert log_page._btn_clear_logs.objectName() == "dangerAction"
    assert "归档当前日志" in log_page._btn_clear_logs.toolTip()

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
    assert page._btn_reset_draws.text() == "重置开奖记录"
    assert page._btn_reset_draws.isEnabled()
    assert page._btn_reset_draws.objectName() == "dangerAction"
    assert "无结算记录" in page._btn_reset_draws.toolTip()


def test_number_catalog_supports_zodiac_year_switching() -> None:
    app()
    page = NumberCatalogPage()
    year_spin = page.findChild(QSpinBox, "zodiacYearSpin")

    assert year_spin is not None
    year_spin.setValue(2026)
    text = page._content.toPlainText()

    assert "静态号码参考表" in text
    assert "生肖号码按所选开奖年份显示，请以实际开奖年份为准。" in text
    assert "当前生肖年份：2026" in text
    assert "马" in text
    assert "01 13 25 37 49" in text
    old_notice = "当前版本不会" + "自动随年份更新"
    assert old_notice not in text

    year_spin.setValue(2025)
    changed_text = page._content.toPlainText()
    assert "当前生肖年份：2025" in changed_text
    assert "蛇" in changed_text
    assert changed_text != text


def test_record_order_window_marks_unimplemented_options_and_footer_scope() -> None:
    app()
    window = RecordOrderWindow()
    window._parse_timer.stop()
    checkboxes = {checkbox.text(): checkbox for checkbox in window.findChildren(QCheckBox)}

    for label in ("识别地区", "智能纠错", "特肖模式", "岁写法", "各->各肖"):
        assert label in checkboxes
    assert "抄写法" not in checkboxes
    assert checkboxes["识别地区"].isEnabled()
    assert checkboxes["智能纠错"].isEnabled()
    for label in ("特肖模式", "岁写法", "各->各肖"):
        assert checkboxes[label].isEnabled()
        assert not checkboxes[label].isChecked()
        assert checkboxes[label].toolTip()
    assert "当前版本重点支持特码类录入和结算" in window.findChild(QLabel, "footerHint").text()
    assert "不会触发结算或余额变动" in window.findChild(QLabel, "footerHint").text()
    assert "全面支持" not in window.findChild(QLabel, "footerHint").text()
    assert "三中三" not in window.findChild(QLabel, "footerHint").text()
    window.close()
    window.deleteLater()


def test_record_order_advanced_option_docs_match_current_scope() -> None:
    documents = [
        Path("README.md").read_text(encoding="utf-8"),
        Path("docs/commercial_test_scope.md").read_text(encoding="utf-8"),
        Path("docs/feature_status.md").read_text(encoding="utf-8"),
        Path("docs/manual_test_script.md").read_text(encoding="utf-8"),
        Path("docs/commercial_acceptance_checklist.md").read_text(encoding="utf-8"),
    ]
    combined = "\n".join(documents)

    for phrase in ("\u7279\u8096\u6a21\u5f0f", "\u5c81\u5199\u6cd5", "\u5404->\u5404\u8096"):
        assert phrase in combined
    assert "\u53ea\u5f71\u54cd\u5f55\u5355\u89e3\u6790" in combined
    assert "\u9ad8\u7ea7\u9009\u9879\u7981\u7528" not in combined
    assert "\u7279\u8096\u6a21\u5f0f\u7981\u7528" not in combined
    assert "\u5c81\u5199\u6cd5\u7981\u7528" not in combined
    assert "\u5404->\u5404\u8096\u7981\u7528" not in combined


def test_readme_and_scope_document_describe_small_commercial_scope() -> None:
    documents = [
        Path("README.md").read_text(encoding="utf-8"),
        Path("docs/commercial_test_scope.md").read_text(encoding="utf-8"),
        Path("docs/feature_status.md").read_text(encoding="utf-8"),
        Path("docs/manual_test_script.md").read_text(encoding="utf-8"),
        Path("docs/commercial_acceptance_checklist.md").read_text(encoding="utf-8"),
        Path("docs/roadmap.md").read_text(encoding="utf-8"),
    ]
    combined = "\n".join(documents)

    for document in documents:
        assert "\u5c0f\u8303\u56f4" in document
        assert "\u5b8c\u6574\u5546\u4e1a\u7248" not in document
        assert "\u5df2\u5b8c\u6210\u5168\u90e8\u529f\u80fd" not in document
        assert "\u4f59\u989d\u5df2\u5b9e\u73b0" not in document
    for phrase in ("\u8ba2\u5355\u5bfc\u5165", "\u62c6\u5355\u52a9\u624b", "\u8c03\u5355\u5feb\u7167", "\u4e2d\u5956\u91d1\u989d", "\u8fd4\u6c34"):
        assert phrase in combined
    assert "\u8ba2\u5355\u5bfc\u5165\u53ea\u9884\u89c8" not in combined
    assert "\u62c6\u5355\u52a9\u624b\u53ea\u505a\u6587\u672c\u6574\u7406" not in combined
    assert "\u8c03\u5355\u4fdd\u5b58\u672a\u5f00\u653e" not in combined
    assert "\u8d54\u4ed8\u91d1\u989d\u6682\u672a\u8ba1\u7b97" not in combined


def test_unopened_feature_freeze_list_is_explicit_and_not_misleading() -> None:
    documents = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/commercial_test_scope.md", "docs/feature_status.md")
    )
    assert "\u9ad8\u98ce\u9669\u672a\u5f00\u653e" in documents
    assert "\u660e\u786e\u4e0d\u7eb3\u5165\u5f53\u524d\u4ea7\u54c1\u8303\u56f4" in documents
    required_items = [
        "\u5ba2\u6237\u8d26\u6237",
        "\u5ba2\u6237\u4f59\u989d",
        "\u4f59\u989d\u6d41\u6c34",
        "\u771f\u5b9e\u5151\u5956\u5165\u8d26",
        "\u6743\u9650\u7cfb\u7edf",
        "\u6e05\u7a7a\u8ba2\u5355",
        "\u6e05\u7a7a\u65e5\u5fd7",
        "\u6279\u91cf\u5220\u9664",
        "\u91cd\u7f6e\u5f00\u5956",
        "\u771f\u5b9e\u4fee\u6539\u539f\u8ba2\u5355\u5f0f\u8c03\u5355",
        "\u771f\u5b9e\u6253\u5370\u673a\u8c03\u7528",
        "\u4e91\u540c\u6b65 / \u5728\u7ebf\u8d26\u53f7",
        "\u6b63\u5f0f\u5b89\u88c5\u5305\u548c\u5347\u7ea7\u6d41\u7a0b",
        "\u80c6\u62d6",
        "\u7ec4\u9009",
        "\u5168\u5305",
    ]
    for item in required_items:
        assert item in documents
    assert "\u4e0d\u505a\u5ba2\u6237\u8d26\u6237" in documents
    assert "\u4e0d\u505a\u4f59\u989d\u6d41\u6c34" in documents
    assert "\u4e0d\u505a\u771f\u5b9e\u5151\u5956\u5165\u8d26" in documents
    assert "\u8fd4\u6c34" in documents
    assert "\u7edf\u8ba1\u9879" in documents
    assert "\u4e0d\u5165\u8d26" in documents
    assert "\u9700\u8981\u53c2\u8003\u8f6f\u4ef6\u6837\u4f8b" in documents
    assert "\u8fd4\u6c34 / \u4f63\u91d1 | \u6682\u672a\u5f00\u653e" not in documents


def test_first_release_settlement_support_scope_is_documented() -> None:
    documents = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("docs/settlement_rules.md", "docs/feature_status.md")
    )

    for phrase in (
        "第一版正式结算支持",
        "可录单但暂不支持正式结算",
        "明确不在第一版范围",
        "连肖复选",
        "二中特",
        "特串",
        "正式结算必须",
        "不得写正式结算快照",
        "不得改变订单",
    ):
        assert phrase in documents


def test_printing_scope_is_text_only_and_not_a_commercial_gap() -> None:
    documents_by_path = {
        path: Path(path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/commercial_test_scope.md",
            "docs/feature_status.md",
            "docs/manual_test_script.md",
            "docs/commercial_acceptance_checklist.md",
            "docs/roadmap.md",
        )
    }
    combined = "\n".join(documents_by_path.values())

    assert "\u6253\u5370\u80fd\u529b\u4ee5\u6587\u672c\u751f\u6210\u3001\u590d\u5236\u3001\u5bfc\u51fa\u4e3a\u51c6" in combined
    assert "\u4e0d\u63a5\u5165\u771f\u5b9e\u6253\u5370\u673a" in combined
    assert "\u6253\u5370\u673a\u9a71\u52a8\u9002\u914d" in combined
    assert "\u9759\u9ed8\u6253\u5370" in combined
    assert "\u6253\u5370\u6a21\u677f\u7f16\u8f91\u5668" in combined
    assert "\u5fc5\u987b\u63a5\u5165\u771f\u5b9e\u6253\u5370\u673a" not in combined
    assert "\u9700\u8981\u6253\u5370\u6a21\u677f\u548c\u8bbe\u5907\u9002\u914d" not in combined
    assert "\u771f\u5b9e\u6253\u5370\u673a\u8c03\u7528\uff1a\u9700\u8981" not in combined

    for path in ("docs/commercial_test_scope.md", "docs/feature_status.md"):
        high_risk_section = documents_by_path[path].split("## \u9ad8\u98ce\u9669\u672a\u5f00\u653e", 1)[1]
        assert "\u771f\u5b9e\u6253\u5370\u673a\u8c03\u7528" not in high_risk_section


def test_docs_split_high_risk_from_out_of_product_scope() -> None:
    documents_by_path = {
        path: Path(path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/commercial_test_scope.md",
            "docs/feature_status.md",
            "docs/manual_test_script.md",
            "docs/commercial_acceptance_checklist.md",
            "docs/roadmap.md",
        )
    }
    combined = "\n".join(documents_by_path.values())

    assert "\u9ad8\u98ce\u9669\u672a\u5f00\u653e" in combined
    assert "\u660e\u786e\u4e0d\u7eb3\u5165\u5f53\u524d\u4ea7\u54c1\u8303\u56f4" in combined
    for phrase in (
        "\u6743\u9650\u7cfb\u7edf",
        "\u6e05\u7a7a\u8ba2\u5355",
        "\u6e05\u7a7a\u65e5\u5fd7",
        "\u91cd\u7f6e\u5f00\u5956",
        "\u771f\u6b63\u4fee\u6539\u539f\u8ba2\u5355\u5f0f\u8c03\u5355",
        "\u9700\u8981\u53c2\u8003\u8f6f\u4ef6\u6837\u4f8b",
    ):
        assert phrase in combined
    for phrase in (
        "\u5ba2\u6237\u8d26\u6237",
        "\u5ba2\u6237\u4f59\u989d",
        "\u4f59\u989d\u6d41\u6c34",
        "\u94b1\u5305\u7cfb\u7edf",
        "\u652f\u4ed8\u7cfb\u7edf",
        "\u771f\u5b9e\u4ed8\u6b3e",
        "\u771f\u5b9e\u6536\u6b3e",
        "\u771f\u5b9e\u5151\u5956\u5165\u8d26",
        "\u771f\u5b9e\u6253\u5370\u673a\u8c03\u7528",
        "\u6253\u5370\u673a\u9a71\u52a8\u9002\u914d",
        "\u4e91\u540c\u6b65 / \u5728\u7ebf\u8d26\u53f7",
    ):
        assert phrase in combined
    assert "\u4e0d\u4f5c\u4e3a\u6b63\u5f0f\u5546\u7528\u5fc5\u505a\u7f3a\u53e3" in combined
    assert "\u5f53\u524d\u7248\u672c\u4e0d\u8ba1\u5212\u5b9e\u73b0" in combined
    assert "\u4e2d\u5956\u91d1\u989d\u662f\u7ed3\u7b97\u5feb\u7167 / \u7edf\u8ba1\u53c2\u8003" in combined
    assert "\u4e0d\u4ee3\u8868\u771f\u5b9e\u4ed8\u6b3e" in combined
    assert "\u4e0d\u5f62\u6210\u5ba2\u6237\u4f59\u989d" in combined


def test_commercial_release_acceptance_plan_and_samples_exist() -> None:
    required_paths = [
        Path("docs/commercial_release_acceptance_plan.md"),
        Path("docs/samples/order_entry_samples.txt"),
        Path("docs/samples/import_orders_sample.csv"),
        Path("docs/samples/settlement_acceptance_cases.md"),
        Path("docs/samples/high_risk_scope_checklist.md"),
    ]
    for path in required_paths:
        assert path.exists(), f"missing acceptance artifact: {path}"
        assert path.read_text(encoding="utf-8").strip()

    plan = Path("docs/commercial_release_acceptance_plan.md").read_text(encoding="utf-8")
    for section in (
        "## 1. 验收目标",
        "## 2. 验收环境",
        "## 3. 验收前准备",
        "## 4. 录单验收样例",
        "## 5. 导入验收样例",
        "## 6. 拆单助手验收样例",
        "## 7. 开奖验收样例",
        "## 8. 结算验收样例",
        "## 9. 复杂玩法结算验收样例",
        "## 10. 订单管理验收",
        "## 11. 调单快照验收",
        "## 12. 操作日志验收",
        "## 13. 备份恢复验收",
        "## 14. 导出 / 打印文本验收",
        "## 15. 高风险维护与未开放确认",
        "## 16. 明确不纳入产品范围确认",
        "## 17. 验收通过标准",
    ):
        assert section in plan

    combined = "\n".join(path.read_text(encoding="utf-8") for path in required_paths)
    for phrase in (
        "不做客户账户",
        "客户余额",
        "余额流水",
        "真实兑奖入账",
        "真实打印机",
        "云同步 / 在线账号",
        "返水",
        "统计项",
        "中奖金额",
        "统计参考",
        "权限 / 登录 / 角色 / 审批",
        "清空订单",
        "清空日志",
        "重置开奖",
        "连肖复选",
        "正码特",
        "特串",
    ):
        assert phrase in combined

    sample_text = Path("docs/samples/order_entry_samples.txt").read_text(encoding="utf-8")
    for phrase in (
        "特码 01 各10",
        "兔各10",
        "红波各20",
        "N不中 08,09,10 各100",
        "平尾 1,3,4,6 各1000",
        "二中二 01,02 各10",
        "复2 01,02,03,04,05 各10",
        "二中二 01,02,03,04,05 拖 06,07,08,09,10 各5",
        "马蛇10",
        "1岁各10",
        "羊马各10",
    ):
        assert phrase in sample_text

    csv_text = Path("docs/samples/import_orders_sample.csv").read_text(encoding="utf-8")
    assert "region,raw_text,declarer,channel,expected_status,expected_total" in csv_text
    assert "failed" in csv_text
    assert "duplicate_check" in csv_text


def test_permission_design_is_frozen_and_accounting_is_out_of_product_scope() -> None:
    permission_doc_path = Path("docs/permission_audit_model.md")
    accounting_doc_path = Path("docs/accounting_ledger_model.md")
    assert permission_doc_path.exists()
    assert accounting_doc_path.exists()

    accounting_doc = accounting_doc_path.read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    feature_status = Path("docs/feature_status.md").read_text(encoding="utf-8")

    for text in (accounting_doc, readme, feature_status):
        assert "\u4e0d\u505a\u5ba2\u6237\u4f59\u989d" in text
        assert "\u4e0d\u505a\u4f59\u989d\u6d41\u6c34" in text
        assert "\u4e0d\u505a\u771f\u5b9e\u5151\u5956\u5165\u8d26" in text
        assert "\u4e0d\u6d89\u53ca\u771f\u5b9e\u8d44\u91d1\u652f\u4ed8" in text
        assert "\u8fd4\u6c34" in text
        assert "\u7edf\u8ba1\u9879" in text
        assert "\u4e0d\u5165\u8d26" in text

    assert "\u5ba2\u6237\u8d26\u6237 / \u4f59\u989d\u6d41\u6c34\u7b2c\u4e00\u9636\u6bb5\u5df2\u5f00\u653e" not in accounting_doc
    assert "\u5df2\u652f\u6301\u624b\u5de5\u52a0\u6b3e" not in accounting_doc
    assert "\u5df2\u652f\u6301\u624b\u5de5\u6263\u6b3e" not in accounting_doc
    assert "entry_type=settlement_payout" not in accounting_doc
    assert "payout_posted_at" not in accounting_doc
    assert "\u4f59\u989d\u6d41\u6c34 / \u5ba2\u6237\u8d26\u6237 | \u7b2c\u4e00\u9636\u6bb5\u53ef\u7528" not in feature_status
    assert "\u771f\u5b9e\u5151\u5956 / \u7ed3\u7b97\u4e2d\u5956\u91d1\u989d\u5165\u8d26\u7b2c\u4e00\u9636\u6bb5" not in feature_status

def test_repository_safety_ignores_runtime_files_and_keeps_migrations_frozen() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    for pattern in ("data/*.db", "data/backups/", "exports/", ".pytest_cache*", "**pycache**/", "build/", "dist/"):
        assert pattern in gitignore

    tracked_db = subprocess.run(
        ["git", "ls-files", "data/fortune.db"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert tracked_db.stdout.strip() == ""

    migration_files = sorted(path.name for path in Path("alembic/versions").glob("*.py"))
    assert migration_files == [
        "20260612_0001_create_data_foundation.py",
        "20260624_0002_create_settlement_records.py",
        "20260624_0003_create_settings_tables.py",
        "20260626_0004_create_app_meta.py",
        "20260628_0005_create_adjustment_records.py",
        "20260701_0006_create_customer_accounts.py",
        "20260702_0007_add_settlement_payout_posting.py",
        "20260702_0008_remove_accounting_ledger_and_payout_posting.py",
        "20260705_0009_add_order_zodiac_year.py",
    ]

def test_order_analysis_dead_demo_code_removed() -> None:
    import ui.pages.order_analysis_page as module

    source = inspect.getsource(module)
    assert "_build_macau_rows" not in source
    assert "_REPORT_HTML" not in source
