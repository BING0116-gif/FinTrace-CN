"""Regression tests for the snapshot consumer-side guards against
fiscal-period placeholders leaking into research outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cn import workbench_service as service  # noqa: E402
from src.cn.periods import supports_period_engine  # noqa: E402


def _payload(statements):
    """Construct a minimal snapshot payload mimicking the on-disk shape."""
    return {
        "snapshot_id": "TEST.UNKNOWN",
        "symbol": "688836.SH",
        "research_as_of": "2026-08-22T23:00:00+08:00",
        "provider": "tushare",
        "data": {
            "profile": {"name": "Unitree", "currency": "CNY", "industry_name": "Robotics"},
            "bars": [
                {"trade_date": "2026-08-21", "close": 672.41, "adjustment": "RAW",
                 "open": 659.0, "high": 706.98, "low": 636.0, "volume": 7605734, "amount": 5138830000.0}
            ],
            "statements": statements,
        },
    }


@pytest.mark.parametrize("placeholder", ["2026UNKNOWN", "2025UNKNOWN", "", "abc", "2026Q5", None])
def test_supports_period_engine_rejects_placeholders(placeholder):
    assert supports_period_engine(placeholder) is False


@pytest.mark.parametrize("valid", ["2026H1", "2026FY", "2026Q1", "20269M", "2022FY"])
def test_supports_period_engine_accepts_canonical_tags(valid):
    assert supports_period_engine(valid) is True


def test_research_summary_tolerates_unparseable_fiscal_period_rows(tmp_path, monkeypatch):
    """A snapshot whose statements include ``YYYYUNKNOWN`` placeholders must not
    crash ``research_summary`` — the legacy ``UNKNOWN`` rows from the 688836
    IPO probe are still on disk in the user's tree, so the consumer must
    degrade rather than surface ``PeriodEngineError``.
    """
    # Stage the synthetic payload as a discoverable snapshot file so the
    # real ``_ledger_validation`` path resolves it.
    from src.cn import workbench_service as svc
    statements = [
        {"statement_type": "income", "fiscal_period": "2026UNKNOWN",
         "period_basis": "2026UNKNOWN_CUMULATIVE", "published_at": None, "available_at": None,
         "currency": "CNY", "unit": "CNY", "values": {"revenue": 1000, "net_profit": 100}},
        {"statement_type": "income", "fiscal_period": "2025UNKNOWN",
         "period_basis": "2025UNKNOWN_CUMULATIVE", "published_at": None, "available_at": None,
         "currency": "CNY", "unit": "CNY", "values": {"revenue": 1000, "net_profit": 100}},
        # ``derive_ttm`` only emits a TTM for FY inputs in isolation; H1 alone
        # produces nothing.  Pair one FY with an H1 to assert the engine picks
        # the supported rows and ignores the placeholders.
        {"statement_type": "income", "fiscal_period": "2024FY",
         "period_basis": "2024FY_CUMULATIVE", "published_at": "2025-03-20T00:00:00+08:00",
         "available_at": "2025-03-20T00:00:00+08:00",
         "currency": "CNY", "unit": "CNY",
         "values": {"revenue": 1000.0, "net_profit": 100.0}},
        {"statement_type": "income", "fiscal_period": "2026H1",
         "period_basis": "2026H1_CUMULATIVE", "published_at": "2026-08-18T00:00:00+08:00",
         "available_at": "2026-08-18T00:00:00+08:00",
         "currency": "CNY", "unit": "CNY",
         "values": {"revenue": 1152245550.58, "net_profit": 273999911.92}},
        {"statement_type": "balance", "fiscal_period": "2026H1",
         "period_basis": "2026H1_END", "published_at": "2026-08-18T00:00:00+08:00",
         "available_at": "2026-08-18T00:00:00+08:00", "currency": "CNY", "unit": "CNY",
         "values": {"total_assets": 5e9, "total_liab": 2e9, "equity": 3e9, "total_share": 364017906.0}},
    ]
    payload = {
        "schema_version": "1.0.0",
        "snapshot_id": "TEST.UNKNOWN",
        "provider": "tushare",
        "symbol": "688836.SH",
        "research_as_of": "2026-08-22T23:00:00+08:00",
        "data": {
            "profile": {"name": "Unitree", "currency": "CNY", "industry_name": "Robotics",
                        "industry_level": "industry", "industry_standard": "tushare_stock_basic",
                        "entity_type": "operating_company"},
            "bars": [
                {"trade_date": "2026-08-21", "close": 672.41, "adjustment": "RAW",
                 "open": 659.0, "high": 706.98, "low": 636.0, "volume": 7605734, "amount": 5138830000.0}
            ],
            "statements": statements,
        },
    }
    snapshot_path = tmp_path / "TEST.UNKNOWN.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(svc, "SNAPSHOT_DIR", tmp_path)

    summary = service.research_summary("TEST.UNKNOWN")

    assert summary["validation"]["valid"] is True
    # TTM is computed from the 2024FY row (the only FY in the supported set);
    # the placeholder rows are dropped before reaching the period engine.
    assert summary["key_metrics"]["ttm_revenue"] == pytest.approx(1000.0)
    assert summary["key_metrics"]["ttm_net_profit"] == pytest.approx(100.0)


def test_research_financials_drops_unsupported_period_rows(monkeypatch):
    snapshot_path = Path("data/snapshots/cn/688836.SH_20260822_tushare_v1.json")
    if not snapshot_path.exists():
        pytest.skip("688836 snapshot not present in this workspace")

    financials = service.research_financials("688836.SH_20260822_tushare_v1")

    fiscal_periods = {row["fiscal_period"] for row in financials["statements"]}
    assert fiscal_periods, "688836 should retain at least one fiscal period after filtering"
    for period in fiscal_periods:
        assert supports_period_engine(period), f"financials leaked unsupported period: {period!r}"


def test_real_688836_snapshot_contains_no_unknown_periods():
    """Direct guard for the on-disk snapshot rebuilt by the new producer."""
    snapshot_path = Path("data/snapshots/cn/688836.SH_20260822_tushare_v1.json")
    if not snapshot_path.exists():
        pytest.skip("688836 snapshot not present in this workspace")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    statements = payload["data"]["statements"]
    assert statements, "rebuilt snapshot must still carry at least one statement"
    for stmt in statements:
        assert supports_period_engine(stmt["fiscal_period"]), (
            f"rebuilt snapshot leaked unsupported fiscal period: {stmt['fiscal_period']!r}"
        )
