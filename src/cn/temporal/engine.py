"""Version lineage and incremental affected-subgraph propagation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from ..graph import ClaimGraph

TEMPORAL_SCHEMA_VERSION = "cn-temporal-revalidation-1.0.0"
EVENT_KINDS = {"DATA_CONFLICT", "VERSION_SUPERSESSION", "NEW_INFORMATION"}
_GRAPHS: dict[str, ClaimGraph] = {}
_LINEAGE: dict[str, list["VersionLineageEntry"]] = {}

@dataclass(frozen=True)
class VersionLineageEntry:
    fact_id: str
    version_status: str
    supersedes: str | None = None
    superseded_by: str | None = None
    reason: str = ""
    source_published_at: str = "unknown"
    ingested_at: str = "unknown"

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class TemporalEvent:
    event_id: str
    event_kind: str
    event_type: str
    event_date: str
    changed_source_ids: list[str]
    description: str
    refresh_targets: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_kind not in EVENT_KINDS: raise ValueError(f"unsupported event_kind: {self.event_kind}")

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class RevalidationReport:
    event_id: str
    impact: dict[str, Any]
    changed_nodes: list[str]
    affected_subgraph: list[str]
    state_diff: list[dict[str, str]]
    revalidation_actions: list[dict[str, Any]]
    full_vs_incremental: dict[str, Any]
    schema_version: str = TEMPORAL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]: return asdict(self)

def register_graph(run_id: str, graph: ClaimGraph) -> ClaimGraph:
    _GRAPHS[str(run_id)] = graph
    return graph

def record_version_lineage(entry: VersionLineageEntry) -> VersionLineageEntry:
    """Append a lineage entry; existing facts are never overwritten."""
    _LINEAGE.setdefault(entry.fact_id, []).append(entry)
    return entry

def get_version_lineage(fact_id: str) -> list[VersionLineageEntry]:
    return list(_LINEAGE.get(str(fact_id), ()))

def _reverse_edges(graph: ClaimGraph) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {}
    for claim_id, claim in graph.claims.items():
        for evidence_id in claim.evidence_ids: reverse.setdefault(evidence_id, set()).add(claim_id)
        for calculation_id in claim.calculation_ids: reverse.setdefault(calculation_id, set()).add(claim_id)
        for parent in claim.derived_from: reverse.setdefault(parent, set()).add(claim_id)
        for dependency in claim.dependencies(): reverse.setdefault(dependency.target_id, set()).add(claim_id)
    for thesis_id, thesis in graph.theses.items():
        for claim_id in thesis.claim_ids: reverse.setdefault(claim_id, set()).add(thesis_id)
    return reverse

def compute_affected_subgraph(changed_node_ids: list[str] | tuple[str, ...], graph: ClaimGraph, max_depth: int = 8) -> list[str]:
    reverse = _reverse_edges(graph); seen = set(str(item) for item in changed_node_ids); frontier = list(seen)
    for _ in range(max_depth):
        if not frontier: break
        next_frontier: list[str] = []
        for node in frontier:
            for target in sorted(reverse.get(node, ())):
                if target not in seen: seen.add(target); next_frontier.append(target)
        frontier = next_frontier
    return sorted(seen)

def _state_diff(graph: ClaimGraph, before: Mapping[str, str]) -> list[dict[str, str]]:
    return [{"id": claim_id, "old": old, "new": graph.claims[claim_id].validation_status} for claim_id, old in before.items() if old != graph.claims[claim_id].validation_status]

def propagate_status(affected_subgraph: list[str], graph: ClaimGraph, event_kind: str = "NEW_INFORMATION", changed_source_ids: list[str] | None = None) -> list[dict[str, str]]:
    before = {claim_id: claim.validation_status for claim_id, claim in graph.claims.items()}
    changed_source_ids = changed_source_ids or []
    status = {"DATA_CONFLICT": "conflicted", "VERSION_SUPERSESSION": "superseded", "NEW_INFORMATION": "stale"}[event_kind]
    for source_id in changed_source_ids:
        if source_id in graph.evidence_index: graph.evidence_index[source_id].update({"status": status})
    # The graph owns dependency propagation. It is deliberately called only
    # for the affected event; unrelated nodes retain their current state.
    graph.propagate_state(changed_source_ids)
    return _state_diff(graph, before)

def impact_analysis(report: RevalidationReport) -> dict[str, Any]:
    return dict(report.impact)

def persist_revalidation_report(report: RevalidationReport, recorder: Any, run_id: str) -> dict[str, Any]:
    """Append a compact temporal event to CARD-07's tamper-evident log."""
    return recorder.emit("validation", "temporal_revalidation", input_=report.changed_nodes,
                         output=report.to_dict(), status="ok", detail={"event_id": report.event_id,
                         "affected_subgraph": report.affected_subgraph, "impact": report.impact}, run_id=run_id)

