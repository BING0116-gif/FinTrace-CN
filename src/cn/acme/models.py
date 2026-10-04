"""Serializable ACME result contracts; no model-generated values are accepted."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

ACME_SCHEMA_VERSION = "cn-acme-1.0.0"

@dataclass(frozen=True)
class TolerancePolicy:
    absolute: float = 1_000.0
    relative: float = 0.001

    def limit(self, *values: float) -> float:
        return max(self.absolute, self.relative * max((abs(float(v)) for v in values), default=0.0))

    def classify(self, residual: float, *values: float) -> str:
        residual = abs(float(residual))
        if residual == 0:
            return "passed"
        return "warning" if residual <= self.limit(*values) else "violated"

@dataclass(frozen=True)
class ConstraintViolation:
    violation_id: str
    constraint_family: str
    constraint_id: str
    inputs: list[dict[str, Any]]
    expected_value: float | None
    actual_value: float | None
    residual: float | None
    tolerance: float
    status: str
    source_refs: list[dict[str, Any]]
    severity: str = "warning"
    resolution_status: str = "opened"
    detected_at: str = "unknown"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload

@dataclass(frozen=True)
class CrossModalInconsistency:
    inconsistency_id: str
    metric: str
    values: dict[str, float | None]
    computed_value: float | None
    conflict_type: str
    resolution_status: str = "unresolved"
    source_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class IntegrityReport:
    document_id: str
    constraint_families_checked: list[str]
    totals: dict[str, int]
    violations: list[ConstraintViolation]
    cross_modal: list[CrossModalInconsistency]
    review_queue: list[str]
    schema_version: str = ACME_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "constraint_families_checked": list(self.constraint_families_checked),
            "totals": dict(self.totals),
            "violations": [v.to_dict() for v in self.violations],
            "cross_modal": [v.to_dict() for v in self.cross_modal],
            "review_queue": list(self.review_queue),
        }
