"""Preview order settlement from the command line without writing data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.settlement_service import SettlementService
from settlement.exceptions import SettlementError


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预览订单中奖判定结果，不修改数据库。")
    parser.add_argument("--order-id", type=int, required=True, help="订单ID")
    parser.add_argument("--draw-id", type=int, help="开奖ID")
    parser.add_argument("--region", help="开奖地区，例如 澳门")
    parser.add_argument("--issue", help="开奖期号")
    args = parser.parse_args()
    if args.draw_id is None and not (args.region and args.issue):
        parser.error("必须提供 --draw-id，或同时提供 --region 和 --issue")
    return args


def main() -> int:
    _configure_console()
    args = parse_args()
    service = SettlementService()
    try:
        if args.draw_id is not None:
            preview = service.preview_order(args.order_id, args.draw_id)
        else:
            preview = service.preview_order_by_issue(args.order_id, args.region, args.issue)
    except SettlementError as exc:
        print(f"结算预览失败：{exc}", file=sys.stderr)
        return 1

    print(f"订单：{preview.order_no}  地区：{preview.region}")
    print(f"开奖：{preview.issue_number}  日期：{preview.draw_date}")
    print(f"普通号：{' '.join(preview.regular_numbers)}  特码：{preview.special_number}")
    print()
    for result in preview.results:
        winner = "不支持" if not result.is_supported else ("中奖" if result.is_winner else "未中奖")
        print(
            f"明细#{result.order_item_id or '-'} "
            f"{result.bet_type} {result.selection} "
            f"金额 {result.amount}：{winner}；{result.reason}"
        )
    print()
    print(
        "汇总："
        f"总明细 {preview.total_items}，"
        f"支持 {preview.supported_items}，"
        f"不支持 {preview.unsupported_items}，"
        f"中奖 {preview.winning_items}，"
        f"未中奖 {preview.losing_items}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
