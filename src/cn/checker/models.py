from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


CHECKER_SCHEMA_VERSION = "cn-report-checker-1.0.0"


@dataclass(frozen=True)
class DraftClaim:
    claim_id: str
    sentence: str
    page: int | None = None
    metric: str | None = None
    period: str | None = None
    value: float | str | None = None
    unit: str | None = None
    growth: float | None = None
    valuation_multiple: str | None = None
    source_reference: str | None = None
    claim_type: str = "factual"
    scope: str | None = None
    evidence_ids: tuple[str, ...] = ()
    temporal_status: str = "historical"

    @property
    def mapped_claim_type(self) -> str:
        return {"factual": "fact", "valuation": "inference", "causal": "inference", "opinion": "opinion"}.get(self.claim_type, self.claim_type)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_ids"] = list(self.evidence_ids)
        return payload


@dataclass(frozen=True)
class Finding:
    claim_id: str
    check_type: str
    severity: str
    original: str
    expected: str
    evidence_ids: tuple[str, ...] = ()
    suggestion: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_ids"] = list(self.evidence_ids)
        payload["schema_version"] = CHECKER_SCHEMA_VERSION
        return payload
