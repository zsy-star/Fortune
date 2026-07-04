"""Unified confirmation dialog for high-risk maintenance operations."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from schemas.maintenance_schema import HighRiskConfirmation, HighRiskOperationSpec


class HighRiskConfirmDialog(QDialog):
    def __init__(self, spec: HighRiskOperationSpec, parent=None):
        super().__init__(parent)
        self._spec = spec
        self.setWindowTitle(f"高风险确认 - {spec.title}")
        self.resize(560, 460)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel(f"{spec.title}：高风险维护操作")
        title.setObjectName("dangerTitle")
        root.addWidget(title)

        summary = QLabel(
            f"影响范围：{spec.impact_summary}\n"
            f"影响数量：{spec.affected_count}\n"
            f"自动备份文件：{spec.backup_path}\n"
            f"风险说明：{spec.warning}"
        )
        summary.setWordWrap(True)
        summary.setObjectName("dangerSummary")
        root.addWidget(summary)

        if spec.extra_counts:
            detail = "\n".join(f"{key}: {value}" for key, value in spec.extra_counts.items())
            detail_label = QLabel("影响明细：\n" + detail)
            detail_label.setWordWrap(True)
            root.addWidget(detail_label)

        form = QFormLayout()
        self._reason_edit = QTextEdit()
        self._reason_edit.setPlaceholderText("请填写执行原因，不能为空")
        self._reason_edit.setFixedHeight(86)
        self._operator_edit = QLineEdit("系统操作员")
        self._phrase_edit = QLineEdit()
        self._phrase_edit.setPlaceholderText(spec.confirm_phrase)
        form.addRow("原因", self._reason_edit)
        form.addRow("操作人", self._operator_edit)
        form.addRow(f"输入确认短语：{spec.confirm_phrase}", self._phrase_edit)
        root.addLayout(form)

        self._error_label = QLabel("")
        self._error_label.setObjectName("dangerError")
        root.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认执行")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.setStyleSheet(
            """
            QLabel#dangerTitle {
                color: #b00020;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#dangerSummary {
                color: #4a1f1f;
                background: #fff2f2;
                border: 1px solid #f0b5b5;
                padding: 8px;
            }
            QLabel#dangerError {
                color: #b00020;
            }
            """
        )

    def confirmation(self) -> HighRiskConfirmation:
        return HighRiskConfirmation(
            reason=self._reason_edit.toPlainText().strip(),
            confirm_phrase=self._phrase_edit.text().strip(),
            operator=self._operator_edit.text().strip() or "系统操作员",
        )

    def _try_accept(self) -> None:
        confirmation = self.confirmation()
        if not confirmation.reason:
            self._error_label.setText("必须填写原因")
            return
        if confirmation.confirm_phrase != self._spec.confirm_phrase:
            self._error_label.setText(f"确认短语不匹配，请输入：{self._spec.confirm_phrase}")
            return
        self.accept()
