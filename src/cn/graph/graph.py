"""Serializable Claim → Calculation → Evidence graph with fail-closed states."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Iterable, Mapping


GRAPH_SCHEMA_VERSION = "cn-claim-evidence-graph-1.0.0"
ROLES = {"REQUIRED", "SUPPORTING", "OPTIONAL"}
CLAIM_TYPES = {"fact", "inference", "opinion"}
CLAIM_STATES = {"pending", "supported", "unsupported", "blocked", "stale", "conflicted"}


@dataclass
class Dependency:
    role: str
    target_id: str
    target_type: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class Claim:
    claim_id: str
    claim_type: str
    temporal_status: str
    text: str
    evidence_ids: list[str] = field(default_factory=list)
    calculation_ids: list[str] = field(default_factory=list)
    derived_from: list[str] = field(default_factory=list)
    dependency_metadata: list[dict[str, str]] = field(default_factory=list)
    verification_status: str = "UNVERIFIABLE"
    validation_status: str = "pending"
    rationale: str | None = None
    assumption_ids: list[str] = field(default_factory=list)

    def dependencies(self) -> list[Dependency]:
        return [Dependency(str(item.get("role", "REQUIRED")).upper(), str(item["target_id"]), str(item.get("target_type", "evidence"))) for item in self.dependency_metadata]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Thesis:
    thesis_id: str
    statement: str
    claim_ids: list[str]
    dependency_roles: dict[str, str]
    status: str = "supported"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Calculation:
    calculation_id: str
    formula: str
    formula_version: str
    inputs: list[dict[str, Any]]
    output: dict[str, Any]
    code_version: str
    validation_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceTree:
    claim: dict[str, Any]
    calculations: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    children: list["TraceTree"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"claim": self.claim, "calculations": self.calculations, "evidence": self.evidence, "children": [child.to_dict() for child in self.children]}


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    orphan_claims: tuple[str, ...] = ()
    unsupported_calculations: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "orphan_claims": list(self.orphan_claims), "unsupported_calculations": list(self.unsupported_calculations), "missing_evidence": list(self.missing_evidence), "errors": list(self.errors)}


@dataclass(frozen=True)
class RevalidationReport:
    changed_evidence_ids: tuple[str, ...]
    impacted_claim_ids: tuple[str, ...]
    state_diff: tuple[dict[str, str], ...]
    thesis_diff: tuple[dict[str, str], ...] = ()
    coverage_dropped: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"changed_evidence_ids": list(self.changed_evidence_ids), "impacted_claim_ids": list(self.impacted_claim_ids), "state_diff": list(self.state_diff), "thesis_diff": list(self.thesis_diff), "coverage_dropped": list(self.coverage_dropped)}


class ClaimGraph:
    def __init__(self, run_id: str, *, claims: Iterable[Claim] = (), theses: Iterable[Thesis] = (), calculations: Iterable[Calculation] = (), evidence_index: Mapping[str, Mapping[str, Any]] | None = None):
        self.run_id = run_id
        self.claims = {item.claim_id: item for item in claims}
        self.theses = {item.thesis_id: item for item in theses}
        self.calculations = {item.calculation_id: item for item in calculations}
        self.evidence_index = {str(key): dict(value) for key, value in (evidence_index or {}).items()}
        self._assert_no_cycles()

    def _assert_no_cycles(self) -> None:
        edges = {claim_id: set(claim.derived_from) | {dep.target_id for dep in claim.dependencies() if dep.target_type == "claim"} for claim_id, claim in self.claims.items()}
        visiting: set[str] = set(); visited: set[str] = set()
        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError(f"claim_cycle:{node}")
            if node in visited:
                return
            visiting.add(node)
            for parent in edges.get(node, ()):
                if parent in self.claims:
                    visit(parent)
            visiting.remove(node); visited.add(node)
        for node in edges:
            visit(node)

    def trace(self, claim_id: str) -> TraceTree:
        if claim_id not in self.claims:
            raise KeyError(f"Unknown claim_id: {claim_id}")
        claim = self.claims[claim_id]
        calculations = [self.calculations[item] for item in claim.calculation_ids if item in self.calculations]
        evidence_ids = list(claim.evidence_ids)
        for calculation in calculations:
            evidence_ids.extend(str(item.get("ref")) for item in calculation.inputs if item.get("ref") in self.evidence_index)
        evidence = [dict(self.evidence_index[item], evidence_id=item) for item in dict.fromkeys(evidence_ids) if item in self.evidence_index]
        children = [self.trace(parent) for parent in claim.derived_from if parent in self.claims]
        return TraceTree(claim.to_dict(), [item.to_dict() for item in calculations], evidence, children)

    def detect_orphan_claims(self) -> list[str]:
        return sorted(item.claim_id for item in self.claims.values() if item.claim_type == "fact" and not item.evidence_ids)

    def detect_unsupported_calculations(self) -> list[str]:
        missing: list[str] = []
        for calculation in self.calculations.values():
            for item in calculation.inputs:
                ref = str(item.get("ref", ""))
                if ref not in self.evidence_index and ref not in self.calculations:
                    missing.append(calculation.calculation_id)
                    break
        return sorted(set(missing))

    def detect_missing_evidence(self) -> list[str]:
        missing: set[str] = set()
        for claim in self.claims.values():
            missing.update(item for item in claim.evidence_ids if item not in self.evidence_index)
            for dependency in claim.dependencies():
                if dependency.target_type == "evidence" and dependency.target_id not in self.evidence_index:
                    missing.add(dependency.target_id)
        return sorted(missing)

    def validate(self) -> ValidationReport:
        errors: list[str] = []
        for claim in self.claims.values():
            if claim.claim_type not in CLAIM_TYPES:
                errors.append(f"invalid_claim_type:{claim.claim_id}")
            if claim.validation_status not in CLAIM_STATES:
                errors.append(f"invalid_claim_status:{claim.claim_id}")
            if claim.claim_type == "fact" and not claim.evidence_ids:
                errors.append(f"fact_without_evidence:{claim.claim_id}")
            if claim.claim_type == "inference" and not claim.derived_from:
                errors.append(f"inference_without_derived_from:{claim.claim_id}")
            if claim.claim_type == "opinion" and not claim.assumption_ids and "主观" not in (claim.rationale or "") and "assumption" not in (claim.rationale or "").lower():
                errors.append(f"opinion_without_assumption:{claim.claim_id}")
            for dependency in claim.dependencies():
                if dependency.role not in ROLES:
                    errors.append(f"invalid_dependency_role:{claim.claim_id}:{dependency.role}")
                if dependency.target_type not in {"claim", "evidence", "calculation", "assumption"}:
                    errors.append(f"invalid_dependency_type:{claim.claim_id}:{dependency.target_type}")
                elif dependency.target_type == "claim" and dependency.target_id not in self.claims:
                    errors.append(f"missing_claim_dependency:{claim.claim_id}:{dependency.target_id}")
                elif dependency.target_type == "calculation" and dependency.target_id not in self.calculations:
                    errors.append(f"missing_calculation_dependency:{claim.claim_id}:{dependency.target_id}")
            errors.extend(f"missing_derived_from:{claim.claim_id}:{parent}" for parent in claim.derived_from if parent not in self.claims)
            errors.extend(f"missing_calculation:{claim.claim_id}:{calculation_id}" for calculation_id in claim.calculation_ids if calculation_id not in self.calculations)
        orphan = self.detect_orphan_claims()
        unsupported = self.detect_unsupported_calculations()
        missing = self.detect_missing_evidence()
        return ValidationReport(not (errors or orphan or unsupported or missing), tuple(orphan), tuple(unsupported), tuple(missing), tuple(sorted(set(errors))))

    def propagate_state(self, changed_ids: Iterable[str] = ()) -> list[dict[str, str]]:
        changed = set(changed_ids)
        old_states = {claim_id: claim.validation_status for claim_id, claim in self.claims.items()}
        # Evidence with status inactive/blocked is unavailable; superseded is stale.
        unavailable = {key for key, value in self.evidence_index.items() if value.get("status") in {"inactive", "blocked", "conflicted"}}
        stale = {key for key, value in self.evidence_index.items() if value.get("status") in {"stale", "superseded"}}
        for _ in range(max(1, len(self.claims))):
            changed_state = False
            for claim in self.claims.values():
                new_state = "supported" if claim.evidence_ids or claim.derived_from else claim.validation_status
                required = [dep for dep in claim.dependencies() if dep.role == "REQUIRED"]
                if not required:
                    required = [Dependency("REQUIRED", item, "evidence") for item in claim.evidence_ids] + [Dependency("REQUIRED", item, "claim") for item in claim.derived_from]
                if any((dep.target_type == "evidence" and dep.target_id in unavailable) or (dep.target_type == "claim" and dep.target_id in self.claims and self.claims[dep.target_id].validation_status in {"blocked", "conflicted"}) for dep in required):
                    new_state = "blocked"
                elif any((dep.target_type == "evidence" and dep.target_id in stale) or (dep.target_type == "claim" and dep.target_id in self.claims and self.claims[dep.target_id].validation_status == "stale") for dep in required):
                    new_state = "stale"
                if new_state != claim.validation_status:
                    claim.validation_status = new_state
                    changed_state = True
            if not changed_state:
                break
        diffs = [{"id": claim_id, "old": old, "new": self.claims[claim_id].validation_status} for claim_id, old in old_states.items() if old != self.claims[claim_id].validation_status]
        thesis_diffs: list[dict[str, str]] = []
        for thesis in self.theses.values():
            old = thesis.status
            required_ids = [item for item in thesis.claim_ids if thesis.dependency_roles.get(item, "REQUIRED") == "REQUIRED"]
            supporting_ids = [item for item in thesis.claim_ids if thesis.dependency_roles.get(item) == "SUPPORTING"]
            states = {item: self.claims[item].validation_status for item in thesis.claim_ids if item in self.claims}
            if any(states.get(item) in {"blocked", "conflicted"} for item in required_ids):
                thesis.status = "blocked"
            elif any(states.get(item) == "stale" for item in required_ids):
                thesis.status = "stale"
            elif any(states.get(item) in {"blocked", "stale", "conflicted"} for item in supporting_ids):
                thesis.status = "weakened"
            else:
                thesis.status = "supported"
            if thesis.status != old:
                thesis_diffs.append({"id": thesis.thesis_id, "old": old, "new": thesis.status})
        return diffs + thesis_diffs

    def export_json(self) -> dict[str, Any]:
        return {"schema_version": GRAPH_SCHEMA_VERSION, "run_id": self.run_id, "claims": {key: item.to_dict() for key, item in self.claims.items()}, "theses": {key: item.to_dict() for key, item in self.theses.items()}, "calculations": {key: item.to_dict() for key, item in self.calculations.items()}, "evidence_index": self.evidence_index}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ClaimGraph":
        claims = [Claim(**value) for value in (payload.get("claims") or {}).values()]
        theses = [Thesis(**value) for value in (payload.get("theses") or {}).values()]
        calculations = [Calculation(**value) for value in (payload.get("calculations") or {}).values()]
        return cls(str(payload["run_id"]), claims=claims, theses=theses, calculations=calculations, evidence_index=payload.get("evidence_index") or {})


_RUN_GRAPHS: dict[str, ClaimGraph] = {}


def build_graph(run_id: str, *, claims: Iterable[Claim] = (), theses: Iterable[Thesis] = (), calculations: Iterable[Calculation] = (), evidence_index: Mapping[str, Mapping[str, Any]] | None = None) -> ClaimGraph:
    graph = ClaimGraph(run_id, claims=claims, theses=theses, calculations=calculations, evidence_index=evidence_index)
    _RUN_GRAPHS[run_id] = graph
    return graph


def validate_graph(graph: ClaimGraph) -> ValidationReport:
    return graph.validate()


def deactivate_evidence(run_id: str, evidence_id: str, reason: str) -> str:
    graph = _RUN_GRAPHS[run_id]
    if evidence_id not in graph.evidence_index:
        raise KeyError(f"Unknown evidence_id: {evidence_id}")
    graph.evidence_index[evidence_id].update({"status": "inactive", "inactive_reason": reason})
    report = revalidate(run_id, [evidence_id])
    return ",".join(report.impacted_claim_ids)


def revalidate(run_id: str, changed_evidence_ids: Iterable[str] | None = None) -> RevalidationReport:
    graph = _RUN_GRAPHS[run_id]
    changed = tuple(changed_evidence_ids or ())
    before = {item.claim_id: item.validation_status for item in graph.claims.values()}
    before_theses = {item.thesis_id: item.status for item in graph.theses.values()}
    graph.propagate_state(changed)
    diff = tuple({"id": claim_id, "old": old, "new": graph.claims[claim_id].validation_status} for claim_id, old in before.items() if old != graph.claims[claim_id].validation_status)
    impacted = tuple(item["id"] for item in diff)
    coverage = tuple(claim_id for claim_id, claim in graph.claims.items() if any(dep.role == "SUPPORTING" and dep.target_id in changed for dep in claim.dependencies()))
    thesis_diff = tuple({"id": thesis_id, "old": old, "new": graph.theses[thesis_id].status} for thesis_id, old in before_theses.items() if old != graph.theses[thesis_id].status)
    return RevalidationReport(changed, impacted, diff, thesis_diff, coverage)
