"""Synchronize public draw data into the local database."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.database import SessionLocal
from scrapers.wz49_client import Wz49Client
from scrapers.wz49_parser import Wz49Parser
from services.draw_service import DrawService
from services.log_service import LogService


@dataclass(slots=True)
class DrawSyncResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def processed(self) -> int:
        return self.created + self.updated + self.skipped + self.failed


class DrawSyncService:
    def __init__(
        self,
        *,
        client: Wz49Client | None = None,
        parser: Wz49Parser | None = None,
        draw_service: DrawService | None = None,
        log_service: LogService | None = None,
    ):
        self.client = client or Wz49Client()
        self.parser = parser or Wz49Parser()
        self.draw_service = draw_service or DrawService()
        self.log_service = log_service or LogService()

    def sync_latest(self, *, lottery_type: int, year: int) -> DrawSyncResult:
        self._log_start("latest", lottery_type=lottery_type, year=year)
        result = DrawSyncResult()
        try:
            payload = self.client.fetch_latest(lottery_type=lottery_type, year=year)
            draw = self.parser.parse_latest(payload, lottery_type=lottery_type)
            self._save_one(draw, result)
            self._log_success("latest", result)
            return result
        except Exception as exc:
            result.failed += 1
            result.errors.append(str(exc))
            self._log_failure("latest", exc)
            return result

    def sync_history_pages(
        self,
        *,
        lottery_type: int,
        year: int,
        pages: int,
        page_size: int = 25,
    ) -> DrawSyncResult:
        self._log_start("history_pages", lottery_type=lottery_type, year=year, pages=pages)
        result = DrawSyncResult()
        try:
            for page_num in range(1, pages + 1):
                payload = self.client.fetch_history_page(
                    lottery_type=lottery_type,
                    year=year,
                    page_num=page_num,
                    page_size=page_size,
                )
                draws = self.parser.parse_history_page(payload, lottery_type=lottery_type)
                for draw in draws:
                    self._save_one(draw, result)
            self._log_success("history_pages", result)
            return result
        except Exception as exc:
            result.failed += 1
            result.errors.append(str(exc))
            self._log_failure("history_pages", exc)
            return result

    def sync_history(self, *, lottery_type: int, year: int, pages: int, page_size: int = 25) -> DrawSyncResult:
        return self.sync_history_pages(
            lottery_type=lottery_type,
            year=year,
            pages=pages,
            page_size=page_size,
        )

    def close(self) -> None:
        self.client.close()

    def _save_one(self, draw, result: DrawSyncResult) -> None:
        try:
            _saved, action = self.draw_service.save_draw(draw)
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"{draw.region} {draw.issue_number}: {exc}")
            return
        if action == "created":
            result.created += 1
        elif action == "updated":
            result.updated += 1
        else:
            result.skipped += 1

    def _log_start(self, mode: str, **meta) -> None:
        self.log_service.create_log(
            module="draw_sync",
            action="start",
            description=f"Start {mode} sync: {meta}",
        )

    def _log_success(self, mode: str, result: DrawSyncResult) -> None:
        self.log_service.create_log(
            module="draw_sync",
            action="success",
            description=(
                f"Finished {mode} sync: created={result.created}, updated={result.updated}, "
                f"skipped={result.skipped}, failed={result.failed}"
            ),
        )

    def _log_failure(self, mode: str, exc: Exception) -> None:
        self.log_service.create_log(
            module="draw_sync",
            action="failure",
            description=f"Failed {mode} sync: {exc}",
        )
