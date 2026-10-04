from src.cn.quality import DIMENSIONS, diagnose_quality


def test_quality_reports_ten_independent_dimensions_without_total_score():
    result = diagnose_quality({
        "claims": [{"claim_id": "c1", "claim_type": "fact", "evidence_ids": ["e1"]}, {"claim_id": "c2", "claim_type": "fact"}],
        "evidence": [{"evidence_id": "e1"}],
        "citations": [{"chunk_id": "e1", "valid": True}],
        "calculations": [{"validation_status": "verified"}],
        "findings": [{"check_type": "numeric_error", "severity": "error"}],
        "replay_runs": [{"deterministic_equal": True}],
        "assumptions": [{"id": "a1"}], "assumptions_expected": 2,
    })
    assert [item["name"] for item in result["dimensions"]] == list(DIMENSIONS)
    assert "total_score" not in result
    assert result["dimensions"][0]["value"] == 0.5


def test_quality_uses_na_when_a_denominator_is_missing():
    result = diagnose_quality({})
    by_name = {item["name"]: item for item in result["dimensions"]}
    assert by_name["citation_precision"]["status"] == "N/A"
    assert by_name["replay_consistency"]["status"] == "N/A"
