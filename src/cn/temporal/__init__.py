"""Deterministic temporal/version revalidation for A-share evidence graphs."""
from .engine import (
    RevalidationReport, TemporalEvent, VersionLineageEntry,
    compare_full_vs_incremental, compute_affected_subgraph,
    impact_analysis, ingest_temporal_event, propagate_status,
    register_graph, run_incremental_revalidation,
    get_version_lineage, record_version_lineage,
    persist_revalidation_report,
)

__all__ = [
    "VersionLineageEntry", "TemporalEvent", "RevalidationReport",
    "register_graph", "ingest_temporal_event", "compute_affected_subgraph",
    "propagate_status", "run_incremental_revalidation", "impact_analysis",
    "compare_full_vs_incremental",
    "record_version_lineage", "get_version_lineage",
    "persist_revalidation_report",
]
