#!/usr/bin/env python3
"""Build a normalized offline A-share snapshot from an existing Tushare probe.

This script is intentionally offline: it reads the raw CSV artifacts produced by
``probe_tushare_cn0.py`` and makes no provider calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd

# Direct script execution places ``scripts/`` rather than the project root on
# sys.path.  Add the root before importing the shared canonical classifier.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.cn.industries import is_financial_institution


VALUE_MAPS: Dict[str, Dict[str, str]] = {
    "income": {"revenue": "revenue", "net_profit": "n_income_attr_p", "ebit": "ebit", "ebitda": "ebitda"},
    "balance": {"total_assets": "total_assets", "total_liabilities": "total_liab", "equity": "total_hldr_eqy_exc_min_int", "total_shares": "total_share"},
    "cashflow": {"operating_cash_flow": "n_cashflow_act", "free_cash_flow": "free_cashflow"},
}


# Period kinds Tushare exposes for the consolidated primary report.  Anything
# outside this set is treated as unverifiable and dropped (never renamed to a
# ``UNKNOWN`` placeholder) so the snapshot never carries fiscal periods the
# deterministic period engine cannot parse.
_VALID_END_TYPES = {"1", "2", "3", "4"}


def _number(value):
    return None if pd.isna(value) else float(value)


def _iso_date(value) -> str | None:
    raw = str(value).strip()
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}T00:00:00+08:00" if len(raw) == 8 and raw.isdigit() else None


def _period(end_date: str, end_type: str, statement_type: str) -> tuple[str, str] | None:
    """Return ``(fiscal_period, period_basis)`` for one Tushare row.

    Returns ``None`` when ``end_type`` is missing or outside the four valid
    quarter codes — a placeholder name like ``"2026UNKNOWN"`` would leak into
    the snapshot and later crash ``FinancialPeriodEngine._parse_period``.  We
    prefer to drop the row entirely: an untyped period is unverifiable data.
    """
    if str(end_type) not in _VALID_END_TYPES:
        return None
    period_name = {"1": "Q1", "2": "H1", "3": "9M", "4": "FY"}[str(end_type)]
    year = str(end_date)[:4]
    if not (len(year) == 4 and year.isdigit()):
        return None
    return f"{year}{period_name}", f"{year}{period_name}{'_END' if statement_type == 'balance' else '_CUMULATIVE'}"


def _statements(probe_dir: Path, statement_type: str, filename: str):
    frame = pd.read_csv(probe_dir / filename, dtype={"ann_date": "string", "f_ann_date": "string", "end_date": "string", "end_type": "string", "report_type": "string", "comp_type": "string", "update_flag": "string"})
    # Tushare uses comp_type 1/2/3/4 for general companies, banks, brokers,
    # and insurers.  They are valid issuer categories; report_type=1 is the
    # consolidated-statement discriminator.  CSV round-trips may yield 1.0.
    report_type = frame["report_type"].str.replace(".0", "", regex=False)
    comp_type = frame["comp_type"].str.replace(".0", "", regex=False)
    frame = frame[(report_type == "1") & comp_type.isin({"1", "2", "3", "4"})].copy()
    frame["effective_date"] = frame["f_ann_date"].fillna(frame["ann_date"])
    frame = frame.sort_values(["end_date", "effective_date"], ascending=[False, False]).drop_duplicates("end_date")
    records = []
    for _, row in frame.iterrows():
        result = _period(str(row["end_date"]), str(row["end_type"]), statement_type)
        if result is None:
            # Skip rows whose end_type the provider omitted (recent IPOs and
            # other filings occasionally arrive without a quarter code).
            continue
        fiscal_period, period_basis = result
        records.append({
            "statement_type": statement_type,
            "fiscal_period": fiscal_period,
            "period_basis": period_basis,
            "published_at": _iso_date(row["ann_date"]),
            "available_at": _iso_date(row["f_ann_date"]) or _iso_date(row["ann_date"]),
            "currency": "CNY",
            "unit": "CNY",
            "values": {target: _number(row.get(source)) for target, source in VALUE_MAPS[statement_type].items()},
            "is_restated": str(row.get("update_flag", "")) == "1",
        })
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--research-as-of", default="2026-08-10T23:00:00+08:00")
    parser.add_argument("--snapshot-id", default=None, help="Optional immutable snapshot ID.")
    args = parser.parse_args()

    profile_row = pd.read_csv(args.probe_dir / "raw_stock_basic.csv").iloc[0]
    symbol = str(profile_row["ts_code"]).strip().upper()
    if not symbol or symbol == "NAN":
        raise SystemExit("raw_stock_basic.csv does not contain a valid ts_code.")
    date_tag = args.research_as_of[:10].replace("-", "")
    snapshot_id = args.snapshot_id or f"{symbol}_{date_tag}_tushare_v1"
    daily = pd.read_csv(args.probe_dir / "raw_daily.csv", dtype={"trade_date": "string"})
    bars = [
        {
            "trade_date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
            "open": _number(row.open), "high": _number(row.high), "low": _number(row.low), "close": _number(row.close),
            "volume": _number(row.vol), "amount": _number(row.amount), "adjustment": "RAW", "trading_status": None,
        }
        for row in daily.itertuples(index=False)
        for date in [str(row.trade_date)]
    ]
    statements = (
        _statements(args.probe_dir, "income", "raw_income.csv")
        + _statements(args.probe_dir, "balance", "raw_balancesheet.csv")
        + _statements(args.probe_dir, "cashflow", "raw_cashflow.csv")
    )
    payload = {
        "schema_version": "1.0.0",
        "snapshot_id": snapshot_id,
        "provider": "tushare",
        "symbol": symbol,
        "research_as_of": args.research_as_of,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_quality": "provider_normalized_from_cn0_probe",
        "source_metadata": {"raw_probe_dir": args.probe_dir.name, "normalization_version": "cn-fields-1.0.0"},
        "data": {
            "profile": {
            "name": str(profile_row["name"]), "currency": "CNY", "industry_standard": "tushare_stock_basic",
            "industry_level": "industry", "industry_name": str(profile_row["industry"]),
            # This is a deterministic canonical-symbol classification, not an
            # LLM inference.  It makes the financial-valuation boundary travel
            # with a provider-normalized snapshot and into every report export.
            "entity_type": "financial_institution" if is_financial_institution(symbol[:6]) else "operating_company",
            },
            "bars": bars,
            "statements": statements,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output} with {len(bars)} RAW bars and {len(statements)} statements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
