from __future__ import annotations

import pytest

from src.cn.documents import DocumentParser, DocumentRegistry, DocumentService
from src.cn.documents.registry import DocumentRegistrationError


def test_registry_uses_content_hash_and_rejects_unknown_extension(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text("营业收入 12.5 亿元", encoding="utf-8")
    record = DocumentRegistry().register(path, fiscal_period="2025FY")
    assert record.document_id == f"doc_{record.sha256[:20]}"
    assert record.file_name == "report.txt"

    bad = tmp_path / "report.csv"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(DocumentRegistrationError, match="Unsupported"):
        DocumentRegistry().register(bad)


def test_text_document_creates_page_fragments_and_candidate_facts(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text(
        "合并利润表\n营业收入：12.5 亿元\n归母净利润: -2.0 亿元\f续表\n营业收入 13.0 亿元",
        encoding="utf-8",
    )
    service = DocumentService()
    record = service.register(
        path, symbol="600519.SH", fiscal_period="2025FY",
        published_at="2026-04-01T00:00:00+08:00",
    )
    result = service.parse(record.document_id)
    assert result.document.status == "complete"
    assert result.document.page_count == 2
    assert [fragment.page_number for fragment in result.fragments] == [1, 2]
    assert result.fragments[0].text_sha256
    assert {fact.metric for fact in result.facts} == {"revenue", "net_profit"}
    assert all(fact.source_fragment_id.startswith("frag_") for fact in result.facts)

    evidence = service.facts_as_evidence(record.document_id)
    assert len(evidence) == 3
    assert all(item.provider == f"document:{record.document_id}" for item in evidence)
    assert all(item.available_at == record.published_at for item in evidence)


def test_parser_keeps_parent_and_consolidated_candidates_distinct(tmp_path):
    path = tmp_path / "mixed_scope.txt"
    path.write_text(
        "归母净利润：2 亿元\n母公司净资产：10 亿元\n合并净资产：14 亿元\n少数股东损益：1 亿元",
        encoding="utf-8",
    )
    service = DocumentService()
    record = service.register(path, symbol="600519.SH", fiscal_period="2025FY")
    facts = service.parse(record.document_id).facts
    by_metric = {fact.accounting_metric or fact.metric: fact for fact in facts}
    assert by_metric["net_profit_parent"].scope == "parent"
    assert by_metric["net_assets_parent"].scope == "parent"
    assert by_metric["net_assets_consolidated"].scope == "consolidated"
    assert by_metric["minority_interest_profit"].scope == "consolidated"


def test_missing_period_does_not_upgrade_candidate_to_financial_evidence(tmp_path):
    path = tmp_path / "draft.md"
    path.write_text("营业收入 12.5 亿元", encoding="utf-8")
    service = DocumentService()
    record = service.register(path, symbol="600519.SH")
    service.parse(record.document_id)
    assert service.get_result(record.document_id).facts
    assert service.facts_as_evidence(record.document_id) == ()


def test_empty_page_is_partial_and_explicitly_requires_ocr(tmp_path):
    path = tmp_path / "partial.txt"
    path.write_text("第一页\f\f第三页", encoding="utf-8")
    service = DocumentService()
    record = service.register(path)
    result = service.parse(record.document_id)
    assert result.document.status == "partial"
    assert "page_2:empty_text_layer" in result.warnings
    assert result.fragments[1].extraction_method == "ocr_required"
    assert result.fragments[1].confidence == "unavailable"


def test_parser_rejects_changed_content_after_registration(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text("营业收入 1 亿元", encoding="utf-8")
    service = DocumentService()
    record = service.register(path)
    path.write_text("营业收入 99 亿元", encoding="utf-8")
    with pytest.raises(ValueError, match="content changed"):
        service.parse(record.document_id)


def test_pdf_parser_provides_page_fragments_when_pymupdf_is_available(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    path = tmp_path / "report.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "营业收入 12.5 亿元")
    document.save(path)
    document.close()

    record = DocumentRegistry().register(path, fiscal_period="2025FY")
    result = DocumentParser().parse(record, path)
    assert result.document.page_count == 1
    assert result.fragments[0].page_number == 1
    assert result.fragments[0].text
    assert result.fragments[0].bbox is not None
