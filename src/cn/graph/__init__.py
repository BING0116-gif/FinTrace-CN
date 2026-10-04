"""Claim-Evidence graph and deterministic dependency validation."""

from .graph import (
    Claim,
    ClaimGraph,
    Calculation,
    Dependency,
    RevalidationReport,
    Thesis,
    TraceTree,
    ValidationReport,
    build_graph,
    deactivate_evidence,
    revalidate,
    validate_graph,
)

__all__ = [
    "Claim", "ClaimGraph", "Calculation", "Dependency", "RevalidationReport", "Thesis",
    "TraceTree", "ValidationReport", "build_graph", "deactivate_evidence", "revalidate", "validate_graph",
]
