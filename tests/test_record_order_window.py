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
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QTableWidgetItem,
    QCheckBox,
    QPushButton,
    QSpinBox,
)

from services.order_parser import ParseResult, parse_order
from ui.app_events import app_events
from ui.windows.record_order_window import _TableColumn


class FakeSettingsService:
    def __init__(self, names: list[str] | None = None, plan_name: str | None = None):
        self._names = names or []
        self._plan_name = plan_name

    def list_declarers(self):
        return [SimpleNamespace(name=name, plan_name=self._plan_name) for name in self._names]


class FailingSettingsService:
    def list_declarers(self):
        raise RuntimeError("settings unavailable")

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

    w = RecordOrderWindow(settings_service=FakeSettingsService())
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

    from services.settings_service import SettingsService

    w = RecordOrderWindow(
        order_intake_service=OrderIntakeService(session_factory),
        settings_service=SettingsService(session_factory),
    )
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


def _log_count(session_factory) -> int:
    from sqlalchemy import func, select

    from models import OperationLog

    with session_factory() as session:
        return int(session.scalar(select(func.count(OperationLog.id))) or 0)


# ══════════════════════════════════════════════════════════════════════
# 1. 窗口创建/关闭
# ══════════════════════════════════════════════════════════════════════


class TestWindowLifecycle:
    def test_create_and_close(self, qapp):
        """窗口可以正常创建和关闭。"""
        from ui.windows.record_order_window import RecordOrderWindow

        w = RecordOrderWindow(settings_service=FakeSettingsService())
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
        assert "澳门: 特码: 01-02-03 各数 10" in output
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

    def test_ranked_lianxiao_enters_table_as_one_group(self, window):
        window._input_text.setPlainText("四连肖猪牛马虎 70")
        window._do_parse()
        window._on_add_result()

        assert len(window._parsed_results) == 1
        assert window._parsed_results[0].total == 70
        assert window._order_table.rowCount() == 1
        assert window._order_table.item(0, 1).text() == "连肖"
        assert window._order_table.item(0, 2).text() == "牛,虎,马,猪"
        assert window._order_table.item(0, _TableColumn.AMOUNT).text() == "70"
        assert window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text() == "70"

    def test_each_package_multi_zodiac_enters_four_supported_rows(self, window):
        window._input_text.setPlainText("牛兔马猪各包10")
        window._do_parse()
        window._on_add_result()

        assert window._order_table.rowCount() == 4
        assert [window._order_table.item(row, 1).text() for row in range(4)] == ["平特一肖"] * 4
        assert [window._order_table.item(row, 2).text() for row in range(4)] == ["牛", "兔", "马", "猪"]
        assert [window._order_table.item(row, _TableColumn.AMOUNT).text() for row in range(4)] == ["10"] * 4
        assert [window._order_table.item(row, _TableColumn.TOTAL_AMOUNT).text() for row in range(4)] == ["10"] * 4
        assert [window._order_table.item(row, _TableColumn.SETTLEMENT_SUPPORT).text() for row in range(4)] == ["支持"] * 4

    def test_ten_non_hit_enters_table_as_one_supported_group(self, window):
        window._input_text.setPlainText("6/18/31/43/22/10/03/15/01/13十不中各4000")
        window._do_parse()
        window._on_add_result()

        assert window._order_table.rowCount() == 1
        assert window._order_table.item(0, 1).text() == "N不中"
        assert window._order_table.item(0, 2).text() == "01,03,06,10,13,15,18,22,31,43"
        assert window._order_table.item(0, _TableColumn.AMOUNT).text() == "4000"
        assert window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text() == "4000"
        assert window._order_table.item(0, _TableColumn.SETTLEMENT_SUPPORT).text() == "支持"


