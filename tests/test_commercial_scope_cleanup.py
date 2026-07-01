from __future__ import annotations

import inspect
import os
import subprocess
from pathlib import Path

import matplotlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QLineEdit, QPushButton

from schemas.order_schema import OrderCreate, OrderItemCreate
from services.adjustment_record_service import AdjustmentRecordService
from services.accounting_service import AccountLedgerService, CustomerAccountService
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
from ui.pages.customer_account_page import CustomerAccountPage
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
        CustomerAccountPage(
            account_service=CustomerAccountService(session_factory),
            ledger_service=AccountLedgerService(session_factory),
        ),
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
    assert "保存本次调整" in button_texts
    assert "调整记录" in button_texts
    assert "调整成为 10 的倍数" not in button_texts
    assert "清空当前调整" not in button_texts
    assert "连肖兑奖" not in button_texts
    assert page._btn_save_adjustment.isEnabled()
    assert page._btn_print.isEnabled()
    assert page._btn_copy_summary.isEnabled()
    assert page._btn_export_summary.isEnabled()
    assert page._btn_reset.isEnabled()
    assert page._btn_clear_output.isEnabled()
    assert page._btn_adjust_records.isEnabled()
    page._on_print_adjustment()
    page._on_reset_adjustment()
    assert "只是生成可复制/导出的打印文本" in page._output.toPlainText()
    assert "未调用系统打印机" in page._output.toPlainText()
    assert "数据库订单未被修改" in page._output.toPlainText()


def test_special_order_page_is_tema_readonly_first_stage(session_factory) -> None:
    app()
    page = SpecialOrderPage(order_service=OrderService(session_factory))
    labels = "\n".join(_texts(page, QLabel))

    assert "特码调单" in labels
    assert "不修改订单" in labels
    assert "连码调单" not in labels
    assert page._summary_table.rowCount() == 49
    assert len(page._adjust_edits) == 49
    assert not page._btn_open_extension.isEnabled()
    assert not page._btn_reset_all.isEnabled()
    assert not page._btn_special_settlement.isEnabled()
    assert "拓展调单规则尚未确认" in page._btn_open_extension.toolTip()
    assert "清空或重置数据需要权限" in page._btn_reset_all.toolTip()
    assert "真实兑奖涉及结算、赔付和余额流水" in page._btn_special_settlement.toolTip()
    assert page._btn_adjust_records.isEnabled()
    assert page._btn_copy_summary.isEnabled()
    assert page._btn_export_summary.isEnabled()
    assert "暂无数据" in page._output.toPlainText()
    page._on_save_adjustment()
    page._on_reset_all_data()
    page._on_special_settlement()
    output = page._output.toPlainText()
    assert "当前没有调整内容，无需保存" in output
    assert "重置所有数据未开放" in output
    assert "不执行兑奖" in output
    assert "不计算赔付金额" in output


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
        page._btn_reset_draw,
    )
    assert all(button.text() in button_texts for button in unopened_buttons)
    assert all(not button.isEnabled() for button in unopened_buttons)
    assert "高风险删除入口" in page._btn_clear_orders.toolTip()
    assert "高风险开奖维护入口" in page._btn_reset_draw.toolTip()
    assert page._btn_import_orders.text() == "导入订单"
    assert page._btn_import_orders.isEnabled()
    assert "预览" in page._btn_import_orders.toolTip()
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

    for label in ("识别地区", "智能纠错", "特肖模式", "岁写法", "各->各肖"):
        assert label in checkboxes
    assert "抄写法" not in checkboxes
    assert checkboxes["识别地区"].isEnabled()
    assert checkboxes["智能纠错"].isEnabled()
    for label in ("特肖模式", "岁写法", "各->各肖"):
        assert checkboxes[label].isEnabled()
        assert not checkboxes[label].isChecked()
        assert checkboxes[label].toolTip()
    assert "当前测试版重点支持特码类录入和结算" in window.findChild(QLabel, "footerHint").text()
    assert "不会触发结算或余额变动" in window.findChild(QLabel, "footerHint").text()
    assert "全面支持" not in window.findChild(QLabel, "footerHint").text()
    assert "三中三" not in window.findChild(QLabel, "footerHint").text()
    window.close()
    window.deleteLater()


def test_record_order_advanced_option_docs_match_current_scope() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    scope = Path("docs/commercial_test_scope.md").read_text(encoding="utf-8")
    feature_status = Path("docs/feature_status.md").read_text(encoding="utf-8")
    manual_script = Path("docs/manual_test_script.md").read_text(encoding="utf-8")
    acceptance = Path("docs/commercial_acceptance_checklist.md").read_text(encoding="utf-8")

    assert "| 特肖模式 | 第一阶段可用 |" in feature_status
    assert "| 岁写法 | 第一阶段可用 |" in feature_status
    assert "| 各->各肖 | 第一阶段可用 |" in feature_status
    assert "| 抄写法 | 暂未开放 |" not in feature_status
    for document in (readme, scope, feature_status, manual_script, acceptance):
        assert "特肖模式、抄写法、各->各肖仍禁用" not in document
        assert "特肖模式、抄写法、各->各肖；规则和保存口径未确认，保持禁用" not in document
        assert "仍禁用：特肖模式、抄写法、各->各肖" not in document
    for document in (readme, scope, acceptance):
        assert "特肖模式、岁写法、各->各肖" in document
        assert "只影响录单解析、预览和保存口径" in document
        assert "不自动结算" in document
        assert "不写余额" in document
        assert "不涉及真实兑奖" in document
    assert "录单高级选项验收样例" in manual_script
    for sample in ("羊马各10", "鼠、牛、虎各5", "龙-羊-猴各80", "25岁、08岁各10"):
        assert sample in manual_script


