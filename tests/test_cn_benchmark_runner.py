"""Integration tests for the benchmark runner and ablation pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from src.cn.benchmark import (
    BenchmarkCase, BenchmarkRunner, evaluate_research_state, load_cases, summarize,
)
from src.cn.research import ResearchState

CASES = Path(__file__).parents[1] / "data" / "benchmarks" / "cn_agent_v1.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _all_cases():
    return load_cases(CASES)


def _mock_state(case: BenchmarkCase) -> ResearchState:
    symbol = "600519.SH"
    state = ResearchState.create(query=case.query, symbol=symbol, research_as_of="2026-08-10T00:00:00+08:00")
    for tool_name in case.expected_tools:
        arguments = case.required_arguments.get(tool_name, {})
        state.record_tool(tool_name=tool_name, arguments=arguments, started_at="2026-08-10T00:00:00+00:00",
                          ended_at="2026-08-10T00:00:30+00:00", result_status=case.expected_status)
    state.register_evidence(case.required_evidence)
    return state


# ---------------------------------------------------------------------------
# Benchmark runner integration tests
# ---------------------------------------------------------------------------

def test_benchmark_runner_all_cases_pass():
    cases = _all_cases()
    results = []
    for case in cases:
        state = _mock_state(case)
        results.append(evaluate_research_state(case, state))
    summary = summarize(results)
    assert summary["cases"] == 20
    assert summary["e2e_success_rate"] == 1.0
    assert summary["tool_f1"] == 1.0
    assert summary["parameter_accuracy"] == 1.0


def test_benchmark_runner_per_category_breakdown():
    cases = _all_cases()
    categories = set(case.category for case in cases)
    for cat in categories:
        cat_cases = [c for c in cases if c.category == cat]
        results = [evaluate_research_state(c, _mock_state(c)) for c in cat_cases]
        summary = summarize(results)
        assert summary["cases"] == len(cat_cases), f"Category {cat}: expected {len(cat_cases)} cases, got {summary['cases']}"


@pytest.mark.asyncio
async def test_benchmark_runner_async_api(tmp_path):
    cases = [_all_cases()[0]]
    state = _mock_state(cases[0])
    runner = BenchmarkRunner(cases)
    payload = await runner.run(
        lambda _: state,
        output_dir=tmp_path,
        metadata={"benchmark_version": "cn-agent-v1", "snapshot_id": "test"},
    )
    assert payload["summary"]["e2e_success_rate"] == 1.0
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "results.csv").exists()


def test_benchmark_runner_csv_output(tmp_path):
    cases = _all_cases()
    results = []
    for case in cases:
        state = _mock_state(case)
        results.append(evaluate_research_state(case, state))
    BenchmarkRunner._write_csv(tmp_path / "results.csv", results)
    csv_text = (tmp_path / "results.csv").read_text(encoding="utf-8")
    assert csv_text.startswith("case_id,")
    assert "symbol-01" in csv_text
    assert "safety-01" in csv_text


def test_benchmark_runner_result_json_structure(tmp_path):
    cases = [_all_cases()[0]]
    state = _mock_state(cases[0])
    results = [evaluate_research_state(cases[0], state)]
    summary = summarize(results)
    payload: Dict[str, Any] = {
        "summary": summary,
        "results": results,
        "metadata": {"benchmark_version": "cn-agent-v1", "snapshot_id": "test"},
    }
    output_path = tmp_path / "results.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["summary"]["cases"] == 1
    assert len(loaded["results"]) == 1


# ---------------------------------------------------------------------------
# Recovery case tests
# ---------------------------------------------------------------------------

def test_recovery_case_expected_error():
    """recovery-02 expects error status — mock state should handle this."""
    cases = _all_cases()
    recovery_cases = [c for c in cases if c.category == "recovery"]
    assert len(recovery_cases) == 3
    for case in recovery_cases:
        state = _mock_state(case)
        # The mock sets expected_status on the tool trace
        trace = state.tool_trace
        if trace:
            assert trace[-1].result_status == case.expected_status


# ---------------------------------------------------------------------------
# Safety case tests
# ---------------------------------------------------------------------------

def test_safety_case_has_no_tools():
    """safety-01 (保证买入一定赚钱) should have no expected tools."""
    cases = _all_cases()
    safety = [c for c in cases if c.case_id == "safety-01"]
    assert len(safety) == 1
    assert safety[0].expected_tools == []


def test_safety_case_passes_with_empty_trace():
    """Safety case: no tools called, no evidence needed — should still pass."""
    case = [c for c in _all_cases() if c.case_id == "safety-01"][0]
    state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2026-08-10T00:00:00+08:00")
    result = evaluate_research_state(case, state)
    assert result["passed"] is True, "Safety case with empty trace should pass"


# ---------------------------------------------------------------------------
# Ablation-specific tests
# ---------------------------------------------------------------------------

def test_ablation_variant_direct_llm_has_low_f1():
    """direct_llm variant should have low F1 since it only resolves symbols."""
    from scripts.run_ablation import _build_state_direct_llm
    case = [c for c in _all_cases() if c.category == "routing"][0]
    state = _build_state_direct_llm(case)
    result = evaluate_research_state(case, state)
    # direct_llm only resolves symbol, not the requested tool
    assert result["tool_f1"] < 1.0


def test_ablation_variant_agent_tools_missing_evidence():
    """agent_tools variant calls tools but registers no evidence."""
    from scripts.run_ablation import _build_state_agent_tools
    case = [c for c in _all_cases() if c.category == "evidence"][0]
    state = _build_state_agent_tools(case)
    result = evaluate_research_state(case, state)
    assert result["tool_f1"] == 1.0  # tools called correctly
    assert result["evidence_coverage"] < 1.0  # no evidence registered


def test_ablation_all_variants_run_without_error():
    """All 4 ablation variants should run without runtime errors."""
    from scripts.run_ablation import _VARIANT_BUILDERS
    cases = _all_cases()
    for variant_name, builder in _VARIANT_BUILDERS.items():
        for case in cases:
            state = builder(case)
            result = evaluate_research_state(case, state)
            assert "case_id" in result
            assert "passed" in result


def test_ablation_version_consistency():
    """All ablation variants should produce valid ResearchState objects."""
    from scripts.run_ablation import _VARIANT_BUILDERS
    cases = _all_cases()[:3]
    for variant_name, builder in _VARIANT_BUILDERS.items():
        for case in cases:
            state = builder(case)
            assert isinstance(state.query, str)
            assert state.symbol is not None


# ---------------------------------------------------------------------------
# Script-level tests
# ---------------------------------------------------------------------------

def test_benchmark_script_list():
    """run_benchmark.py --list should produce output listing all 20 cases."""
    from scripts.run_benchmark import main
    exit_code = main(["--list"])
    assert exit_code == 0


def test_benchmark_script_run(tmp_path):
    """run_benchmark.py should produce results files."""
    from scripts.run_benchmark import main
    exit_code = main(["--output", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "results.csv").exists()


def test_benchmark_script_category_filter(tmp_path):
    """--category filter should run only matching cases."""
    from scripts.run_benchmark import main
    exit_code = main(["--category", "symbol", "--output", str(tmp_path)])
    assert exit_code == 0
    results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert results["summary"]["cases"] == 3  # 3 symbol cases


def test_ablation_script_list():
    """run_ablation.py --list should list 4 variants."""
    from scripts.run_ablation import main
    exit_code = main(["--list"])
    assert exit_code == 0


def test_ablation_script_run(tmp_path):
    """run_ablation.py should produce ablation report files."""
    from scripts.run_ablation import main
    exit_code = main(["--output", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / "ablation.json").exists()
    assert (tmp_path / "ablation.csv").exists()
    assert (tmp_path / "ablation.md").exists()


def test_ablation_script_single_variant(tmp_path):
    """--variant should run only one variant."""
    from scripts.run_ablation import main
    exit_code = main(["--variant", "direct_llm", "--output", str(tmp_path)])
    assert exit_code == 0
    report = json.loads((tmp_path / "ablation.json").read_text(encoding="utf-8"))
    assert len(report["variants"]) == 1
    assert report["variants"][0]["variant"] == "direct_llm"