class TestAdvancedOptionsFirstStage:
    def _checkboxes(self, window):
        return {checkbox.text(): checkbox for checkbox in window.findChildren(QCheckBox)}

    def test_advanced_options_are_enabled_and_default_unchecked(self, window):
        checkboxes = self._checkboxes(window)
        year_spin = window.findChild(QSpinBox, "zodiacYearSpin")

        assert checkboxes["识别地区"].isEnabled()
        assert "自动识别澳门/香港" in checkboxes["识别地区"].toolTip()
        assert checkboxes["智能纠错"].isEnabled()
        assert "低风险规范化" in checkboxes["智能纠错"].toolTip()
        assert year_spin is not None
        assert year_spin.value() == 2026
        assert "抄写法" not in checkboxes
        for label in ("特肖模式", "岁写法", "各->各肖"):
            assert checkboxes[label].isEnabled()
            assert not checkboxes[label].isChecked()
            assert checkboxes[label].toolTip()

    def test_zodiac_year_switch_changes_preview_numbers(self, window):
        year_spin = window.findChild(QSpinBox, "zodiacYearSpin")
        assert year_spin is not None

        year_spin.setValue(2026)
        window._input_text.setPlainText("兔各10")
        window._do_parse()
        assert window._parsed_results[0].numbers == (4, 16, 28, 40)

        year_spin.setValue(2025)
        window._do_parse()
        assert window._parsed_results[0].numbers == (3, 15, 27, 39)
        assert "生肖年份2025" in window._advanced_status.text()

    def test_advanced_options_parse_and_status_text(self, window):
        checkboxes = self._checkboxes(window)
        checkboxes["特肖模式"].setChecked(True)
        checkboxes["岁写法"].setChecked(True)
        checkboxes["各->各肖"].setChecked(True)

        window._input_text.setPlainText("马各10")
        window._do_parse()

        assert window._parsed_results[0].category == "平特一肖"
        assert window._parsed_results[0].total == 10
        status = window._advanced_status.text()
        assert "岁写法" in status
        assert "各->各肖" in status
        assert "特肖模式" in status

    def test_age_writing_preview_result_can_enter_table(self, window):
        checkboxes = self._checkboxes(window)
        checkboxes["岁写法"].setChecked(True)
        window._input_text.setPlainText("25岁、08岁各10")
        window._do_parse()
        window._on_add_result()

        assert window._order_table.rowCount() == 1
        assert window._order_table.item(0, 1).text() == "特码"
        assert window._order_table.item(0, 2).text() == "08,25"
        assert window._order_table.item(0, _TableColumn.AMOUNT).text() == "10"
        assert window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text() == "20"

    def test_detect_region_hong_kong_sets_radio_and_results(self, window):
        checkboxes = self._checkboxes(window)
        checkboxes["识别地区"].setChecked(True)
        window._input_text.setPlainText("香港盘兔各10")
        window._do_parse()

        assert window._radio_hk.isChecked()
        assert window._parsed_results[0].region == "香港"
        assert "已识别地区：香港" in window._advanced_status.text()

    def test_detect_region_macau_sets_radio_and_results(self, window):
        checkboxes = self._checkboxes(window)
        checkboxes["识别地区"].setChecked(True)
        window._radio_hk.setChecked(True)
        window._input_text.setPlainText("澳门盘01/10")
        window._do_parse()

        assert window._radio_macau.isChecked()
        assert window._parsed_results[0].region == "澳门"
        assert "已识别地区：澳门" in window._advanced_status.text()

    def test_detect_region_conflict_blocks_parse_and_save(self, save_window):
        checkboxes = self._checkboxes(save_window)
        checkboxes["识别地区"].setChecked(True)
        save_window._input_text.setPlainText("澳门兔各10\n香港马各5")
        save_window._do_parse()

        assert save_window._parsed_results == []
        assert "地区冲突" in save_window._advanced_status.text()
        assert "地区冲突" in save_window._output_text.toPlainText()
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "地区冲突" in warning.call_args.args[2]

    def test_smart_correction_normalizes_fullwidth_punctuation_and_parses(self, window):
        checkboxes = self._checkboxes(window)
        checkboxes["智能纠错"].setChecked(True)
        window._input_text.setPlainText("０１，０２、０３　各　￥１０元")
        window._do_parse()

        assert len(window._parsed_results) == 1
        result = window._parsed_results[0]
        assert result.success
        assert result.numbers == (1, 2, 3)
        assert result.amount == 10
        assert "已应用智能纠错" in window._advanced_status.text()

    def test_smart_correction_does_not_rewrite_uncertain_play_name(self, window):
        checkboxes = self._checkboxes(window)
        checkboxes["智能纠错"].setChecked(True)
        window._input_text.setPlainText("未知玩法　各　１０")
        window._do_parse()

        assert window._parsed_results == []
        assert window._last_parse_raw == "未知玩法 各 10"
        assert "无法识别的类别" in window._output_text.toPlainText()


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

    def test_amount_and_order_total_columns_use_structured_values(self, window):
        """金额列使用 r.amount，订单总额列使用 r.total。"""
        self._setup_parsed(window)
        window._on_add_result()
        amount = window._order_table.item(0, _TableColumn.AMOUNT).text()
        total_amount = window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text()
        assert amount == "10"
        assert total_amount == "30"

    def test_amount_280_and_total_4480_are_not_swapped(self, window):
        window._parsed_results = [
            ParseResult(
                success=True,
                category="特码",
                numbers=tuple(range(1, 17)),
                amount=280,
                total=4480,
                region="澳门",
                original_text="16个号码各280",
            )
        ]

        window._on_add_result()

        assert window._order_table.item(0, _TableColumn.AMOUNT).text() == "280"
        assert window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text() == "4480"

    def test_fushi_three_in_two_displays_amount_and_total(self, window):
        self._setup_parsed(window, "10 11 24 38复式三中二一组20")
        window._on_add_result()

        assert window._order_table.item(0, _TableColumn.AMOUNT).text() == "20"
        assert window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text() == "80"

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

    def test_table_headers_follow_business_order(self, window):
        headers = [
            window._order_table.horizontalHeaderItem(column).text()
            for column in range(window._order_table.columnCount())
        ]

        assert window._order_table.columnCount() == 11
        assert headers == [
            "区域",
            "投注类型",
            "订单信息",
            "复选类型",
            "计算方式",
            "金额",
            "订单总额",
            "是否自定义",
            "申报人",
            "备注",
            "结算支持",
        ]


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
        # 仅剩兔各20: 订单总额 80（r.total=80 在订单总额列）
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
        """录单工具栏安全文本处理按钮均启用。"""
        from PySide6.QtWidgets import QPushButton

        all_buttons = window.findChildren(QPushButton)
        toolbar_buttons = [
            btn for btn in all_buttons
            if btn.objectName() == "toolButton"
        ]
        assert len(toolbar_buttons) >= 12
        enabled_buttons = [btn for btn in toolbar_buttons if btn.isEnabled()]
        enabled_texts = {btn.text() for btn in enabled_buttons}
        expected = {
            "去除空行",
            "去分割符",
            "订单标记",
            "去空格",
            "号码补零",
            "重复提示",
            "快速预览",
            "复制预览",
            "标记香港",
            "去小数点",
            "语义转换",
            "指定替换",
            "替换预设",
        }
        assert expected.issubset(enabled_texts)
        assert len(enabled_buttons) == len(toolbar_buttons)
        for btn in toolbar_buttons:
            assert btn.toolTip()