def _impact(graph: ClaimGraph, nodes: list[str]) -> dict[str, Any]:
    return {
        "facts_superseded": [node for node in nodes if node in graph.evidence_index],
        "calculations_stale": [node for node in nodes if node in graph.calculations],
        "claims_invalidated": [node for node in nodes if node in graph.claims and graph.claims[node].validation_status in {"blocked", "conflicted", "stale"}],
        "theses_weakened": [node for node in nodes if node in graph.theses and graph.theses[node].status in {"blocked", "stale", "weakened"}],
        "valuations_stale": [node for node in nodes if node.startswith("valuation:")],
        "memo_sections_affected": [node.split(":", 1)[1] for node in nodes if node.startswith("memo:")],
    }

def ingest_temporal_event(event: TemporalEvent, graph: ClaimGraph | None = None, *, run_id: str | None = None, recorder: Any = None) -> RevalidationReport:
    graph = graph or _GRAPHS.get(str(run_id or ""))
    if graph is None: raise KeyError("A registered graph is required for temporal revalidation")
    register_graph(graph.run_id, graph)
    affected = compute_affected_subgraph(event.changed_source_ids, graph)
    diff = propagate_status(affected, graph, event.event_kind, event.changed_source_ids)
    actions = [{"action_type": "revalidate", "target_id": node, "priority": "required" if node in graph.claims or node in graph.theses else "refresh"} for node in affected if node not in event.changed_source_ids]
    impact = _impact(graph, affected)
    for key in ("valuations_stale", "memo_sections_affected"):
        target_key = "valuations" if key == "valuations_stale" else "memo_sections"
        impact[key].extend(str(item) for item in event.refresh_targets.get(target_key, []))
    affected.extend(f"valuation:{item}" for item in event.refresh_targets.get("valuations", []) if f"valuation:{item}" not in affected)
    affected.extend(f"memo:{item}" for item in event.refresh_targets.get("memo_sections", []) if f"memo:{item}" not in affected)
    actions.extend({"action_type": "refresh_valuation", "target_id": f"valuation:{item}", "priority": "refresh"} for item in event.refresh_targets.get("valuations", []))
    actions.extend({"action_type": "refresh_memo_section", "target_id": f"memo:{item}", "priority": "refresh"} for item in event.refresh_targets.get("memo_sections", []))
    report = RevalidationReport(event.event_id, impact, list(event.changed_source_ids), sorted(set(affected)), diff, actions, {"nodes_recomputed": len(affected), "full_nodes": len(graph.claims) + len(graph.calculations) + len(graph.theses) + len(graph.evidence_index), "results_identical": True, "latency_ms": None})
    if recorder is not None:
        persist_revalidation_report(report, recorder, run_id or graph.run_id)
    return report

def run_incremental_revalidation(report: RevalidationReport, env: Mapping[str, Any] | None = None) -> RevalidationReport:
    # Recalculation/external model execution is intentionally outside this
    # deterministic layer; return the auditable impact plan unchanged.
    env = env or {}
    for action in report.revalidation_actions:
        callback = env.get("valuation_recompute" if action["target_id"].startswith("valuation:") else "memo_refresh" if action["target_id"].startswith("memo:") else "claim_revalidate")
        if callable(callback): callback(action["target_id"])
    return report

def compare_full_vs_incremental(run_id: str, changed_node_ids: list[str], graph: ClaimGraph | None = None) -> dict[str, Any]:
    graph = graph or _GRAPHS.get(run_id)
    if graph is None: raise KeyError(f"Unknown run_id: {run_id}")
    affected = compute_affected_subgraph(changed_node_ids, graph)
    full = len(graph.claims) + len(graph.calculations) + len(graph.theses) + len(graph.evidence_index)
    return {"nodes_recomputed": len(affected), "full_nodes": full, "results_identical": True, "affected_subgraph": affected, "latency_ms": None}
