"""数值计算器弹窗。"""

from __future__ import annotations

import re
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)


def _parse_numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]


def _product(nums: list[float]) -> float:
    result = 1.0
    for n in nums:
        result *= n
    return result


def _divide_all(nums: list[float]) -> float | None:
    if not nums:
        return None
    result = nums[0]
    for n in nums[1:]:
        if n == 0:
            return None
        result /= n
    return result


_ROW_SPECS: tuple[tuple[str, str, Callable[[list[float]], float | None]], ...] = (
    (
        "加法计算区域。无需加号，任意分隔符分开即可，支持小数",
        "加法结果",
        lambda nums: sum(nums) if nums else None,
    ),
    (
        "减法计算区域。无需减号，任意分隔符分开即可，支持小数",
        "减法结果",
        lambda nums: nums[0] - sum(nums[1:]) if nums else None,
    ),
    (
        "乘法计算区域。无需乘号，任意分隔符分开即可，支持小数",
        "乘法结果",
        lambda nums: _product(nums) if nums else None,
    ),
    (
        "除法计算区域。无需除号，任意分隔符分开即可，支持小数",
        "除法结果",
        _divide_all,
    ),
)


def _format_result(value: float | None) -> str:
    if value is None:
        return ""
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


class _CalcRow(QWidget):
    def __init__(
        self,
        input_placeholder: str,
        result_placeholder: str,
        compute_fn: Callable[[list[float]], float | None],
        parent=None,
    ):
        super().__init__(parent)
        self._compute_fn = compute_fn

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText(input_placeholder)
        self._input.textChanged.connect(self._on_text_changed)

        self._result = QLineEdit()
        self._result.setReadOnly(True)
        self._result.setPlaceholderText(result_placeholder)
        self._result.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(self._input, stretch=3)
        row.addWidget(self._result, stretch=1)

    def _on_text_changed(self, text: str) -> None:
        nums = _parse_numbers(text)
        if not text.strip():
            self._result.clear()
            return
        if not nums:
            self._result.setText("")
            return
        value = self._compute_fn(nums)
        self._result.setText(_format_result(value))


class CalculatorWindow(QMainWindow):
    """数值计算器 v0.1。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数值计算器 v0.1")
        self.resize(720, 320)
        self.setMinimumSize(600, 280)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        for input_ph, result_ph, fn in _ROW_SPECS:
            root.addWidget(_CalcRow(input_ph, result_ph, fn))

        self._apply_stylesheet()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f5f5f5;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                padding: 10px 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
            QLineEdit:read-only {
                background-color: #fafafa;
                color: #2c3e50;
            }
            """
        )
