"""Local configuration center dialog."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from schemas.settings_schema import OddsRebateItemUpdate, OddsRebatePlanResult
from services.settings_service import SettingsService
from ui.app_events import app_events


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_service: SettingsService | None = None):
        super().__init__(parent)
        self._service = settings_service or SettingsService()
        self._plans: list[OddsRebatePlanResult] = []
        self._loading = False

        self.setWindowTitle("配置")
        self.resize(940, 620)
        self.setMinimumSize(780, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("个人设置 / 配置中心")
        title.setObjectName("settingsTitle")
        subtitle = QLabel("配置数据仅保存在本机，不自动参与赔付、余额或结算计算。")
        subtitle.setObjectName("settingsSubtitle")
        title_row.addWidget(title)
        title_row.addWidget(subtitle)
        title_row.addStretch(1)
        root.addLayout(title_row)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_rate_tab(), "赔率/返水")
        self._tabs.addTab(self._build_declarer_tab(), "申报人")
        self._tabs.addTab(self._build_key_tab(), "导入/导出秘钥")
        root.addWidget(self._tabs, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._apply_stylesheet()
        try:
            self._service.ensure_default_plan()
            self.reload_data()
        except Exception as exc:
            self._show_error(f"设置数据加载失败：{exc}")

    def _build_rate_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(7)

        toolbar = QFrame()
        toolbar.setObjectName("settingsToolbar")
        grid = QGridLayout(toolbar)
        grid.setContentsMargins(8, 7, 8, 7)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        self._plan_combo = QComboBox()
        self._plan_combo.setMinimumWidth(170)
        self._plan_combo.currentIndexChanged.connect(self._on_plan_changed)
        self._btn_add_plan = QPushButton("新增方案")
        self._btn_delete_plan = QPushButton("删除方案")
        self._btn_add_plan.clicked.connect(self._on_add_plan)
        self._btn_delete_plan.clicked.connect(self._on_delete_plan)
        grid.addWidget(QLabel("配置方案"), 0, 0)
        grid.addWidget(self._plan_combo, 0, 1)
        grid.addWidget(self._btn_add_plan, 0, 2)
        grid.addWidget(self._btn_delete_plan, 0, 3)

        self._bet_type_input = QLineEdit()
        self._bet_type_input.setPlaceholderText("输入投注类型")
        self._odds_input = QLineEdit()
        self._odds_input.setPlaceholderText("必填，例如 47")
        self._rebate_input = QLineEdit()
        self._rebate_input.setPlaceholderText("必填，0~100")
        self._btn_add_item = QPushButton("添加")
        self._btn_delete_item = QPushButton("删除选中")
        self._btn_save_items = QPushButton("保存表格修改")
        self._btn_save_items.setObjectName("primarySettingsButton")
        self._btn_add_item.clicked.connect(self._on_add_item)
        self._btn_delete_item.clicked.connect(self._on_delete_item)
        self._btn_save_items.clicked.connect(self._on_save_items)

        grid.addWidget(QLabel("投注类型"), 1, 0)
        grid.addWidget(self._bet_type_input, 1, 1)
        grid.addWidget(QLabel("赔率"), 1, 2)
        grid.addWidget(self._odds_input, 1, 3)
        grid.addWidget(QLabel("返水"), 1, 4)
        grid.addWidget(self._rebate_input, 1, 5)
        grid.addWidget(self._btn_add_item, 1, 6)
        grid.addWidget(self._btn_delete_item, 1, 7)
        grid.addWidget(self._btn_save_items, 1, 8)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(5, 1)
        layout.addWidget(toolbar)

        self._rate_table = QTableWidget(0, 3)
        self._rate_table.setHorizontalHeaderLabels(["投注类型", "赔率", "返水"])
        self._rate_table.verticalHeader().setVisible(False)
        self._rate_table.setAlternatingRowColors(True)
        self._rate_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._rate_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed
        )
        header = self._rate_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._rate_table, stretch=1)

        options = QHBoxLayout()
        self._default_plan_check = QCheckBox("设置当前方案为默认")
        self._default_plan_check.toggled.connect(self._on_default_toggled)
        options.addWidget(self._default_plan_check)
        options.addStretch(1)
        layout.addLayout(options)

        explanation = QPlainTextEdit()
        explanation.setObjectName("settingsExplanation")
        explanation.setReadOnly(True)
        explanation.setMaximumHeight(92)
        explanation.setPlainText(
            "说明：此页仅保存赔率与返水配置，不执行赔付、盈亏或结算计算。\n"
            "双击表格中的赔率或返水可编辑，编辑后请点击“保存表格修改”。\n"
            "默认方案和仅剩的最后一个方案不能删除；已绑定申报人的方案也会受到保护。"
        )
        layout.addWidget(explanation)
        return tab

    def _build_declarer_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        self._declarer_table = QTableWidget(0, 2)
        self._declarer_table.setHorizontalHeaderLabels(["申报人", "赔率配置"])
        self._declarer_table.verticalHeader().setVisible(False)
        self._declarer_table.setAlternatingRowColors(True)
        self._declarer_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._declarer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._declarer_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self._declarer_table, stretch=1)

        add_row = QHBoxLayout()
        self._declarer_name_input = QLineEdit()
        self._declarer_name_input.setPlaceholderText("输入新申报人名称")
        self._btn_add_declarer = QPushButton("添加申报人")
        self._btn_delete_declarer = QPushButton("删除申报人")
        self._btn_add_declarer.clicked.connect(self._on_add_declarer)
        self._btn_delete_declarer.clicked.connect(self._on_delete_declarer)
        add_row.addWidget(self._declarer_name_input, stretch=1)
        add_row.addWidget(self._btn_add_declarer)
        add_row.addWidget(self._btn_delete_declarer)
        left_layout.addLayout(add_row)

        info_group = QGroupBox("说明")
        info_layout = QVBoxLayout(info_group)
        info = QPlainTextEdit()
        info.setReadOnly(True)
        info.setPlainText(
            "申报人用于保存本机常用名称及其配置方案。\n\n"
            "新增申报人会自动绑定当前默认方案；可直接在表格的“赔率配置”下拉框中切换方案。\n\n"
            "申报人名称不能为空且不能重复。本次配置不会改变已经保存的历史订单。"
        )
        info_layout.addWidget(info)
        splitter.addWidget(left)
        splitter.addWidget(info_group)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        return tab

    def _build_key_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 14, 12, 8)
        layout.setSpacing(10)

        form = QFrame()
        form.setObjectName("settingsToolbar")
        grid = QGridLayout(form)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        self._import_key_input = QLineEdit()
        self._export_key_input = QLineEdit()
        self._import_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._export_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._show_import_key = QCheckBox("显示")
        self._show_export_key = QCheckBox("显示")
        self._show_import_key.toggled.connect(
            lambda checked: self._toggle_secret(self._import_key_input, checked)
        )
        self._show_export_key.toggled.connect(
            lambda checked: self._toggle_secret(self._export_key_input, checked)
        )
        grid.addWidget(QLabel("导入文件的秘钥"), 0, 0)
        grid.addWidget(self._import_key_input, 0, 1)
        grid.addWidget(self._show_import_key, 0, 2)
        grid.addWidget(QLabel("导出文件的秘钥"), 1, 0)
        grid.addWidget(self._export_key_input, 1, 1)
        grid.addWidget(self._show_export_key, 1, 2)
        grid.setColumnStretch(1, 1)
        layout.addWidget(form)

        self._btn_save_keys = QPushButton("保存秘钥设置")
        self._btn_save_keys.setObjectName("primarySettingsButton")
        self._btn_save_keys.clicked.connect(self._on_save_keys)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._btn_save_keys)
        layout.addLayout(button_row)

        explanation = QGroupBox("说明")
        explanation_layout = QVBoxLayout(explanation)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "导入秘钥与导出秘钥是为后续文件配置预留的本地设置。\n\n"
            "本阶段只保存和读取设置，不实现真实文件加密、解密或导入/导出业务。\n\n"
            "秘钥默认以掩码显示。当前数据保存在本机数据库中，请勿将其视为系统级安全凭据存储。"
        )
        explanation_layout.addWidget(text)
        layout.addWidget(explanation, stretch=1)
        return tab

    def reload_data(self, *, selected_plan_id: int | None = None) -> None:
        self._reload_plans(selected_plan_id=selected_plan_id)
        self._reload_declarers()
        secrets = self._service.get_secret_settings()
        self._import_key_input.setText(secrets.import_key)
        self._export_key_input.setText(secrets.export_key)

    def _notify_settings_changed(self) -> None:
        app_events.settings_changed.emit()
        app_events.logs_changed.emit()

    def _reload_plans(self, *, selected_plan_id: int | None = None) -> None:
        if selected_plan_id is None:
            selected_plan_id = self._plan_combo.currentData()
        self._plans = self._service.list_plans()
        self._loading = True
        self._plan_combo.blockSignals(True)
        self._plan_combo.clear()
        selected_index = 0
        for index, plan in enumerate(self._plans):
            label = f"{plan.name}（默认）" if plan.is_default else plan.name
            self._plan_combo.addItem(label, plan.id)
            if plan.id == selected_plan_id:
                selected_index = index
        if self._plans:
            self._plan_combo.setCurrentIndex(selected_index)
        self._plan_combo.blockSignals(False)
        self._loading = False
        self._reload_plan_items()

    def _reload_plan_items(self) -> None:
        plan = self._current_plan()
        self._loading = True
        self._rate_table.setRowCount(len(plan.items) if plan else 0)
        if plan:
            for row, item in enumerate(plan.items):
                bet_type = QTableWidgetItem(item.bet_type)
                bet_type.setData(Qt.ItemDataRole.UserRole, item.id)
                bet_type.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._rate_table.setItem(row, 0, bet_type)
                self._rate_table.setItem(row, 1, QTableWidgetItem(_decimal_text(item.odds)))
                self._rate_table.setItem(row, 2, QTableWidgetItem(_decimal_text(item.rebate)))
        self._default_plan_check.setChecked(bool(plan and plan.is_default))
        self._loading = False
        enabled = plan is not None
        self._btn_add_item.setEnabled(enabled)
        self._btn_delete_item.setEnabled(enabled)
        self._btn_save_items.setEnabled(enabled)
        self._btn_delete_plan.setEnabled(len(self._plans) > 1)

    def _reload_declarers(self) -> None:
        rows = self._service.list_declarers()
        self._declarer_table.setRowCount(len(rows))
        for row_index, declarer in enumerate(rows):
            name = QTableWidgetItem(declarer.name)
            name.setData(Qt.ItemDataRole.UserRole, declarer.id)
            self._declarer_table.setItem(row_index, 0, name)
            combo = QComboBox()
            for plan in self._plans:
                combo.addItem(plan.name, plan.id)
            selected = combo.findData(declarer.plan_id)
            combo.setCurrentIndex(max(0, selected))
            combo.currentIndexChanged.connect(
                lambda _index, declarer_id=declarer.id, widget=combo: self._on_declarer_plan_changed(
                    declarer_id, widget
                )
            )
            self._declarer_table.setCellWidget(row_index, 1, combo)

    def _current_plan(self) -> OddsRebatePlanResult | None:
        plan_id = self._plan_combo.currentData()
        return next((plan for plan in self._plans if plan.id == plan_id), None)

    def _on_plan_changed(self, _index: int) -> None:
        if not self._loading:
            self._reload_plan_items()

    def _on_add_plan(self) -> None:
        name, ok = QInputDialog.getText(self, "新增配置方案", "配置方案名称")
        if not ok:
            return
        try:
            plan = self._service.create_plan(name)
            self._reload_plans(selected_plan_id=plan.id)
            self._reload_declarers()
            self._notify_settings_changed()
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_delete_plan(self) -> None:
        plan = self._current_plan()
        if plan is None:
            self._show_error("请先选择配置方案")
            return
        choice = QMessageBox.question(
            self,
            "删除配置方案",
            f"确认删除配置方案“{plan.name}”及其配置项？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_plan(plan.id)
            self.reload_data()
            self._notify_settings_changed()
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_default_toggled(self, checked: bool) -> None:
        if self._loading:
            return
        plan = self._current_plan()
        if plan is None:
            return
        if not checked:
            self._loading = True
            self._default_plan_check.setChecked(plan.is_default)
            self._loading = False
            return
        try:
            self._service.set_default_plan(plan.id)
            self._reload_plans(selected_plan_id=plan.id)
            self._notify_settings_changed()
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_add_item(self) -> None:
        plan = self._current_plan()
        if plan is None:
            self._show_error("请先选择配置方案")
            return
        try:
            self._service.add_item(
                plan.id,
                self._bet_type_input.text(),
                self._odds_input.text(),
                self._rebate_input.text(),
            )
            self._bet_type_input.clear()
            self._odds_input.clear()
            self._rebate_input.clear()
            self._reload_plans(selected_plan_id=plan.id)
            self._notify_settings_changed()
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_delete_item(self) -> None:
        plan = self._current_plan()
        row = self._rate_table.currentRow()
        if plan is None or row < 0:
            self._show_error("请先选择一条配置项")
            return
        item_id = self._rate_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        try:
            self._service.delete_item(plan.id, int(item_id))
            self._reload_plans(selected_plan_id=plan.id)
            self._notify_settings_changed()
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_save_items(self) -> None:
        plan = self._current_plan()
        if plan is None:
            self._show_error("请先选择配置方案")
            return
        updates: list[OddsRebateItemUpdate] = []
        for row in range(self._rate_table.rowCount()):
            updates.append(
                OddsRebateItemUpdate(
                    id=int(self._rate_table.item(row, 0).data(Qt.ItemDataRole.UserRole)),
                    odds=self._rate_table.item(row, 1).text(),
                    rebate=self._rate_table.item(row, 2).text(),
                )
            )
        try:
            self._service.update_items(plan.id, updates)
            self._reload_plans(selected_plan_id=plan.id)
            self._notify_settings_changed()
            QMessageBox.information(self, "保存配置", "赔率/返水配置已保存。")
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_add_declarer(self) -> None:
        default_plan = next((plan for plan in self._plans if plan.is_default), None)
        plan = default_plan or (self._plans[0] if self._plans else None)
        if plan is None:
            self._show_error("请先创建赔率配置方案")
            return
        try:
            self._service.add_declarer(self._declarer_name_input.text(), plan.id)
            self._declarer_name_input.clear()
            self._reload_declarers()
            self._notify_settings_changed()
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_delete_declarer(self) -> None:
        row = self._declarer_table.currentRow()
        if row < 0:
            self._show_error("请先选择申报人")
            return
        declarer_id = int(self._declarer_table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        try:
            self._service.delete_declarer(declarer_id)
            self._reload_declarers()
            self._notify_settings_changed()
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_declarer_plan_changed(self, declarer_id: int, combo: QComboBox) -> None:
        plan_id = combo.currentData()
        if plan_id is None:
            return
        try:
            self._service.update_declarer_plan(declarer_id, int(plan_id))
            self._notify_settings_changed()
        except ValueError as exc:
            self._show_error(str(exc))
            self._reload_declarers()

    def _toggle_secret(self, line_edit: QLineEdit, visible: bool) -> None:
        line_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

    def _on_save_keys(self) -> None:
        try:
            self._service.save_secret_settings(
                self._import_key_input.text(),
                self._export_key_input.text(),
            )
            self._notify_settings_changed()
            QMessageBox.information(self, "保存秘钥", "导入/导出秘钥设置已保存。")
        except ValueError as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "配置", message)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #f4f6f7; }
            QLabel#settingsTitle { font-size: 18px; font-weight: 700; color: #2c3e50; }
            QLabel#settingsSubtitle { color: #7f8c8d; }
            QFrame#settingsToolbar { background: #ffffff; border: 1px solid #c8d4d7; }
            QTabWidget::pane { border: 1px solid #bac8cb; background: #ffffff; }
            QTabBar::tab { padding: 7px 18px; background: #e8edef; border: 1px solid #c4d0d2; }
            QTabBar::tab:selected { background: #ffffff; border-bottom-color: #ffffff; }
            QLineEdit, QComboBox { min-height: 26px; border: 1px solid #b7c5c8; padding: 1px 6px; }
            QPushButton { min-height: 26px; padding: 1px 10px; border: 1px solid #b7c5c8; background: #ffffff; }
            QPushButton:hover { background: #e9f5f7; border-color: #69aeb6; }
            QPushButton#primarySettingsButton { background: #3498db; color: white; border-color: #2980b9; }
            QTableWidget { border: 1px solid #b8c7ca; gridline-color: #d5dfe1; alternate-background-color: #f7fafb; }
            QHeaderView::section { background: #dff2f3; border: none; border-right: 1px solid #b5cbce; border-bottom: 1px solid #9cb8bc; padding: 5px; font-weight: 600; }
            QPlainTextEdit#settingsExplanation { background: #fbfcfc; color: #5d6d70; }
            QGroupBox { border: 1px solid #c0cccf; margin-top: 8px; padding-top: 7px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            """
        )
