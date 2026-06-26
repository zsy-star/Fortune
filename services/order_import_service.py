"""订单导入第一阶段：文件读取与只读解析预览。"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from models import Order
from schemas.order_import_schema import (
    ImportSourceResult,
    OrderImportConfirmResult,
    OrderImportContext,
    OrderImportPreview,
    OrderImportPreviewRow,
)
from services.log_service import LogService
from services.order_intake_service import OrderIntakeService
from services.order_parser import ParseResult, parse_lines

TEXT_COLUMN_NAMES = {
    "text",
    "order_text",
    "content",
    "原文",
    "原始文本",
    "订单内容",
    "订单文本",
    "投注内容",
}
SUPPORTED_SUFFIXES = {".txt", ".csv", ".xlsx"}
TEMPLATE_EXAMPLES = ("01各10", "02各5")


class OrderImportService:
    """只读导入预览服务。

    文件读取和解析预览只读；确认导入时只通过 OrderIntakeService 保存成功行。
    """

    def __init__(
        self,
        order_intake_service: OrderIntakeService | None = None,
        log_service: LogService | None = None,
    ):
        self._order_intake_service = order_intake_service or OrderIntakeService()
        self._log_service = log_service or LogService(self._order_intake_service._session_factory)

    def read_file(self, path: str | Path, *, encoding: str = "utf-8") -> ImportSourceResult:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return ImportSourceResult(
                lines=[],
                error="当前仅支持 txt/csv/xlsx",
            )

        if suffix == ".xlsx":
            return self.extract_xlsx_lines(file_path)

        try:
            content = self._read_text(file_path, encoding=encoding)
        except OSError as exc:
            return ImportSourceResult(lines=[], error=f"文件读取失败：{exc}")
        except UnicodeError as exc:
            return ImportSourceResult(lines=[], error=f"文件编码读取失败：{exc}")

        if suffix == ".txt":
            return self.extract_txt_lines(content)
        return self.extract_csv_lines(content)

    def create_template(self, path: str | Path, *, file_type: str | None = None) -> Path:
        """Create a minimal import template that can be read by the current importer."""

        target = Path(path)
        suffix = (file_type or target.suffix).lower().lstrip(".")
        if suffix not in {"txt", "csv", "xlsx"}:
            raise ValueError("导入模板仅支持 txt/csv/xlsx")

        if suffix == "txt":
            target.write_text("\n".join(TEMPLATE_EXAMPLES) + "\n", encoding="utf-8")
            return target

        if suffix == "csv":
            with open(target, "w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["订单文本"])
                for example in TEMPLATE_EXAMPLES:
                    writer.writerow([example])
            return target

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "订单导入模板"
        sheet.append(["订单文本"])
        for example in TEMPLATE_EXAMPLES:
            sheet.append([example])
        workbook.save(target)
        workbook.close()
        return target

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

    def extract_xlsx_lines(self, path: str | Path) -> ImportSourceResult:
        """Read order text lines from the first worksheet of an xlsx file."""

        try:
            workbook = load_workbook(path, data_only=True, read_only=True)
        except Exception as exc:
            return ImportSourceResult(lines=[], error=f"xlsx 文件读取失败：{exc}")

        try:
            sheet = workbook.worksheets[0]
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        finally:
            workbook.close()

        if not rows:
            return ImportSourceResult(lines=[], skipped_count=0)

        first_non_empty_index: int | None = None
        for index, row in enumerate(rows):
            if any(self._cell_text(cell) for cell in row):
                first_non_empty_index = index
                break
        if first_non_empty_index is None:
            return ImportSourceResult(lines=[], skipped_count=len(rows))

        header_index = self._detect_text_column(
            [self._cell_text(cell) for cell in rows[first_non_empty_index]]
        )
        data_rows = rows[first_non_empty_index + 1 :] if header_index is not None else rows[first_non_empty_index:]
        text_index = header_index if header_index is not None else 0

        lines: list[str] = []
        skipped = first_non_empty_index
        for row in data_rows:
            if not row or all(not self._cell_text(cell) for cell in row):
                skipped += 1
                continue
            if text_index >= len(row):
                skipped += 1
                continue
            text = self._cell_text(row[text_index])
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

    def _cell_text(self, value) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def preview_lines(
        self,
        lines: list[str],
        *,
        region_mode: str | None = None,
        skipped_count: int = 0,
        history_duplicate_check: bool = False,
        customer_name: str | None = None,
    ) -> OrderImportPreview:
        rows = [
            self._preview_line(line_number=index, raw_text=line, region_mode=region_mode)
            for index, line in enumerate(lines, start=1)
        ]
        rows = self._mark_duplicate_rows(rows)
        history_enabled = False
        history_error = ""
        if history_duplicate_check:
            try:
                rows = self._mark_history_duplicate_rows(rows, customer_name=customer_name)
                history_enabled = True
            except Exception as exc:
                history_error = f"历史重复检测失败：{exc}"
        return OrderImportPreview(
            rows=rows,
            skipped_count=skipped_count,
            history_duplicate_check_enabled=history_enabled,
            history_duplicate_error=history_error,
        )

    def preview_text(
        self,
        content: str,
        *,
        region_mode: str | None = None,
        history_duplicate_check: bool = False,
        customer_name: str | None = None,
    ) -> OrderImportPreview:
        source = self.extract_txt_lines(content)
        return self.preview_lines(
            source.lines,
            region_mode=region_mode,
            skipped_count=source.skipped_count,
            history_duplicate_check=history_duplicate_check,
            customer_name=customer_name,
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

    def _mark_duplicate_rows(self, rows: list[OrderImportPreviewRow]) -> list[OrderImportPreviewRow]:
        counts: dict[str, int] = {}
        for row in rows:
            key = self._duplicate_key(row.raw_text)
            counts[key] = counts.get(key, 0) + 1
        return [
            replace(row, duplicate_warning="疑似重复行") if counts[self._duplicate_key(row.raw_text)] > 1 else row
            for row in rows
        ]

    def _duplicate_key(self, text: str) -> str:
        return self._normalize_duplicate_text(text)

    def _mark_history_duplicate_rows(
        self,
        rows: list[OrderImportPreviewRow],
        *,
        customer_name: str | None = None,
    ) -> list[OrderImportPreviewRow]:
        candidate_rows = [row for row in rows if row.success and row.region in {"澳门", "香港"}]
        if not candidate_rows:
            return rows

        wanted_regions = {row.region for row in candidate_rows}
        with self._order_intake_service._session_factory() as session:
            stmt = select(Order.id, Order.order_no, Order.raw_text, Order.region, Order.customer_name).where(
                Order.region.in_(wanted_regions),
                Order.raw_text.is_not(None),
            )
            if customer_name:
                stmt = stmt.where(Order.customer_name == customer_name)
            history = list(session.execute(stmt))

        history_map: dict[tuple[str, str], tuple[int, str]] = {}
        for order_id, order_no, raw_text, region, _customer in history:
            key = (self._normalize_duplicate_text(raw_text), str(region))
            history_map.setdefault(key, (int(order_id), str(order_no)))

        marked: list[OrderImportPreviewRow] = []
        for row in rows:
            key = (self._normalize_duplicate_text(row.raw_text), row.region)
            match = history_map.get(key)
            if match and row.success:
                order_id, order_no = match
                marked.append(
                    replace(
                        row,
                        history_duplicate_warning=f"疑似历史重复：订单 {order_no}",
                        history_duplicate_order_id=order_id,
                        history_duplicate_order_no=order_no,
                    )
                )
            else:
                marked.append(row)
        return marked

    def _normalize_duplicate_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or "")).strip()
        normalized = normalized.translate(str.maketrans({"，": ",", "、": ",", "；": ";", "：": ":", "　": " "}))
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def confirm_import(
        self,
        preview: OrderImportPreview,
        *,
        file_path: str = "",
        channel: str = "导入",
        customer_name: str | None = None,
        config_plan_name: str | None = None,
        skip_history_duplicates: bool = True,
        source: str = "order_import",
    ) -> OrderImportConfirmResult:
        """Save only parse-success rows through OrderIntakeService.

        Rows are saved independently. Parse-failed rows are skipped; save-failed rows keep
        their error in the returned preview.
        """

        updated_rows: list[OrderImportPreviewRow] = []
        attempted = 0
        imported = 0
        save_failed = 0
        skipped_parse_failed = 0
        skipped_history_duplicate = 0

        for row in preview.rows:
            if not row.success:
                skipped_parse_failed += 1
                updated_rows.append(
                    replace(row, import_status="未导入，解析失败", import_error=row.error or "解析失败")
                )
                continue
            if skip_history_duplicates and row.history_duplicate_warning:
                skipped_history_duplicate += 1
                updated_rows.append(
                    replace(
                        row,
                        import_status="已跳过，疑似历史重复",
                        import_error=row.history_duplicate_warning,
                    )
                )
                continue

            attempted += 1
            try:
                save_result = self._save_row(
                    row,
                    channel=channel,
                    customer_name=customer_name,
                    config_plan_name=config_plan_name,
                    source=source,
                )
            except Exception as exc:
                save_failed += 1
                updated_rows.append(
                    replace(
                        row,
                        import_status="导入失败",
                        import_error=f"保存失败：{exc}",
                    )
                )
                continue
            if save_result.success and save_result.order is not None:
                imported += 1
                updated_rows.append(
                    replace(
                        row,
                        import_status="已导入",
                        import_error="",
                        order_id=save_result.order.id,
                        order_no=save_result.order.order_no,
                    )
                )
            else:
                save_failed += 1
                updated_rows.append(
                    replace(
                        row,
                        import_status="导入失败",
                        import_error=save_result.error or "保存失败",
                    )
                )

        updated_preview = OrderImportPreview(
            rows=updated_rows,
            skipped_count=preview.skipped_count,
            history_duplicate_check_enabled=preview.history_duplicate_check_enabled,
            history_duplicate_error=preview.history_duplicate_error,
        )
        log_id = self._write_import_log(
            file_path=file_path,
            preview=preview,
            imported_count=imported,
            save_failed_count=save_failed,
            skipped_parse_failed_count=skipped_parse_failed,
            context=OrderImportContext(
                customer_name=customer_name,
                channel=channel,
                config_plan_name=config_plan_name,
                history_duplicate_check_enabled=preview.history_duplicate_check_enabled,
                skip_history_duplicates=skip_history_duplicates,
                history_duplicate_count=preview.history_duplicate_count,
                skipped_history_duplicate_count=skipped_history_duplicate,
            ),
        )
        return OrderImportConfirmResult(
            preview=updated_preview,
            attempted_count=attempted,
            imported_count=imported,
            save_failed_count=save_failed,
            skipped_parse_failed_count=skipped_parse_failed,
            skipped_history_duplicate_count=skipped_history_duplicate,
            log_id=log_id,
        )

    def _save_row(
        self,
        row: OrderImportPreviewRow,
        *,
        channel: str,
        customer_name: str | None,
        config_plan_name: str | None,
        source: str,
    ):
        region = row.region if row.region in {"澳门", "香港"} else None
        preview = self._order_intake_service.preview_raw_text(
            row.raw_text,
            customer_name=customer_name,
            config_plan_name=config_plan_name,
            channel=channel,
            region=region,
            source=source,
        )
        return self._order_intake_service.save_preview(preview)

    def _write_import_log(
        self,
        *,
        file_path: str,
        preview: OrderImportPreview,
        imported_count: int,
        save_failed_count: int,
        skipped_parse_failed_count: int,
        context: OrderImportContext | None = None,
    ) -> int | None:
        context = context or OrderImportContext()
        try:
            log = self._log_service.create_log(
                module="order",
                action="order/import",
                description=(
                    "订单导入汇总；"
                    f"file={Path(file_path).name if file_path else '未选择文件'}; "
                    f"declarer={context.display_customer_name}; "
                    f"channel={context.channel}; "
                    f"config_plan={context.display_config_plan_name}; "
                    f"history_duplicate_check={context.history_duplicate_check_enabled}; "
                    f"history_duplicate_count={context.history_duplicate_count}; "
                    f"skipped_history_duplicate={context.skipped_history_duplicate_count}; "
                    f"total_rows={preview.total_count}; "
                    f"parse_success={preview.success_count}; "
                    f"parse_failed={preview.failure_count}; "
                    f"imported={imported_count}; "
                    f"save_failed={save_failed_count}; "
                    f"skipped_empty={preview.skipped_count}; "
                    f"skipped_parse_failed={skipped_parse_failed_count}"
                ),
                operator="system",
                related_type="order_import",
            )
            return log.id
        except Exception:
            return None
