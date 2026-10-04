"""Synthetic financial-semantic fuzzing with auditable, honest metrics."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping, Sequence

class MutationOperators(str, Enum):
    NUMERIC = "numeric"; UNIT = "unit"; SIGN = "sign"; PERIOD = "period"; YTD_VS_SINGLE = "ytd_vs_single"
    SCOPE = "scope"; VERSION = "version"; VALUATION = "valuation"; CITATION = "citation"; CAUSAL = "causal"

@dataclass(frozen=True)
class MutationSpec:
    mutation_id: str
    operator: str
    source_claim: dict[str, Any]
    mutated_claim: dict[str, Any]
    description: str
    expected_detection: bool = True

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class MutationResult:
    spec: MutationSpec
    detected_by: str | None
    detected: bool
    detection_time_ms: int
    error_type_classified: str | None
    extractor_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self); payload["spec"] = self.spec.to_dict(); return payload

@dataclass(frozen=True)
class FinFuzzReport:
    suite_id: str
    overall: dict[str, Any]
    per_error_type: dict[str, dict[str, Any]]
    baseline_holdout: dict[str, Any]
    extractor_vs_checker: dict[str, Any]
    results: list[dict[str, Any]] = field(default_factory=list)
    seed: int = 42
    schema_version: str = "cn-finfuzz-1.0.0"

    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _claim_dict(claim: Any) -> dict[str, Any]:
    if hasattr(claim, "to_dict"): return dict(claim.to_dict())
    if isinstance(claim, Mapping): return dict(claim)
    return dict(vars(claim))

def _mutate(source: Mapping[str, Any], operator: MutationOperators) -> tuple[dict[str, Any], str, bool]:
    mutated = deepcopy(dict(source)); value = mutated.get("value")
    if operator is MutationOperators.NUMERIC:
        mutated["value"] = float(value) * 10 if isinstance(value, (int, float)) else value; return mutated, "numeric magnitude multiplied by 10", True
    if operator is MutationOperators.UNIT:
        old = mutated.get("unit", "元"); mutated["unit"] = "亿元" if old != "亿元" else "元"; return mutated, f"unit changed from {old} to {mutated['unit']} without trusted conversion", True
    if operator is MutationOperators.SIGN:
        if isinstance(mutated.get("growth"), (int, float)): mutated["growth"] = -float(mutated["growth"])
        elif isinstance(value, (int, float)): mutated["value"] = -float(value)
        return mutated, "sign inverted", True
    if operator is MutationOperators.PERIOD:
        period = str(mutated.get("period") or "2025FY"); mutated["period"] = (f"{int(period[:4]) - 1}{period[4:]}" if period[:4].isdigit() else "2024FY"); return mutated, "economic period changed", True
    if operator is MutationOperators.YTD_VS_SINGLE:
        mutated["period_basis"] = "SINGLE_QUARTER" if mutated.get("period_basis") != "SINGLE_QUARTER" else "H1"; return mutated, "YTD and single-quarter basis swapped", True
    if operator is MutationOperators.SCOPE:
        mutated["scope"] = "parent" if mutated.get("scope") != "parent" else "consolidated"; return mutated, "accounting scope changed", True
    if operator is MutationOperators.VERSION:
        mutated["version"] = "AS_REPORTED" if mutated.get("version") in {"CORRECTED", "RESTATED"} else "CORRECTED"; return mutated, "reported version changed", True
    if operator is MutationOperators.VALUATION:
        mutated["valuation_multiple"] = "12x" if str(mutated.get("valuation_multiple")) != "12x" else "8x"; mutated["metric"] = "pb" if mutated.get("metric") == "pe" else "pe"; return mutated, "valuation basis changed", True
    if operator is MutationOperators.CITATION:
        mutated["source_reference"] = "page:999" if str(mutated.get("source_reference")) != "page:999" else "missing-evidence"; mutated["page"] = 999; return mutated, "citation locator changed", True
    if operator is MutationOperators.CAUSAL:
        mutated["claim_type"] = "causal"; mutated["sentence"] = str(mutated.get("sentence", "")) + "，因此导致该结果"; return mutated, "descriptive statement rewritten as causal", True
    raise ValueError(f"unsupported operator: {operator}")

def generate_mutation_specs(claims: Iterable[Any], operators: Iterable[str | MutationOperators], seed: int = 42) -> list[MutationSpec]:
    # Seed is part of the reproducibility contract. Operators are applied in
    # caller order; no random sampling means the same inputs always serialize identically.
    del seed
    rows = []
    for index, claim in enumerate(claims):
        source = _claim_dict(claim)
        for raw_operator in operators:
            operator = raw_operator if isinstance(raw_operator, MutationOperators) else MutationOperators(str(raw_operator))
            mutated, description, expected = _mutate(source, operator)
            digest = hashlib.sha256(json.dumps([index, operator.value, source], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]
            rows.append(MutationSpec(f"mut_{digest}", operator.value, source, mutated, description, expected))
    return rows

def _target_findings(target: Any, claim: dict[str, Any]) -> tuple[bool, str | None, bool]:
    if target is None: return False, None, True
    try:
        output = target(claim) if callable(target) else target.check(claim)
    except Exception:
        return False, None, False
    if isinstance(output, Mapping):
        if output.get("extractor_failed"): return False, None, True
        findings = output.get("findings", [])
    else: findings = output
    if findings is None: return False, None, False
    if not isinstance(findings, (list, tuple, set)): findings = [findings]
    types = []
    for finding in findings:
        kind = finding.get("check_type") if isinstance(finding, Mapping) else getattr(finding, "check_type", None)
        if kind: types.append(str(kind))
    return bool(types), (types[0] if types else None), False

def run_suite(specs: Iterable[MutationSpec], targets: Mapping[str, Any] | Callable[[dict[str, Any]], Any]) -> list[MutationResult]:
    target_map = targets if isinstance(targets, Mapping) else {"checker": targets}
    results = []
    for spec in specs:
        detected_by = None; classified = None; extractor_failed = False
        for name, target in target_map.items():
            detected, classified, failed = _target_findings(target, spec.mutated_claim)
            extractor_failed = extractor_failed or failed
            if detected:
                detected_by = str(name); break
        results.append(MutationResult(spec, detected_by, detected_by is not None, 0, classified, extractor_failed))
    return results

def _prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else None; recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}

def compute_metrics(results: Iterable[MutationResult]) -> FinFuzzReport:
    rows = list(results); positives = [r for r in rows if r.spec.expected_detection]; negatives = [r for r in rows if not r.spec.expected_detection]
    tp = sum(r.detected for r in positives); fn = len(positives) - tp; fp = sum(r.detected for r in negatives)
    overall = _prf(tp, fp, fn); overall["false_positive_rate"] = fp / len(negatives) if negatives else None
    per: dict[str, dict[str, Any]] = {}
    for operator in sorted({r.spec.operator for r in rows}):
        group = [r for r in positives if r.spec.operator == operator]; detected = sum(r.detected for r in group)
        per[operator] = {"recall": detected / len(group) if group else None, "n": len(group), "detected": detected}
    extractor_failures = sum(r.extractor_failed for r in rows); checker_misses = sum((not r.detected) and (not r.extractor_failed) for r in positives)
    return FinFuzzReport("unassigned", overall, per, {}, {"extractor_failures": extractor_failures, "checker_misses": checker_misses}, [r.to_dict() for r in rows])

def run_finfuzz(suite_id: str, claims: Iterable[Any], operators: Iterable[str | MutationOperators], targets: Mapping[str, Any] | Callable[[dict[str, Any]], Any], holdout: Iterable[Any] | None = None, *, seed: int = 42) -> FinFuzzReport:
    specs = generate_mutation_specs(claims, operators, seed=seed); report = compute_metrics(run_suite(specs, targets))
    holdout_report = compute_metrics(run_suite(generate_mutation_specs(holdout or [], operators, seed=seed), targets)) if holdout else None
    return FinFuzzReport(suite_id, report.overall, report.per_error_type, holdout_report.overall if holdout_report else {}, report.extractor_vs_checker, report.results, seed)
