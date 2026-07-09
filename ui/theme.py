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
            background-color: #223142;
            border-bottom: 1px solid #172332;
        }

        QPushButton#navButton {
            color: #dce6ef;
            background-color: transparent;
            border: none;
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 12px;
            font-weight: 500;
        }

        QPushButton#navButton:hover {
            background-color: #34495e;
            color: #ffffff;
        }

        QPushButton#navButton:checked,
        QPushButton#navButton[active="true"] {
            background-color: #2f80ed;
            color: #ffffff;
            font-weight: 700;
        }

        QPushButton#navMenuArrow {
            color: #dce6ef;
            background-color: transparent;
            border: none;
            border-radius: 6px;
            padding: 7px 2px;
            font-size: 12px;
        }

        QPushButton#navMenuArrow:hover {
            background-color: #34495e;
            color: #ffffff;
        }

        QPushButton#navActionButton {
            color: #1f2d3d;
            background-color: #f5b041;
            border: none;
            border-radius: 6px;
            padding: 7px 12px;
            font-size: 12px;
            font-weight: 700;
        }

        QPushButton#navActionButton:hover {
            background-color: #f8c471;
            color: #17202a;
        }

        QPushButton#settingsButton {
            color: #dce6ef;
            background-color: transparent;
            border: 1px solid #41566c;
            border-radius: 6px;
            padding: 7px 12px;
            font-size: 12px;
            font-weight: 600;
        }

        QPushButton#settingsButton:hover {
            background-color: #34495e;
            border-color: #6f8aa3;
            color: #ffffff;
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
