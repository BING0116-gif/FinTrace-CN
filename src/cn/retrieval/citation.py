"""Citation validation and delayed evidence registration."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
from typing import Iterable, Mapping

from .bm25 import CorpusChunk


class Citation(str, Enum):
    QUOTE = "quote"
    PARAPHRASE = "paraphrase"
    INFERENCE = "inference"
    quote = "quote"
    paraphrase = "paraphrase"
    inference = "inference"


class CitationError(ValueError):
    pass


@dataclass(frozen=True)
class CitationRecord:
    citation_id: str
    chunk_id: str
    citation_type: Citation
    span: str
    derived_from: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["citation_type"] = self.citation_type.value
        payload["derived_from"] = list(self.derived_from)
        return payload


def cite_chunk(chunk_id: str, citation_type: Citation | str, span: str, *, derived_from: Iterable[str] = ()) -> str:
    """Create a citation token; this does not create an Evidence record."""
    kind = Citation(citation_type)
    if not str(chunk_id).strip() or not str(span).strip():
        raise CitationError("chunk_id and span are required")
    parents = tuple(str(item) for item in derived_from)
    if kind is Citation.INFERENCE and not parents:
        raise CitationError("inference citation requires derived_from")
    digest = hashlib.sha256(f"{chunk_id}|{kind.value}|{span}|{'|'.join(parents)}".encode("utf-8")).hexdigest()[:16]
    return f"citation_{digest}"


def validate_citation(record: CitationRecord, chunks: Mapping[str, CorpusChunk] | Iterable[CorpusChunk]) -> bool:
    lookup = chunks if isinstance(chunks, Mapping) else {chunk.chunk_id: chunk for chunk in chunks}
    chunk = lookup.get(record.chunk_id)
    if chunk is None:
        raise CitationError(f"Unknown chunk_id: {record.chunk_id}")
    if record.citation_type is Citation.QUOTE and record.span not in chunk.text:
        raise CitationError("quote span is not an exact substring of chunk text")
    if record.citation_type is Citation.PARAPHRASE and not record.chunk_id:
        raise CitationError("paraphrase citation requires chunk_id")
    if record.citation_type is Citation.INFERENCE and not record.derived_from:
        raise CitationError("inference citation requires derived_from")
    return True


class CitationStore:
    """Keeps selected citations separate from unselected retrieval chunks."""
    def __init__(self, chunks: Iterable[CorpusChunk] = ()):
        self._chunks = {chunk.chunk_id: chunk for chunk in chunks}
        self._citations: dict[str, CitationRecord] = {}

    def cite(self, chunk_id: str, citation_type: Citation | str, span: str, *, derived_from: Iterable[str] = ()) -> CitationRecord:
        parents = tuple(derived_from)
        record = CitationRecord(cite_chunk(chunk_id, citation_type, span, derived_from=parents), chunk_id, Citation(citation_type), span, parents)
        validate_citation(record, self._chunks)
        self._citations[record.citation_id] = record
        return record

    def register(self, citation_id: str) -> str:
        """Return the retrieval evidence ID only for an existing citation."""
        record = self._citations.get(citation_id)
        if record is None:
            raise CitationError(f"Unknown citation_id: {citation_id}")
        return f"retrieval_{record.chunk_id}"

    def records(self) -> tuple[CitationRecord, ...]:
        return tuple(self._citations.values())

    def evidence_ids(self) -> tuple[str, ...]:
        """Evidence IDs exist only for explicitly cited chunks."""
        return tuple(dict.fromkeys(f"retrieval_{record.chunk_id}" for record in self._citations.values()))

    def to_dict(self) -> dict[str, object]:
        return {"citations": [record.to_dict() for record in self.records()], "evidence_ids": list(self.evidence_ids())}
