#!/usr/bin/env python3
"""Run the explicitly approved, no-retry CN-0 Tushare provider probe.

Budget: exactly six endpoint calls for 600519.SH.  The script stops immediately
after the first failed call and saves only local diagnostic artifacts.  It never
prints the token.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from time import perf_counter

import tushare as ts
from dotenv import load_dotenv


SYMBOL = "600519.SH"
START_DATE = "20260701"
END_DATE = "20260810"
PROBE_ROOT = Path(__file__).resolve().parents[1] / "data" / "provider_probes" / "cn0"


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise SystemExit("TUSHARE_TOKEN is not configured in .env")

    output_dir = PROBE_ROOT / f"{SYMBOL}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "provider": "tushare",
        "symbol": SYMBOL,
        "budgeted_calls": 6,
        "retry_policy": "no_retry_stop_on_first_failure",
        "calls": [],
    }
    client = ts.pro_api(token)
    calls = [
        (
            "stock_basic",
            lambda: client.stock_basic(
                ts_code=SYMBOL,
                fields="ts_code,symbol,name,area,industry,market,list_date",
            ),
        ),
        ("daily", lambda: client.daily(ts_code=SYMBOL, start_date=START_DATE, end_date=END_DATE)),
        ("income", lambda: client.income(ts_code=SYMBOL)),
        ("balancesheet", lambda: client.balancesheet(ts_code=SYMBOL)),
        ("cashflow", lambda: client.cashflow(ts_code=SYMBOL)),
        ("fina_indicator", lambda: client.fina_indicator(ts_code=SYMBOL)),
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
