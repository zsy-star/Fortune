from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTextEdit

from ui.pages.number_catalog_page import NumberCatalogPage, _build_catalog_html


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_number_catalog_page_creates_and_contains_complete_reference_boundary() -> None:
    app()
    page = NumberCatalogPage()
    try:
        text = page._content.toPlainText()
        for expected in (
            "2026最新",
            "01 13 25 37 49",
            "02 14 26 38",
            "红波",
            "半波",
            "天肖",
            "三合",
            "六合",
            "大小中边数",
            "合数（固定不变）",
            "门数",
            "段位",
            "模三数",
            "模七数",
            "前落码",
            "九星号码",
            "05月；龙，兔，马，兔。",
            "11月；狗，鸡，鼠，鸡。",
            "牛 [立东]",
            "五福肖",
            "鼠、虎、兔、蛇、猴[龙]。",
            "本页为静态号码参考资料；实际录单、结算支持范围以系统提示为准。",
        ):
            assert expected in text
    finally:
        page.close()
        page.deleteLater()


def test_wave_half_wave_and_zodiac_color_groups_color_actual_content() -> None:
    html = _build_catalog_html(2026)

    for label, color, numbers in (
        ("红波", "#D93025", "01 02 07 08"),
        ("蓝波", "#1565C0", "03 04 09 10"),
        ("绿波", "#138A36", "05 06 11 16"),
        ("红双", "#D93025", "02-08-12-18"),
        ("红单", "#D93025", "01-07-13-19"),
        ("蓝双", "#1565C0", "04-10-14-20"),
        ("蓝单", "#1565C0", "03-09-15-25"),
        ("绿双", "#138A36", "06-16-22-28"),
        ("绿单", "#138A36", "05-11-17-21"),
    ):
        assert f'color:{color};">{label}</b>' in html
        assert f'color:{color};font-size:15px;font-weight:600;">{numbers}' in html

    assert '<b style="color:#D93025;">红肖</b>' in html
    assert '<span style="font-weight:600;color:#D93025;">马、兔、鼠、鸡</span>' in html
    assert '<b style="color:#1565C0;">蓝肖</b>' in html
    assert '<b style="color:#138A36;">绿肖</b>' in html


def test_search_uses_visible_text_wraps_and_reports_missing_content() -> None:
    app()
    page = NumberCatalogPage()
    try:
        for keyword in ("49", "红波", "马", "模三数", "前落码", "天肖", "三合", "六合"):
            page._search_edit.setText(keyword)
            page._search_next()
            selections = page._content.extraSelections()
            assert selections
            assert selections[0].cursor.selectedText() == keyword
            page._search_next()
            page._search_next(backward=True)

        page._search_edit.setText("span style")
        page._search_next()
        assert page._content.extraSelections() == []
        assert page._search_status.text() == "未找到“span style”。"
    finally:
        page.close()
        page.deleteLater()


def test_year_switch_and_scrollable_content_remain_available() -> None:
    application = app()
    page = NumberCatalogPage()
    try:
        content = page.findChild(QTextEdit, "catalogContent")
        assert content is not None
        assert content.isReadOnly()
        assert content.verticalScrollBar() is not None

        page._year_spin.setValue(2025)
        assert "当前生肖年份：2025" in content.toPlainText()
        page._year_spin.setValue(2026)
        assert "当前生肖年份：2026" in content.toPlainText()
        assert "01 13 25 37 49" in content.toPlainText()

        page.resize(900, 600)
        page.show()
        application.processEvents()
        assert content.verticalScrollBar().maximum() > 0
    finally:
        page.close()
        page.deleteLater()
