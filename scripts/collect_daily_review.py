"""CLI to build a FinTrace-CN market review snapshot.

Default behaviour (offline-first, but realtime when configured): without
``--live`` / ``--offline`` the script auto-discovers a Tushare token from the
``TUSHARE_TOKEN`` env var or the project-root ``.env``.  If a token is present it
*attempts* a real pull (best-effort, falls back to the clearly flagged
``synthetic_demo`` snapshot on any failure); if no token is configured it writes
the offline demo so the daily review module is always demoable without network or
API budget.

Examples
--------
    # auto: realtime if TUSHARE_TOKEN is set, otherwise offline demo
    .venv\\Scripts\\python.exe scripts\\collect_daily_review.py --review-date 20260814
    # force realtime (errors out if no token)
    .venv\\Scripts\\python.exe scripts\\collect_daily_review.py --live --review-date 20260814
    # force offline demo regardless of token
    .venv\\Scripts\\python.exe scripts\\collect_daily_review.py --offline --review-date 20260814
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cn.daily_review.collector import (
    collect_daily_review,
    load_tushare_token,
    write_market_snapshot,
)

DEFAULT_DIR = PROJECT_ROOT / "data" / "snapshots" / "market"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a FinTrace-CN market review snapshot.")
    parser.add_argument("--review-date", default="20260814", help="YYYYMMDD review date.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR, help="Where to write the snapshot.")
    parser.add_argument("--live", action="store_true", help="Force a real Tushare pull (errors if no token).")
    parser.add_argument("--offline", action="store_true", help="Force the offline synthetic_demo snapshot.")
    parser.add_argument("--token", default=None, help="Tushare token (overrides env / .env).")
    parser.add_argument("--force-refresh", action="store_true", help="Ignore local cache and re-pull.")
    parser.add_argument("--no-cache", action="store_true", help="Do not persist the pulled payload to cache.")
    args = parser.parse_args()

    token = args.token or load_tushare_token()
    if args.offline:
        live = False
    elif args.live:
        if not token:
            print("ERROR: --live 需要 TUSHARE_TOKEN（在 .env 或 --token 提供）。", file=sys.stderr)
            raise SystemExit(2)
        live = True
    else:
        # Default = auto: try realtime when a token exists, else offline demo.
        live = bool(token)

    payload = collect_daily_review(
        args.review_date,
        token=token,
        live=live,
        force_refresh=args.force_refresh,
        use_cache=not args.no_cache,
    )
    path = write_market_snapshot(payload, args.output_dir)
    cached = payload.get("source_metadata", {}).get("cached")
    print(
        f"Wrote {path}\n"
        f"  provider={payload['provider']}  synthetic_demo={payload['source_metadata'].get('synthetic_demo')}"
        f"{'  (from cache)' if cached else ''}\n"
        f"  indices={len(payload['data']['indices'])} sectors={len(payload['data']['sectors'])} "
        f"limit_up={len(payload['data']['limit_up'])} flow={len(payload['data']['money_flow'])} "
        f"hotspots={len(payload['data']['hotspots'])}"
    )


if __name__ == "__main__":
    main()
