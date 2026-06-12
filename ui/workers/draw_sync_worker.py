"""Qt worker for non-blocking lottery draw synchronization."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from services.draw_sync_service import DrawSyncResult, DrawSyncService


class _DrawSyncThread(QThread):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        mode: str,
        lottery_type: int,
        year: int,
        pages: int,
        page_size: int,
        service_factory: Callable[[], DrawSyncService],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._mode = mode
        self._lottery_type = lottery_type
        self._year = year
        self._pages = pages
        self._page_size = page_size
        self._service_factory = service_factory

    def run(self) -> None:
        service = self._service_factory()
        try:
            if self._mode == "latest":
                self.progress.emit("正在获取最新开奖...")
                result = service.sync_latest(lottery_type=self._lottery_type, year=self._year)
            elif self._mode == "history":
                self.progress.emit(f"正在同步历史开奖 1-{self._pages} 页...")
                result = service.sync_history_pages(
                    lottery_type=self._lottery_type,
                    year=self._year,
                    pages=self._pages,
                    page_size=self._page_size,
                )
            else:
                raise ValueError(f"Unsupported sync mode: {self._mode}")

            if result.failed and result.created == 0 and result.updated == 0 and result.skipped == 0:
                self.failed.emit("; ".join(result.errors) or "同步失败")
            else:
                self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()


class DrawSyncTask(QObject):
    """Small QThread wrapper with duplicate-start protection."""

    started = Signal()
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        *,
        mode: str,
        lottery_type: int,
        year: int,
        pages: int = 1,
        page_size: int = 25,
        service_factory: Callable[[], DrawSyncService] = DrawSyncService,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._active = False
        self._thread = _DrawSyncThread(
            mode=mode,
            lottery_type=lottery_type,
            year=year,
            pages=pages,
            page_size=page_size,
            service_factory=service_factory,
            parent=self,
        )
        self._thread.started.connect(self.started)
        self._thread.progress.connect(self.progress)
        self._thread.succeeded.connect(self.succeeded)
        self._thread.failed.connect(self.failed)
        self._thread.finished.connect(self._on_finished)
        self._thread.finished.connect(self.finished)

    def start(self) -> bool:
        if self._active:
            return False
        self._active = True
        self._thread.start()
        return True

    def is_active(self) -> bool:
        return self._active

    def wait(self, timeout_ms: int = 5000) -> bool:
        return self._thread.wait(timeout_ms)

    def _on_finished(self) -> None:
        self._active = False
