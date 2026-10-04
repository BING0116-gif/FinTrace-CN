"""Fail-closed structural fragility analysis for ClaimGraph theses.

This module reports graph structure, not an investment score. It never invents
thresholds and never uses an LLM to rank a dependency.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import product
from typing import Any, Iterable, Mapping

from ..graph import ClaimGraph

FRAGILITY_SCHEMA_VERSION = "cn-thesis-fragility-1.0.0"
THRESHOLD_SOURCES = {"public_assumption", "analyst_input", "model_constraint"}

@dataclass(frozen=True)
class MonitoringPlan:
    dependency: str
    observable_kpi_event: str
    trigger_condition: str
    affected_claims: list[str]
    revalidation_action: str

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class FragilityReport:
    thesis_id: str
    critical_dependencies: list[dict[str, Any]]
    required_dependencies: list[dict[str, Any]]
    minimal_cut_sets: list[list[str]]
    numeric_thresholds: list[dict[str, Any]]
    unresolved_assumptions: list[dict[str, Any]]
    monitoring_metrics: list[dict[str, Any]]
    status: str = "complete"
    warnings: list[str] = field(default_factory=list)
    schema_version: str = FRAGILITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _required_claim_ids(graph: ClaimGraph, thesis_id: str) -> list[str]:
    thesis = graph.theses[thesis_id]
    return [cid for cid in thesis.claim_ids if thesis.dependency_roles.get(cid, "REQUIRED").upper() == "REQUIRED"]

def _claim_required_nodes(graph: ClaimGraph, claim_id: str, *, max_depth: int = 8, depth: int = 0) -> list[dict[str, str]]:
    if depth > max_depth or claim_id not in graph.claims: return []
    claim = graph.claims[claim_id]; rows = [{"node_id": claim_id, "node_type": "claim"}]
    deps = claim.dependencies()
    if not deps:
        # Multiple evidence IDs are alternative source paths; they are all
        # represented for criticality, while cut-set logic groups them as OR.
        rows.extend({"node_id": eid, "node_type": "evidence"} for eid in claim.evidence_ids)
    for dep in deps:
        if dep.role != "REQUIRED": continue
        rows.append({"node_id": dep.target_id, "node_type": dep.target_type})
        if dep.target_type == "claim": rows.extend(_claim_required_nodes(graph, dep.target_id, max_depth=max_depth, depth=depth + 1))
    rows.extend({"node_id": aid, "node_type": "assumption"} for aid in claim.assumption_ids)
    return rows

def identify_critical_nodes(graph: ClaimGraph, thesis_ids: Iterable[str]) -> list[dict[str, Any]]:
    thesis_ids = list(thesis_ids)
    counts: dict[tuple[str, str], set[str]] = {}
    for thesis_id in thesis_ids:
        if thesis_id not in graph.theses: continue
        for claim_id in _required_claim_ids(graph, thesis_id):
            for row in _claim_required_nodes(graph, claim_id):
                key = (row["node_id"], row["node_type"])
                counts.setdefault(key, set()).add(thesis_id)
    total = len(set(thesis_ids))
    output = []
    for (node_id, node_type), owners in sorted(counts.items()):
        output.append({"node_id": node_id, "node_type": node_type, "thesis_ids": sorted(owners), "required_path_count": len(owners), "is_single_point": total > 0 and len(owners) == total})
    return output

def detect_single_points_of_failure(critical_nodes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in critical_nodes if bool(row.get("is_single_point"))]

def _union_sets(left: list[frozenset[str]], right: list[frozenset[str]], max_sets: int) -> list[frozenset[str]]:
    merged = {a | b for a in left for b in right}
    # A superset is not minimal if a smaller cut already exists.
    minimal = [item for item in sorted(merged, key=lambda x: (len(x), sorted(x))) if not any(other < item for other in merged)]
    return minimal[:max_sets]

def _claim_cut_sets(graph: ClaimGraph, claim_id: str, depth: int, max_depth: int, max_sets: int) -> list[frozenset[str]]:
    if depth > max_depth or claim_id not in graph.claims: return [frozenset({claim_id})]
    claim = graph.claims[claim_id]; deps = [dep for dep in claim.dependencies() if dep.role == "REQUIRED"]
    if not deps:
        evidence = [frozenset({eid}) for eid in claim.evidence_ids]
        if not evidence: return [frozenset({claim_id})]
        # The claim itself can be invalidated directly; alternatively every
        # alternative evidence path must be removed.
        return [frozenset({claim_id}), frozenset().union(*evidence)]
    # A claim's required dependencies form an AND: failing any one fails claim.
    alternatives: list[frozenset[str]] = []
    for dep in deps:
        if dep.target_type == "claim": alternatives.extend(_claim_cut_sets(graph, dep.target_id, depth + 1, max_depth, max_sets))
        else: alternatives.append(frozenset({dep.target_id}))
    return _union_sets([frozenset()], alternatives, max_sets)

def compute_minimal_cut_sets(graph: ClaimGraph, thesis_id: str, max_depth: int = 8, max_sets: int = 20) -> list[list[str]]:
    if thesis_id not in graph.theses: raise KeyError(f"Unknown thesis_id: {thesis_id}")
    required = _required_claim_ids(graph, thesis_id)
    if not required: return []
    # Thesis required claims form an AND, so any required branch can fail it.
    cuts: set[frozenset[str]] = set()
    for claim_id in required: cuts.update(_claim_cut_sets(graph, claim_id, 0, max_depth, max_sets))
    minimal = [item for item in sorted(cuts, key=lambda x: (len(x), sorted(x))) if not any(other < item for other in cuts)]
    return [sorted(item) for item in minimal[:max_sets]]

def identify_fragile_assumptions(graph: ClaimGraph, assumptions: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    rows = list(assumptions.values()) if isinstance(assumptions, Mapping) else list(assumptions)
    by_id = {str(row.get("assumption_id", row.get("id", ""))): dict(row) for row in rows}
    used = {aid for claim in graph.claims.values() for aid in claim.assumption_ids}
    output = []
    for aid in sorted(used):
        row = dict(by_id.get(aid, {"assumption_id": aid, "status": "unresolved"}))
        row["assumption_id"] = aid
        if str(row.get("status", "unresolved")).lower() in {"unresolved", "expired", "invalid", "blocked"} or aid not in by_id:
            output.append(row)
    return output

def compute_numeric_fragility(graph: ClaimGraph, thresholds: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if not thresholds: return []
    output = []
    for item in thresholds:
        row = dict(item); source = str(row.get("source_type", ""))
        if source not in THRESHOLD_SOURCES: raise ValueError(f"unsupported threshold source_type: {source}")
        if row.get("current_value") is None or row.get("threshold") is None: raise ValueError("numeric threshold requires current_value and threshold")
        current, threshold = float(row["current_value"]), float(row["threshold"])
        direction = str(row.get("direction", "min"))
        distance = current - threshold if direction == "min" else threshold - current
        row["distance_to_invalidation"] = distance
        row["at_threshold"] = distance == 0
        output.append(row)
    return output

def generate_monitoring_plans(graph: ClaimGraph, report: FragilityReport) -> list[MonitoringPlan]:
    plans = []
    for row in report.critical_dependencies:
        node = row["node_id"]
        if row["node_type"] == "evidence":
            event, trigger = "来源披露或证据状态变化", "evidence status becomes stale, superseded, inactive, or conflicted"
        elif row["node_type"] == "assumption":
            event, trigger = "假设输入更新", "assumption expires or is revised"
        else:
            event, trigger = "上游 Claim 验证状态变化", "claim becomes blocked, stale, or conflicted"
        plans.append(MonitoringPlan(node, event, trigger, sorted(row.get("thesis_ids", [])), "revalidate affected claims and rebuild thesis fragility"))
    return plans

def build_fragility_report(graph: ClaimGraph, thesis_ids: Iterable[str] | str, thresholds: Iterable[Mapping[str, Any]] | None = None, assumptions: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = ()) -> FragilityReport:
    ids = [thesis_ids] if isinstance(thesis_ids, str) else list(thesis_ids)
    if len(ids) != 1: raise ValueError("build_fragility_report currently requires exactly one thesis_id")
    thesis_id = ids[0]
    critical = identify_critical_nodes(graph, ids)
    required = [row for row in critical if row.get("node_type") in {"claim", "evidence", "assumption"}]
    cuts = compute_minimal_cut_sets(graph, thesis_id)
    numeric = compute_numeric_fragility(graph, thresholds)
    unresolved = identify_fragile_assumptions(graph, assumptions)
    report = FragilityReport(thesis_id, critical, required, cuts, numeric, unresolved, [])
    plans = generate_monitoring_plans(graph, report)
    return FragilityReport(thesis_id, critical, required, cuts, numeric, unresolved, [plan.to_dict() for plan in plans], warnings=["single_thesis_analysis"] if len(ids) == 1 else [])
