"""订单导入预览数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ImportSourceResult:
    """从文件中提取出的待解析订单文本。"""

    lines: list[str]
    skipped_count: int = 0
    error: str = ""


@dataclass(frozen=True, slots=True)
class OrderImportContext:
    """确认导入时随订单一起传递的业务归属信息。"""

    customer_name: str | None = None
    channel: str = "导入"
    config_plan_name: str | None = None
    history_duplicate_check_enabled: bool = False
    skip_history_duplicates: bool = True
    history_duplicate_count: int = 0
    skipped_history_duplicate_count: int = 0

    @property
    def display_customer_name(self) -> str:
        return self.customer_name or "未设置申报人"

    @property
    def display_config_plan_name(self) -> str:
        return self.config_plan_name or "未绑定配置方案"


@dataclass(frozen=True, slots=True)
class OrderImportPreviewRow:
    """导入预览中的单行结果。"""

    line_number: int
    raw_text: str
    region: str
    success: bool
    bet_type_summary: str = ""
    amount_total: float = 0.0
    item_count: int = 0
    selection_summary: str = ""
    error: str = ""
    duplicate_warning: str = ""
    history_duplicate_warning: str = ""
    history_duplicate_order_id: int | None = None
    history_duplicate_order_no: str | None = None
    import_status: str = "未导入"
    import_error: str = ""
    order_id: int | None = None
    order_no: str | None = None


@dataclass(frozen=True, slots=True)
class OrderImportPreview:
    """订单导入预览结果；第一阶段只读，不保存订单。"""

    rows: list[OrderImportPreviewRow] = field(default_factory=list)
    skipped_count: int = 0
    history_duplicate_check_enabled: bool = False
    history_duplicate_error: str = ""

    @property
    def total_count(self) -> int:
        return len(self.rows)

    @property
    def success_count(self) -> int:
        return sum(1 for row in self.rows if row.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for row in self.rows if not row.success)

    @property
    def history_duplicate_count(self) -> int:
        return sum(1 for row in self.rows if row.history_duplicate_warning)


@dataclass(frozen=True, slots=True)
class OrderImportConfirmResult:
    """确认导入后的逐行保存结果。"""

    preview: OrderImportPreview
    attempted_count: int
    imported_count: int
    save_failed_count: int
    skipped_parse_failed_count: int
    skipped_history_duplicate_count: int = 0
    log_id: int | None = None
