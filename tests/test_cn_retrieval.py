from __future__ import annotations

import pytest

from src.cn.retrieval import Bm25Index, Citation, CitationError, CitationStore, CorpusChunk, HybridRetriever, cite_chunk, validate_citation


def chunks():
    return [
        CorpusChunk("c1", "d1", 3, "MD&A", "收入增长主要来自产品销量提升。"),
        CorpusChunk("c2", "d1", 8, "风险", "原材料价格上涨压缩毛利率。"),
        CorpusChunk("c3", "d2", 2, "经营", "经营现金流保持稳定。"),
    ]


def test_bm25_returns_manual_relevant_order_and_is_deterministic():
    index = Bm25Index(chunks())
    first = index.search("收入增长", top_k=2)
    second = index.search("收入增长", top_k=2)
    assert [hit.chunk.chunk_id for hit in first] == ["c1"]
    assert first == second
    assert first[0].mode == "bm25"


def test_empty_and_unknown_queries_are_explicit_empty_results():
    index = Bm25Index(chunks())
    assert index.search("") == []
    assert index.search("不存在的词") == []


def test_quote_paraphrase_and_inference_citations_are_validated():
    lookup = {item.chunk_id: item for item in chunks()}
    quote_id = cite_chunk("c1", Citation.quote, "收入增长")
    assert quote_id.startswith("citation_")
    assert validate_citation(type("R", (), {"chunk_id": "c1", "citation_type": Citation.quote, "span": "收入增长", "derived_from": ()})(), lookup)
    with pytest.raises(CitationError, match="exact substring"):
        validate_citation(type("R", (), {"chunk_id": "c1", "citation_type": Citation.quote, "span": "不存在", "derived_from": ()})(), lookup)
    store = CitationStore(chunks())
    paraphrase = store.cite("c1", "paraphrase", "销量带动收入")
    inference = store.cite("c1", "inference", "收入改善", derived_from=(paraphrase.citation_id,))
    assert len(store.evidence_ids()) == 1  # one selected chunk, not every search hit
    assert inference.chunk_id == "c1"


def test_retrieval_does_not_create_evidence_until_explicit_citation_and_fallback_is_honest():
    index = Bm25Index(chunks())
    assert not hasattr(index.search("收入" )[0], "evidence_id")
    hits = HybridRetriever(index).search("收入")
    assert hits[0].mode == "bm25"
