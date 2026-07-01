"""Application-wide Qt signals for committed UI data changes."""

from PySide6.QtCore import QObject, Signal


class AppEvents(QObject):
    orders_changed = Signal()
    logs_changed = Signal()
    settlements_changed = Signal()
    ledger_changed = Signal()
    draws_changed = Signal()
    settings_changed = Signal()
    app_data_reloaded = Signal()


app_events = AppEvents()
