from __future__ import annotations

import pytest

from src.cn.analysis import analyze_financials, compute_single_quarter_qoq, compute_yoy, run_diagnostics
from src.cn.normalization import NormalizedFact


def fact(metric: str, period: str, value: float, *, basis: str = "FY") -> NormalizedFact:
    return NormalizedFact(
        fact_id=f"norm_{metric}_{period}", symbol="600519.SH", metric=metric, value=value,
        currency="CNY", unit="CNY", fiscal_period=period, period_basis=basis,
        statement_type="income", flow_stock="flow", scope="consolidated",
        source_periods=(period,), source_evidence_ids=(f"e_{metric}_{period}",),
        provider="fixture", published_at=None, available_at=None, validation_status="normalized",
    )


@pytest.mark.parametrize(("previous", "current", "semantic", "pct"), [
    (100, 120, "normal", 0.2),
    (-100, 20, "turnaround", None),
    (100, -20, "to_loss", None),
    (-100, -120, "loss_widening", None),
    (-100, -80, "loss_narrowing", None),
    (0, 20, "not_computable", None),
])
def test_yoy_has_explicit_earnings_state_semantics(previous, current, semantic, pct):
    result = compute_yoy(current, previous, metric="net_profit_parent", period_key="2025FY")
    assert result.comparison_semantic == semantic
    assert result.delta_abs == pytest.approx(current - previous)
    if pct is None:
        assert result.delta_pct is None
    else:
        assert result.delta_pct == pytest.approx(pct)


def test_qoq_contract_is_for_single_quarter_values():
    result = compute_single_quarter_qoq(160, 130, metric="revenue", period_key="2025Q3")
    assert result.comparison == "qoq"
    assert result.delta_pct == pytest.approx(30 / 130)


def test_analysis_computes_core_metrics_and_four_diagnostics():
    rows = []
    values = {
        "revenue": (100, 130), "net_profit_parent": (10, 15),
        "net_profit_deducted": (10, 8), "cfo": (20, 15),
        "receivables": (10, 30), "inventory": (10, 30), "capex": (5, 6),
    }
    for metric, (old, current) in values.items():
        rows.extend([fact(metric, "2024FY", old), fact(metric, "2025FY", current)])
    result = analyze_financials(rows)
    assert not result.data_complete  # ratio/contract inputs are intentionally absent
    assert {signal.signal_id for signal in result.signals} == {
        "earnings_quality_warning", "receivable_risk", "inventory_pressure", "non_recurring_contribution",
    }
    profit = next(item for item in result.metrics if item.metric == "net_profit_parent" and item.period_key == "2025FY")
    assert profit.comparison_semantic == "normal"
    assert profit.delta_pct == pytest.approx(0.5)
    assert all(item.calculation_id.startswith("calc_") for item in result.metrics)
    assert all("因为" not in signal.detail and "导致" not in signal.detail for signal in result.signals)


def test_analysis_does_not_create_signal_when_required_data_is_missing():
    rows = [fact("revenue", "2024FY", 100), fact("revenue", "2025FY", 120),
            fact("net_profit_parent", "2024FY", 10), fact("net_profit_parent", "2025FY", 15)]
    result = analyze_financials(rows)
    assert result.signals == ()
    assert result.missing


def test_run_diagnostics_reuses_metric_semantics():
    metrics = [
        compute_yoy(120, 100, metric="revenue", period_key="2025FY"),
        compute_yoy(15, 10, metric="net_profit_parent", period_key="2025FY"),
        compute_yoy(15, 20, metric="cfo", period_key="2025FY"),
    ]
    signals = run_diagnostics(metrics)
    assert [signal.signal_id for signal in signals] == ["earnings_quality_warning"]
