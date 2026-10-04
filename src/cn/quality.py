"""Independent report-quality diagnostics; deliberately no aggregate score."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


DIMENSIONS = (
    "evidence_coverage", "citation_precision", "citation_recall", "calculation_validity",
    "numeric_accuracy", "assumption_disclosure", "unsupported_claims", "factual_errors",
    "false_positive_risk", "replay_consistency",
)


@dataclass(frozen=True)
class Diagnostic:
    name: str
    numerator: int | None
    denominator: int | None
    value: float | None
    status: str
    claim_ids: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["claim_ids"] = list(self.claim_ids)
        return payload


def _ratio(name: str, numerator: int, denominator: int, claims: list[str], reason: str = "") -> Diagnostic:
    if denominator <= 0:
        return Diagnostic(name, None, None, None, "N/A", tuple(claims), reason or "no denominator")
    return Diagnostic(name, numerator, denominator, numerator / denominator, "ok", tuple(claims), reason)


def diagnose_quality(report: Mapping[str, Any]) -> dict[str, Any]:
    claims = list(report.get("claims") or [])
    findings = list(report.get("findings") or [])
    calculations = list(report.get("calculations") or [])
    citations = list(report.get("citations") or [])
    evidence_ids = {str(item.get("evidence_id")) for item in report.get("evidence", []) if isinstance(item, Mapping)}
    claim_ids = [str(item.get("claim_id")) for item in claims if item.get("claim_id")]
    with_evidence = [item for item in claims if item.get("evidence_ids")]
    cited = [item for item in claims if item.get("evidence_ids") or item.get("citation_ids")]
    valid_citations = [item for item in citations if item.get("valid", item.get("chunk_id") in evidence_ids)]
    valid_calculations = [item for item in calculations if item.get("validation_status") in {"valid", "verified", "supported", "ok"}]
    numeric_findings = [item for item in findings if item.get("check_type") in {"numeric_error", "calculation_error", "unit_error"}]
    factual_findings = [item for item in findings if item.get("check_type") in {"numeric_error", "period_error", "scope_error", "wrong_citation", "revision_superseded"}]
    unsupported = [item for item in claims if not item.get("evidence_ids") and item.get("claim_type") in {"fact", "factual"}]
    assumptions = list(report.get("assumptions") or [])
    assumptions_expected = int(report.get("assumptions_expected", len(assumptions)))
    replay = list(report.get("replay_runs") or [])
    diagnostics = [
        _ratio("evidence_coverage", len(with_evidence), len(claims), claim_ids),
        _ratio("citation_precision", len(valid_citations), len(citations), claim_ids, "citation validity is deterministic"),
        _ratio("citation_recall", len(cited), len(claims), claim_ids),
        _ratio("calculation_validity", len(valid_calculations), len(calculations), claim_ids),
        _ratio("numeric_accuracy", max(0, len(claims) - len(numeric_findings)), len(claims), claim_ids),
        _ratio("assumption_disclosure", len(assumptions), assumptions_expected, claim_ids),
        Diagnostic("unsupported_claims", len(unsupported), len(claims), None, "count", tuple(str(item.get("claim_id")) for item in unsupported)),
        Diagnostic("factual_errors", len(factual_findings), len(claims), None, "count", claim_ids),
        _ratio("false_positive_risk", len([item for item in findings if item.get("severity") == "warning"]), len(findings), claim_ids),
        _ratio("replay_consistency", sum(bool(item.get("deterministic_equal")) for item in replay), len(replay), claim_ids),
    ]
    return {
        "schema_version": "cn-report-quality-diagnostics-1.0.0",
        "dimensions": [item.to_dict() for item in diagnostics],
        "claim_ids": claim_ids,
        "notes": ["Dimensions are independent diagnostics; no calibrated overall score is produced."],
    }
