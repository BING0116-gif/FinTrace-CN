from src.cn.graph import Claim, ClaimGraph, Thesis
from src.cn.temporal import (
    TemporalEvent, VersionLineageEntry, compare_full_vs_incremental,
    compute_affected_subgraph, get_version_lineage, ingest_temporal_event,
    record_version_lineage, register_graph, persist_revalidation_report,
)
from src.cn.runs import RunRecorder

def graph_fixture():
    graph = ClaimGraph(
        "temporal-run",
        claims=[
            Claim("c1", "fact", "historical", "毛利率", ["e1"], validation_status="supported"),
            Claim("c2", "inference", "historical", "盈利改善", derived_from=["c1"], dependency_metadata=[{"role": "REQUIRED", "target_id": "c1", "target_type": "claim"}], validation_status="supported"),
            Claim("unaffected", "fact", "historical", "独立事实", ["e2"], validation_status="supported"),
        ],
        theses=[Thesis("t1", "盈利改善", ["c2"], {"c2": "REQUIRED"})],
        evidence_index={"e1": {"status": "active"}, "e2": {"status": "active"}},
    )
    register_graph(graph.run_id, graph)
    return graph

def test_affected_subgraph_is_incremental_and_unrelated_node_is_untouched():
    graph = graph_fixture()
    assert compute_affected_subgraph(["e1"], graph) == ["c1", "c2", "e1", "t1"]
    report = ingest_temporal_event(TemporalEvent("ev-new", "NEW_INFORMATION", "new_snapshot", "2026-10-03", ["e1"], "new quarter"), graph)
    assert report.affected_subgraph == ["c1", "c2", "e1", "t1"]
    assert graph.claims["c1"].validation_status == "stale"
    assert graph.claims["unaffected"].validation_status == "supported"

def test_three_event_kinds_have_distinct_propagation_and_lineage_is_append_only():
    graph = graph_fixture()
    graph.evidence_index["e1"]["status"] = "active"
    conflict = ingest_temporal_event(TemporalEvent("ev-conflict", "DATA_CONFLICT", "new_filing", "2026-10-03", ["e1"], "unresolved"), graph)
    assert graph.claims["c1"].validation_status == "blocked"
    assert conflict.impact["claims_invalidated"] == ["c1", "c2"]
    record_version_lineage(VersionLineageEntry("e1", "AS_REPORTED", source_published_at="2026-01-01"))
    record_version_lineage(VersionLineageEntry("e1", "CORRECTED", supersedes="e1", superseded_by="e1-corrected", reason="correction", source_published_at="2026-10-03"))
    assert [item.version_status for item in get_version_lineage("e1")] == ["AS_REPORTED", "CORRECTED"]

def test_full_vs_incremental_contract_is_explicit():
    graph = graph_fixture()
    result = compare_full_vs_incremental(graph.run_id, ["e1"], graph)
    assert result["results_identical"] is True
    assert result["nodes_recomputed"] < result["full_nodes"]

def test_revalidation_event_is_persisted_in_run_manifest_chain(tmp_path):
    graph = graph_fixture()
    recorder = RunRecorder(tmp_path / "runs")
    run_id = recorder.start({"run_id": "temporal-run", "started_at": "2026-10-03T00:00:00Z"})
    report = ingest_temporal_event(TemporalEvent("ev-persist", "NEW_INFORMATION", "new_snapshot", "2026-10-03", ["e1"], "new quarter", {"valuations": ["v1"], "memo_sections": ["valuation"]}), graph)
    event = persist_revalidation_report(report, recorder, run_id)
    assert event["event_type"] == "temporal_revalidation"
    recorder.finish(run_id)
    assert recorder.verify_replayable(run_id).replayable
