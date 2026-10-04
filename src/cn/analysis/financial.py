"""Financial analysis with explicit period and earnings-state semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional

from ..normalization import NormalizedFact


SIGNIFICANT_GROWTH_GAP = 0.10  # ten percentage points; kept explicit for review


@dataclass(frozen=True)
class MetricResult:
    metric: str
    value: Optional[float]
    unit: str
    period_key: str
    comparison: Optional[str]
    comparison_semantic: Optional[str]
    delta_abs: Optional[float]
    delta_pct: Optional[float]
    calculation_id: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DiagnosticSignal:
    signal_id: str
    periods: tuple[str, ...]
    detail: str
    metric_calculation_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["periods"] = list(self.periods)
        payload["metric_calculation_ids"] = list(self.metric_calculation_ids)
        return payload


@dataclass(frozen=True)
class AnalysisResult:
    metrics: tuple[MetricResult, ...]
    signals: tuple[DiagnosticSignal, ...]
    data_complete: bool
    missing: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "metrics": [metric.to_dict() for metric in self.metrics],
            "signals": [signal.to_dict() for signal in self.signals],
            "data_complete": self.data_complete,
            "missing": list(self.missing),
        }


def _comparison_semantic(current: float, previous: float) -> tuple[str, Optional[float], Optional[float]]:
    delta = current - previous
    if previous == 0:
        return "not_computable", delta, None
    if previous < 0 < current:
        return "turnaround", delta, None
    if previous > 0 > current:
        return "to_loss", delta, None
    if previous < 0 and current < 0:
        return ("loss_widening" if current < previous else "loss_narrowing"), delta, None
    return "normal", delta, delta / abs(previous)


def _metric_result(metric: str, current: float, previous: Optional[float], *, unit: str,
                   period_key: str, comparison: Optional[str], calculation_id: str) -> MetricResult:
    if previous is None or comparison is None:
        return MetricResult(metric, current, unit, period_key, comparison, "not_computable", None, None, calculation_id)
    semantic, delta_abs, delta_pct = _comparison_semantic(current, previous)
    return MetricResult(metric, current, unit, period_key, comparison, semantic, delta_abs, delta_pct, calculation_id)


def compute_yoy(current: float, previous: float, *, metric: str = "metric", period_key: str = "unknown",
                unit: str = "CNY", calculation_id: Optional[str] = None) -> MetricResult:
    """Compute YoY with five earnings-state branches and no false percentages."""
    return _metric_result(metric, float(current), float(previous), unit=unit, period_key=period_key,
                          comparison="yoy", calculation_id=calculation_id or f"calc_yoy_{metric}_{period_key}")


def compute_qoq(current_q: float, previous_q: float, *, metric: str = "metric", period_key: str = "unknown",
                unit: str = "CNY", calculation_id: Optional[str] = None) -> MetricResult:
    """Compare already single-quarter values; callers must not pass YTD rows."""
    return _metric_result(metric, float(current_q), float(previous_q), unit=unit, period_key=period_key,
                          comparison="qoq", calculation_id=calculation_id or f"calc_qoq_{metric}_{period_key}")


def compute_single_quarter_qoq(current_q: float, previous_q: float, **kwargs: object) -> MetricResult:
    """Named contract alias emphasizing that inputs must already be quarterized."""
    return compute_qoq(current_q, previous_q, **kwargs)  # type: ignore[arg-type]


def run_diagnostics(metrics: Iterable[MetricResult]) -> list[DiagnosticSignal]:
    """Derive conservative signals from already computed comparison metrics."""
    rows = list(metrics)
    by_key = {(row.metric, row.period_key): row for row in rows}
    signals: list[DiagnosticSignal] = []
    for period in sorted({row.period_key for row in rows}):
        profit = by_key.get(("net_profit_parent", period))
        cfo = by_key.get(("cfo", period))
        if profit and cfo and profit.delta_pct is not None and cfo.delta_pct is not None and profit.delta_pct > 0 and cfo.delta_pct < 0:
            signals.append(DiagnosticSignal("earnings_quality_warning", (period,), "净利润同比上升且经营现金流同比下降，提示盈利质量背离。", (profit.calculation_id, cfo.calculation_id)))
        revenue = by_key.get(("revenue", period))
        for metric, signal_id, label in (("receivables", "receivable_risk", "应收账款"), ("inventory", "inventory_pressure", "存货")):
            item = by_key.get((metric, period))
            if item and revenue and item.delta_pct is not None and revenue.delta_pct is not None and item.delta_pct - revenue.delta_pct > SIGNIFICANT_GROWTH_GAP:
                signals.append(DiagnosticSignal(signal_id, (period,), f"{label}同比增速高于收入同比增速超过阈值，提示结构性压力。", (item.calculation_id, revenue.calculation_id)))
        deducted = by_key.get(("net_profit_deducted", period))
        if profit and deducted and profit.delta_pct is not None and deducted.delta_pct is not None and profit.delta_pct > 0 and deducted.delta_pct < 0:
            signals.append(DiagnosticSignal("non_recurring_contribution", (period,), "净利润同比上升而扣非净利润同比下降，提示非经常性项目贡献。", (profit.calculation_id, deducted.calculation_id)))
    return signals


def _period_year(period: str) -> int:
    try:
        return int(str(period)[:4])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid period key: {period}") from exc


def _index(facts: Iterable[NormalizedFact]) -> dict[tuple[str, str, str], NormalizedFact]:
    index: dict[tuple[str, str, str], NormalizedFact] = {}
    scopes = {fact.scope for fact in facts}
    # A single analysis result is one calculation chain.  Parent and group
    # statements must be analyzed independently; joining them is invalid even
    # when their metric names happen to align.
    if len(scopes) > 1:
        raise ValueError("scope_mismatch_in_analysis")
    for fact in facts:
        key = (fact.metric, fact.fiscal_period, fact.period_basis)
        if key in index:
            raise ValueError(f"Duplicate normalized fact: {key}")
        index[key] = fact
    return index


def _fact(index: dict[tuple[str, str, str], NormalizedFact], metric: str, period: str, basis: str) -> Optional[NormalizedFact]:
    return index.get((metric, period, basis))


def _yoy_for(index: dict[tuple[str, str, str], NormalizedFact], metric: str, period: str, basis: str,
             missing: list[str]) -> Optional[MetricResult]:
    current = _fact(index, metric, period, basis)
    if current is None:
        missing.append(f"{metric}:{period}:{basis}")
        return None
    previous_period = f"{_period_year(period) - 1}{period[4:]}"
    previous = _fact(index, metric, previous_period, basis)
    if previous is None:
        missing.append(f"{metric}:{previous_period}:{basis}")
        return _metric_result(metric, current.value, None, unit=current.unit, period_key=period,
                              comparison="yoy", calculation_id=f"calc_yoy_{metric}_{period}")
    return compute_yoy(current.value, previous.value, metric=metric, period_key=period, unit=current.unit,
                       calculation_id=f"calc_yoy_{metric}_{period}_{basis}")


def _level_ratio(index: dict[tuple[str, str, str], NormalizedFact], numerator: str, denominator: str,
                 period: str, basis: str, missing: list[str]) -> Optional[MetricResult]:
    left, right = _fact(index, numerator, period, basis), _fact(index, denominator, period, basis)
    if left is None or right is None:
        missing.append(f"{numerator}/{denominator}:{period}:{basis}")
        return None
    if right.value == 0:
        return MetricResult(f"{numerator}/{denominator}", None, "ratio", period, "level", "not_computable", None, None,
                            f"calc_ratio_{numerator}_{denominator}_{period}")
    return MetricResult(f"{numerator}/{denominator}", left.value / right.value, "ratio", period, "level", "normal", None, None,
                        f"calc_ratio_{numerator}_{denominator}_{period}")


def analyze_financials(facts: list[NormalizedFact]) -> AnalysisResult:
    """Compute available YoY/QoQ/ratio metrics and conservative diagnostics."""
    index = _index(facts)
    missing: list[str] = []
    metrics: list[MetricResult] = []
    signals: list[DiagnosticSignal] = []
    periods = sorted({fact.fiscal_period for fact in facts}, key=lambda value: (value[:4], value[4:]))
    if not periods:
        return AnalysisResult((), (), False, ("financial_facts",))
    candidate_bases = ("TTM", "FY", "SINGLE_QUARTER")
    for basis in candidate_bases:
        matching = [period for period in periods if _fact(index, "revenue", period, basis)]
        for period in matching[-1:]:
            for metric in ("revenue", "net_profit_parent", "net_profit_deducted", "capex", "cfo", "receivables", "inventory"):
                result = _yoy_for(index, metric, period, basis, missing)
                if result is not None:
                    metrics.append(result)
            if basis == "SINGLE_QUARTER":
                previous_period = f"{_period_year(period) - 1}{period[4:]}"
                current = _fact(index, "revenue", period, basis)
                previous = _fact(index, "revenue", previous_period, basis)
                if current and previous:
                    metrics.append(compute_qoq(current.value, previous.value, metric="revenue", period_key=period,
                                                calculation_id=f"calc_qoq_revenue_{period}"))
                else:
                    missing.append(f"revenue_qoq:{period}")
            for numerator, denominator in (("net_profit_parent", "revenue"), ("cfo", "net_profit_parent"),
                                           ("receivables", "revenue"), ("inventory", "revenue")):
                result = _level_ratio(index, numerator, denominator, period, basis, missing)
                if result is not None:
                    metrics.append(result)
            revenue_fact = _fact(index, "revenue", period, basis)
            operating_cost = _fact(index, "operating_cost", period, basis)
            if revenue_fact and operating_cost and revenue_fact.value != 0:
                metrics.append(MetricResult("gross_margin", (revenue_fact.value - operating_cost.value) / revenue_fact.value,
                                            "ratio", period, "level", "normal", None, None, f"calc_gross_margin_{period}"))
            else:
                missing.append(f"gross_margin:{period}")
            equity = _fact(index, "average_equity_parent", period, basis)
            profit = _fact(index, "net_profit_parent", period, basis)
            if equity and profit and equity.value != 0:
                metrics.append(MetricResult("roe", profit.value / equity.value, "ratio", period, "level", "normal", None, None,
                                            f"calc_roe_{period}"))
            else:
                missing.append(f"roe:{period}")
            cfo, capex, profit, deducted = (_fact(index, key, period, basis) for key in ("cfo", "capex", "net_profit_parent", "net_profit_deducted"))
            if cfo and capex:
                metrics.append(MetricResult("fcf", cfo.value - capex.value, "CNY", period, "level", "normal", None, None,
                                            f"calc_fcf_{period}"))
            else:
                missing.append(f"fcf:{period}")
            contract = _fact(index, "contract_liabilities", period, "POINT_IN_TIME")
            if contract:
                metrics.append(MetricResult("contract_liabilities", contract.value, contract.unit, period, "level", "normal", None, None,
                                            f"calc_contract_liabilities_{period}"))
            else:
                missing.append(f"contract_liabilities:{period}")

            # Signals compare the same normalized period and never claim causality.
            profit_yoy = next((item for item in metrics if item.metric == "net_profit_parent" and item.period_key == period), None)
            cfo_yoy = _yoy_for(index, "cfo", period, basis, [])
            if profit_yoy and cfo_yoy and profit_yoy.comparison_semantic == "normal" and (profit_yoy.delta_pct or 0) > 0 and (cfo_yoy.delta_pct or 0) < 0:
                signals.append(DiagnosticSignal("earnings_quality_warning", (period,), "净利润同比上升且经营现金流同比下降，提示盈利质量背离。", (profit_yoy.calculation_id, cfo_yoy.calculation_id)))
            for metric, signal_id, label in (("receivables", "receivable_risk", "应收账款"), ("inventory", "inventory_pressure", "存货")):
                growth = _yoy_for(index, metric, period, basis, [])
                revenue_growth = _yoy_for(index, "revenue", period, basis, [])
                if growth and revenue_growth and growth.delta_pct is not None and revenue_growth.delta_pct is not None and growth.delta_pct - revenue_growth.delta_pct > SIGNIFICANT_GROWTH_GAP:
                    signals.append(DiagnosticSignal(signal_id, (period,), f"{label}同比增速高于收入同比增速超过阈值，提示结构性压力。", (growth.calculation_id, revenue_growth.calculation_id)))
            deducted_yoy = next((item for item in metrics if item.metric == "net_profit_deducted" and item.period_key == period), None)
            if profit_yoy and deducted_yoy and profit_yoy.delta_pct is not None and deducted_yoy.delta_pct is not None and profit_yoy.delta_pct > 0 and deducted_yoy.delta_pct < 0:
                signals.append(DiagnosticSignal("non_recurring_contribution", (period,), "净利润同比上升而扣非净利润同比下降，提示非经常性项目贡献。", (profit_yoy.calculation_id, deducted_yoy.calculation_id)))
    return AnalysisResult(tuple(metrics), tuple(signals), not missing, tuple(sorted(set(missing))))
