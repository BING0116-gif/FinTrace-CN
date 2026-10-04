import pytest

from src.cn.fragility import build_fragility_report, compute_minimal_cut_sets, compute_numeric_fragility, identify_critical_nodes
from src.cn.graph import Claim, ClaimGraph, Thesis

def graph_fixture():
    claims = [
        Claim("c1", "fact", "historical", "毛利率改善", ["e1", "e2"], validation_status="supported"),
        Claim("c2", "fact", "historical", "收入增长", ["e3"], validation_status="supported"),
        Claim("c3", "inference", "historical", "盈利改善持续", derived_from=["c1", "c2"], dependency_metadata=[{"role": "REQUIRED", "target_id": "c1", "target_type": "claim"}, {"role": "REQUIRED", "target_id": "c2", "target_type": "claim"}], validation_status="supported", assumption_ids=["a1"]),
    ]
    return ClaimGraph("frag-run", claims=claims, theses=[Thesis("t1", "盈利改善持续", ["c3"], {"c3": "REQUIRED"})])

def test_critical_nodes_and_single_points_are_structural():
    graph = graph_fixture()
    rows = identify_critical_nodes(graph, ["t1"])
    assert {row["node_id"] for row in rows} >= {"c1", "c2", "e1", "e2", "e3"}
    assert all(row["is_single_point"] for row in rows)

def test_minimal_cut_sets_reverse_check_has_alternative_evidence_cut():
    graph = graph_fixture()
    cuts = compute_minimal_cut_sets(graph, "t1")
    assert ["c1"] in cuts and ["c2"] in cuts and ["e1", "e2"] in cuts

def test_threshold_whitelist_and_monitoring_report():
    graph = graph_fixture()
    report = build_fragility_report(graph, "t1", thresholds=[{"node_id": "c1", "threshold": 29.4, "current_value": 31.2, "source_type": "analyst_input"}], assumptions=[])
    assert report.numeric_thresholds[0]["distance_to_invalidation"] == pytest.approx(1.8)
    assert report.unresolved_assumptions and report.monitoring_metrics
    with pytest.raises(ValueError): compute_numeric_fragility(graph, [{"threshold": 1, "current_value": 2, "source_type": "llm_guess"}])
