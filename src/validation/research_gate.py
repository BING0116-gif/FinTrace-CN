"""Deterministic blocking gate for evidence-backed A-share conclusions.

``FinancialValidator`` checks evidence that exists. This gate additionally
checks whether the tool execution and provenance are complete enough to permit
a deterministic financial conclusion at all. It never relies on model prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Optional

from src.cn.industries import get_industry_code, is_financial_institution
from src.cn.research import ResearchState
from src.validation.financial_validator import FinancialValidator, ValidationResult


@dataclass(frozen=True)
class ResearchGateRequirements:
    """Explicit requirements derived from the benchmark case/research plan."""

    required_metrics: tuple[str, ...] = ()
    requires_evidence: bool = False
    requested_valuation_method: Optional[str] = None


class ResearchGateValidator:
    """Block conclusions when execution, evidence, or applicability is invalid."""

    def __init__(self, *, max_data_age_days: int = 365) -> None:
        self._financial = FinancialValidator(max_data_age_days=max_data_age_days)

    def validate(
        self,
        ledger: Any,
        *,
        state: ResearchState,
        snapshot_payload: Mapping[str, Any],
        research_as_of: str,
        requirements: ResearchGateRequirements,
    ) -> ValidationResult:
        base = self._financial.validate(ledger, research_as_of=research_as_of)
        records = list(ledger.records())
        errors = list(base.errors)

        for trace in state.tool_trace:
            if trace.result_status != "ok":
                errors.append(f"tool_error:{trace.tool_name}")

        if requirements.requires_evidence and not records:
            errors.append("no_evidence")

        if not _is_valid_timestamp(research_as_of):
            errors.append(f"invalid_research_as_of:{research_as_of}")

        for record in records:
            if record.kind != "fact":
                continue
            if not record.available_at:
                errors.append(f"availability_unknown:{record.evidence_id}")
            elif not _is_valid_timestamp(str(record.available_at)):
                errors.append(f"invalid_availability_timestamp:{record.evidence_id}")

        present_metrics = {str(record.metric).lower() for record in records if record.metric}
        for requested in requirements.required_metrics:
            metric = requested.lower()
            if metric in present_metrics:
                continue
            future_availability = self._future_metric_availability(
                snapshot_payload, metric=metric, research_as_of=research_as_of,
            )
            if future_availability:
                errors.append(f"unavailable_before_cutoff:{metric}:{future_availability}")
            else:
                errors.append(f"requested_metric_missing:{metric}")

        method = self._normalize_method(requirements.requested_valuation_method)
        if method:
            entity_type, classification_error = self._resolve_entity_type(
                snapshot_payload, state=state,
            )
            if classification_error:
                errors.append(classification_error)
            if entity_type is None:
                errors.append(f"industry_classification_unknown:{method}")
            elif not classification_error:
                applicable = {"PE", "PB"} if entity_type == "financial_institution" else {"PE", "PB", "PS"}
                if method not in applicable:
                    errors.append(f"industry_valuation_inapplicable:{entity_type}:{method}")

        errors = list(dict.fromkeys(errors))
        return ValidationResult(
            valid=not errors,
            errors=errors,
            warnings=list(base.warnings),
            recalculated_values=dict(base.recalculated_values),
            evidence_coverage=base.evidence_coverage,
        )

    @staticmethod
    def _future_metric_availability(
        snapshot_payload: Mapping[str, Any], *, metric: str, research_as_of: str,
    ) -> Optional[str]:
        future_dates = []
        for statement in snapshot_payload.get("data", {}).get("statements", []):
            values = statement.get("values") or {}
            if values.get(metric) is None:
                continue
            available_at = statement.get("available_at")
            if available_at and _is_after(str(available_at), research_as_of):
                future_dates.append(str(available_at))
        return min(future_dates) if future_dates else None

    @staticmethod
    def _normalize_method(method: Optional[str]) -> Optional[str]:
        if not method:
            return None
        normalized = method.upper().replace("_", "/").replace("-", "/").replace(" ", "")
        return {
            "P/E": "PE", "P/B": "PB", "P/S": "PS",
            "EVEBITDA": "EV/EBITDA", "EV/EBITDA": "EV/EBITDA",
        }.get(normalized, normalized)

    @staticmethod
    def _resolve_entity_type(
        snapshot_payload: Mapping[str, Any], *, state: ResearchState,
    ) -> tuple[Optional[str], Optional[str]]:
        profile = snapshot_payload.get("data", {}).get("profile") or {}
        declared = str(profile.get("entity_type") or "").strip().lower()
        if declared not in {"financial_institution", "operating_company"}:
            declared = ""

        symbol = str(snapshot_payload.get("symbol") or state.symbol or "")
        code = symbol.split(".", 1)[0]
        if not code:
            return (declared or None), None

        canonical: Optional[str] = None
        if get_industry_code(code):
            canonical = (
                "financial_institution"
                if is_financial_institution(code)
                else "operating_company"
            )
        if canonical and declared and canonical != declared:
            return canonical, f"industry_classification_conflict:{declared}:{canonical}"
        return canonical or declared or None, None


class SnapshotEvidenceLedger:
    """Small read-only adapter over evidence reconstructed from a snapshot.

    Tool traces preserve IDs, not raw payloads.  This adapter may reconstruct
    values from the pinned snapshot only for IDs that a successful tool call
    actually returned and the state actually registered.
    """

    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self._records = records

    def records(self) -> List[Any]:
        return [SimpleNamespace(**record) for record in self._records]


def snapshot_evidence_records(
    snapshot_payload: Mapping[str, Any], *, state: ResearchState,
) -> List[Dict[str, Any]]:
    """Return fact records backed by successfully registered snapshot evidence.

    This intentionally cannot manufacture provenance: an ID must occur both in
    the state and in a successful tool trace before its snapshot value is made
    available to the validator.
    """
    registered_ids = {*state.facts, *state.calculations}
    successful_ids = {
        evidence_id
        for trace in state.tool_trace
        if trace.result_status == "ok"
        for evidence_id in trace.evidence_ids
    }
    trusted_ids = registered_ids & successful_ids
    if not trusted_ids:
        return []

    symbol = str(snapshot_payload.get("symbol") or state.symbol)
    data = snapshot_payload.get("data") or {}
    records: List[Dict[str, Any]] = []

    for trace in state.tool_trace:
        if trace.result_status != "ok":
            continue
        if trace.tool_name in {"get_cn_prices", "generate_cn_research_report"}:
            start_date = str(trace.arguments.get("start_date") or "")
            end_date = str(trace.arguments.get("end_date") or "")
            bars = [
                bar for bar in data.get("bars", [])
                if bar.get("adjustment") == "RAW"
                and (not start_date or str(bar.get("trade_date", "")) >= start_date)
                and (not end_date or str(bar.get("trade_date", "")) <= end_date)
                and str(bar.get("trade_date", "")) <= state.research_as_of[:10]
            ]
            if bars:
                latest = max(bars, key=lambda bar: str(bar["trade_date"]))
                evidence_id = f"fact_{symbol.replace('.', '_')}_close_{latest['trade_date']}_RAW"
                if evidence_id in trusted_ids:
                    available_at = f"{latest['trade_date']}T15:00:00+08:00"
                    records.append({
                        "evidence_id": evidence_id, "kind": "fact", "symbol": symbol,
                        "metric": "close", "value": latest["close"], "currency": "CNY",
                        "unit": "CNY/share", "fiscal_period": None, "period_basis": "RAW",
                        "published_at": available_at, "available_at": available_at,
                        "provider": "snapshot",
                    })

        if trace.tool_name in {"get_cn_financials", "generate_cn_research_report"}:
            cutoff = str(trace.arguments.get("research_as_of") or state.research_as_of)
            for statement in data.get("statements", []):
                available_at = statement.get("available_at")
                if available_at and str(available_at) > cutoff:
                    continue
                for metric, value in (statement.get("values") or {}).items():
                    if value is None:
                        continue
                    evidence_id = f"fact_{symbol.replace('.', '_')}_{metric}_{statement['fiscal_period']}"
                    if evidence_id not in trusted_ids:
                        continue
                    records.append({
                        "evidence_id": evidence_id, "kind": "fact", "symbol": symbol,
                        "metric": metric, "value": value,
                        "currency": statement.get("currency", ""), "unit": statement.get("unit", ""),
                        "fiscal_period": statement.get("fiscal_period"),
                        "period_basis": statement.get("period_basis"),
                        "published_at": statement.get("published_at"),
                        "available_at": available_at, "provider": "snapshot",
                    })

    # A report tool can expose price/financial evidence even though it has no
    # individual data-tool traces.  The loop above already handles that path.
    unique: Dict[str, Dict[str, Any]] = {record["evidence_id"]: record for record in records}
    return list(unique.values())


def _is_after(value: str, cutoff: str) -> bool:
    try:
        return datetime.fromisoformat(value) > datetime.fromisoformat(cutoff)
    except (TypeError, ValueError):
        return False


def _is_valid_timestamp(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True
