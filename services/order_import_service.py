"""订单导入第一阶段：文件读取与只读解析预览。"""

from __future__ import annotations

import csv
from pathlib import Path

from schemas.order_import_schema import (
    ImportSourceResult,
    OrderImportPreview,
    OrderImportPreviewRow,
)
from services.order_parser import ParseResult, parse_lines

TEXT_COLUMN_NAMES = {"text", "order_text", "content", "原文", "原始文本", "订单内容"}
SUPPORTED_SUFFIXES = {".txt", ".csv"}


class OrderImportService:
    """只读导入预览服务。

    本服务只负责读取文本和调用现有解析器生成预览，不创建订单、不写数据库。
    """

    def read_file(self, path: str | Path, *, encoding: str = "utf-8") -> ImportSourceResult:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return ImportSourceResult(
                lines=[],
                error="当前仅支持 txt/csv，xlsx 后续开放",
            )

        try:
            content = self._read_text(file_path, encoding=encoding)
        except OSError as exc:
            return ImportSourceResult(lines=[], error=f"文件读取失败：{exc}")
        except UnicodeError as exc:
            return ImportSourceResult(lines=[], error=f"文件编码读取失败：{exc}")

        if suffix == ".txt":
            return self.extract_txt_lines(content)
        return self.extract_csv_lines(content)

    def _read_text(self, path: Path, *, encoding: str) -> str:
        encodings = [encoding]
        for fallback in ("utf-8-sig", "gbk"):
            if fallback not in encodings:
                encodings.append(fallback)

        last_error: UnicodeError | None = None
        for candidate in encodings:
            try:
                return path.read_text(encoding=candidate)
            except UnicodeError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def extract_txt_lines(self, content: str) -> ImportSourceResult:
        lines: list[str] = []
        skipped = 0
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                skipped += 1
                continue
            lines.append(line)
        return ImportSourceResult(lines=lines, skipped_count=skipped)

    def extract_csv_lines(self, content: str) -> ImportSourceResult:
        rows = list(csv.reader(content.splitlines()))
        if not rows:
            return ImportSourceResult(lines=[], skipped_count=0)

        header_index = self._detect_text_column(rows[0])
        data_rows = rows[1:] if header_index is not None else rows
        text_index = header_index if header_index is not None else 0

        lines: list[str] = []
        skipped = 0
        for row in data_rows:
            if not row or all(not cell.strip() for cell in row):
                skipped += 1
                continue
            if text_index >= len(row):
                skipped += 1
                continue
            text = row[text_index].strip()
            if not text:
                skipped += 1
                continue
            lines.append(text)
        return ImportSourceResult(lines=lines, skipped_count=skipped)

    def _detect_text_column(self, first_row: list[str]) -> int | None:
        for index, cell in enumerate(first_row):
            if cell.strip().lower() in TEXT_COLUMN_NAMES:
                return index
        return None

    def preview_lines(
        self,
        lines: list[str],
        *,
        region_mode: str | None = None,
        skipped_count: int = 0,
    ) -> OrderImportPreview:
        rows = [
            self._preview_line(line_number=index, raw_text=line, region_mode=region_mode)
            for index, line in enumerate(lines, start=1)
        ]
        return OrderImportPreview(rows=rows, skipped_count=skipped_count)

    def preview_text(
        self,
        content: str,
        *,
        region_mode: str | None = None,
    ) -> OrderImportPreview:
        source = self.extract_txt_lines(content)
        return self.preview_lines(
            source.lines,
            region_mode=region_mode,
            skipped_count=source.skipped_count,
        )

    def _preview_line(
        self,
        *,
        line_number: int,
        raw_text: str,
        region_mode: str | None,
    ) -> OrderImportPreviewRow:
        parse_text = self._with_region(raw_text, region_mode)
        results = parse_lines(parse_text)
        if not results:
            return OrderImportPreviewRow(
                line_number=line_number,
                raw_text=raw_text,
                region=self._display_region(region_mode, []),
                success=False,
                error="未解析出订单明细",
            )

        failed = [result for result in results if not result.success]
        if failed:
            return OrderImportPreviewRow(
                line_number=line_number,
                raw_text=raw_text,
                region=self._display_region(region_mode, results),
                success=False,
                error="；".join(result.error or "解析失败" for result in failed),
            )

        return OrderImportPreviewRow(
            line_number=line_number,
            raw_text=raw_text,
            region=self._display_region(region_mode, results),
            success=True,
            bet_type_summary=self._bet_type_summary(results),
            amount_total=sum(result.total for result in results),
            item_count=len(results),
            selection_summary=self._selection_summary(results),
        )

    def _display_region(self, region_mode: str | None, results: list[ParseResult]) -> str:
        if region_mode in {"澳门", "香港"}:
            return region_mode
        regions = sorted({result.region for result in results if result.region})
        if len(regions) == 1:
            return regions[0]
        if len(regions) > 1:
            return "多地区"
        return "未识别/默认"

    def _with_region(self, raw_text: str, region_mode: str | None) -> str:
        if region_mode not in {"澳门", "香港"}:
            return raw_text
        stripped = raw_text.strip()
        if stripped.startswith(("澳门", "澳", "香港", "港")):
            return raw_text
        return f"{region_mode}{raw_text}"

    def _bet_type_summary(self, results: list[ParseResult]) -> str:
        values = []
        for result in results:
            if result.category and result.category not in values:
                values.append(result.category)
        return "、".join(values)

    def _selection_summary(self, results: list[ParseResult]) -> str:
        parts: list[str] = []
        for result in results:
            if result.zodiac_groups:
                group_names = ",".join(name for name, _numbers in result.zodiac_groups)
                parts.append(group_names)
            elif result.numbers:
                parts.append(",".join(f"{number:02d}" for number in result.numbers[:8]))
            if len(parts) >= 3:
                break
        return "；".join(parts)
