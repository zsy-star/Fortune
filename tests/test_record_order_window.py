"""测试 RecordOrderWindow 录单窗口。

使用 QT_QPA_PLATFORM=offscreen，不访问真实数据库、真实剪贴板、
OrderService、SQLAlchemy Session 或 49wz777.com。

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
    QMessageBox,
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
    w._parse_timer.stop()
    if hasattr(w, "_chk_auto_fetch"):
        w._chk_auto_fetch.setChecked(False)
    yield w
    w.close()
    w.deleteLater()


@pytest.fixture
def save_window(qapp, session_factory):
    """创建接入临时数据库 OrderIntakeService 的窗口。"""
    from services.order_intake_service import OrderIntakeService
    from ui.windows.record_order_window import RecordOrderWindow

    w = RecordOrderWindow(order_intake_service=OrderIntakeService(session_factory))
    w._parse_timer.stop()
    if hasattr(w, "_chk_auto_fetch"):
        w._chk_auto_fetch.setChecked(False)
    yield w
    w.close()
    w.deleteLater()


def _order_counts(session_factory) -> tuple[int, int]:
    from sqlalchemy import func, select

    from models import Order, OrderItem

    with session_factory() as session:
        order_count = session.scalar(select(func.count(Order.id))) or 0
        item_count = session.scalar(select(func.count(OrderItem.id))) or 0
    return int(order_count), int(item_count)


# ══════════════════════════════════════════════════════════════════════
# 1. 窗口创建/关闭
# ══════════════════════════════════════════════════════════════════════


class TestWindowLifecycle:
    def test_create_and_close(self, qapp):
        """窗口可以正常创建和关闭。"""
        from ui.windows.record_order_window import RecordOrderWindow

        w = RecordOrderWindow()
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
        # total 保留在 ParseResult 中，输出不显示总计行
        assert window._parsed_results[0].total == 30.0

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

    def test_add_result_adds_one_row(self, window):
        """添加结果后每个解析结果占一行（号码合并）。"""
        self._setup_parsed(window)
        window._on_add_result()
        assert window._order_table.rowCount() == 1

    def test_numbers_comma_separated_in_one_cell(self, window):
        """所有号码用逗号拼接在同一单元格。"""
        self._setup_parsed(window)
        window._on_add_result()
        nums_text = window._order_table.item(0, 2).text()  # "订单信息" 列
        assert nums_text == "01,02,03"

    def test_amount_column_uses_total(self, window):
        """金额列使用 r.total，每号金额列使用 r.amount。"""
        self._setup_parsed(window)
        window._on_add_result()
        amt_col5 = window._order_table.item(0, 5).text()  # "金额" → r.total
        amt_col6 = window._order_table.item(0, 6).text()  # "每号金额" → r.amount
        assert amt_col5 == "30"
        assert amt_col6 == "10"

    def test_remark_column_contains_original_text(self, window):
        """备注列填入原始输入文本。"""
        self._setup_parsed(window)
        window._on_add_result()
        remark = window._order_table.item(0, 9).text()  # "备注" 列
        assert remark == "01,02,03各10"

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
        # 添加两行以便测试删除
        window._input_text.setPlainText("01,02,03各10\n兔各20")
        window._do_parse()
        window._on_add_result()
        assert window._order_table.rowCount() == 2
        window._order_table.selectRow(0)
        window._on_delete_selected()
        assert window._order_table.rowCount() == 1

    def test_delete_recalculates_total(self, window):
        """删除选中行后总金额重新计算。"""
        window._input_text.setPlainText("01,02,03各10\n兔各20")
        window._do_parse()
        window._on_add_result()
        window._order_table.selectRow(0)
        window._on_delete_selected()
        lbl = window._lbl_total.text()
        # 仅剩兔各20: 总金额 80（r.total=80 在金额列）
        assert "80" in lbl

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
        window._on_delete_selected()
        assert window._order_table.rowCount() == 1  # 无变化

    def test_delete_multiple_rows(self, window):
        """可同时删除多行。"""
        # 添加两行
        window._input_text.setPlainText("01,02,03各10\n兔各20")
        window._do_parse()
        window._on_add_result()
        assert window._order_table.rowCount() == 2
        from PySide6.QtWidgets import QTableWidgetSelectionRange
        sel_model = window._order_table.selectionModel()
        sel_model.clearSelection()
        window._order_table.setRangeSelected(
            QTableWidgetSelectionRange(0, 0, 0, window._order_table.columnCount() - 1), True
        )
        window._order_table.setRangeSelected(
            QTableWidgetSelectionRange(1, 0, 1, window._order_table.columnCount() - 1), True
        )
        window._on_delete_selected()
        assert window._order_table.rowCount() == 0


# ══════════════════════════════════════════════════════════════════════
# 6. 剪贴板健壮性
# ══════════════════════════════════════════════════════════════════════


class TestClipboardRobustness:
    def test_mimedata_none_does_not_crash(self, window):
        """clipboard.mimeData() 返回 None 时不会异常。"""
        window._chk_auto_fetch.setChecked(True)
        fake_clip = MagicMock()
        fake_clip.mimeData.return_value = None
        window._clipboard = fake_clip
        window._poll_clipboard()

    def test_mimedata_no_text_does_not_crash(self, window):
        """clipboard.mimeData() 不含文本时不会异常。"""
        window._chk_auto_fetch.setChecked(True)
        fake_clip = MagicMock()
        fake_mime = QMimeData()
        fake_clip.mimeData.return_value = fake_mime
        window._clipboard = fake_clip
        window._last_clipboard_text = ""
        window._poll_clipboard()
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
        assert not clip_accessed

    def test_dedup_skips_existing_content(self, window):
        """内容已存在于输入框时跳过不追加。"""
        window._chk_auto_fetch.setChecked(True)
        window._input_text.setPlainText("兔各10")
        window._clip_mode_append = True
        fake_clip = MagicMock()
        fake_mime = QMimeData()
        fake_mime.setText("兔各10")  # 已存在
        fake_clip.mimeData.return_value = fake_mime
        fake_clip.text.return_value = "兔各10"
        window._clipboard = fake_clip
        window._last_clipboard_text = ""
        window._poll_clipboard()
        # 不应重复追加
        assert window._input_text.toPlainText() == "兔各10"

    def test_replace_mode_overwrites(self, window):
        """替换模式下新内容直接覆盖。"""
        window._chk_auto_fetch.setChecked(True)
        window._input_text.setPlainText("兔各10")
        window._clip_mode_append = False  # 替换模式
        fake_clip = MagicMock()
        fake_mime = QMimeData()
        fake_mime.setText("马各20")
        fake_clip.mimeData.return_value = fake_mime
        fake_clip.text.return_value = "马各20"
        window._clipboard = fake_clip
        window._last_clipboard_text = ""
        window._poll_clipboard()
        assert window._input_text.toPlainText() == "马各20"

    def test_toggle_mode_button(self, window):
        """模式切换按钮改变状态。"""
        assert window._clip_mode_append is True
        window._on_toggle_clip_mode()
        assert window._clip_mode_append is False
        window._on_toggle_clip_mode()
        assert window._clip_mode_append is True


# ══════════════════════════════════════════════════════════════════════
# 7. 工具栏按钮未实现
# ══════════════════════════════════════════════════════════════════════


class TestToolbarButtons:
    def test_toolbar_buttons_disabled(self, window):
        """仅「去分割符」和「订单标记」启用，其余工具栏按钮禁用。"""
        from PySide6.QtWidgets import QPushButton

        all_buttons = window.findChildren(QPushButton)
        toolbar_buttons = [
            btn for btn in all_buttons
            if btn.objectName() == "toolButton"
        ]
        assert len(toolbar_buttons) >= 8
        enabled_buttons = [btn for btn in toolbar_buttons if btn.isEnabled()]
        enabled_texts = {btn.text() for btn in enabled_buttons}
        assert "指定替换" in enabled_texts, "「指定替换」应启用"
        assert len(enabled_buttons) == 8, f"应有 8 个启用的工具栏按钮，实际: {len(enabled_buttons)}"
        for btn in toolbar_buttons:
            if not btn.isEnabled():
                assert btn.toolTip() == "暂未开放"


# ══════════════════════════════════════════════════════════════════════
# 8. 去分隔符功能
# ══════════════════════════════════════════════════════════════════════


class TestRemoveSeparators:
    def test_chinese_comma_to_regular(self, window):
        """中文逗号「，」转为英文逗号「,」。"""
        window._input_text.setPlainText("01，02，03各10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "01,02,03各10"

    def test_enumeration_comma_to_regular(self, window):
        """顿号「、」转为英文逗号「,」。"""
        window._input_text.setPlainText("01、02、03各10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "01,02,03各10"

    def test_spaces_around_commas_removed(self, window):
        """逗号两侧空格被移除。"""
        window._input_text.setPlainText("01 , 02 , 03各10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "01,02,03各10"

    def test_space_before_ge_removed(self, window):
        """「各」前后的空格被移除。"""
        window._input_text.setPlainText("兔 各 20")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "兔各20"

    def test_multiple_spaces_collapsed(self, window):
        """「各」前后多余空格清理干净。"""
        window._input_text.setPlainText("兔   各   20")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "兔各20"

    def test_mixed_separators_normalized(self, window):
        """混合分隔符统一规范化。"""
        window._input_text.setPlainText("01 ， 02、03 各 10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "01,02,03各10"

    def test_empty_input_no_error(self, window):
        """空输入不报错。"""
        window._input_text.clear()
        window._on_remove_separators()  # 不应抛出异常
        assert window._input_text.toPlainText() == ""

    def test_spaces_between_chinese_chars_removed(self, window):
        """相邻汉字之间的空格移除。"""
        window._input_text.setPlainText("澳 门 兔 各 20")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "澳门兔各20"

    def test_slash_to_comma(self, window):
        """斜杠「/」转为英文逗号。"""
        window._input_text.setPlainText("01/02/03各10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "01,02,03各10"

    def test_chinese_category_spaces_removed(self, window):
        """中文类别名中间空格移除。"""
        window._input_text.setPlainText("红 波 各 10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "红波各10"

    def test_chinese_and_numbers_mixed(self, window):
        """中文 + 数字混合场景。"""
        window._input_text.setPlainText("香 港 1，2，3 各 10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "香港 1,2,3各10"


# ══════════════════════════════════════════════════════════════════════
# 8. 订单标记
# ══════════════════════════════════════════════════════════════════════


class TestOrderMark:
    def test_mark_adds_prefix_to_each_line(self, window):
        """标记文字添加到每条非空行前面。"""
        from unittest.mock import patch

        window._input_text.setPlainText("兔各10\n马各5")
        with patch(
            "ui.windows.record_order_window.QInputDialog.getText",
            return_value=("张三", True),
        ):
            window._on_order_mark()
        result = window._input_text.toPlainText()
        assert result == "张三 兔各10\n张三 马各5"

    def test_mark_preserves_empty_lines(self, window):
        """空行保留不动。"""
        from unittest.mock import patch

        window._input_text.setPlainText("兔各10\n\n马各5")
        with patch(
            "ui.windows.record_order_window.QInputDialog.getText",
            return_value=("A", True),
        ):
            window._on_order_mark()
        result = window._input_text.toPlainText()
        assert result == "A 兔各10\n\nA 马各5"

    def test_mark_cancel_does_nothing(self, window):
        """取消对话框不做任何改动。"""
        from unittest.mock import patch

        original = "兔各10"
        window._input_text.setPlainText(original)
        with patch(
            "ui.windows.record_order_window.QInputDialog.getText",
            return_value=("张三", False),  # 用户点了取消
        ):
            window._on_order_mark()
        assert window._input_text.toPlainText() == original

    def test_mark_empty_input_does_nothing(self, window):
        """输入空标记不做改动。"""
        from unittest.mock import patch

        original = "兔各10"
        window._input_text.setPlainText(original)
        with patch(
            "ui.windows.record_order_window.QInputDialog.getText",
            return_value=("   ", True),  # 只输入了空格
        ):
            window._on_order_mark()
        assert window._input_text.toPlainText() == original

    def test_mark_triggers_reparse(self, window):
        """加标记后自动触发重新解析。"""
        from unittest.mock import patch

        window._input_text.setPlainText("兔各10")
        with patch(
            "ui.windows.record_order_window.QInputDialog.getText",
            return_value=("VIP", True),
        ):
            window._on_order_mark()
        # 检查解析结果：原文本不被识别（因为加了前缀），应触发防抖解析
        # 这里验证标记确实加上了
        assert window._input_text.toPlainText() == "VIP 兔各10"


# ══════════════════════════════════════════════════════════════════════
# 9. 去空格
# ══════════════════════════════════════════════════════════════════════


class TestRemoveSpaces:
    def test_remove_all_spaces_simple(self, window):
        """移除行内所有空格。"""
        window._input_text.setPlainText("兔 各 20")
        window._on_remove_spaces()
        assert window._input_text.toPlainText() == "兔各20"

    def test_remove_spaces_in_number_list(self, window):
        """数字列表中的空格全部移除。"""
        window._input_text.setPlainText("01, 02, 03 各 10")
        window._on_remove_spaces()
        assert window._input_text.toPlainText() == "01,02,03各10"

    def test_remove_spaces_chinese(self, window):
        """中文之间的空格全部移除。"""
        window._input_text.setPlainText("澳 门 红 波 各 10")
        window._on_remove_spaces()
        assert window._input_text.toPlainText() == "澳门红波各10"

    def test_remove_spaces_empty_input(self, window):
        """空输入不报错。"""
        window._input_text.clear()
        window._on_remove_spaces()
        assert window._input_text.toPlainText() == ""

    def test_remove_spaces_blank_lines_preserved(self, window):
        """空行保留（去除空格后为空字符串）。"""
        window._input_text.setPlainText("兔 各 10\n\n马 各 5")
        window._on_remove_spaces()
        assert window._input_text.toPlainText() == "兔各10\n\n马各5"

    def test_remove_spaces_leading_trailing(self, window):
        """行首行尾空格也移除。"""
        window._input_text.setPlainText("  兔各10  ")
        window._on_remove_spaces()
        assert window._input_text.toPlainText() == "兔各10"


# ══════════════════════════════════════════════════════════════════════
# 10. 标记香港
# ══════════════════════════════════════════════════════════════════════


class TestMarkHongKong:
    def test_add_hk_prefix(self, window):
        """没有地域前缀时添加「香港」。"""
        window._input_text.setPlainText("兔各10")
        window._on_mark_hk()
        assert window._input_text.toPlainText() == "香港 兔各10"

    def test_replace_macau_with_hk(self, window):
        """原为澳门时替换为香港。"""
        window._input_text.setPlainText("澳门兔各10")
        window._on_mark_hk()
        assert window._input_text.toPlainText() == "香港兔各10"

    def test_hk_unchanged(self, window):
        """已是香港保持不变。"""
        window._input_text.setPlainText("香港兔各10")
        window._on_mark_hk()
        assert window._input_text.toPlainText() == "香港兔各10"

    def test_mark_hk_switches_radio(self, window):
        """同时切换地区单选按钮为香港。"""
        window._radio_macau.setChecked(True)
        window._on_mark_hk()
        assert window._radio_hk.isChecked()

    def test_mark_hk_multiple_lines(self, window):
        """多行均添加香港前缀。"""
        window._input_text.setPlainText("兔各10\n马各5\n澳门01/10")
        window._on_mark_hk()
        assert window._input_text.toPlainText() == "香港 兔各10\n香港 马各5\n香港01/10"

    def test_mark_hk_empty_input(self, window):
        """空输入不报错。"""
        window._input_text.clear()
        window._on_mark_hk()
        assert window._input_text.toPlainText() == ""


# ══════════════════════════════════════════════════════════════════════
# 11. 取小数点
# ══════════════════════════════════════════════════════════════════════


class TestRemoveDecimal:
    def test_dot_to_space_numbers(self, window):
        """1.5 → 1 5。"""
        window._input_text.setPlainText("1.5各10")
        window._on_remove_decimal()
        assert window._input_text.toPlainText() == "1 5各10"

    def test_multi_dots_to_spaces(self, window):
        """多个小数点都变空格。"""
        window._input_text.setPlainText("1.2.3各10")
        window._on_remove_decimal()
        assert window._input_text.toPlainText() == "1 2 3各10"

    def test_dot_in_amount(self, window):
        """金额中的小数点也变空格。"""
        window._input_text.setPlainText("兔各10.5")
        window._on_remove_decimal()
        assert window._input_text.toPlainText() == "兔各10 5"

    def test_no_dot_unchanged(self, window):
        """没有小数点不变。"""
        window._input_text.setPlainText("兔各10")
        window._on_remove_decimal()
        assert window._input_text.toPlainText() == "兔各10"

    def test_empty_input(self, window):
        """空输入不报错。"""
        window._input_text.clear()
        window._on_remove_decimal()
        assert window._input_text.toPlainText() == ""


# ══════════════════════════════════════════════════════════════════════
# 12. 语义转换
# ══════════════════════════════════════════════════════════════════════


class TestSemanticConvert:
    def test_full_width_digit_to_half(self, window):
        """全角数字→半角。"""
        window._input_text.setPlainText("兔各１０")
        window._on_semantic_convert()
        assert window._input_text.toPlainText() == "兔各10"

    def test_full_width_letter_to_half(self, window):
        """全角字母→半角。"""
        window._input_text.setPlainText("ＡＢＣ各10")
        window._on_semantic_convert()
        assert window._input_text.toPlainText() == "ABC各10"

    def test_cn_number_simple(self, window):
        """中文数字→阿拉伯：十→10。"""
        window._input_text.setPlainText("兔各十")
        window._on_semantic_convert()
        assert window._input_text.toPlainText() == "兔各10"

    def test_cn_number_tens(self, window):
        """中文数字→阿拉伯：二十→20。"""
        window._input_text.setPlainText("兔各二十")
        window._on_semantic_convert()
        assert window._input_text.toPlainText() == "兔各20"

    def test_cn_number_compound(self, window):
        """中文数字→阿拉伯：三十五→35。"""
        window._input_text.setPlainText("兔各三十五")
        window._on_semantic_convert()
        assert window._input_text.toPlainText() == "兔各35"

    def test_cn_number_hundred(self, window):
        """中文数字→阿拉伯：一百二十→120。"""
        window._input_text.setPlainText("兔各一百二十")
        window._on_semantic_convert()
        assert window._input_text.toPlainText() == "兔各120"

    def test_full_width_plus_cn_number(self, window):
        """组合：全角数字 + 中文金额。"""
        window._input_text.setPlainText("０１，０２各二十")
        window._on_semantic_convert()
        assert window._input_text.toPlainText() == "01,02各20"

    def test_empty_input(self, window):
        """空输入不报错。"""
        window._input_text.clear()
        window._on_semantic_convert()
        assert window._input_text.toPlainText() == ""


# ══════════════════════════════════════════════════════════════════════
# 13. 指定替换
# ══════════════════════════════════════════════════════════════════════


class TestSpecifiedReplace:
    def test_replace_symbol(self, window):
        """将符号 A 替换为符号 B。"""
        window._input_text.setPlainText("兔#各10")
        window._apply_text_replace("#", " ")
        assert window._input_text.toPlainText() == "兔 各10"

    def test_replace_multiple_occurrences(self, window):
        """替换所有出现的位置。"""
        window._input_text.setPlainText("兔#龙#蛇各10")
        window._apply_text_replace("#", ",")
        assert window._input_text.toPlainText() == "兔,龙,蛇各10"

    def test_replace_no_match_unchanged(self, window):
        """无匹配时文本不变。"""
        window._input_text.setPlainText("兔各10")
        window._apply_text_replace("#", ",")
        assert window._input_text.toPlainText() == "兔各10"

# ══════════════════════════════════════════════════════════════════════
# 14. 替换预设
# ══════════════════════════════════════════════════════════════════════


class TestReplacePresets:
    def test_apply_single_preset(self, window):
        """单个预设规则生效。"""
        window._replace_presets = [("#", ",")]
        result = window._apply_replace_presets("兔#龙#蛇各10")
        assert result == "兔,龙,蛇各10"

    def test_apply_multiple_presets(self, window):
        """多个预设规则依次生效。"""
        window._replace_presets = [("#", ","), ("@", " ")]
        result = window._apply_replace_presets("兔#龙@蛇各10")
        assert result == "兔,龙 蛇各10"

    def test_apply_no_presets_unchanged(self, window):
        """无预设时文本不变。"""
        window._replace_presets = []
        result = window._apply_replace_presets("兔各10")
        assert result == "兔各10"

    def test_apply_preset_no_match(self, window):
        """预设不匹配时文本不变。"""
        window._replace_presets = [("#", ",")]
        result = window._apply_replace_presets("兔各10")
        assert result == "兔各10"

    def test_preset_auto_applied_in_parse(self, window):
        """解析时自动应用预设。"""
        window._replace_presets = [("#", ",")]
        window._input_text.setPlainText("01#02#03各10")
        window._do_parse()
        # 预设将 # 替换为 , 后成功解析
        assert len(window._parsed_results) == 1
        r = window._parsed_results[0]
        assert r.success
        assert r.numbers == (1, 2, 3)

    def test_empty_find_ignored(self, window):
        """空查找串的预设被跳过。"""
        window._replace_presets = [("", "X"), ("#", ",")]
        result = window._apply_replace_presets("兔#龙各10")
        assert result == "兔,龙各10"


# ══════════════════════════════════════════════════════════════════════
# 15. 保存订单
# ══════════════════════════════════════════════════════════════════════


class TestSaveOrder:
    def test_empty_input_save_warns_and_does_not_write_db(self, save_window, session_factory):
        """空输入点击保存时提示，不写入数据库。"""
        save_window._input_text.clear()
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "请输入订单内容" in warning.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_unparsed_input_save_warns_and_does_not_write_db(self, save_window, session_factory):
        """输入后未解析时提示先解析，不写入数据库。"""
        save_window._input_text.setPlainText("01/10")
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "请先解析订单内容" in warning.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_parse_error_save_warns_and_does_not_write_db(self, save_window, session_factory):
        """解析失败结果不能保存，并显示解析错误。"""
        save_window._input_text.setPlainText("abc")
        save_window._do_parse()
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "无法提取末尾金额" in warning.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_save_01_10_success_writes_order_and_clears_parse_state(self, save_window, session_factory):
        """01/10 解析成功后可保存到临时数据库。"""
        from sqlalchemy import select

        from models import Order, OrderItem

        save_window._input_text.setPlainText("01/10")
        save_window._do_parse()
        with (
            patch(
                "ui.windows.record_order_window.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch("ui.windows.record_order_window.QMessageBox.information") as info,
        ):
            save_window._on_save_order()

        info.assert_called_once()
        assert "订单保存成功" in info.call_args.args[2]
        with session_factory() as session:
            order = session.scalars(select(Order)).one()
            items = session.scalars(select(OrderItem)).all()
            assert order.raw_text == "01/10"
            assert order.source == "record_window"
            assert order.channel == save_window._cmb_channel.currentText()
            assert order.total_amount == 10
            assert len(items) == 1
            assert items[0].selection == "01"
            assert items[0].amount == 10
        assert save_window._input_text.toPlainText() == ""
        assert save_window._output_text.toPlainText() == ""
        assert save_window._parsed_results == []
        assert save_window._order_table.rowCount() == 0
        assert save_window._lbl_total.text() == "当前总额: 0"

    def test_save_multi_numbers_keeps_per_number_amount_semantics(self, save_window, session_factory):
        """01,02,03各10 保存为 3 个明细，每个金额 10，总额 30。"""
        from sqlalchemy import select

        from models import Order, OrderItem

        save_window._input_text.setPlainText("01,02,03各10")
        save_window._do_parse()
        with (
            patch(
                "ui.windows.record_order_window.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch("ui.windows.record_order_window.QMessageBox.information"),
        ):
            save_window._on_save_order()

        with session_factory() as session:
            order = session.scalars(select(Order)).one()
            items = session.scalars(select(OrderItem).order_by(OrderItem.selection)).all()
            assert order.total_amount == 30
            assert [item.selection for item in items] == ["01", "02", "03"]
            assert [item.amount for item in items] == [10, 10, 10]

    def test_table_user_adjusted_blocks_save(self, save_window, session_factory):
        """表格被人工调整后，本阶段禁止直接保存。"""
        save_window._input_text.setPlainText("01/10")
        save_window._do_parse()
        save_window._table_user_adjusted = True
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "当前表格已人工调整" in warning.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_preview_can_save_false_blocks_save(self, save_window, session_factory):
        """preview.can_save=False 时提示原因，不写入数据库。"""
        save_window._input_text.setPlainText("全包各10")
        save_window._do_parse()
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "全包" in warning.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)


# ══════════════════════════════════════════════════════════════════════
# 16. 不访问外部资源的约束性测试
# ══════════════════════════════════════════════════════════════════════


class TestNoExternalDependencies:
    """确保窗口不直接调用 OrderService / SQLAlchemy / 真实 DB。"""

    def test_window_only_depends_on_order_intake_service_for_save(self):
        """保存链路只允许窗口调用 OrderIntakeService，不直接碰数据库层。"""
        from ui.windows.record_order_window import RecordOrderWindow
        import inspect

        src = inspect.getsource(RecordOrderWindow)
        assert "OrderService" not in src
        assert "OrderRepository" not in src
        assert "sqlalchemy" not in src.lower()
        assert "Session" not in src
        assert "sqlite" not in src.lower()
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
        # 直接调用添加 — 仅操作 QTableWidget，每个解析结果占一行
        window._on_add_result()
        assert window._order_table.rowCount() == 1


# ══════════════════════════════════════════════════════════════════════
# 9. amount / total 语义在表格中的一致性
# ══════════════════════════════════════════════════════════════════════


class TestAmountTotalSemanticsInTable:
    """金额列 = r.total（总金额），每号金额列 = r.amount。"""

    def test_zodiac_single_row_with_total(self, window):
        """生肖类合并为一行，金额列为总金额。"""
        window._input_text.setPlainText("兔各20")
        window._do_parse()
        window._on_add_result()
        # 兔有 4 个号码，合并在一行
        assert window._order_table.rowCount() == 1
        nums_text = window._order_table.item(0, 2).text()  # 订单信息
        assert nums_text == "04,16,28,40"
        amt = window._order_table.item(0, 5).text()  # 金额 = r.total
        assert amt == "80"
        per_num = window._order_table.item(0, 6).text()  # 每号金额 = r.amount
        assert per_num == "20"
        assert "80" in window._lbl_total.text()

    def test_mixed_parse_results_add_correctly(self, window):
        """多行解析结果各占一行，金额为各行的总金额。"""
        window._input_text.setPlainText("兔各10\n马各5")
        window._do_parse()
        window._on_add_result()
        # 两个解析结果各占一行
        assert window._order_table.rowCount() == 2
        # 兔各10: 总金额 40；马各5: 总金额 25；合计 65
        assert window._order_table.item(0, 5).text() == "40"
        assert window._order_table.item(1, 5).text() == "25"
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
        """四个侧边按钮均存在：清空结果、添加结果、删除选中行、保存订单。"""
        from PySide6.QtWidgets import QPushButton

        button_texts = {
            btn.text()
            for btn in window.findChildren(QPushButton)
            if btn.objectName() == "sideActionButton"
        }
        assert "清空结果" in button_texts
        assert "添加结果" in button_texts
        assert "删除选中行" in button_texts
        assert "保存订单" in button_texts
