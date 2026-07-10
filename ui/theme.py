"""Shared visual theme helpers for the desktop UI."""

from __future__ import annotations


def get_main_window_stylesheet() -> str:
    """Return the shared stylesheet applied to the main shell."""
    return """
        QWidget#mainShell,
        QStackedWidget#contentStack {
            background: #F5F7FA;
        }

        QWidget#topNavBar {
            background-color: #FFFFFF;
            border-bottom: 1px solid #E5E7EB;
        }

        QPushButton#navButton {
            color: #1F2933;
            background-color: transparent;
            border: none;
            border-radius: 6px;
            padding: 7px 9px;
            font-size: 12px;
            font-weight: 400;
        }

        QPushButton#navButton:hover {
            background-color: #F3F4F6;
            color: #111827;
        }

        QPushButton#navButton:checked,
        QPushButton#navButton[active="true"] {
            background-color: #ECFDF5;
            color: #16A34A;
            font-weight: 500;
        }

        QPushButton#navMenuArrow {
            color: #4B5563;
            background-color: transparent;
            border: none;
            border-radius: 6px;
            padding: 7px 1px;
            font-size: 12px;
        }

        QPushButton#navMenuArrow:hover {
            background-color: #F3F4F6;
            color: #16A34A;
        }

        QPushButton#navActionButton {
            color: #16A34A;
            background-color: #FFFFFF;
            border: 1px solid #BBF7D0;
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 12px;
            font-weight: 500;
        }

        QPushButton#navActionButton:hover {
            background-color: #ECFDF5;
            border-color: #86EFAC;
            color: #15803D;
        }

        QPushButton#settingsButton {
            color: #374151;
            background-color: transparent;
            border: 1px solid #E5E7EB;
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 12px;
            font-weight: 400;
        }

        QPushButton#settingsButton:hover {
            background-color: #F3F4F6;
            border-color: #D1D5DB;
            color: #111827;
        }

        QLabel#pageTitle {
            font-size: 22px;
            font-weight: 700;
            color: #1f2d3d;
        }

        QLabel#pageHint {
            font-size: 14px;
            color: #6b7c8f;
            margin-top: 8px;
        }

        QTableWidget {
            background: #ffffff;
            alternate-background-color: #f8fafc;
            gridline-color: #e1e7ef;
            border: 1px solid #cfd8e3;
            selection-background-color: #d7e9ff;
            selection-color: #1f2d3d;
        }

        QHeaderView::section {
            background: #eaf1f8;
            color: #243447;
            padding: 5px 6px;
            border: none;
            border-right: 1px solid #cfd8e3;
            border-bottom: 1px solid #c3cfdb;
            font-weight: 700;
        }

        QLineEdit,
        QComboBox,
        QDateEdit,
        QSpinBox,
        QDoubleSpinBox {
            min-height: 26px;
            padding: 3px 8px;
            border: 1px solid #c4ceda;
            border-radius: 5px;
            background: #ffffff;
            color: #243447;
        }

        QLineEdit:focus,
        QComboBox:focus,
        QDateEdit:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus {
            border-color: #2f80ed;
        }

        QPushButton {
            min-height: 26px;
            padding: 4px 12px;
            border: 1px solid #c4ceda;
            border-radius: 5px;
            background: #ffffff;
            color: #1f4e79;
            font-weight: 600;
        }

        QPushButton:hover {
            background: #edf5ff;
            border-color: #8eb8e8;
        }

        QPushButton:disabled {
            color: #9aa8b5;
            background: #f1f4f7;
            border-color: #d7dee7;
        }

        QPushButton#dangerAction {
            color: #9f1d1d;
            border-color: #e0a3a3;
            background: #fffafa;
        }

        QPushButton#dangerAction:hover {
            background: #fff1f1;
            border-color: #c0392b;
        }

        QFrame#toolbar,
        QFrame#filterPanel,
        QFrame#summaryBar,
        QFrame#detailPanel,
        QFrame#backupPanel,
        QFrame#overviewCard,
        QFrame#overviewStatsCard,
        QFrame#overviewChartCard,
        QFrame#drawPanel,
        QGroupBox {
            background: #ffffff;
            border: 1px solid #d7dee7;
            border-radius: 6px;
        }

        QPlainTextEdit,
        QTextEdit {
            background: #ffffff;
            border: 1px solid #cfd8e3;
            border-radius: 5px;
            color: #243447;
        }
    """
