"""Configure Matplotlib for Chinese text rendering."""

from __future__ import annotations

import os
import platform
from typing import Iterable

import matplotlib
from matplotlib import font_manager

_CJK_FONT_FILES: dict[str, tuple[str, ...]] = {
    "Windows": (
        "msyh.ttc",
        "msyhbd.ttc",
        "simhei.ttf",
        "msjh.ttc",
        "msjhbd.ttc",
        "simsun.ttc",
    ),
    "Darwin": (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ),
}

_CJK_FONT_NAMES: tuple[str, ...] = (
    "Microsoft YaHei",
    "SimHei",
    "Microsoft JhengHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
    "PingFang SC",
    "Heiti SC",
    "STHeiti",
    "WenQuanYi Micro Hei",
    "Source Han Sans SC",
)

_configured = False


def _windows_font_dir() -> str:
    return os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _iter_font_file_candidates() -> Iterable[str]:
    system = platform.system()
    if system == "Windows":
        fonts_dir = _windows_font_dir()
        for filename in _CJK_FONT_FILES["Windows"]:
            yield os.path.join(fonts_dir, filename)
        return

    if system == "Darwin":
        for path in _CJK_FONT_FILES["Darwin"]:
            yield path


def _pick_font_by_name() -> str | None:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in _CJK_FONT_NAMES:
        if name in available:
            return name
    lowered = {name.lower(): name for name in available}
    for candidate in _CJK_FONT_NAMES:
        key = candidate.lower()
        for available_key, available_name in lowered.items():
            if key in available_key:
                return available_name
    return None


def _apply_font_name(font_name: str) -> None:
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False


def _configure_cjk_font() -> str | None:
    for font_path in _iter_font_file_candidates():
        if not os.path.isfile(font_path):
            continue
        font_manager.fontManager.addfont(font_path)
        font_name = font_manager.FontProperties(fname=font_path).get_name()
        _apply_font_name(font_name)
        return font_name

    font_name = _pick_font_by_name()
    if font_name:
        _apply_font_name(font_name)
    else:
        matplotlib.rcParams["axes.unicode_minus"] = False
    return font_name


def configure_matplotlib(*, use_qt_backend: bool = True) -> str | None:
    """Apply backend and CJK font settings for Matplotlib."""
    if use_qt_backend:
        matplotlib.use("QtAgg")
    return _configure_cjk_font()


def ensure_matplotlib_configured(*, use_qt_backend: bool = True) -> str | None:
    """Configure Matplotlib once per process."""
    global _configured
    if _configured:
        return matplotlib.rcParams.get("font.sans-serif", ["DejaVu Sans"])[0]
    font_name = configure_matplotlib(use_qt_backend=use_qt_backend)
    _configured = True
    return font_name
