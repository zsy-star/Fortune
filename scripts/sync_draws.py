from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapers.wz49_parser import LOTTERY_TYPE_REGION
from services.draw_sync_service import DrawSyncService

REGION_LOTTERY_TYPE = {region: lottery_type for lottery_type, region in LOTTERY_TYPE_REGION.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync lottery draws from 49wz777.")
    parser.add_argument("--latest", action="store_true", help="Sync latest draw only. Default behavior.")
    parser.add_argument("--pages", type=int, help="Sync a limited number of history pages.")
    parser.add_argument("--region", choices=sorted(REGION_LOTTERY_TYPE), default="澳门")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--page-size", type=int, default=25)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.pages is not None and args.pages <= 0:
        print("--pages must be greater than 0", file=sys.stderr)
        return 2
    if args.page_size <= 0 or args.page_size > 50:
        print("--page-size must be between 1 and 50", file=sys.stderr)
        return 2

    lottery_type = REGION_LOTTERY_TYPE[args.region]
    service = DrawSyncService()
    try:
        if args.pages is not None:
            print(f"Syncing {args.region} {args.year}, pages={args.pages}, page_size={args.page_size}")
            result = service.sync_history_pages(
                lottery_type=lottery_type,
                year=args.year,
                pages=args.pages,
                page_size=args.page_size,
            )
        else:
            print(f"Syncing latest {args.region} {args.year}")
            result = service.sync_latest(lottery_type=lottery_type, year=args.year)
    finally:
        service.close()

    print(
        "created={created} updated={updated} skipped={skipped} failed={failed}".format(
            created=result.created,
            updated=result.updated,
            skipped=result.skipped,
            failed=result.failed,
        )
    )
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
