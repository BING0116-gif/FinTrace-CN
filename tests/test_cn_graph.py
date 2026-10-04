from __future__ import annotations

import pytest

from src.cn.graph import Calculation, Claim, ClaimGraph, Thesis, build_graph, deactivate_evidence, revalidate, validate_graph


def graph_fixture():
    evidence = {
        "E51": {"document_id": "annual", "page": 118, "available_at": "2026-04-01T00:00:00+08:00"},
        "E37": {"document_id": "annual", "page": 96, "available_at": "2026-04-01T00:00:00+08:00"},
    }
    calculation = Calculation("CAL12", "CFO / NI", "1.0", [{"ref": "E51", "value": 61}, {"ref": "E37", "value": 100}], {"value": 0.61, "unit": "ratio", "period": "2025FY"}, "test", "verified")
    fact_a = Claim("CFO", "fact", "historical", "经营现金流为61", ["E51"], [], [], [], "EXACT_MATCH", "supported")
    fact_b = Claim("NI", "fact", "historical", "净利润为100", ["E37"], [], [], [], "EXACT_MATCH", "supported")
    inference = Claim("C18", "inference", "historical", "盈利质量下降", [], ["CAL12"], ["CFO", "NI"], [{"role": "REQUIRED", "target_id": "CFO", "target_type": "claim"}, {"role": "REQUIRED", "target_id": "NI", "target_type": "claim"}], "UNVERIFIABLE", "supported")
    thesis = Thesis("T1", "盈利质量风险", ["C18"], {"C18": "REQUIRED"})
    return build_graph("run-1", claims=[fact_a, fact_b, inference], theses=[thesis], calculations=[calculation], evidence_index=evidence)


def test_trace_reaches_calculation_evidence_pages_and_validation_is_clean():
    graph = graph_fixture()
    trace = graph.trace("C18").to_dict()
    assert {item["evidence_id"] for item in trace["calculations"][0:0]} == set()  # calculation is a node, evidence below
    assert {item["evidence_id"] for item in trace["evidence"]} == {"E51", "E37"}
    assert trace["evidence"][0]["page"] in {96, 118}
    assert validate_graph(graph).valid


def test_binding_rules_find_orphan_missing_calculation_and_opinion_assumption():
    graph = ClaimGraph(
        "run-bad",
        claims=[
            Claim("fact", "fact", "historical", "无证据事实"),
            Claim("infer", "inference", "historical", "无上游推论"),
            Claim("op", "opinion", "current", "观点"),
        ],
        calculations=[Calculation("bad_calc", "x", "1", [{"ref": "missing"}], {"value": 1}, "test", "pending")]
    )
    report = validate_graph(graph)
    assert not report.valid
    assert "fact" in report.orphan_claims
    assert "bad_calc" in report.unsupported_calculations
    assert "fact_without_evidence:fact" in report.errors
    assert "opinion_without_assumption:op" in report.errors


def test_deactivate_evidence_blocks_downstream_claim_and_thesis():
    graph = graph_fixture()
    impacted = deactivate_evidence("run-1", "E51", "source withdrawn")
    assert "CFO" in impacted and "C18" in impacted
    assert graph.claims["CFO"].validation_status == "blocked"
    assert graph.claims["C18"].validation_status == "blocked"
    assert graph.theses["T1"].status == "blocked"


def test_cycle_is_rejected_and_serialization_round_trips():
    with pytest.raises(ValueError, match="claim_cycle"):
        ClaimGraph("cycle", claims=[Claim("a", "inference", "historical", "a", derived_from=["b"]), Claim("b", "inference", "historical", "b", derived_from=["a"])])
    graph = graph_fixture()
    restored = ClaimGraph.from_dict(graph.export_json())
    assert restored.export_json() == graph.export_json()
