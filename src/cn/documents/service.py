"""Service boundary joining registration, parsing, and document evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..evidence import EvidenceLedger, EvidenceRecord
from .parser import DocumentParser
from .registry import DocumentRegistry
from .schema import DocumentRecord, ParseResult


class DocumentService:
    def __init__(self, *, registry: DocumentRegistry | None = None, parser: DocumentParser | None = None):
        self.registry = registry or DocumentRegistry()
        self.parser = parser or DocumentParser()
        self._paths: dict[str, Path] = {}
        self._records: dict[str, DocumentRecord] = {}
        self._results: dict[str, ParseResult] = {}

    def register(self, path: str | Path, **metadata: Any) -> DocumentRecord:
        record = self.registry.register(path, **metadata)
        self._paths[record.document_id] = Path(path)
        self._records[record.document_id] = record
        return record

    def parse(self, document_id: str) -> ParseResult:
        if document_id not in self._paths:
            raise KeyError(f"Unknown document_id: {document_id}")
        result = self.parser.parse(self._registered_record(document_id), self._paths[document_id])
        self._results[document_id] = result
        return result

    def get_result(self, document_id: str) -> ParseResult:
        try:
            return self._results[document_id]
        except KeyError as exc:
            raise KeyError(f"Document has not been parsed: {document_id}") from exc

    def get_record(self, document_id: str) -> DocumentRecord:
        if document_id in self._results:
            return self._results[document_id].document
        try:
            return self._records[document_id]
        except KeyError as exc:
            raise KeyError(f"Unknown document_id: {document_id}") from exc

    def facts_as_evidence(self, document_id: str) -> tuple[EvidenceRecord, ...]:
        """Register only candidates with explicit accounting metadata.

        The parser may identify a number, but it never invents missing scope or
        period.  Candidates without enough metadata remain candidates and are
        intentionally not upgraded to financial Evidence.
        """
        result = self.get_result(document_id)
        if not result.document.symbol:
            return ()
        ledger = EvidenceLedger(snapshot_id=f"document_{document_id}")
        created: list[EvidenceRecord] = []
        for fact in result.facts:
            if not fact.period or not fact.raw_unit or not fact.raw_currency:
                continue
            created.append(ledger.add_fact(
                evidence_id=fact.fact_id, symbol=result.document.symbol,
                metric=fact.accounting_metric or fact.metric, value=fact.raw_value, currency=fact.raw_currency,
                unit=fact.raw_unit, fiscal_period=fact.period, period_basis=fact.period,
                published_at=result.document.published_at,
                available_at=result.document.published_at, provider=f"document:{document_id}",
                field_path=f"fragments.{fact.source_fragment_id}",
                scope=fact.scope, version=fact.version,
            ))
        return tuple(created)

    def _registered_record(self, document_id: str) -> DocumentRecord:
        path = self._paths[document_id]
        # Re-registering verifies the content hash before every parse.
        existing = self.registry.register(path)
        registered = self._records.get(document_id)
        if registered is None or registered.sha256 != existing.sha256:
            raise ValueError("Document content changed after registration; register it again.")
        return registered
