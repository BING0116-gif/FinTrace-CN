"""Fail-closed FCFF DCF valuation with an explicit EV-to-equity bridge."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from .valuation import Assumption, AssumptionRegistry


@dataclass(frozen=True)
class DcfBridge:
    enterprise_value: float
    net_debt: float
    minority_interest: float
    non_operating_assets: float
    other_adjustments: float
    equity_value: float
    diluted_shares: float
    implied_price: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DcfResult:
    method: str
    industry: str
    forecast_method: str
    bridge: DcfBridge
    sensitivity: dict[str, Any]
    assumptions: list[Assumption]
    applicability: dict[str, Any]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bridge"] = self.bridge.to_dict()
        payload["assumptions"] = [item.to_dict() for item in self.assumptions]
        payload["warnings"] = list(self.warnings)
        return payload


_GATE = {
    "bank": (False, "银行优先使用 PB/ROE 或 DDM，FCFF 不适用"),
    "insurance": (False, "保险优先使用 PEV/PB，FCFF 不适用"),
    "manufacturing": (True, "普通制造业可使用 PE + FCFF DCF"),
    "growth_unprofitable": (False, "未盈利成长公司优先使用 PS/EV-Sales"),
}


def valuation_applicability(industry: str) -> dict[str, Any]:
    key = str(industry or "").strip().lower()
    allowed, reason = _GATE.get(key, (True, "未识别行业：仅在现金流与桥接证据完整时演示 FCFF DCF"))
    return {"industry": key or "unknown", "method": "fcff_dcf", "allowed": allowed, "reason": reason}


def _evidence_value(bridge: Mapping[str, Any], key: str) -> float:
    raw = bridge.get(key)
    if not isinstance(raw, Mapping) or raw.get("evidence_id") in (None, ""):
        raise ValueError(f"missing_bridge_evidence:{key}")
    value = raw.get("value")
    if value is None:
        raise ValueError(f"missing_bridge_value:{key}")
    return float(value)


def _assumption(registry: AssumptionRegistry, name: str, value: Any, source: str, reason: str) -> str:
    return registry.register(float(value), source=source, reason=reason).assumption_id


def dcf_sensitivity(fcffs: Iterable[float], wacc_values: Iterable[float], growth_values: Iterable[float]) -> dict[str, Any]:
    flows = [float(value) for value in fcffs]
    waccs = [float(value) for value in wacc_values]
    growths = [float(value) for value in growth_values]
    if not flows or not waccs or not growths:
        raise ValueError("sensitivity_inputs_required")
    rows: list[list[float]] = []
    for wacc in waccs:
        row: list[float] = []
        for growth in growths:
            if wacc <= growth:
                raise ValueError("wacc_must_exceed_terminal_growth")
            pv = sum(flow / ((1 + wacc) ** (index + 1)) for index, flow in enumerate(flows))
            terminal = flows[-1] * (1 + growth) / (wacc - growth)
            pv += terminal / ((1 + wacc) ** len(flows))
            row.append(pv)
        rows.append(row)
    return {"x_name": "Terminal growth", "y_name": "WACC", "x_values": growths, "y_values": waccs, "matrix": rows}


def build_dcf(base_inputs: Mapping[str, Any], registry: AssumptionRegistry | None = None) -> DcfResult:
    registry = registry or AssumptionRegistry()
    industry = str(base_inputs.get("industry") or "unknown")
    applicability = valuation_applicability(industry)
    if not applicability["allowed"]:
        raise ValueError(f"dcf_not_applicable:{applicability['reason']}")
    forecasts = base_inputs.get("forecast_fcff")
    if not isinstance(forecasts, list) or not forecasts:
        raise ValueError("forecast_fcff_required")
    if base_inputs.get("forecast_method") not in {"explicit_fcff"}:
        raise ValueError("forecast_method_must_be_explicit_fcff")
    wacc = float(base_inputs.get("wacc"))
    growth = float(base_inputs.get("terminal_growth"))
    if wacc <= growth:
        raise ValueError("wacc_must_exceed_terminal_growth")
    fcffs = [float(value) for value in forecasts]
    enterprise = sum(value / ((1 + wacc) ** (index + 1)) for index, value in enumerate(fcffs))
    enterprise += fcffs[-1] * (1 + growth) / (wacc - growth) / ((1 + wacc) ** len(fcffs))
    _assumption(registry, "wacc", wacc, "assumption:wacc", "显式折现率假设")
    _assumption(registry, "terminal_growth", growth, "assumption:terminal_growth", "显式终值增长率假设")
    bridge = base_inputs.get("bridge")
    if not isinstance(bridge, Mapping):
        raise ValueError("bridge_required")
    net_debt = _evidence_value(bridge, "net_debt")
    minority = _evidence_value(bridge, "minority_interest")
    non_operating = _evidence_value(bridge, "non_operating_assets")
    other = _evidence_value(bridge, "other_adjustments")
    shares = _evidence_value(bridge, "diluted_shares")
    if shares <= 0:
        raise ValueError("diluted_shares_must_be_positive")
    equity = enterprise - net_debt - minority + non_operating + other
    return DcfResult(
        "fcff_dcf", industry, "explicit_fcff",
        DcfBridge(enterprise, net_debt, minority, non_operating, other, equity, shares, equity / shares),
        dcf_sensitivity(fcffs, base_inputs.get("wacc_range", [wacc]), base_inputs.get("growth_range", [growth])),
        [registry.get(identifier) for identifier in registry.ids()], applicability,
    )
