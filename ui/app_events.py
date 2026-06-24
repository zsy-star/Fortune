"""Application-wide Qt signals for committed UI data changes."""

from PySide6.QtCore import QObject, Signal


class AppEvents(QObject):
    orders_changed = Signal()
    logs_changed = Signal()
    settlements_changed = Signal()


app_events = AppEvents()
