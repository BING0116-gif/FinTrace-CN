"""Regression coverage for ``build_cn_snapshot_from_probe.py``.

The most damaging failure mode for the snapshot builder is silently naming
fiscal periods with placeholder strings (historically ``"YYYYUNKNOWN"``).
Those rows survive into the JSON, then blow up every report that calls
``FinancialPeriodEngine.derive_ttm``.  The 688836 (Unitree) IPO probe in
August 2026 produced several rows where Tushare omitted ``end_type``; this
suite ensures the builder drops them rather than renames them.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_cn_snapshot_from_probe import (  # noqa: E402  (sys.path insertion)
    _period,
    _statements,
    _VALID_END_TYPES,
)


def test_period_returns_none_for_missing_end_type():
    """Rows whose end_type is missing must be dropped, not renamed."""
    assert _period("20260331", "", "income") is None
    assert _period("20250930", "", "income") is None
    assert _period("20260630", "n/a", "income") is None
    assert _period("20260630", "5", "income") is None


def test_period_emits_canonical_tag_for_each_valid_end_type():
    for end_type, expected in (("1", "Q1"), ("2", "H1"), ("3", "9M"), ("4", "FY")):
        fiscal, basis = _period("20240630", end_type, "income")
        assert fiscal == "2024" + expected
        assert basis == f"2024{expected}_CUMULATIVE"


def test_period_marks_balance_basis_as_stock_snapshot():
    fiscal, basis = _period("20241231", "4", "balance")
    assert fiscal == "2024FY"
    assert basis == "2024FY_END"


def test_period_valid_end_types_match_tushare_doc():
    assert _VALID_END_TYPES == {"1", "2", "3", "4"}


def test_statements_skips_rows_with_missing_end_type(tmp_path):
    """The full pipeline must drop rows lacking end_type — never write ``UNKNOWN``."""
    headers = [
        "end_date", "end_type", "report_type", "comp_type",
        "ann_date", "f_ann_date", "update_flag",
        "revenue", "n_income_attr_p", "ebit", "ebitda",
    ]
    probe_dir = tmp_path
    rows = [
        # Valid rows that must survive.
        ["20260630", "2", "1", "1", "20260818", "20260818", "1",
         "1000", "200", None, None],
        ["20241231", "4", "1", "1", "20250320", "20250320", "1",
         "4000", "800", None, None],
        # Rows with empty end_type (recent IPOs) must be dropped.
        ["20260331", "", "1", "1", "20260525", "20260731", "1",
         "500", "50", None, None],
        ["20250930", "", "1", "1", "20260320", "20260320", "1",
         "3000", "400", None, None],
        # Row with bogus end_type must be dropped.
        ["20250630", "9", "1", "1", "20260818", "20260818", "1",
         "2000", "300", None, None],
    ]
    with (probe_dir / "raw_income.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)

    records = _statements(probe_dir, "income", "raw_income.csv")

    fiscal_periods = [record["fiscal_period"] for record in records]
    assert fiscal_periods == ["2026H1", "2024FY"]
    assert not any("UNKNOWN" in period for period in fiscal_periods), (
        "snapshot must never carry UNKNOWN fiscal periods; they crash FinancialPeriodEngine"
    )


def test_statements_dedupes_repeated_end_dates_and_keeps_latest(tmp_path):
    """Multiple announces for one end_date (restatements) → keep the latest update."""
    headers = [
        "end_date", "end_type", "report_type", "comp_type",
        "ann_date", "f_ann_date", "update_flag",
        "revenue", "n_income_attr_p",
    ]
    rows = [
        # Original 2025 FY then updated same day — both update_flag=1, later f_ann_date wins.
        ["20251231", "4", "1", "1", "20260320", "20260731", "1", "3000", "600"],
        ["20251231", "4", "1", "1", "20260320", "20260818", "1", "3000", "600"],
    ]
    with (tmp_path / "raw_income.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)

    records = _statements(tmp_path, "income", "raw_income.csv")
    assert len(records) == 1
    assert records[0]["available_at"] == "2026-08-18T00:00:00+08:00"
