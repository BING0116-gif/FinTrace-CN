from pathlib import Path

import json
import pytest

from src.cn.benchmark import (
    BenchmarkRegressionError, BenchmarkRunner, check_regression, evaluate_case,
    evaluate_research_state, load_cases, summarize, write_ablation_report,
)
from src.cn.research import ResearchState


CASES = Path(__file__).parents[1] / "data" / "benchmarks" / "cn_agent_v1.json"


def test_benchmark_has_required_offline_case_distribution():
    cases = load_cases(CASES)
    categories = {case.category for case in cases}
    assert len(cases) == 20
    assert {"symbol", "routing", "parameter", "numerical", "evidence", "recovery", "safety"} <= categories


def test_evaluator_scores_trace_arguments_evidence_and_summary():
    case = load_cases(CASES)[3]
    result = evaluate_case(case, [
        {"tool_name": "resolve_cn_symbol", "arguments": {"query": "贵州茅台"}, "result_status": "ok"},
        {"tool_name": "get_cn_prices", "arguments": {"ticker": "600519.SH"}, "result_status": "ok"},
    ], evidence_ids=["fact_600519_SH_close_2026-08-10_RAW"])
    assert result["passed"]
    assert summarize([result])["e2e_success_rate"] == 1.0


def _state_for(case):
    state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2026-08-10T00:00:00+08:00")
    for tool_name in case.expected_tools:
        state.record_tool(tool_name=tool_name, arguments=case.required_arguments.get(tool_name, {}),
                          started_at="2026-08-10T00:00:00+00:00", result_status=case.expected_status)
    state.register_evidence(case.required_evidence)
    return state


@pytest.mark.asyncio
async def test_runner_writes_real_research_state_json_csv_and_baseline_gate(tmp_path):
    case = load_cases(CASES)[3]
    state = _state_for(case)
    row = evaluate_research_state(case, state)
    assert row["trace_id"] == state.trace_id

    runner = BenchmarkRunner([case])
    payload = await runner.run(lambda _: state, output_dir=tmp_path,
                               metadata={"benchmark_version": "cn-agent-v1", "snapshot_id": "snapshot-v1"})
    assert payload["summary"]["e2e_success_rate"] == 1.0
    assert payload["summary"]["avg_llm_calls"] == 0.0
    assert payload["summary"]["total_cost_usd"] == 0.0
    assert payload["metadata"]["snapshot_id"] == "snapshot-v1"
    assert (tmp_path / "results.csv").read_text(encoding="utf-8").startswith("case_id,")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(payload), encoding="utf-8")
    rerun = await runner.run(lambda _: state, output_dir=tmp_path / "rerun", baseline_path=baseline)
    assert rerun["regression"]["passed"]


@pytest.mark.asyncio
async def test_runner_rejects_metric_drop_beyond_threshold(tmp_path):
    case = load_cases(CASES)[3]
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"summary": {"tool_f1": 1.0, "parameter_accuracy": 1.0,
                                                 "evidence_coverage": 1.0, "e2e_success_rate": 1.0}}), encoding="utf-8")
    failing_state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2026-08-10T00:00:00+08:00")
    with pytest.raises(BenchmarkRegressionError):
        await BenchmarkRunner([case]).run(lambda _: failing_state, output_dir=tmp_path / "out", baseline_path=baseline)
    assert not check_regression({"tool_f1": .9, "parameter_accuracy": 1., "evidence_coverage": 1., "e2e_success_rate": 1.},
                                {"tool_f1": 1., "parameter_accuracy": 1., "evidence_coverage": 1., "e2e_success_rate": 1.},
                                max_regression={"tool_f1": .05})["passed"]


def test_ablation_report_writes_only_captured_runs_and_rejects_mismatched_snapshots(tmp_path):
    run = {"summary": {"cases": 20, "tool_f1": 1.0, "parameter_accuracy": 1.0,
                       "evidence_coverage": 1.0, "e2e_success_rate": 1.0},
           "metadata": {"benchmark_version": "cn-agent-v1", "snapshot_id": "snapshot-v1"}}
    report = write_ablation_report(tmp_path, {"agent_tools": run, "agent_tools_evidence": run})
    assert report["missing_variants"] == ["direct_llm", "agent_tools_evidence_validator"]
    assert "agent_tools" in (tmp_path / "ablation.md").read_text(encoding="utf-8")
    mismatched = {**run, "metadata": {"benchmark_version": "cn-agent-v1", "snapshot_id": "snapshot-v2"}}
    with pytest.raises(ValueError, match="snapshot_id"):
        write_ablation_report(tmp_path / "bad", {"agent_tools": run, "agent_tools_evidence": mismatched})
