"""Small, dependency-light BM25 implementation.

The constants are the conventional Okapi BM25 defaults (k1=1.5, b=0.75).
Tokenisation deliberately has a deterministic fallback so offline snapshots do
not depend on an installed search service or a mutable model.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import math
import re
from typing import Iterable, Sequence


K1 = 1.5
B = 0.75
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenise Chinese characters and alphanumeric runs reproducibly."""
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(str(text or "").lower()):
        value = match.group(0)
        if len(value) == 1 and "\u4e00" <= value <= "\u9fff":
            tokens.append(value)
        else:
            tokens.append(value)
    return tuple(tokens)


@dataclass(frozen=True)
class CorpusChunk:
    chunk_id: str
    document_id: str
    page: int | None
    section: str | None
    text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SearchHit:
    chunk: CorpusChunk
    score: float
    mode: str
    rank: int

    def to_dict(self) -> dict[str, object]:
        return {"chunk": self.chunk.to_dict(), "score": self.score, "mode": self.mode, "rank": self.rank}


class Bm25Index:
    def __init__(self, chunks: Iterable[CorpusChunk] = (), *, k1: float = K1, b: float = B):
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 requires k1 > 0 and 0 <= b <= 1")
        self.k1, self.b = float(k1), float(b)
        self._chunks: tuple[CorpusChunk, ...] = ()
        self._terms: tuple[Counter[str], ...] = ()
        self._df: Counter[str] = Counter()
        self._avgdl = 0.0
        self.add(chunks)

    def add(self, chunks: Iterable[CorpusChunk]) -> None:
        incoming = tuple(chunks)
        if not incoming:
            return
        if len({chunk.chunk_id for chunk in incoming}) != len(incoming):
            raise ValueError("chunk_id must be unique within an index")
        if {chunk.chunk_id for chunk in incoming} & {chunk.chunk_id for chunk in self._chunks}:
            raise ValueError("chunk_id already exists in index")
        terms = tuple(Counter(tokenize(chunk.text)) for chunk in incoming)
        self._chunks += incoming
        self._terms += terms
        for counts in terms:
            self._df.update(counts.keys())
        self._avgdl = sum(sum(counts.values()) for counts in self._terms) / len(self._terms)

    def search(self, query: str, *, top_k: int = 5, mode: str = "bm25") -> list[SearchHit]:
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if not self._chunks or not str(query or "").strip() or top_k == 0:
            return []
        query_terms = tuple(dict.fromkeys(tokenize(query)))
        if not query_terms:
            return []
        scored: list[tuple[float, str, CorpusChunk]] = []
        n_docs = len(self._chunks)
        for chunk, counts in zip(self._chunks, self._terms):
            dl = sum(counts.values())
            score = 0.0
            for term in query_terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                df = self._df.get(term, 0)
                idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
                score += idf * (tf * (self.k1 + 1.0)) / (tf + self.k1 * (1.0 - self.b + self.b * dl / self._avgdl))
            if score > 0:
                scored.append((score, chunk.chunk_id, chunk))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [SearchHit(chunk, score, mode, rank) for rank, (score, _, chunk) in enumerate(scored[:top_k], 1)]

    @property
    def chunks(self) -> tuple[CorpusChunk, ...]:
        return self._chunks


class HybridRetriever:
    """Optional model-dependent rerank boundary with honest BM25 fallback."""
    def __init__(self, index: Bm25Index, embedding_model: object | None = None):
        self.index = index
        self.embedding_model = embedding_model

    def search(self, query: str, *, top_k: int = 5) -> list[SearchHit]:
        if self.embedding_model is None:
            return self.index.search(query, top_k=top_k, mode="bm25")
        rerank = getattr(self.embedding_model, "rerank", None)
        if not callable(rerank):
            # A configured object that cannot rerank is not silently presented
            # as hybrid; the deterministic path remains explicit.
            return self.index.search(query, top_k=top_k, mode="bm25")
        hits = self.index.search(query, top_k=max(top_k, len(self.index.chunks)), mode="bm25")
        ranked = rerank(query, [hit.chunk.text for hit in hits])
        if not isinstance(ranked, (list, tuple)) or len(ranked) != len(hits):
            return self.index.search(query, top_k=top_k, mode="bm25")
        combined = sorted(zip(ranked, hits), key=lambda pair: (-float(pair[0]), pair[1].chunk.chunk_id))[:top_k]
        return [SearchHit(hit.chunk, float(score), "hybrid", rank) for rank, (score, hit) in enumerate(combined, 1)]
