"""Financial Claim Passport: proof-carrying claims with a standalone verifier.

The verifier is intentionally small and conservative. It consumes serialized
graph data, evidence metadata and calculation inputs; it never asks a model to
decide whether a number or citation is valid.
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from ..graph.graph import ClaimGraph, _RUN_GRAPHS

VERIFIER_VERSION = "cn-claim-passport-verifier-1.0.0"
PASSPORT_SCHEMA_VERSION = "cn-financial-proof-object-1.0.0"
STATUSES = {"VERIFIED", "DEGRADED", "STALE", "BLOCKED", "CONFLICTED"}

@dataclass(frozen=True)
class FinancialProofObject:
    claim_id: str
    claim_type: str
    claim_text: str
    economic_period: str = ""
    scope: str = ""
    version_status: str = "AS_REPORTED"
    source_proof: dict[str, Any] = field(default_factory=dict)
    accounting_context: dict[str, Any] = field(default_factory=dict)
    calculation_proof: dict[str, Any] = field(default_factory=dict)
    assumption_proof: dict[str, Any] = field(default_factory=dict)
    dependency_proof: dict[str, Any] = field(default_factory=dict)
    validation_proof: dict[str, Any] = field(default_factory=dict)
    integrity_proof: dict[str, Any] = field(default_factory=dict)

    def unsigned_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        integrity = dict(payload["integrity_proof"])
        integrity.pop("object_hash", None)
        payload["integrity_proof"] = integrity
        return payload

    def object_hash(self) -> str:
        raw = json.dumps(self.unsigned_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = PASSPORT_SCHEMA_VERSION
        payload["integrity_proof"] = dict(payload["integrity_proof"])
        payload["integrity_proof"]["object_hash"] = self.object_hash()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FinancialProofObject":
        allowed = {key: payload.get(key) for key in cls.__dataclass_fields__}
        return cls(**{key: (value if value is not None else {}) if key.endswith("_proof") else (value if value is not None else "") for key, value in allowed.items()})

@dataclass(frozen=True)
class VerificationResult:
    proof_id: str
    overall_status: str
    status_reasons: list[str]
    checks: list[dict[str, str]]
    verify_source_version: str = VERIFIER_VERSION
    verified_at: str = "unknown"

    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {"check": name, "status": status, "message": message}

def _result_status(checks: list[dict[str, str]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    statuses = {item["status"] for item in checks}
    if "blocked" in statuses:
        overall = "BLOCKED"
    elif "conflicted" in statuses:
        overall = "CONFLICTED"
    elif "stale" in statuses:
        overall = "STALE"
    elif "degraded" in statuses or "warning" in statuses:
        overall = "DEGRADED"
    else:
        overall = "VERIFIED"
    reasons.extend(item["message"] for item in checks if item["status"] not in {"pass", "skipped"})
    return overall, reasons

def verify_source(fpo: FinancialProofObject) -> dict[str, str]:
    source = fpo.source_proof or {}
    if not source.get("evidence_ids") and not source.get("document_id"):
        return _check("source", "blocked", "source proof is missing")
    evidence = source.get("evidence", {})
    if isinstance(evidence, list): evidence = {str(item.get("evidence_id")): item for item in evidence if isinstance(item, Mapping)}
    evidence_ids = {str(item) for item in source.get("evidence_ids", [])}
    present_ids = {str(key) for key in evidence} if isinstance(evidence, Mapping) else set()
    if evidence_ids and not evidence_ids.issubset(present_ids):
        return _check("source", "blocked", "one or more evidence IDs are missing")
    statuses = {str(item.get("status", "active")) for item in evidence.values()} if isinstance(evidence, Mapping) else set()
    if statuses & {"inactive", "blocked"}:
        return _check("source", "blocked", "required evidence is inactive or blocked")
    if statuses & {"conflicted", "unresolved"}:
        return _check("source", "conflicted", "source conflict is unresolved")
    if statuses & {"stale", "superseded"}:
        return _check("source", "stale", "source evidence is stale or superseded")
    path = source.get("document_path")
    expected = source.get("sha256")
    if path and expected:
        try: actual = sha256(Path(str(path)).read_bytes()).hexdigest()
        except OSError as exc: return _check("source", "blocked", f"document cannot be read: {exc}")
        if actual != str(expected): return _check("source", "blocked", "document hash mismatch")
    return _check("source", "pass", "source evidence exists and is active")

def verify_period(fpo: FinancialProofObject) -> dict[str, str]:
    period = fpo.economic_period or fpo.accounting_context.get("period")
    inputs = (fpo.calculation_proof or {}).get("inputs", [])
    periods = {str(item.get("period")) for item in inputs if isinstance(item, Mapping) and item.get("period")}
    if period and periods and periods != {str(period)}:
        return _check("period", "blocked", "calculation inputs use mixed economic periods")
    return _check("period", "pass", "economic period is consistent")

def verify_scope_unit(fpo: FinancialProofObject) -> dict[str, str]:
    context = fpo.accounting_context or {}
    inputs = (fpo.calculation_proof or {}).get("inputs", [])
    for key in ("scope", "unit", "currency"):
        expected = context.get(key) or (fpo.scope if key == "scope" else None)
        values = {str(item.get(key)) for item in inputs if isinstance(item, Mapping) and item.get(key) is not None}
        if expected and values and values != {str(expected)}:
            return _check("scope_unit", "blocked", f"mixed {key} in proof inputs")
    return _check("scope_unit", "pass", "scope, unit and currency are comparable")

def _safe_eval(expression: str, variables: Mapping[str, float]) -> float:
    tree = ast.parse(expression, mode="eval")
    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression): return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return float(node.value)
        if isinstance(node, ast.Name) and node.id in variables: return float(variables[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)): return (-1 if isinstance(node.op, ast.USub) else 1) * visit(node.operand)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            return left ** right
        raise ValueError("unsupported formula expression")
    return visit(tree)

def verify_calculation(fpo: FinancialProofObject, *, tolerance: float = 1e-6) -> dict[str, str]:
    proof = fpo.calculation_proof or {}
    if not proof: return _check("calculation", "skipped", "claim has no calculation proof")
    inputs = proof.get("inputs", [])
    if not inputs or proof.get("output", {}).get("value") is None or not proof.get("formula"):
        return _check("calculation", "blocked", "calculation proof is incomplete")
    variables = {}
    for index, item in enumerate(inputs):
        if not isinstance(item, Mapping) or item.get("value") is None: return _check("calculation", "blocked", "calculation input is missing")
        value = float(item["value"]); variables[f"input_{index}"] = value
        ref = str(item.get("ref", "")); variables[ref.replace("-", "_")] = value
    try: calculated = _safe_eval(str(proof["formula"]), variables)
    except (ValueError, ZeroDivisionError, SyntaxError) as exc: return _check("calculation", "blocked", f"formula cannot be evaluated: {exc}")
    expected = float(proof["output"]["value"])
    if abs(calculated - expected) > tolerance * max(1.0, abs(calculated), abs(expected)):
        return _check("calculation", "blocked", "deterministic calculation output mismatch")
    return _check("calculation", "pass", "calculation output re-computed")

def verify_dependencies(fpo: FinancialProofObject, *, graph: ClaimGraph | None = None) -> dict[str, str]:
    proof = fpo.dependency_proof or {}; deps = proof.get("upstream_claims", proof.get("dependencies", []))
    if not deps: return _check("dependencies", "skipped", "claim has no upstream dependencies")
    if graph is None: return _check("dependencies", "blocked", "dependency graph is unavailable")
    for dep in deps:
        target = str(dep.get("target_id", dep.get("claim_id", "")))
        role = str(dep.get("role", "REQUIRED")).upper()
        target_type = str(dep.get("target_type", "claim"))
        if target_type != "claim":
            continue
        claim = graph.claims.get(target)
        if role == "REQUIRED" and (claim is None or claim.validation_status in {"blocked", "conflicted"}):
            return _check("dependencies", "blocked", f"required dependency is blocked: {target}")
        if role == "REQUIRED" and claim.validation_status == "stale": return _check("dependencies", "stale", f"required dependency is stale: {target}")
        if role == "SUPPORTING" and (claim is None or claim.validation_status in {"blocked", "stale", "conflicted"}): return _check("dependencies", "degraded", f"supporting dependency is unavailable: {target}")
    return _check("dependencies", "pass", "claim dependencies are valid")

def verify_assumptions(fpo: FinancialProofObject) -> dict[str, str]:
    rows = (fpo.assumption_proof or {}).get("assumptions", [])
    if not rows: return _check("assumptions", "skipped", "claim has no assumptions")
    if any(str(row.get("status", "active")).lower() in {"expired", "invalid", "blocked"} for row in rows): return _check("assumptions", "degraded", "one or more assumptions are no longer active")
    return _check("assumptions", "pass", "assumptions are active")

def verify_validator_state(fpo: FinancialProofObject) -> dict[str, str]:
    result = str((fpo.validation_proof or {}).get("result", "pass")).lower()
    if result in {"blocked", "invalid", "failed"}: return _check("validator", "blocked", "validator state does not support claim")
    if result in {"conflicted", "conflict"}: return _check("validator", "conflicted", "validator reports unresolved conflict")
    if result in {"warning", "degraded"}: return _check("validator", "degraded", "validator reports a non-blocking warning")
    return _check("validator", "pass", "validator state supports claim")

def verify_fpo(fpo: FinancialProofObject, *, graph: ClaimGraph | None = None) -> VerificationResult:
    checks = [verify_source(fpo), verify_period(fpo), verify_scope_unit(fpo), verify_calculation(fpo), verify_dependencies(fpo, graph=graph), verify_assumptions(fpo), verify_validator_state(fpo)]
    # Hash mismatch is an integrity failure, checked independently of the proof payload.
    supplied = (fpo.integrity_proof or {}).get("object_hash")
    if supplied and supplied != fpo.object_hash(): checks.append(_check("integrity", "blocked", "proof hash mismatch"))
    else: checks.append(_check("integrity", "pass", "proof hash is reproducible"))
    status, reasons = _result_status(checks)
    return VerificationResult(f"proof-{fpo.claim_id}", status, reasons, checks)

def _claim_to_fpo(graph: ClaimGraph, claim_id: str) -> FinancialProofObject:
    claim = graph.claims.get(claim_id)
    if claim is None: raise KeyError(f"Unknown claim_id: {claim_id}")
    calcs = [graph.calculations[item] for item in claim.calculation_ids if item in graph.calculations]
    calc = calcs[0].to_dict() if calcs else {}
    evidence = {eid: dict(graph.evidence_index[eid]) for eid in claim.evidence_ids if eid in graph.evidence_index}
    periods = {str(item.get("period")) for item in evidence.values() if item.get("period")}
    context = {key: next((item.get(key) for item in evidence.values() if item.get(key) is not None), None) for key in ("scope", "unit", "currency")}
    context["period"] = next(iter(periods), "")
    deps = [dep.to_dict() for dep in claim.dependencies()]
    integrity = {"run_id": graph.run_id, "audit_chain_ref": graph.run_id}
    return FinancialProofObject(claim.claim_id, claim.claim_type, claim.text, context.get("period", ""), context.get("scope") or "", claim.verification_status or "AS_REPORTED", {"evidence_ids": list(claim.evidence_ids), "evidence": evidence}, context, calc, {"assumption_ids": list(claim.assumption_ids)}, {"upstream_claims": deps}, {"result": claim.validation_status}, integrity)

def build_financial_proof_object(claim_id: str, run_id: str) -> FinancialProofObject:
    graph = _RUN_GRAPHS.get(run_id)
    if graph is None: raise KeyError(f"Unknown run_id: {run_id}")
    return _claim_to_fpo(graph, claim_id)

def verify_claim(claim_id: str, run_id: str | None = None) -> VerificationResult:
    if run_id is None:
        matches = [graph for graph in _RUN_GRAPHS.values() if claim_id in graph.claims]
        if len(matches) != 1: raise KeyError(f"Claim is not uniquely registered: {claim_id}")
        graph = matches[0]
    else:
        graph = _RUN_GRAPHS.get(run_id)
        if graph is None: raise KeyError(f"Unknown run_id: {run_id}")
    return verify_fpo(_claim_to_fpo(graph, claim_id), graph=graph)