class TestRemoveBlankLines:
    def test_remove_blank_lines(self, window):
        window._input_text.setPlainText("兔各10\n\n  \n马各5\n")
        window._on_remove_blank_lines()
        assert window._input_text.toPlainText() == "兔各10\n马各5"


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

    def test_space_separated_numbers_normalized(self, window):
        """空格分隔的号码列表整理为逗号分隔。"""
        window._input_text.setPlainText("平码 01 02 03 各 10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "平码 01,02,03各10"

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

    def test_slash_group_separator_is_preserved(self, window):
        """斜杠「/」作为拖式/分组组合分隔符时不被破坏。"""
        window._input_text.setPlainText("01/02/03各10")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "01/02/03各10"

    def test_drag_slash_format_is_preserved(self, window):
        window._input_text.setPlainText("二中二 01，02 / 03，04 各 5")
        window._on_remove_separators()
        assert window._input_text.toPlainText() == "二中二 01,02 / 03,04各5"

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


class TestPadNumbers:
    def test_pad_single_digit_numbers(self, window):
        window._input_text.setPlainText("平码 1,2,9各10")
        window._on_pad_numbers()
        assert window._input_text.toPlainText() == "平码 01,02,09各10"

    def test_pad_numbers_does_not_touch_amount(self, window):
        window._input_text.setPlainText("兔各5")
        window._on_pad_numbers()
        assert window._input_text.toPlainText() == "兔各5"

    def test_pad_numbers_does_not_touch_keywords(self, window):
        window._input_text.setPlainText("复2 1,2各10\n三中二 1,2,3各10\n二中二 1,2各10\n1头各10\n尾1各10")
        window._on_pad_numbers()
        assert window._input_text.toPlainText() == (
            "复2 01,02各10\n"
            "三中二 01,02,03各10\n"
            "二中二 01,02各10\n"
            "1头各10\n"
            "尾1各10"
        )

    def test_pad_numbers_does_not_touch_age_writing(self, window):
        window._input_text.setPlainText("1岁各10")
        window._on_pad_numbers()
        assert window._input_text.toPlainText() == "1岁各10"

    def test_pad_numbers_keeps_bracket_group_shape(self, window):
        window._input_text.setPlainText("二中二 (1-2)各10")
        window._on_pad_numbers()
        assert window._input_text.toPlainText() == "二中二 (01-02)各10"

    def test_pad_numbers_keeps_drag_slash_shape(self, window):
        window._input_text.setPlainText("二中二 1,2/3,4各5")
        window._on_pad_numbers()
        assert window._input_text.toPlainText() == "二中二 01,02/03,04各5"

    def test_pad_numbers_does_not_touch_pingwei_tails(self, window):
        window._input_text.setPlainText("平尾 1,3,4各100")
        window._on_pad_numbers()
        assert window._input_text.toPlainText() == "平尾 1,3,4各100"


class TestSafePreviewTools:
    def test_duplicate_hint_does_not_modify_input(self, window):
        original = "01,02,01各10"
        window._input_text.setPlainText(original)
        with patch("ui.windows.record_order_window.QMessageBox.information") as info:
            window._on_duplicate_number_hint()
        assert window._input_text.toPlainText() == original
        assert "01" in info.call_args.args[2]

    def test_quick_preview_reuses_current_parse_logic(self, window):
        window._input_text.setPlainText("兔各10")
        window._on_quick_preview()
        assert len(window._parsed_results) == 1
        assert window._parsed_results[0].success
        assert "已重新解析当前输入" in window.statusBar().currentMessage()

    def test_clear_output_confirmed_requires_confirmation_no(self, window):
        window._input_text.setPlainText("兔各10")
        window._do_parse()
        with patch(
            "ui.windows.record_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ):
            window._on_clear_output_confirmed()
        assert window._input_text.toPlainText() == "兔各10"

    def test_clear_output_confirmed_yes_clears_current_input_and_preview(self, window):
        window._input_text.setPlainText("兔各10")
        window._do_parse()
        window._on_add_result()
        with patch(
            "ui.windows.record_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            window._on_clear_output_confirmed()
        assert window._input_text.toPlainText() == ""
        assert window._output_text.toPlainText() == ""
        assert window._order_table.rowCount() == 0

    def test_copy_preview_result_does_not_save_order(self, window, qapp):
        window._order_intake_service.save_preview = MagicMock()
        window._input_text.setPlainText("兔各10")
        window._do_parse()
        window._on_add_result()
        window._on_copy_preview()
        copied = qapp.clipboard().text()
        assert "投注类型" in copied
        assert "特码" in copied
        window._order_intake_service.save_preview.assert_not_called()

    def test_copy_preview_without_rows_uses_parse_output(self, window, qapp):
        window._input_text.setPlainText("兔各10")
        window._do_parse()
        window._on_copy_preview()
        copied = qapp.clipboard().text()
        assert "特码" in copied
        assert "兔 各数 10" in copied


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
# 15. 申报人配置接入
# ══════════════════════════════════════════════════════════════════════


class TestDeclarerIntegration:
    def test_configured_declarers_are_loaded(self, qapp, session_factory):
        from services.order_intake_service import OrderIntakeService
        from services.settings_service import SettingsService
        from ui.windows.record_order_window import RecordOrderWindow

        settings = SettingsService(session_factory)
        plan = settings.ensure_default_plan()
        custom = settings.create_plan("46倍6水")
        settings.add_declarer("林林", plan.id)
        settings.add_declarer("老汪", custom.id)
        window = RecordOrderWindow(
            order_intake_service=OrderIntakeService(session_factory),
            settings_service=settings,
        )
        try:
            assert [window._cmb_declarer.itemText(index) for index in range(2)] == ["林林", "老汪"]
            assert window._selected_declarer_name() == "林林"
            assert window._selected_config_plan_name() == "默认方案"
            assert window._lbl_declarer_plan.text() == "配置方案：默认方案"
            window._cmb_declarer.setCurrentText("老汪")
            assert window._selected_config_plan_name() == "46倍6水"
            assert window._lbl_declarer_plan.text() == "配置方案：46倍6水"
        finally:
            window.close()
            window.deleteLater()

    def test_settings_changed_refreshes_declarer_options_and_plan_label(self, qapp, session_factory):
        from services.order_intake_service import OrderIntakeService
        from services.settings_service import SettingsService
        from ui.windows.record_order_window import RecordOrderWindow

        settings = SettingsService(session_factory)
        settings.ensure_default_plan()
        custom = settings.create_plan("47倍4水")
        window = RecordOrderWindow(
            order_intake_service=OrderIntakeService(session_factory),
            settings_service=settings,
        )
        try:
            assert "未设置" in window._cmb_declarer.currentText()

            settings.add_declarer("事件申报人", custom.id)
            app_events.settings_changed.emit()

            index = window._cmb_declarer.findData("事件申报人")
            assert index >= 0
            window._cmb_declarer.setCurrentIndex(index)
            assert window._selected_declarer_name() == "事件申报人"
            assert window._lbl_declarer_plan.text() == "配置方案：47倍4水"
        finally:
            window.close()
            window.deleteLater()

    def test_no_configured_declarer_keeps_window_usable(self, save_window):
        assert save_window._cmb_declarer.count() == 1
        assert "未设置" in save_window._cmb_declarer.currentText()
        assert save_window._selected_declarer_name() is None
        assert save_window._lbl_declarer_plan.text() == "配置方案：未绑定配置方案"

    def test_declarer_without_plan_uses_safe_placeholder(self, qapp):
        from ui.windows.record_order_window import RecordOrderWindow

        window = RecordOrderWindow(settings_service=FakeSettingsService(["临时申报人"]))
        try:
            assert window._selected_declarer_name() == "临时申报人"
            assert window._selected_config_plan_name() is None
            assert window._lbl_declarer_plan.text() == "配置方案：未绑定配置方案"
        finally:
            window.close()
            window.deleteLater()

    def test_settings_read_failure_does_not_crash(self, qapp):
        from ui.windows.record_order_window import RecordOrderWindow

        window = RecordOrderWindow(settings_service=FailingSettingsService())
        try:
            assert "配置读取失败" in window._cmb_declarer.currentText()
            assert window._lbl_declarer_plan.text() == "配置方案：配置读取失败"
            assert window._selected_declarer_name() is None
        finally:
            window.close()
            window.deleteLater()

    def test_selected_declarer_saves_and_displays_in_order_detail(self, qapp, session_factory):
        from sqlalchemy import select

        from models import OperationLog, Order
        from services.log_service import LogService
        from services.order_intake_service import OrderIntakeService
        from services.order_service import OrderService
        from services.settings_service import SettingsService
        from ui.pages.order_detail_page import OrderDetailPage
        from ui.windows.record_order_window import RecordOrderWindow

        settings = SettingsService(session_factory)
        plan = settings.ensure_default_plan()
        settings.add_item(plan.id, "特码", "999", "100")
        settings.add_declarer("林林", plan.id)
        window = RecordOrderWindow(
            order_intake_service=OrderIntakeService(session_factory),
            settings_service=settings,
        )
        try:
            window._cmb_declarer.setCurrentText("林林")
            window._input_text.setPlainText("01/10")
            window._do_parse()
            with patch("ui.windows.record_order_window.QMessageBox.information"):
                window._on_save_order()
        finally:
            window.close()
            window.deleteLater()

        with session_factory() as session:
            order = session.scalars(select(Order)).one()
            order_log = session.scalars(
                select(OperationLog).where(
                    OperationLog.module == "order",
                    OperationLog.action == "create",
                )
            ).one()
            assert order.customer_name == "林林"
            assert order.total_amount == 10
            assert "declarer=林林" in order_log.description
            assert "config_plan=默认方案" in order_log.description

        page = OrderDetailPage(
            order_service=OrderService(session_factory),
            log_service=LogService(session_factory),
        )
        assert page._table.rowCount() == 1
        assert page._table.item(0, 7).text() == "林林"

    def test_adjusted_table_save_preserves_selected_declarer(self, qapp, session_factory):
        from sqlalchemy import select

        from models import OperationLog, Order
        from services.order_intake_service import OrderIntakeService
        from services.settings_service import SettingsService
        from ui.windows.record_order_window import RecordOrderWindow

        settings = SettingsService(session_factory)
        plan = settings.ensure_default_plan()
        settings.add_declarer("老汪", plan.id)
        window = RecordOrderWindow(
            order_intake_service=OrderIntakeService(session_factory),
            settings_service=settings,
        )
        try:
            window._cmb_declarer.setCurrentText("老汪")
            window._input_text.setPlainText("01/10")
            window._do_parse()
            window._on_add_result()
            assert window._order_table.item(0, 8).text() == "老汪"
            window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).setText("25")
            with patch("ui.windows.record_order_window.QMessageBox.information"):
                window._on_save_order()
        finally:
            window.close()
            window.deleteLater()

        with session_factory() as session:
            order = session.scalars(select(Order)).one()
            order_log = session.scalars(
                select(OperationLog).where(
                    OperationLog.module == "order",
                    OperationLog.action == "create",
                )
            ).one()
            assert order.customer_name == "老汪"
            assert order.source == "record_window_adjusted"
            assert "config_plan=默认方案" in order_log.description


# ══════════════════════════════════════════════════════════════════════
# 16. 保存订单
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

    def test_mixed_success_and_failed_lines_require_confirmation(self, save_window, session_factory):
        """存在失败行时明确确认；取消则不保存成功项。"""
        save_window._input_text.setPlainText("01/10\n50/10")
        save_window._do_parse()
        assert any(r.success for r in save_window._last_parse_results)
        assert any(not r.success for r in save_window._last_parse_results)

        with patch(
            "ui.windows.record_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question:
            save_window._on_save_order()

        question.assert_called_once()
        assert "只保存识别成功项" in question.call_args.args[2]
        assert "超出范围" in question.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_mixed_success_and_failed_lines_confirm_saves_success_only(self, save_window, session_factory):
        save_window._input_text.setPlainText("01/10\n50/10")
        save_window._do_parse()

        with (
            patch(
                "ui.windows.record_order_window.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ) as question,
            patch("ui.windows.record_order_window.QMessageBox.information"),
        ):
            save_window._on_save_order()

        assert question.call_count >= 1
        assert "只保存识别成功项" in question.call_args_list[0].args[2]
        assert _order_counts(session_factory) == (1, 1)

    def test_save_01_10_success_writes_order_and_clears_parse_state(self, save_window, session_factory):
        """01/10 解析成功后可保存到临时数据库。"""
        from sqlalchemy import select

        from models import Order, OrderItem

        save_window._spin_zodiac_year.setValue(2025)
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
            assert order.zodiac_year == 2025
            assert order.total_amount == 10
            assert len(items) == 1
            assert items[0].selection == "01"
            assert items[0].amount == 10
        assert save_window._input_text.toPlainText() == ""
        assert save_window._output_text.toPlainText() == ""
        assert save_window._parsed_results == []
        assert save_window._order_table.rowCount() == 0
        assert save_window._lbl_total.text() == "当前总额: 0"

    def test_successful_save_emits_orders_changed_once(self, save_window):
        """保存成功后发出一次订单数据变化通知。"""
        event_counts = {"orders": 0}

        def on_orders_changed():
            event_counts["orders"] += 1

        app_events.orders_changed.connect(on_orders_changed)
        try:
            save_window._input_text.setPlainText("01/10")
            save_window._do_parse()
            with (
                patch(
                    "ui.windows.record_order_window.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ),
                patch("ui.windows.record_order_window.QMessageBox.information"),
            ):
                save_window._on_save_order()
        finally:
            app_events.orders_changed.disconnect(on_orders_changed)

        assert event_counts["orders"] == 1

    def test_failed_save_does_not_emit_orders_changed(self, save_window):
        """保存失败时不发订单变化通知。"""
        event_counts = {"orders": 0}

        def on_orders_changed():
            event_counts["orders"] += 1

        app_events.orders_changed.connect(on_orders_changed)
        try:
            save_window._input_text.setPlainText("全包各10")
            save_window._do_parse()
            with patch("ui.windows.record_order_window.QMessageBox.warning"):
                save_window._on_save_order()
        finally:
            app_events.orders_changed.disconnect(on_orders_changed)

        assert event_counts["orders"] == 0

    def test_special_zodiac_mode_save_uses_order_intake_service_chain(self, save_window, session_factory):
        """特肖模式保存仍走 OrderIntakeService，并保存为平特一肖。"""
        from sqlalchemy import select

        from models import Order, OrderItem

        checkboxes = {checkbox.text(): checkbox for checkbox in save_window.findChildren(QCheckBox)}
        checkboxes["特肖模式"].setChecked(True)
        save_window._input_text.setPlainText("马蛇10")
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
            item = session.scalars(select(OrderItem)).one()
            assert order.total_amount == 20
            assert item.bet_type == "平特一肖"
            assert item.selection == "马,蛇"
            assert item.amount == 20

    def test_advanced_adjusted_table_save_preserves_amount_region_channel_declarer_and_events(
        self,
        qapp,
        session_factory,
    ):
        """高级选项预览进表格后，人工调整保存仍以表格当前数据为准。"""
        from sqlalchemy import select

        from models import Order, OrderItem
        from services.order_intake_service import OrderIntakeService
        from services.settings_service import SettingsService
        from ui.windows.record_order_window import RecordOrderWindow

        settings = SettingsService(session_factory)
        plan = settings.ensure_default_plan()
        settings.add_declarer("验收申报人", plan.id)
        window = RecordOrderWindow(
            order_intake_service=OrderIntakeService(session_factory),
            settings_service=settings,
        )
        event_counts = {"orders": 0, "logs": 0}

        def on_orders_changed():
            event_counts["orders"] += 1

        def on_logs_changed():
            event_counts["logs"] += 1

        app_events.orders_changed.connect(on_orders_changed)
        app_events.logs_changed.connect(on_logs_changed)
        try:
            window._parse_timer.stop()
            if hasattr(window, "_chk_auto_fetch"):
                window._chk_auto_fetch.setChecked(False)
            checkboxes = {checkbox.text(): checkbox for checkbox in window.findChildren(QCheckBox)}
            checkboxes["特肖模式"].setChecked(True)
            window._radio_hk.setChecked(True)
            window._cmb_channel.setCurrentText("现金")
            window._cmb_declarer.setCurrentText("验收申报人")
            window._input_text.setPlainText("马蛇10")
            window._do_parse()
            window._on_add_result()
            window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).setText("30")

            with (
                patch(
                    "ui.windows.record_order_window.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ),
                patch("ui.windows.record_order_window.QMessageBox.information"),
            ):
                window._on_save_order()
        finally:
            app_events.orders_changed.disconnect(on_orders_changed)
            app_events.logs_changed.disconnect(on_logs_changed)
            window.close()
            window.deleteLater()

        with session_factory() as session:
            order = session.scalars(select(Order)).one()
            item = session.scalars(select(OrderItem)).one()
            assert order.region == "香港"
            assert order.channel == "现金"
            assert order.customer_name == "验收申报人"
            assert order.source == "record_window_adjusted"
            assert order.total_amount == 30
            assert item.bet_type == "平特一肖"
            assert item.selection == "马,蛇"
            assert item.amount == 30
        assert event_counts == {"orders": 1, "logs": 1}

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

    def test_delete_one_table_row_then_save_success(self, save_window, session_factory):
        """解析后删除错误行，剩余表格明细可以保存。"""
        from sqlalchemy import select

        from models import Order, OrderItem

        save_window._input_text.setPlainText("01/10\n02/20")
        save_window._do_parse()
        save_window._on_add_result()
        save_window._order_table.selectRow(1)
        save_window._on_delete_selected()
        assert save_window._table_user_adjusted is True

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
            assert order.total_amount == 10
            assert len(items) == 1
            assert items[0].selection == "01"
            assert items[0].amount == 10
        assert _log_count(session_factory) == 1

    def test_modify_table_order_total_then_save_recalculates_total(self, save_window, session_factory):
        """修改订单总额后保存，以表格订单总额重新计算订单和明细金额。"""
        from sqlalchemy import select

        from models import Order, OrderItem

        save_window._spin_zodiac_year.setValue(2025)
        save_window._input_text.setPlainText("01/10")
        save_window._do_parse()
        save_window._on_add_result()
        save_window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).setText("25")
        assert save_window._table_user_adjusted is True

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
            item = session.scalars(select(OrderItem)).one()
            assert order.total_amount == 25
            assert item.amount == 25
        assert _log_count(session_factory) == 1

    def test_modify_table_number_and_region_then_save(self, save_window, session_factory):
        """修改号码和地区后保存，使用表格中的最终数据。"""
        from sqlalchemy import select

        from models import Order, OrderItem

        save_window._input_text.setPlainText("01/10")
        save_window._do_parse()
        save_window._on_add_result()
        save_window._order_table.item(0, 0).setText("香港")
        save_window._order_table.item(0, 2).setText("03")

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
            item = session.scalars(select(OrderItem)).one()
            assert order.region == "香港"
            assert item.selection == "03"
            assert item.amount == 10

    def test_invalid_table_amount_blocks_save(self, save_window, session_factory):
        """表格金额不合法时阻止保存。"""
        save_window._input_text.setPlainText("01/10")
        save_window._do_parse()
        save_window._on_add_result()
        save_window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).setText("abc")
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "金额不是有效数字" in warning.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_delete_all_table_rows_blocks_save(self, save_window, session_factory):
        """删除全部表格行后不能保存。"""
        save_window._input_text.setPlainText("01/10")
        save_window._do_parse()
        save_window._on_add_result()
        save_window._order_table.selectRow(0)
        save_window._on_delete_selected()
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "表格没有可保存的订单明细" in warning.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_adjusted_multi_number_row_saves_expected_item_count(self, save_window, session_factory):
        """人工调整多号码行金额后，保存成功且明细数量正确。"""
        from sqlalchemy import select

        from models import Order, OrderItem

        save_window._input_text.setPlainText("01,02,03各10")
        save_window._do_parse()
        save_window._on_add_result()
        save_window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).setText("45")

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
            assert order.total_amount == 45
            assert [item.selection for item in items] == ["01", "02", "03"]
            assert [item.amount for item in items] == [15, 15, 15]
        assert _log_count(session_factory) == 1

    def test_preview_can_save_false_blocks_save(self, save_window, session_factory):
        """preview.can_save=False 时提示原因，不写入数据库。"""
        save_window._input_text.setPlainText("全包各10")
        save_window._do_parse()
        with patch("ui.windows.record_order_window.QMessageBox.warning") as warning:
            save_window._on_save_order()
        warning.assert_called_once()
        assert "全包" in warning.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_supported_play_preview_has_support_column_without_risk_warning(self, window):
        """支持玩法添加到表格后显示支持，不出现强风险提示。"""
        window._input_text.setPlainText("01/10")
        window._do_parse()
        window._on_add_result()

        assert "结算风险" not in window._output_text.toPlainText()
        assert window._order_table.horizontalHeaderItem(_TableColumn.SETTLEMENT_SUPPORT).text() == "结算支持"
        support_item = window._order_table.item(0, _TableColumn.SETTLEMENT_SUPPORT)
        assert support_item.text() == "支持"
        assert "正式结算已支持" in support_item.toolTip()

    def test_unsupported_four_zodiac_keeps_support_text_and_tooltip(self, window):
        window._parsed_results = [
            ParseResult(
                success=True,
                category="四肖",
                amount=70,
                total=70,
                zodiac_groups=[("猪", ()), ("牛", ()), ("马", ()), ("虎", ())],
                original_text="猪牛马虎四肖70",
            )
        ]

        window._on_add_result()

        support_item = window._order_table.item(0, _TableColumn.SETTLEMENT_SUPPORT)
        assert support_item.text() == "暂不支持"
        assert "暂不支持正式结算" in support_item.toolTip()

    def test_unsupported_play_preview_shows_settlement_risk(self, window):
        """不支持正式结算的可保存玩法会在预览中显示风险提示。"""
        window._input_text.setPlainText("二中特 01 02 各10")
        window._do_parse()

        output = window._output_text.toPlainText()
        assert "结算风险" in output
        assert "暂不支持正式结算" in output

    def test_real_mixed_clause_preview_shows_error_and_keeps_success_rows(self, window):
        window._input_text.setPlainText("27.49.47.27.44.32各5，龙猪鸡猴各20")
        window._do_parse()

        output = window._output_text.toPlainText()
        assert "无法识别: 27.49.47.27.44.32各5" in output
        assert "号码27重复" in output
        assert "建议格式" in output
        assert len(window._parsed_results) == 1
        assert len(window._last_parse_results) == 2

        window._on_add_result()
        assert window._order_table.rowCount() == 4
        assert [window._order_table.item(row, 1).text() for row in range(4)] == ["平特一肖"] * 4
        assert [window._order_table.item(row, 2).text() for row in range(4)] == ["龙", "猪", "鸡", "猴"]
        assert [
            window._order_table.item(row, _TableColumn.AMOUNT).text()
            for row in range(4)
        ] == ["20"] * 4

    def test_unsupported_play_save_cancel_does_not_persist(self, save_window, session_factory):
        """保存不支持玩法时用户取消确认，不写订单。"""
        save_window._input_text.setPlainText("二中特 01 02 各10")
        save_window._do_parse()

        with patch(
            "ui.windows.record_order_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question:
            save_window._on_save_order()

        question.assert_called_once()
        assert "第一版可保存记账" in question.call_args.args[2]
        assert _order_counts(session_factory) == (0, 0)

    def test_unsupported_play_save_confirm_persists_accounting_order(self, save_window, session_factory):
        """用户确认后，不支持正式结算玩法仍可保存为记账订单。"""
        from sqlalchemy import select

        from models import OrderItem

        save_window._input_text.setPlainText("二中特 01 02 各10")
        save_window._do_parse()

        with (
            patch(
                "ui.windows.record_order_window.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ) as question,
            patch("ui.windows.record_order_window.QMessageBox.information"),
        ):
            save_window._on_save_order()

        assert question.call_count >= 1
        assert "第一版可保存记账" in question.call_args_list[0].args[2]
        with session_factory() as session:
            item = session.scalars(select(OrderItem)).one()
            assert item.bet_type == "二中特"
            assert item.note == "结算规则待确认"


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
    """金额列 = r.amount，订单总额列 = r.total。"""

    def test_zodiac_single_row_with_total(self, window):
        """生肖类合并为一行，金额与订单总额分别显示。"""
        window._input_text.setPlainText("兔各20")
        window._do_parse()
        window._on_add_result()
        # 兔有 4 个号码，合并在一行
        assert window._order_table.rowCount() == 1
        nums_text = window._order_table.item(0, 2).text()  # 订单信息
        assert nums_text == "04,16,28,40"
        amount = window._order_table.item(0, _TableColumn.AMOUNT).text()
        assert amount == "20"
        total_amount = window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text()
        assert total_amount == "80"
        assert "80" in window._lbl_total.text()

    def test_mixed_parse_results_add_correctly(self, window):
        """多行解析结果各占一行，金额与订单总额不交换。"""
        window._input_text.setPlainText("兔各10\n马各5")
        window._do_parse()
        window._on_add_result()
        # 两个解析结果各占一行
        assert window._order_table.rowCount() == 2
        # 兔各10: 金额 10 / 总额 40；马各5: 金额 5 / 总额 25；合计 65
        assert window._order_table.item(0, _TableColumn.AMOUNT).text() == "10"
        assert window._order_table.item(1, _TableColumn.AMOUNT).text() == "5"
        assert window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text() == "40"
        assert window._order_table.item(1, _TableColumn.TOTAL_AMOUNT).text() == "25"
        assert "65" in window._lbl_total.text()

    def test_special_zodiac_result_keeps_pingte_bet_type_in_table(self, window):
        """特肖模式添加到表格时不误转成特码号码。"""
        checkboxes = {checkbox.text(): checkbox for checkbox in window.findChildren(QCheckBox)}
        checkboxes["特肖模式"].setChecked(True)
        window._input_text.setPlainText("马蛇10")
        window._do_parse()
        window._on_add_result()

        assert window._order_table.rowCount() == 1
        assert window._order_table.item(0, 1).text() == "平特一肖"
        assert window._order_table.item(0, 2).text() == "马,蛇"
        assert window._order_table.item(0, _TableColumn.AMOUNT).text() == "10"
        assert window._order_table.item(0, _TableColumn.TOTAL_AMOUNT).text() == "20"


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
