"""Typed, serializable contracts for user supplied research documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


DOCUMENT_SCHEMA_VERSION = "cn-document-1.0.0"


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    file_name: str
    document_type: str
    sha256: str
    ingested_at: str
    source: str
    status: str = "registered"
    symbol: Optional[str] = None
    fiscal_period: Optional[str] = None
    published_at: Optional[str] = None
    parser_name: Optional[str] = None
    parser_version: Optional[str] = None
    page_count: int = 0
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = DOCUMENT_SCHEMA_VERSION
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class SourceFragment:
    fragment_id: str
    document_id: str
    page_number: int
    text: str
    text_sha256: str
    extraction_method: str
    confidence: str
    bbox: Optional[tuple[float, float, float, float]] = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = list(self.bbox) if self.bbox is not None else None
        return payload


@dataclass(frozen=True)
class ExtractedFact:
    fact_id: str
    metric: str
    raw_value: float
    raw_unit: Optional[str]
    raw_currency: Optional[str]
    period: Optional[str]
    scope: Optional[str]
    source_fragment_id: str
    version: str = "AS_REPORTED"
    accounting_metric: Optional[str] = None
    extraction_status: str = "extracted"
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class ParseResult:
    document: DocumentRecord
    fragments: tuple[SourceFragment, ...] = ()
    facts: tuple[ExtractedFact, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "fragments": [fragment.to_dict() for fragment in self.fragments],
            "facts": [fact.to_dict() for fact in self.facts],
            "warnings": list(self.warnings),
        }
