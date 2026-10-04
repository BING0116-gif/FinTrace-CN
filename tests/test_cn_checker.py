from __future__ import annotations

from src.cn.checker import DraftClaim, check_raw_report, check_report, extract_claims, summarize


def facts():
    return [
        {"fact_id": "f_rev_2024", "metric": "revenue", "value": 100.0, "unit": "CNY", "fiscal_period": "2024FY", "scope": "consolidated", "version": "AS_REPORTED", "available_at": "2025-03-01T00:00:00+08:00"},
        {"fact_id": "f_rev_2025", "metric": "revenue", "value": 120.0, "unit": "CNY", "fiscal_period": "2025FY", "scope": "consolidated", "version": "AS_REPORTED", "available_at": "2026-03-01T00:00:00+08:00"},
    ]


def test_extractor_preserves_source_sentence_and_maps_claim_type():
    sentence = "公司2025年营业收入为120元。"
    claims = extract_claims([{"text": sentence, "page": 2}], lambda _: [{"sentence": sentence, "metric": "revenue", "period": "2025FY", "value": 120, "unit": "元", "claim_type": "factual"}])
    assert claims[0].sentence == sentence
    assert claims[0].mapped_claim_type == "fact"


def test_checker_accepts_unit_conversion_but_flags_numeric_and_missing_citation():
    good = DraftClaim("good", "收入120元", metric="revenue", period="2025FY", value=120, unit="元", source_reference="f_rev_2025")
    bad = DraftClaim("bad", "收入130元", metric="revenue", period="2025FY", value=130, unit="元")
    findings = check_report([good, bad], facts())
    assert any(item.claim_id == "bad" and item.check_type == "numeric_error" for item in findings)
    assert any(item.claim_id == "bad" and item.check_type == "missing_citation" for item in findings)
    assert not any(item.claim_id == "good" and item.check_type == "numeric_error" for item in findings)


def test_checker_catches_period_citation_causal_and_stale_revision_rules():
    claim = DraftClaim("c", "2026年收入因市场扩张导致增长", metric="revenue", period="2026FY", value=120, unit="元", source_reference="f_rev_2025", claim_type="causal")
    findings = check_report([claim], facts(), research_as_of="2027-03-01T00:00:00+08:00")
    kinds = {item.check_type for item in findings}
    assert {"period_error", "wrong_citation", "unsupported_causal_claim"} <= kinds
    assert summarize(findings)["total"] == len(findings)


def test_checker_does_not_judge_forward_looking_claims():
    claim = DraftClaim("fwd", "预计2026年收入增长", metric="revenue", period="2026FY", value=130, unit="元", temporal_status="forward_looking")
    assert check_report([claim], facts()) == []


def planted_facts():
    rows = facts()
    rows[0]["page"] = 10
    rows[1]["page"] = 12
    rows.append({"fact_id": "f_pe_2025", "metric": "pe", "value": 10.0, "unit": "x", "fiscal_period": "2025FY", "scope": "consolidated", "version": "AS_REPORTED", "available_at": "2026-03-01T00:00:00+08:00", "page": 20})
    rows.append({"fact_id": "f_rev_2025_corrected", "metric": "revenue", "value": 121.0, "unit": "CNY", "fiscal_period": "2025FY", "scope": "consolidated", "version": "CORRECTED", "available_at": "2026-04-01T00:00:00+08:00", "page": 13})
    return rows


def test_all_thirteen_planted_checker_categories_are_detected():
    rows = planted_facts()
    cases = [
        DraftClaim("numeric", "营收130元", metric="revenue", period="2025FY", value=130, unit="元", source_reference="f_rev_2025"),
        DraftClaim("unit", "营收120万元", metric="revenue", period="2025FY", value=120, unit="万元", source_reference="f_rev_2025"),
        DraftClaim("period", "营收为100", metric="revenue", period="2026FY", value=100, unit="元", source_reference="f_rev_2025"),
        DraftClaim("scope", "母公司营收120", metric="revenue", period="2025FY", value=120, unit="元", scope="parent", source_reference="f_rev_2025"),
        DraftClaim("calc", "营收同比10%", metric="revenue", period="2025FY", value=120, unit="元", growth=10, source_reference="f_rev_2025"),
        DraftClaim("multiple", "PE 12x", metric="pe", period="2025FY", value=10, unit="x", valuation_multiple="12x", source_reference="f_pe_2025"),
        DraftClaim("missing", "营收120", metric="revenue", period="2025FY", value=120, unit="元"),
        DraftClaim("wrong_citation", "营收120", metric="revenue", period="2025FY", value=120, unit="元", source_reference="f_rev_2024"),
        DraftClaim("unsupported", "营收120", metric="revenue", period="2025FY", value=120, unit="元", source_reference="does-not-exist"),
        DraftClaim("wrong_page", "营收120", page=99, metric="revenue", period="2025FY", value=120, unit="元", source_reference="f_rev_2025"),
        DraftClaim("stale", "营收120", metric="revenue", period="2025FY", value=120, unit="元", source_reference="f_rev_2025"),
        DraftClaim("revision", "营收120", metric="revenue", period="2025FY", value=120, unit="元", source_reference="f_rev_2025"),
        DraftClaim("causal", "市场扩张导致营收增长", metric="revenue", period="2025FY", value=120, unit="元", source_reference="f_rev_2025", claim_type="causal"),
    ]
    findings = check_report(cases, rows, research_as_of="2027-04-01T00:00:00+08:00")
    kinds_by_claim = {claim_id: {item.check_type for item in findings if item.claim_id == claim_id} for claim_id in {case.claim_id for case in cases}}
    expected = {
        "numeric": "numeric_error", "unit": "unit_error", "period": "period_error", "scope": "scope_error",
        "calc": "calculation_error", "multiple": "valuation_multiple_error", "missing": "missing_citation",
        "wrong_citation": "wrong_citation", "unsupported": "unsupported_citation", "wrong_page": "wrong_page",
        "stale": "stale_citation", "revision": "revision_superseded", "causal": "unsupported_causal_claim",
    }
    assert all(expected[claim_id] in kinds_by_claim.get(claim_id, set()) for claim_id in expected)


def test_good_draft_has_zero_findings_and_raw_report_reports_unextracted_sentence():
    sentence = "公司2025年营业收入为120元。"
    good = [{"text": sentence, "page": 2}]
    result = check_raw_report(good, lambda _: [{"sentence": sentence, "metric": "revenue", "period": "2025FY", "value": 120, "unit": "元", "source_reference": "f_rev_2025", "claim_type": "factual"}], facts())
    assert result["summary"]["total"] == 0
    bad = check_raw_report([{"text": sentence}, {"text": "无法解析的句子"}], lambda _: [{"sentence": sentence, "metric": "revenue", "period": "2025FY", "value": 120, "unit": "元", "source_reference": "f_rev_2025"}], facts())
    assert bad["summary"]["unextracted_sentences"] == 1
