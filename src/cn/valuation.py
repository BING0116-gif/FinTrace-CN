"""Deterministic peer-multiple calculations for A-share research."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import math
from statistics import median
from typing import Dict, Iterable, List, Literal, Mapping, Optional


MultipleName = Literal["PE", "PB", "PS"]


@dataclass(frozen=True)
class Assumption:
    assumption_id: str
    value: float | str
    source: str
    reason: str
    valid_from: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class AssumptionRegistry:
    """Explicit registry for analyst inputs; facts must cite Evidence IDs."""
    def __init__(self, assumptions: Iterable[Assumption] = ()):
        self._items: dict[str, Assumption] = {}
        for item in assumptions:
            self.add(item)

    def add(self, assumption: Assumption) -> Assumption:
        if assumption.assumption_id in self._items:
            raise ValueError(f"Duplicate assumption_id: {assumption.assumption_id}")
        self._items[assumption.assumption_id] = assumption
        return assumption

    def register(self, value: float | str, *, source: str, reason: str, valid_from: str | None = None, assumption_id: str | None = None) -> Assumption:
        if not source or not reason:
            raise ValueError("assumption source and reason are required")
        identifier = assumption_id or f"assumption_{len(self._items) + 1:04d}"
        return self.add(Assumption(identifier, value, source, reason, valid_from or date.today().isoformat()))

    def get(self, assumption_id: str) -> Assumption:
        return self._items[assumption_id]

    def ids(self) -> tuple[str, ...]:
        return tuple(self._items)

    def to_dict(self) -> dict[str, dict[str, object]]:
        return {key: item.to_dict() for key, item in self._items.items()}


@dataclass(frozen=True)
class ScenarioValuation:
    method: str
    scenario: str
    value_low: float | None
    value_mid: float | None
    value_high: float | None
    assumption_ids: list[str] = field(default_factory=list)
    calculation_ids: list[str] = field(default_factory=list)
    status: str = "ok"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SensitivityMatrix:
    x_name: str
    y_name: str
    x_values: list[float]
    y_values: list[float]
    matrix: list[list[float]]
    assumption_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ValuationResult:
    scenarios: list[ScenarioValuation]
    sensitivity: list[SensitivityMatrix]
    method_dispersion: dict[str, object]
    applicability_note: str
    assumptions: list[Assumption] = field(default_factory=list)
    validation: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "scenarios": [item.to_dict() for item in self.scenarios],
            "sensitivity": [item.to_dict() for item in self.sensitivity],
            "method_dispersion": self.method_dispersion,
            "applicability_note": self.applicability_note,
            "assumptions": [item.to_dict() for item in self.assumptions],
            "validation": self.validation,
        }


@dataclass(frozen=True)
class PeerValuationInput:
    symbol: str
    raw_price: float
    total_shares: float
    net_profit: Optional[float]
    book_equity: Optional[float]
    revenue: Optional[float]
    period_basis: str

    @property
    def market_cap(self) -> float:
        return self.raw_price * self.total_shares


@dataclass(frozen=True)
class PeerMultiple:
    symbol: str
    name: MultipleName
    value: Optional[float]
    exclusion_reason: Optional[str] = None


@dataclass(frozen=True)
class MultipleSummary:
    name: MultipleName
    median: Optional[float]
    included_symbols: List[str]
    excluded: Dict[str, str]
    confidence: Literal["high", "medium", "low", "unavailable"]


def calculate_multiple(peer: PeerValuationInput, name: MultipleName) -> PeerMultiple:
    if peer.raw_price <= 0 or peer.total_shares <= 0:
        return PeerMultiple(peer.symbol, name, None, "invalid_raw_price_or_shares")
    denominator = {
        "PE": peer.net_profit,
        "PB": peer.book_equity,
        "PS": peer.revenue,
    }[name]
    if denominator is None or denominator <= 0:
        return PeerMultiple(peer.symbol, name, None, f"non_positive_{name}_denominator")
    return PeerMultiple(peer.symbol, name, peer.market_cap / denominator)


def _iqr_bounds(values: List[float]) -> tuple[float, float]:
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    lower_half = sorted_values[:midpoint]
    upper_half = sorted_values[midpoint + (len(sorted_values) % 2):]
    q1, q3 = median(lower_half), median(upper_half)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def summarize_peer_multiple(peers: Iterable[PeerValuationInput], name: MultipleName) -> MultipleSummary:
    """Filter invalid values and IQR outliers before calculating a peer median."""
    computed = [calculate_multiple(peer, name) for peer in peers]
    excluded = {item.symbol: item.exclusion_reason for item in computed if item.exclusion_reason}
    valid = [item for item in computed if item.value is not None]
    if not valid:
        return MultipleSummary(name, None, [], excluded, "unavailable")

    # IQR becomes meaningful only with four or more valid peers.  Smaller samples
    # remain visible but explicitly have low confidence rather than fabricated
    # outlier decisions.
    included = valid
    if len(valid) >= 4:
        lower, upper = _iqr_bounds([item.value for item in valid if item.value is not None])
        included = []
        for item in valid:
            if item.value is not None and not lower <= item.value <= upper:
                excluded[item.symbol] = "iqr_outlier"
            else:
                included.append(item)
    confidence: Literal["high", "medium", "low", "unavailable"]
    confidence = "high" if len(included) >= 6 else "medium" if len(included) >= 4 else "low"
    return MultipleSummary(
        name=name,
        median=median([item.value for item in included if item.value is not None]) if included else None,
        included_symbols=[item.symbol for item in included],
        excluded=excluded,
        confidence=confidence if included else "unavailable",
    )


def implied_price(
    target: PeerValuationInput, *, multiple: MultipleSummary, denominator: Literal["net_profit", "book_equity", "revenue"]
) -> Optional[float]:
    """Return a per-share value only when the target and peer basis are valid."""
    if multiple.median is None or target.total_shares <= 0:
        return None
    value = getattr(target, denominator)
    if value is None or value <= 0:
        return None
    return multiple.median * value / target.total_shares


def _registry_item(registry: AssumptionRegistry, scenario: str, key: str, raw: object) -> tuple[float, str]:
    """Resolve a scenario input and ensure it is represented in the registry."""
    assumption_id: str | None = None
    value = raw
    source = f"assumption:{scenario}:{key}"
    reason = f"{scenario} scenario {key}"
    valid_from: str | None = None
    if isinstance(raw, dict):
        value = raw.get("value")
        assumption_id = str(raw.get("assumption_id")) if raw.get("assumption_id") else None
        source = str(raw.get("source") or source)
        reason = str(raw.get("reason") or reason)
        valid_from = str(raw.get("valid_from")) if raw.get("valid_from") else None
    if value is None:
        raise ValueError(f"missing_{scenario}_{key}")
    numeric = float(value)
    if assumption_id:
        item = registry.get(assumption_id)
        if float(item.value) != numeric:
            raise ValueError(f"assumption_value_mismatch:{assumption_id}")
    else:
        item = registry.register(numeric, source=source, reason=reason, valid_from=valid_from, assumption_id=f"assumption_{scenario}_{key}")
        assumption_id = item.assumption_id
    return numeric, assumption_id


def _range_input(registry: AssumptionRegistry, scenario: str, key: str, raw: object) -> tuple[float, float, float, list[str]]:
    if isinstance(raw, dict) and any(name in raw for name in ("low", "mid", "high")):
        values: list[float] = []
        ids: list[str] = []
        for label in ("low", "mid", "high"):
            value, identifier = _registry_item(registry, scenario, f"{key}_{label}", raw.get(label))
            values.append(value); ids.append(identifier)
        return values[0], values[1], values[2], ids
    value, identifier = _registry_item(registry, scenario, key, raw)
    return value, value, value, [identifier]


def build_scenarios(base_inputs: Mapping[str, object], assumption_registry: AssumptionRegistry) -> list[ScenarioValuation]:
    """Build independent PE/PB/PS bear/base/bull outputs.

    Inputs are intentionally explicit: ``base_inputs['scenarios'][scenario]``
    must provide EPS/BPS/revenue-per-share and each applicable target multiple.
    Missing data produces a typed not_applicable result rather than borrowing a
    value from another method or scenario.
    """
    scenarios_input = base_inputs.get("scenarios") if isinstance(base_inputs, Mapping) else None
    if not isinstance(scenarios_input, Mapping):
        raise ValueError("scenarios_input_required")
    shares = base_inputs.get("shares")
    if shares is None or float(shares) <= 0:
        raise ValueError("missing_total_shares")
    declared_basis = base_inputs.get("period_basis")
    if declared_basis is not None and not str(declared_basis).upper().endswith("TTM"):
        raise ValueError("valuation_requires_ttm_inputs")
    methods = ("pe", "pb", "ps")
    outputs: list[ScenarioValuation] = []
    for scenario in ("bear", "base", "bull"):
        values = scenarios_input.get(scenario)
        if not isinstance(values, Mapping):
            raise ValueError(f"missing_scenario:{scenario}")
        scenario_basis = values.get("period_basis")
        if scenario_basis is not None and not str(scenario_basis).upper().endswith("TTM"):
            raise ValueError("valuation_requires_ttm_inputs")
        for method in methods:
            metric_key = {"pe": "eps", "pb": "bps", "ps": "revenue_per_share"}[method]
            multiple_key = {"pe": "target_pe", "pb": "target_pb", "ps": "target_ps"}[method]
            try:
                low_metric, mid_metric, high_metric, metric_ids = _range_input(assumption_registry, scenario, metric_key, values.get(metric_key))
                low_multiple, mid_multiple, high_multiple, multiple_ids = _range_input(assumption_registry, scenario, multiple_key, values.get(multiple_key))
            except ValueError as exc:
                outputs.append(ScenarioValuation(method, scenario, None, None, None, [], [], f"not_applicable:{exc}"))
                continue
            products = (low_metric * low_multiple, mid_metric * mid_multiple, high_metric * high_multiple)
            if mid_metric <= 0 and method == "pe":
                outputs.append(ScenarioValuation(method, scenario, None, None, None, metric_ids + multiple_ids, [f"calc_{method}_{scenario}"], "not_applicable_negative_eps"))
            elif mid_metric <= 0 and method == "pb":
                outputs.append(ScenarioValuation(method, scenario, None, None, None, metric_ids + multiple_ids, [f"calc_{method}_{scenario}"], "not_applicable_non_positive_bps"))
            else:
                outputs.append(ScenarioValuation(method, scenario, *products, metric_ids + multiple_ids, [f"calc_{method}_{scenario}"], "ok"))
    return outputs


def sensitivity_pe_eps(eps_range: Iterable[float], target_pe_range: Iterable[float], shares: float = 1.0, *, assumption_ids: Iterable[str] = ()) -> SensitivityMatrix:
    if shares <= 0:
        raise ValueError("shares must be positive")
    eps_values, pe_values = [float(item) for item in eps_range], [float(item) for item in target_pe_range]
    if not eps_values or not pe_values:
        raise ValueError("sensitivity ranges must not be empty")
    return SensitivityMatrix("Target PE", "EPS (TTM)", pe_values, eps_values, [[eps * pe for pe in pe_values] for eps in eps_values], list(assumption_ids))


def sensitivity_pb_roe(roe_range: Iterable[float], target_pb_range: Iterable[float], bps: float | Iterable[float], shares: float = 1.0, *, assumption_ids: Iterable[str] = ()) -> SensitivityMatrix:
    if shares <= 0:
        raise ValueError("shares must be positive")
    roe_values, pb_values = [float(item) for item in roe_range], [float(item) for item in target_pb_range]
    bps_values = [float(item) for item in bps] if not isinstance(bps, (int, float)) else [float(bps)] * len(roe_values)
    if len(bps_values) != len(roe_values):
        raise ValueError("bps range must match roe range length")
    return SensitivityMatrix("Target PB", "ROE (BPS fixed for each row)", pb_values, roe_values, [[book * pb for pb in pb_values] for book in bps_values], list(assumption_ids))


def method_dispersion(scenarios: Iterable[ScenarioValuation]) -> dict[str, object]:
    report: dict[str, object] = {}
    for method in ("pe", "pb", "ps"):
        values = [value for item in scenarios if item.method == method for value in (item.value_low, item.value_mid, item.value_high) if value is not None]
        mids = [item.value_mid for item in scenarios if item.method == method and item.value_mid is not None]
        if not values:
            report[method] = {"status": "unavailable", "min": None, "max": None, "mid_range": None, "mean": None, "spread_pct": None}
            continue
        low, high = min(values), max(values)
        mean = sum(mids) / len(mids) if mids else None
        report[method] = {"status": "ok", "min": low, "max": high, "mid_range": (min(mids), max(mids)) if mids else None, "mean": mean, "spread_pct": (high - low) / abs(mean) if mean else None}
    return report


def validate_valuation_result(result: ValuationResult, registry: AssumptionRegistry) -> dict[str, object]:
    errors: list[str] = []
    known = set(registry.ids())
    for item in result.scenarios:
        missing = [identifier for identifier in item.assumption_ids if identifier not in known]
        errors.extend(f"missing_assumption:{identifier}" for identifier in missing)
    for matrix in result.sensitivity:
        for row in matrix.matrix:
            if any(row[index] > row[index + 1] for index in range(len(row) - 1)):
                errors.append(f"non_monotonic_x:{matrix.x_name}")
        for index in range(len(matrix.matrix[0]) if matrix.matrix else 0):
            column = [row[index] for row in matrix.matrix]
            if any(column[row] > column[row + 1] for row in range(len(column) - 1)):
                errors.append(f"non_monotonic_y:{matrix.y_name}")
    return {"valid": not errors, "errors": sorted(set(errors)), "dispersion_present": bool(result.method_dispersion)}


def build_valuation_result(base_inputs: Mapping[str, object], assumption_registry: AssumptionRegistry) -> ValuationResult:
    scenarios = build_scenarios(base_inputs, assumption_registry)
    matrices: list[SensitivityMatrix] = []
    if base_inputs.get("eps_range") is not None and base_inputs.get("target_pe_range") is not None:
        matrices.append(sensitivity_pe_eps(base_inputs["eps_range"], base_inputs["target_pe_range"], float(base_inputs.get("shares", 1.0)), assumption_ids=assumption_registry.ids()))
    if base_inputs.get("roe_range") is not None and base_inputs.get("target_pb_range") is not None and base_inputs.get("bps") is not None:
        matrices.append(sensitivity_pb_roe(base_inputs["roe_range"], base_inputs["target_pb_range"], base_inputs["bps"], float(base_inputs.get("shares", 1.0)), assumption_ids=assumption_registry.ids()))
    result = ValuationResult(
        scenarios=scenarios, sensitivity=matrices, method_dispersion=method_dispersion(scenarios),
        applicability_note="PE requires positive TTM EPS; PB requires positive BPS; PS is generally for operating companies. Methods remain separate and are not merged into a synthetic range.",
        assumptions=[assumption_registry.get(identifier) for identifier in assumption_registry.ids()],
    )
    return ValuationResult(result.scenarios, result.sensitivity, result.method_dispersion, result.applicability_note, result.assumptions, validate_valuation_result(result, assumption_registry))
