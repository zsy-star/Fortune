"""Tests for Matplotlib Chinese font setup."""

from __future__ import annotations

import matplotlib

from ui.matplotlib_setup import configure_matplotlib, ensure_matplotlib_configured


def test_configure_matplotlib_sets_cjk_font_and_minus_sign() -> None:
    font_name = configure_matplotlib(use_qt_backend=False)

    assert matplotlib.rcParams["axes.unicode_minus"] is False
    sans_serif = matplotlib.rcParams["font.sans-serif"]
    assert sans_serif
    if font_name is not None:
        assert sans_serif[0] == font_name


def test_ensure_matplotlib_configured_is_idempotent() -> None:
    first = ensure_matplotlib_configured(use_qt_backend=False)
    second = ensure_matplotlib_configured(use_qt_backend=False)
    assert first == second
