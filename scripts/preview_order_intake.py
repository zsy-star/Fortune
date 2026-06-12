"""Preview order intake conversion from the command line without saving."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.order_intake_service import OrderIntakeService


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预览订单解析适配结果，不写入数据库。")
    parser.add_argument("--text", help="原始订单文本")
    parser.add_argument("--file", type=Path, help="从文件读取原始文本")
    parser.add_argument("--region", help="订单地区：澳门 或 香港")
    parser.add_argument("--customer", help="客户名称")
    parser.add_argument("--channel", help="渠道")
    parser.add_argument("--source", default="record_window", help="订单来源标识")
    args = parser.parse_args()
    if not args.text and not args.file:
        parser.error("必须提供 --text 或 --file")
    if args.text and args.file:
        parser.error("不能同时提供 --text 和 --file")
    return args


def _load_text(args: argparse.Namespace) -> str:
    if args.file:
        return args.file.read_text(encoding="utf-8")
    return args.text or ""


def main() -> int:
    _configure_console()
    args = parse_args()
    raw_text = _load_text(args)

    try:
        preview = OrderIntakeService().preview_raw_text(
            raw_text,
            customer_name=args.customer,
            channel=args.channel,
            region=args.region,
            source=args.source,
        )
    except Exception as exc:
        print(f"预览失败：{exc}")
        return 1

    print(f"地区：{preview.region or '—'}")
    print(f"客户：{preview.customer_name or '—'}")
    print(f"渠道：{preview.channel or '—'}")
    print(f"来源：{preview.source}")
    print(f"总金额：{preview.total_amount:.2f}")
    print(f"可保存：{'是' if preview.can_save else '否'}")
    print(f"有效明细：{preview.valid_items}    无效明细：{preview.invalid_items}")

    if preview.warnings:
        print("\n警告：")
        for warning in preview.warnings:
            print(f"  - {warning}")

    if preview.errors:
        print("\n错误：")
        for error in preview.errors:
            print(f"  - {error}")

    print("\n明细：")
    for index, item in enumerate(preview.items, start=1):
        status = "有效" if item.is_valid else "无效"
        norm_type = item.normalized_bet_type or "—"
        norm_sel = item.normalized_selection or "—"
        amount = f"{item.amount:.2f}" if item.amount is not None else "—"
        print(
            f"{index}. [{status}] 原始类型={item.original_bet_type} "
            f"标准类型={norm_type} 原始内容={item.original_selection} "
            f"标准内容={norm_sel} 金额={amount} 保存类型={item.order_bet_type or '—'}"
        )
        if item.warning:
            print(f"     警告：{item.warning}")
        if item.error:
            print(f"     错误：{item.error}")

    return 0 if preview.can_save or not preview.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
