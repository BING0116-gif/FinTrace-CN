#!/usr/bin/env python3
"""Run the explicitly approved, no-retry CN-0 Tushare provider probe.

Budget: exactly six endpoint calls for 600519.SH.  The script stops immediately
after the first failed call and saves only local diagnostic artifacts.  It never
prints the token.
"""

from __future__ import annotations

import json
import os
import argparse
from datetime import datetime
from pathlib import Path
from time import perf_counter

import tushare as ts
from dotenv import load_dotenv


DEFAULT_SYMBOL = "600519.SH"
DEFAULT_START_DATE = "20260701"
DEFAULT_END_DATE = "20260810"
PROBE_ROOT = Path(__file__).resolve().parents[1] / "data" / "provider_probes" / "cn0"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture one auditable, raw Tushare A-share probe (six calls; no retries)."
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Canonical Tushare symbol, e.g. 000858.SZ")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="YYYYMMDD")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="YYYYMMDD")
    args = parser.parse_args()
    symbol = args.symbol.strip().upper()
    if len(args.start_date) != 8 or not args.start_date.isdigit() or len(args.end_date) != 8 or not args.end_date.isdigit():
        raise SystemExit("--start-date and --end-date must use YYYYMMDD.")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise SystemExit("TUSHARE_TOKEN is not configured in .env")

    output_dir = PROBE_ROOT / f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "provider": "tushare",
        "symbol": symbol,
        "budgeted_calls": 6,
        "retry_policy": "no_retry_stop_on_first_failure",
        "calls": [],
    }
    client = ts.pro_api(token)
    calls = [
        (
            "stock_basic",
            lambda: client.stock_basic(
                ts_code=symbol,
                fields="ts_code,symbol,name,area,industry,market,list_date",
            ),
        ),
        ("daily", lambda: client.daily(ts_code=symbol, start_date=args.start_date, end_date=args.end_date)),
        ("income", lambda: client.income(ts_code=symbol)),
        ("balancesheet", lambda: client.balancesheet(ts_code=symbol)),
        ("cashflow", lambda: client.cashflow(ts_code=symbol)),
        ("fina_indicator", lambda: client.fina_indicator(ts_code=symbol)),
    ]

    for endpoint, request in calls:
        started = perf_counter()
        record = {"endpoint": endpoint, "attempts": 1}
        try:
            frame = request()
            elapsed_ms = round((perf_counter() - started) * 1000, 1)
            frame.to_csv(output_dir / f"raw_{endpoint}.csv", index=False, encoding="utf-8-sig")
            record.update(
                {
                    "status": "ok",
                    "elapsed_ms": elapsed_ms,
                    "rows": int(len(frame)),
                    "columns": list(frame.columns),
                }
            )
        except Exception as exc:
            record.update(
                {
                    "status": "failed",
                    "elapsed_ms": round((perf_counter() - started) * 1000, 1),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            summary["calls"].append(record)
            summary["stopped_early"] = True
            (output_dir / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"STOPPED after {endpoint}: {record['error_type']}; artifacts: {output_dir}")
            return 1
        summary["calls"].append(record)

    summary["stopped_early"] = False
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Completed {len(calls)} calls; artifacts: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
