"""Shared text helpers for features intentionally unavailable in the MVP."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

UNAVAILABLE_PREFIX = "当前测试版暂未开放"
UNAVAILABLE_TOOLTIP = "当前测试版暂未开放；后续版本开放前不会执行业务写入。"


def unavailable_text(feature: str, reason: str, next_step: str | None = None) -> str:
    parts = [f"{UNAVAILABLE_PREFIX}：{feature}。", reason]
    if next_step:
        parts.append(next_step)
    parts.append("本入口不会写入订单、结算、开奖或操作日志数据。")
    return "\n".join(parts)


def mark_unavailable(button: QPushButton) -> None:
    button.setEnabled(False)
    button.setToolTip(UNAVAILABLE_TOOLTIP)