def test_readme_and_scope_document_describe_commercial_test_scope() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    scope = Path("docs/commercial_test_scope.md").read_text(encoding="utf-8")
    feature_status = Path("docs/feature_status.md").read_text(encoding="utf-8")
    manual_script = Path("docs/manual_test_script.md").read_text(encoding="utf-8")
    acceptance = Path("docs/commercial_acceptance_checklist.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmap.md").read_text(encoding="utf-8")

    for heading in ("当前测试版已完成", "当前测试版暂未开放", "后续规划"):
        assert heading in readme
    for document in (readme, scope, feature_status, manual_script, acceptance, roadmap):
        assert "商用测试版 / 内部试用版" in document
        assert "正式版、完整商业版" not in document
        assert "完整商业版" not in document
        assert "已完成全部功能" not in document
        assert "真实盈亏" not in document
        assert "余额已实现" not in document
    assert "录单窗口尚未接入数据库" not in readme
    assert "订单详情、数据总览、订单分析仍未读取真实订单数据" not in readme
    assert "订单导入、批量删除、清空订单" not in readme
    assert "拆单助手仅做文本整理，不识别复杂玩法、不保存订单、不写数据库" not in readme
    for document in (readme, scope, feature_status, manual_script, acceptance):
        assert "订单导入只预览" not in document
        assert "只预览不写库" not in document
        assert "拆单助手只做文本整理" not in document
        assert "拆单助手不能保存订单" not in document
        assert "调单保存未开放" not in document
        assert "赔付金额暂未计算" not in document
    assert "导入订单 | 暂未开放" not in feature_status
    assert "拆单助手保存订单 | 暂未开放" not in feature_status
    assert "赔付金额 / 中奖金额 | 暂未开放" not in feature_status
    assert "导入订单 | 第一阶段可用" in feature_status
    assert "拆单助手保存订单 | 第一阶段可用" in feature_status
    assert "调单快照记录" in feature_status
    assert "商用测试版 / 内部试用版范围" in scope
    assert "不显示假业务数据" in scope
    assert "调单页面保存的调整记录仅为快照，不修改订单状态" in scope
    assert "能预览订单并保存勾选的解析成功行" in acceptance
    assert "导入订单为第一阶段可用，只保存确认导入的成功行" in acceptance


def test_unopened_feature_freeze_list_is_explicit_and_not_misleading() -> None:
    documents = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/commercial_test_scope.md", "docs/feature_status.md")
    )
    required_items = [
        "客户账户 / 余额流水",
        "返水 / 佣金",
        "权限系统",
        "清空订单",
        "清空日志",
        "批量删除",
        "重置开奖",
        "真实兑奖",
        "真实修改原订单式调单",
        "真实打印机调用",
        "特肖模式",
        "岁写法",
        "各->各肖",
        "胆拖",
        "组选",
        "全包",
        "复式组合",
        "云同步 / 在线账号",
        "正式安装包",
    ]
    for item in required_items:
        assert item in documents
    assert "未冻结规则的写法不强行识别" in documents
    assert "完整规则未确认前不接入正式结算" in documents
    assert "不自动接入结算兑奖" in documents
    assert "功能边界" in documents


def test_permission_design_is_frozen_and_accounting_first_stage_is_bounded() -> None:
    permission_doc_path = Path("docs/permission_audit_model.md")
    accounting_doc_path = Path("docs/accounting_ledger_model.md")
    assert permission_doc_path.exists()
    assert accounting_doc_path.exists()

    permission_doc = permission_doc_path.read_text(encoding="utf-8")
    accounting_doc = accounting_doc_path.read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    feature_status = Path("docs/feature_status.md").read_text(encoding="utf-8")

    assert "暂未实现登录、账号、角色、权限审批" in permission_doc
    assert "当前不开放清空订单" in permission_doc
    assert "当前不开放真实兑奖" in permission_doc
    assert "当前不开放余额修改" in permission_doc
    assert "审计日志不可绕过" in permission_doc
    assert "二次确认" in permission_doc

    assert "客户账户 / 余额流水第一阶段已开放" in accounting_doc
    assert "已支持手工加款、手工扣款" in accounting_doc
    assert "余额不能直接覆盖" in accounting_doc
    assert "当前不自动把正式结算中奖金额入账" in accounting_doc
    assert "当前不开放真实兑奖" in accounting_doc
    assert "当前不做返水 / 佣金" in accounting_doc
    assert "所有金额使用 `Decimal`" in accounting_doc
    assert "禁止 `float`" in accounting_doc

    assert "[权限与审计模型](docs/permission_audit_model.md)" in readme
    assert "[账务 / 余额流水模型](docs/accounting_ledger_model.md)" in readme
    assert "权限与审计模型设计 | 设计已冻结，功能未开放" in feature_status
    assert "余额流水 / 客户账户 | 第一阶段可用" in feature_status
    assert "账务 / 余额流水模型 | 第一阶段可用" in feature_status
    assert "权限与审计模型设计 | 已完成" not in feature_status
    assert "余额流水 / 客户账户 | 暂未开放" not in feature_status


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
    ]


def test_order_analysis_dead_demo_code_removed() -> None:
    import ui.pages.order_analysis_page as module

    source = inspect.getsource(module)
    assert "_build_macau_rows" not in source
    assert "_REPORT_HTML" not in source
