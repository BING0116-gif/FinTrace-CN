"""Deterministic, license-safe demo snapshots for a fresh checkout.

The values in this module are deliberately illustrative. They are generated
locally, never fetched from a provider, and must not be used for investment
research. Real Tushare snapshots stay under the git-ignored ``data/`` tree.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


DEMO_SNAPSHOT_ID = "600519.SH_illustrative_demo_v1"
BLOCKED_DEMO_SNAPSHOT_ID = "600519.SH_illustrative_missing_shares_v1"
DEMO_RESEARCH_AS_OF = "2025-04-30T23:00:00+08:00"

_COMPANIES = (
    ("600519.SH", "贵州茅台（演示数据）", 100.0, 1_000_000_000.0, 80_000_000_000.0, 40_000_000_000.0, 120_000_000_000.0),
    ("000858.SZ", "五粮液（演示数据）", 52.0, 2_000_000_000.0, 72_000_000_000.0, 24_000_000_000.0, 95_000_000_000.0),
    ("000568.SZ", "泸州老窖（演示数据）", 46.0, 1_500_000_000.0, 48_000_000_000.0, 18_000_000_000.0, 70_000_000_000.0),
    ("600809.SH", "山西汾酒（演示数据）", 38.0, 1_200_000_000.0, 36_000_000_000.0, 12_000_000_000.0, 52_000_000_000.0),
    ("002304.SZ", "洋河股份（演示数据）", 31.0, 1_600_000_000.0, 40_000_000_000.0, 10_000_000_000.0, 58_000_000_000.0),
)


def _statement(
    statement_type: str,
    fiscal_period: str,
    period_basis: str,
    published_at: str,
    values: dict[str, float | None],
) -> dict[str, Any]:
    return {
        "statement_type": statement_type,
        "fiscal_period": fiscal_period,
        "period_basis": period_basis,
        "published_at": published_at,
        "available_at": published_at,
        "currency": "CNY",
        "unit": "CNY",
        "values": values,
        "is_restated": False,
    }


def _company_snapshot(
    symbol: str,
    name: str,
    price: float,
    shares: float,
    revenue_2024: float,
    profit_2024: float,
    equity: float,
) -> dict[str, Any]:
    symbol_key = symbol.replace(".", "_")
    revenue_2023 = revenue_2024 / 1.1
    profit_2023 = profit_2024 / 1.12
    revenue_q1_2024 = revenue_2024 * 0.24
    profit_q1_2024 = profit_2024 * 0.24
    revenue_q1_2025 = revenue_2024 * 0.27
    profit_q1_2025 = profit_2024 * 0.28
    bars = []
    for offset, day in enumerate(("2025-04-24", "2025-04-25", "2025-04-28", "2025-04-29", "2025-04-30")):
        close = round(price * (0.98 + offset * 0.005), 2)
        bars.append({
            "trade_date": day,
            "open": round(close * 0.995, 2),
            "high": round(close * 1.012, 2),
            "low": round(close * 0.988, 2),
            "close": close,
            "volume": 100_000.0 + offset * 5_000,
            "amount": close * (100_000.0 + offset * 5_000),
            "adjustment": "RAW",
            "trading_status": "NORMAL",
        })
    return {
        "schema_version": "1.0.0",
        "snapshot_id": f"{symbol}_illustrative_demo_v1",
        "provider": "illustrative_fixture",
        "symbol": symbol,
        "research_as_of": DEMO_RESEARCH_AS_OF,
        "fetched_at": DEMO_RESEARCH_AS_OF,
        "data_quality": "illustrative_demo_not_for_investment",
        "source_metadata": {
            "synthetic_demo": True,
            "source": "deterministic_local_generator",
            "note": "All values are illustrative and do not represent actual company filings or prices.",
        },
        "data": {
            "profile": {
                "name": name,
                "currency": "CNY",
                "industry_standard": "illustrative_fixture",
                "industry_level": "L1",
                "industry_code": "L1_01",
                "industry_name": "食品饮料",
                "entity_type": "operating_company",
            },
            "bars": bars,
            "statements": [
                _statement("income", "2023FY", "2023FY_CUMULATIVE", "2024-03-30T00:00:00+08:00", {"revenue": revenue_2023, "net_profit": profit_2023}),
                _statement("income", "2024Q1", "2024Q1_CUMULATIVE", "2024-04-28T00:00:00+08:00", {"revenue": revenue_q1_2024, "net_profit": profit_q1_2024}),
                _statement("income", "2024FY", "2024FY_CUMULATIVE", "2025-03-29T00:00:00+08:00", {"revenue": revenue_2024, "net_profit": profit_2024}),
                _statement("income", "2025Q1", "2025Q1_CUMULATIVE", "2025-04-28T00:00:00+08:00", {"revenue": revenue_q1_2025, "net_profit": profit_q1_2025}),
                _statement("balance", "2025Q1", "POINT_IN_TIME", "2025-04-28T00:00:00+08:00", {"total_shares": shares, "equity": equity}),
            ],
        },
        "demo_evidence_prefix": f"illustrative_{symbol_key}",
    }


def ensure_demo_snapshots(destination: Path | str) -> list[Path]:
    """Create the deterministic demo bundle without overwriting local data."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    target_payload: dict[str, Any] | None = None
    for company in _COMPANIES:
        payload = _company_snapshot(*company)
        if payload["symbol"] == "600519.SH":
            payload["snapshot_id"] = DEMO_SNAPSHOT_ID
            target_payload = payload
        path = destination / f"{payload['snapshot_id']}.json"
        if not path.exists():
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written.append(path)

    if target_payload is None:  # pragma: no cover - constant bundle invariant
        raise RuntimeError("Illustrative target snapshot is missing.")
    blocked = deepcopy(target_payload)
    blocked["snapshot_id"] = BLOCKED_DEMO_SNAPSHOT_ID
    blocked["data_quality"] = "illustrative_demo_missing_total_shares"
    blocked["data"]["profile"]["name"] = "贵州茅台（缺关键证据演示）"
    for statement in blocked["data"]["statements"]:
        statement.get("values", {}).pop("total_shares", None)
    blocked_path = destination / f"{BLOCKED_DEMO_SNAPSHOT_ID}.json"
    if not blocked_path.exists():
        blocked_path.write_text(json.dumps(blocked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(blocked_path)
    return written
