from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from services.draw_sync_service import DrawSyncResult
from ui.workers import DrawSyncTask


class SuccessService:
    def sync_latest(self, *, lottery_type: int, year: int) -> DrawSyncResult:
        return DrawSyncResult(created=1)

    def sync_history_pages(self, *, lottery_type: int, year: int, pages: int, page_size: int) -> DrawSyncResult:
        return DrawSyncResult(skipped=pages)

    def close(self) -> None:
        pass


class FailureService:
    def sync_latest(self, *, lottery_type: int, year: int) -> DrawSyncResult:
        raise RuntimeError("network timeout")

    def close(self) -> None:
        pass


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def wait_for(task: DrawSyncTask) -> None:
    loop = QEventLoop()
    task.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()


def test_draw_sync_worker_success_signal() -> None:
    app()
    task = DrawSyncTask(
        mode="latest",
        lottery_type=2,
        year=2026,
        service_factory=SuccessService,
    )
    results = []
    task.succeeded.connect(results.append)

    assert task.start() is True
    wait_for(task)

    assert results and results[0].created == 1


def test_draw_sync_worker_failure_signal() -> None:
    app()
    task = DrawSyncTask(
        mode="latest",
        lottery_type=2,
        year=2026,
        service_factory=FailureService,
    )
    errors = []
    task.failed.connect(errors.append)

    task.start()
    wait_for(task)

    assert errors
    assert "timeout" in errors[0]


def test_draw_sync_worker_duplicate_start_protection() -> None:
    app()
    task = DrawSyncTask(
        mode="latest",
        lottery_type=2,
        year=2026,
        service_factory=SuccessService,
    )

    assert task.start() is True
    assert task.start() is False
    wait_for(task)
