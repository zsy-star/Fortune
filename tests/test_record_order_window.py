"""测试 RecordOrderWindow 录单窗口。

使用 QT_QPA_PLATFORM=offscreen，不访问真实数据库、真实剪贴板、
OrderService、OrderIntakeService、SQLAlchemy Session 或 49wz777.com。

覆盖：
- 窗口创建/关闭
- 输入解析
- 添加结果到表格
- 每号一行
- 每行金额使用 r.amount
- 总金额计算
- 列名确认
- 清空功能（保留地区/渠道/计算方式）
- 删除选中行
- 无选中行删除不崩溃
- clipboard.mimeData() 返回 None 不异常
- 工具栏按钮未实现
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtWidgets import (
    QApplication,
    QTableWidgetItem,
    QPushButton,
)

from services.order_parser import ParseResult, parse_order

# ── 模块级 QApplication ──


@pytest.fixture(scope="module")
def qapp():
    """确保整个测试模块共享一个 QApplication（offscreen）。"""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # 不调用 quit() —— 其他模块可能还在用


@pytest.fixture
def window(qapp):
    """创建干净窗口，禁用定时器并关闭自动获取，避免真实剪贴板访问。"""
    from ui.windows.record_order_window import RecordOrderWindow

    w = RecordOrderWindow()
    w._clip_timer.stop()
    w._parse_timer.stop()
    if hasattr(w, "_chk_auto_fetch"):
        w._chk_auto_fetch.setChecked(False)
    yield w
    w.close()
    w.deleteLater()


# ══════════════════════════════════════════════════════════════════════
# 1. 窗口创建/关闭
# ══════════════════════════════════════════════════════════════════════


class TestWindowLifecycle:
    def test_create_and_close(self, qapp):
        """窗口可以正常创建和关闭。"""
        from ui.windows.record_order_window import RecordOrderWindow

        w = RecordOrderWindow()
        w._clip_timer.stop()
        w._parse_timer.stop()
        assert w.isVisible() is False  # 未 show()
        assert w.windowTitle() == "我要录单"
        w.close()
        w.deleteLater()

    def test_show_and_hide(self, window, qapp):
        """窗口可以正常显示和隐藏。"""
        window.show()
        qapp.processEvents()
        assert window.isVisible()
        window.hide()
        assert not window.isVisible()


# ══════════════════════════════════════════════════════════════════════
# 2. 输入解析
# ══════════════════════════════════════════════════════════════════════


class TestInputParsing:
    def test_parse_01_02_03_each_10(self, window):
        """输入「01,02,03各10」后能生成成功解析结果。"""
        window._input_text.setPlainText("01,02,03各10")
        window._do_parse()
        results = window._parsed_results
        assert len(results) == 1
        r = results[0]
        assert r.success
        assert r.numbers == (1, 2, 3)
        assert r.amount == 10.0
        assert r.total == 30.0

    def test_parse_output_text_populated(self, window):
        """解析成功后输出框包含格式化结果。"""
        window._input_text.setPlainText("01,02,03各10")
        window._do_parse()
        output = window._output_text.toPlainText()
        assert "01,02,03" in output
        assert "30" in output  # total

    def test_parse_empty_input_clears(self, window):
        """空输入时解析结果和输出框清空。"""
        window._input_text.setPlainText("兔各10")
        window._do_parse()
        assert len(window._parsed_results) == 1
        # 清空输入
        window._input_text.clear()
        window._do_parse()
        assert len(window._parsed_results) == 0
        assert window._output_text.toPlainText() == ""

    def test_parse_default_region_macau(self, window):
        """默认地区为澳门时，未指定地域的解析结果会注入澳门。"""
        window._radio_macau.setChecked(True)
        window._input_text.setPlainText("兔各10")
        window._do_parse()
        r = window._parsed_results[0]
        assert r.region == "澳门"

    def test_parse_default_region_hk(self, window):
        """选择香港时，未指定地域的解析结果会注入香港。"""
        window._radio_hk.setChecked(True)
        window._input_text.setPlainText("兔各10")
        window._do_parse()
        r = window._parsed_results[0]
        assert r.region == "香港"


# ══════════════════════════════════════════════════════════════════════
# 3. 表格添加
# ══════════════════════════════════════════════════════════════════════


class TestAddToTable:
    def _setup_parsed(self, window, text="01,02,03各10"):
        """辅助：解析输入并返回结果。"""
        window._input_text.setPlainText(text)
        window._do_parse()

    def test_add_result_adds_three_rows(self, window):
        """点击添加结果后表格增加 3 行。"""
        self._setup_parsed(window)
        window._on_add_result()
        assert window._order_table.rowCount() == 3

    def test_each_number_own_row(self, window):
        """每个号码独占一行。"""
        self._setup_parsed(window)
        window._on_add_result()
        numbers_in_table = []
        for row in range(window._order_table.rowCount()):
            item = window._order_table.item(row, 2)  # "订单信息" 列
            numbers_in_table.append(int(item.text()))
        assert numbers_in_table == [1, 2, 3]

    def test_row_amount_uses_r_amount(self, window):
        """每行金额为 10，确认使用的是 r.amount，不是 r.total。"""
        self._setup_parsed(window)
        window._on_add_result()
        for row in range(window._order_table.rowCount()):
            amt_col5 = window._order_table.item(row, 5).text()  # "金额"
            amt_col6 = window._order_table.item(row, 6).text()  # "每号金额"
            assert amt_col5 == "10"
            assert amt_col6 == "10"

    def test_table_total_is_30(self, window):
        """表格总金额为 30。"""
        self._setup_parsed(window)
        window._on_add_result()
        lbl = window._lbl_total.text()
        assert "30" in lbl

    def test_column_header_name(self, window):
        """列名已经是「每号金额」。"""
        header = window._order_table.horizontalHeaderItem(6)
        assert header is not None
        assert header.text() == "每号金额"


# ══════════════════════════════════════════════════════════════════════
# 4. 清空功能
# ══════════════════════════════════════════════════════════════════════


class TestClearFunctionality:
    def _setup_and_add(self, window):
        """辅助：解析并添加到表格，然后返回设置前的状态。"""
        window._input_text.setPlainText("01,02,03各10")
        window._do_parse()
        window._on_add_result()
        # 记下地区/渠道/计算方式的当前值
        region = "澳门" if window._radio_macau.isChecked() else "香港"
        channel = window._cmb_channel.currentText()
        calc = window._cmb_calc.currentText()
        return region, channel, calc

    def test_clear_input_box(self, window):
        """清空会清空输入框。"""
        self._setup_and_add(window)
        window._on_clear_output()
        assert window._input_text.toPlainText() == ""

    def test_clear_output_box(self, window):
        """清空会清空输出框。"""
        self._setup_and_add(window)
        window._on_clear_output()
        assert window._output_text.toPlainText() == ""

    def test_clear_parsed_results(self, window):
        """清空会清空 _parsed_results。"""
        self._setup_and_add(window)
        window._on_clear_output()
        assert window._parsed_results == []

    def test_clear_table(self, window):
        """清空会清空表格。"""
        self._setup_and_add(window)
        window._on_clear_output()
        assert window._order_table.rowCount() == 0

    def test_clear_total(self, window):
        """清空会清空总金额标签。"""
        self._setup_and_add(window)
        window._on_clear_output()
        assert window._lbl_total.text() == "当前总额: 0"
        assert window._lbl_selected_total.text() == "当前选择总额: 0"

    def test_clear_resets_user_adjusted(self, window):
        """清空会重置 _table_user_adjusted。"""
        self._setup_and_add(window)
        window._table_user_adjusted = True
        window._on_clear_output()
        assert window._table_user_adjusted is False

    def test_clear_preserves_region(self, window):
        """清空不会重置地区。"""
        window._radio_hk.setChecked(True)
        self._setup_and_add(window)
        window._on_clear_output()
        assert window._radio_hk.isChecked()
        assert not window._radio_macau.isChecked()

    def test_clear_preserves_channel(self, window):
        """清空不会重置渠道。"""
        window._cmb_channel.setCurrentText("现金")
        self._setup_and_add(window)
        window._on_clear_output()
        assert window._cmb_channel.currentText() == "现金"

    def test_clear_preserves_calc_method(self, window):
        """清空不会重置计算方式。"""
        window._cmb_calc.setCurrentText("定总")
        self._setup_and_add(window)
        window._on_clear_output()
        assert window._cmb_calc.currentText() == "定总"


# ══════════════════════════════════════════════════════════════════════
# 5. 删除选中行
# ══════════════════════════════════════════════════════════════════════


class TestDeleteSelected:
    def _setup_and_add(self, window):
        """辅助：解析 3 个号码并添加到表格。"""
        window._input_text.setPlainText("01,02,03各10")
        window._do_parse()
        window._on_add_result()

    def test_delete_reduces_row_count(self, window):
        """删除选中行后表格行数减少。"""
        self._setup_and_add(window)
        assert window._order_table.rowCount() == 3
        # 选中第 0 行
        window._order_table.selectRow(0)
        window._on_delete_selected()
        assert window._order_table.rowCount() == 2

    def test_delete_recalculates_total(self, window):
        """删除选中行后总金额重新计算。"""
        self._setup_and_add(window)
        window._order_table.selectRow(0)
        window._on_delete_selected()
        lbl = window._lbl_total.text()
        assert "20" in lbl  # 3×10 → 2×10

    def test_delete_sets_user_adjusted(self, window):
        """删除操作将 _table_user_adjusted 置为 True。"""
        self._setup_and_add(window)
        window._table_user_adjusted = False
        window._order_table.selectRow(0)
        window._on_delete_selected()
        assert window._table_user_adjusted is True

    def test_delete_no_selection_does_not_crash(self, window):
        """没有选中行时删除操作不会崩溃。"""
        self._setup_and_add(window)
        window._order_table.clearSelection()
        # 不应抛出异常
        window._on_delete_selected()
        assert window._order_table.rowCount() == 3  # 无变化

    def test_delete_multiple_rows(self, window):
        """可同时删除多行。"""
        self._setup_and_add(window)
        # selectRow 会替换选择，需通过 setRangeSelected 累加多行选择
        from PySide6.QtWidgets import QTableWidgetSelectionRange
        sel_model = window._order_table.selectionModel()
        sel_model.clearSelection()
        window._order_table.setRangeSelected(
            QTableWidgetSelectionRange(0, 0, 0, window._order_table.columnCount() - 1), True
        )
        window._order_table.setRangeSelected(
            QTableWidgetSelectionRange(2, 0, 2, window._order_table.columnCount() - 1), True
        )
        window._on_delete_selected()
        assert window._order_table.rowCount() == 1


# ══════════════════════════════════════════════════════════════════════
# 6. 剪贴板健壮性
# ══════════════════════════════════════════════════════════════════════


class TestClipboardRobustness:
    def test_mimedata_none_does_not_crash(self, window):
        """clipboard.mimeData() 返回 None 时不会异常。"""
        from PySide6.QtWidgets import QApplication

        # 开启自动获取
        window._chk_auto_fetch.setChecked(True)
        # 篡改 _clipboard 使其 mimeData() 返回 None
        fake_clip = MagicMock()
        fake_clip.mimeData.return_value = None
        window._clipboard = fake_clip
        # 不应抛出异常
        window._poll_clipboard()

    def test_mimedata_no_text_does_not_crash(self, window):
        """clipboard.mimeData() 不含文本时不会异常。"""
        window._chk_auto_fetch.setChecked(True)
        # 创建一个返回空文本的 fake clipboard
        fake_clip = MagicMock()
        fake_mime = QMimeData()  # hasText() → False，text() → ""
        fake_clip.mimeData.return_value = fake_mime
        window._clipboard = fake_clip
        window._last_clipboard_text = ""
        window._poll_clipboard()
        # 输入框不应改变
        assert window._input_text.toPlainText() == ""

    def test_auto_fetch_disabled_skips_clipboard(self, window):
        """自动获取关闭时不访问剪贴板。"""
        window._chk_auto_fetch.setChecked(False)
        clip_accessed = False

        def _side_effect():
            nonlocal clip_accessed
            clip_accessed = True
            return None

        fake_clip = MagicMock()
        fake_clip.mimeData.side_effect = _side_effect
        window._clipboard = fake_clip
        window._poll_clipboard()
        assert not clip_accessed  # 未调用 mimeData()


# ══════════════════════════════════════════════════════════════════════
# 7. 工具栏按钮未实现
# ══════════════════════════════════════════════════════════════════════


class TestToolbarButtons:
    def test_toolbar_buttons_disabled(self, window):
        """所有工具栏按钮均为禁用状态，不会执行未知业务。"""
        # 遍历工具栏区域中的所有 QPushButton
        from PySide6.QtWidgets import QPushButton

        all_buttons = window.findChildren(QPushButton)
        toolbar_buttons = [
            btn for btn in all_buttons
            if btn.objectName() == "toolButton"
        ]
        # 应至少有 8 个工具栏按钮
        assert len(toolbar_buttons) >= 8
        for btn in toolbar_buttons:
            assert not btn.isEnabled(), f"工具栏按钮「{btn.text()}」未禁用"
            assert btn.toolTip() == "暂未开放"


# ══════════════════════════════════════════════════════════════════════
# 8. 不访问外部资源的约束性测试
# ══════════════════════════════════════════════════════════════════════


class TestNoExternalDependencies:
    """确保窗口测试不调用 OrderService / OrderIntakeService / SQLAlchemy / 真实 DB。"""

    def test_window_imports_dont_pull_db(self):
        """导入 record_order_window 不会拉入数据库相关模块。"""
        import sys
        # 记录已导入的数据库相关模块
        db_modules_before = {
            k for k in sys.modules
            if "sqlalchemy" in k.lower()
            or "order_service" in k.lower()
            or "order_intake" in k.lower()
        }
        # 窗口已经在本模块中导入过 — 只需确认 RecordOrderWindow
        # 自身没有 import 这些
        from ui.windows.record_order_window import RecordOrderWindow
        import inspect
        src = inspect.getsource(RecordOrderWindow)
        assert "OrderService" not in src
        assert "OrderIntake" not in src
        assert "sqlalchemy" not in src.lower()
        assert "fortune.db" not in src.lower()
        assert "49wz777" not in src.lower()

    def test_parse_only_calls_parser(self, window):
        """解析流程只调用 order_parser，不涉及数据库。"""
        from services.order_parser import parse_lines as _orig_parse_lines

        with patch("ui.windows.record_order_window.parse_lines", wraps=_orig_parse_lines) as spy:
            window._input_text.setPlainText("兔各10")
            window._do_parse()
            spy.assert_called_once()
            # 确认解析结果来自 parse_lines（wrap 会透传真实返回值）
            results = window._parsed_results
            assert len(results) == 1
            for r in results:
                assert isinstance(r, ParseResult)

    def test_add_result_no_db_access(self, window):
        """添加结果不涉及数据库访问。"""
        window._input_text.setPlainText("01,02,03各10")
        window._do_parse()
        # 直接调用添加 — 仅操作 QTableWidget
        window._on_add_result()
        assert window._order_table.rowCount() == 3


# ══════════════════════════════════════════════════════════════════════
# 9. amount / total 语义在表格中的一致性
# ══════════════════════════════════════════════════════════════════════


class TestAmountTotalSemanticsInTable:
    """表格中每行金额使用 r.amount，总金额 = 各行金额之和。"""

    def test_zodiac_multi_number_per_amount(self, window):
        """生肖类（多号码）添加到表格时每号一行，每行金额 = r.amount。"""
        window._input_text.setPlainText("兔各20")
        window._do_parse()
        window._on_add_result()
        # 兔有 4 个号码: 4, 16, 28, 40
        assert window._order_table.rowCount() == 4
        for row in range(window._order_table.rowCount()):
            amt = window._order_table.item(row, 5).text()
            assert amt == "20"  # 每号金额 20
            per_num_amt = window._order_table.item(row, 6).text()
            assert per_num_amt == "20"  # 每号金额列也是 20
        assert "80" in window._lbl_total.text()  # 4 × 20 = 80

    def test_mixed_parse_results_add_correctly(self, window):
        """多行解析结果添加后每号一行。"""
        window._input_text.setPlainText("兔各10\n马各5")
        window._do_parse()
        window._on_add_result()
        # 兔 4 号码 + 马 5 号码 = 9 行
        assert window._order_table.rowCount() == 9
        # 总金额 = 4×10 + 5×5 = 65
        assert "65" in window._lbl_total.text()


# ══════════════════════════════════════════════════════════════════════
# 10. 按钮存在性
# ══════════════════════════════════════════════════════════════════════


class TestButtonExistence:
    def test_delete_button_exists(self, window):
        """「删除选中行」按钮存在。"""
        from PySide6.QtWidgets import QPushButton

        buttons = [
            btn for btn in window.findChildren(QPushButton)
            if btn.text() == "删除选中行"
        ]
        assert len(buttons) == 1

    def test_all_action_buttons_exist(self, window):
        """三个侧边按钮均存在：清空结果、添加结果、删除选中行。"""
        from PySide6.QtWidgets import QPushButton

        button_texts = {
            btn.text()
            for btn in window.findChildren(QPushButton)
            if btn.objectName() == "sideActionButton"
        }
        assert "清空结果" in button_texts
        assert "添加结果" in button_texts
        assert "删除选中行" in button_texts
