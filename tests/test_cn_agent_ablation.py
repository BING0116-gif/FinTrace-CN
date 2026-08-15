"""Tests for the real LLM Agent Ablation pipeline.

All tests are offline — they use a mock provider so no actual LLM is called.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.cn.ablation_agent import (
    ABLATION_VARIANTS,
    AblationAgent,
    _MiniLedger,
    _DictRecord,
    compute_ablation_metrics,
)
from src.cn.benchmark import BenchmarkCase, evaluate_research_state, load_cases, summarize
from src.cn.research import ResearchState
from src.validation.research_gate import ResearchGateRequirements, ResearchGateValidator


# ---------------------------------------------------------------------------
# Minimal ToolCall / LLMToolResponse for the mock provider
# (avoids importing from src.llms.async_client, which triggers a broken
#  ``from logger import get_logger`` chain in src/llms/openai.py)
# ---------------------------------------------------------------------------

@dataclass
class _ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]
    parse_error: Optional[str] = None


@dataclass
class _LLMToolResponse:
    text: str
    tool_calls: List[_ToolCall] = field(default_factory=list)
    cost: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


ABLATION_CASES = Path(__file__).parents[1] / "data" / "benchmarks" / "cn_agent_ablation_v3.json"
FIXTURE = Path(__file__).parent / "fixtures" / "cn" / "600519.SH_illustrative_v1.json"
BANK_FIXTURE = Path(__file__).parent / "fixtures" / "cn" / "600036.SH_bank_boundary_v1.json"


# ---------------------------------------------------------------------------
# Fixture case tests
# ---------------------------------------------------------------------------

def test_ablation_v3_has_required_case_distribution():
    cases = load_cases(ABLATION_CASES)
    assert len(cases) == 7
    categories = {case.category for case in cases}
    assert {"routing", "validator", "recovery"} <= categories
    case_ids = {case.case_id for case in cases}
    assert {"normal-price", "normal-financials", "expired-data", "future-disclosure",
            "missing-evidence", "wrong-code", "industry-boundary"} <= case_ids


def test_ablation_v3_cases_have_snapshot_paths():
    cases = load_cases(ABLATION_CASES)
    for case in cases:
        assert case.snapshot_path, f"Case {case.case_id} missing snapshot_path"


def test_ablation_v3_list():
    """--list should produce output without error."""
    from scripts.run_agent_ablation import main
    exit_code = main(["--list", "--cases", str(ABLATION_CASES)])
    assert exit_code == 0


def test_ablation_v3_requires_explicit_model():
    """A real run must not silently make a paid model call."""
    from scripts.run_agent_ablation import main
    exit_code = main(["--cases", str(ABLATION_CASES), "--output", str(Path.cwd())])
    assert exit_code == 2


# ---------------------------------------------------------------------------
# Mock provider for ablation test
# ---------------------------------------------------------------------------

class _MockLLM:
    """Simulates an LLM that follows the expected tool sequence."""

    model_name = "gpt-4o-mini"
    api_style = "openai"

    def __init__(self, expected_tools, required_arguments):
        self._expected = list(expected_tools)
        self._required_args = required_arguments
        self._turn = 0
        self.calls = []

    async def call_with_tools(self, messages, tools, temperature=0.0, **kwargs):
        self._turn += 1
        if self._turn <= len(self._expected):
            tool_name = self._expected[self._turn - 1]
            args = self._required_args.get(tool_name, {})
            call = _ToolCall(id=f"call-{self._turn}", name=tool_name, arguments=args, parse_error=None)
            self.calls.append(call)
            return _LLMToolResponse(
                text="", tool_calls=[call], cost=0.001,
                raw={"role": "assistant", "tool_calls": []},
            )
        # Final answer
        return _LLMToolResponse(
            text="已完成分析。", tool_calls=[], cost=0.001,
            raw={"role": "assistant", "content": "已完成分析。"},
        )

    async def __call__(self, messages, temperature=0.0):
        return "Mock response", 0.001


# ---------------------------------------------------------------------------
# Ablation Agent tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ablation_agent_direct_llm_variant():
    """direct_llm variant should not call any tools."""
    provider = _MockLLM([], {})
    agent = AblationAgent(
        variant="direct_llm", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
    )
    state = await agent.run("查询 600519.SH 的价格")
    assert len(state.tool_trace) == 0
    assert len(state.facts) == 0
    assert len(state.calculations) == 0
    assert agent.total_cost > 0


@pytest.mark.asyncio
async def test_ablation_agent_agent_tools_variant_strips_evidence():
    """agent_tools variant should record tools but strip evidence."""
    provider = _MockLLM(
        ["resolve_cn_symbol", "get_cn_prices"],
        {"resolve_cn_symbol": {"query": "600519.SH"}, "get_cn_prices": {"ticker": "600519.SH"}},
    )
    agent = AblationAgent(
        variant="agent_tools", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
    )
    state = await agent.run("查询 600519.SH 的价格")
    assert len(state.tool_trace) == 2
    assert [t.tool_name for t in state.tool_trace] == ["resolve_cn_symbol", "get_cn_prices"]
    # Evidence should be stripped (empty evidence_ids in tool trace)
    assert all(len(t.evidence_ids) == 0 for t in state.tool_trace)


@pytest.mark.asyncio
async def test_ablation_agent_agent_tools_evidence_tracks_evidence():
    """agent_tools_evidence variant should record tools and evidence."""
    provider = _MockLLM(
        ["resolve_cn_symbol", "get_cn_prices"],
        {"resolve_cn_symbol": {"query": "600519.SH"}, "get_cn_prices": {"ticker": "600519.SH"}},
    )
    agent = AblationAgent(
        variant="agent_tools_evidence", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
    )
    state = await agent.run("查询 600519.SH 的价格")
    assert len(state.tool_trace) == 2
    # Evidence should be tracked
    price_trace = state.tool_trace[1]
    assert len(price_trace.evidence_ids) > 0
    assert price_trace.evidence_ids[0].startswith("fact_600519_SH_close")


@pytest.mark.asyncio
async def test_ablation_agent_full_variant_validator_gate():
    """agent_tools_evidence_validator should run the validator gate."""
    provider = _MockLLM(
        ["resolve_cn_symbol", "get_cn_prices"],
        {"resolve_cn_symbol": {"query": "600519.SH"}, "get_cn_prices": {"ticker": "600519.SH"}},
    )
    agent = AblationAgent(
        variant="agent_tools_evidence_validator", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
        # Use a research_as_of that makes the data expired (>365 days)
        research_as_of="2026-08-10T00:00:00+08:00",
        required_metrics=["close"],
    )
    state = await agent.run("查询 600519.SH 的价格")
    # The validator should detect expired data (trade_date 2025-03-31, research_as_of 2026-08-10)
    assert agent.validator_intercepted, "Validator should intercept expired data"
    assert "无法验证" in (agent.answer or ""), "Agent should return rejection message"
    assert state.validation_result is not None
    assert not state.validation_result.get("valid", True), "Validation should fail"


@pytest.mark.asyncio
async def test_ablation_agent_full_variant_passes_valid_data():
    """agent_tools_evidence_validator should pass with valid (non-expired) data."""
    provider = _MockLLM(
        ["resolve_cn_symbol", "get_cn_prices"],
        {"resolve_cn_symbol": {"query": "600519.SH"}, "get_cn_prices": {"ticker": "600519.SH"}},
    )
    agent = AblationAgent(
        variant="agent_tools_evidence_validator", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
        # research_as_of close to the data date → data is not expired
        research_as_of="2025-04-01T00:00:00+08:00",
        required_metrics=["close"],
    )
    state = await agent.run("查询 600519.SH 的价格")
    assert not agent.validator_intercepted, "Validator should NOT intercept valid data"
    assert state.validation_result is not None
    assert state.validation_result.get("valid", False), "Validation should pass"


@pytest.mark.asyncio
async def test_validator_gate_blocks_tool_error_and_no_evidence():
    provider = _MockLLM(["resolve_cn_symbol"], {"resolve_cn_symbol": {"query": "BADCODE"}})
    agent = AblationAgent(
        variant="agent_tools_evidence_validator", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
        research_as_of="2025-04-01T00:00:00+08:00", requires_evidence=True,
    )
    state = await agent.run("Fetch BADCODE price")

    assert agent.validator_intercepted
    assert "tool_error:resolve_cn_symbol" in agent.validator_errors
    assert "no_evidence" in agent.validator_errors
    assert state.validation_result["valid"] is False
    assert agent.answer.startswith("无法验证/拒绝结论")


@pytest.mark.asyncio
async def test_validator_gate_blocks_metric_unavailable_before_cutoff():
    provider = _MockLLM(
        ["resolve_cn_symbol", "get_cn_financials"],
        {"resolve_cn_symbol": {"query": "600519.SH"},
         "get_cn_financials": {"ticker": "600519.SH", "research_as_of": "2025-04-01T00:00:00+08:00"}},
    )
    agent = AblationAgent(
        variant="agent_tools_evidence_validator", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
        research_as_of="2025-04-01T00:00:00+08:00",
        required_metrics=["ebit"], requires_evidence=True,
    )
    await agent.run("Fetch EBIT at the cutoff")

    assert agent.validator_intercepted
    assert any(error.startswith("unavailable_before_cutoff:ebit:2025-04-26") for error in agent.validator_errors)


@pytest.mark.asyncio
async def test_validator_gate_blocks_requested_metric_missing_from_snapshot():
    provider = _MockLLM(
        ["resolve_cn_symbol", "get_cn_financials"],
        {"resolve_cn_symbol": {"query": "600519.SH"}, "get_cn_financials": {"ticker": "600519.SH"}},
    )
    agent = AblationAgent(
        variant="agent_tools_evidence_validator", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
        research_as_of="2025-04-01T00:00:00+08:00",
        required_metrics=["ebitda"], requires_evidence=True,
    )
    await agent.run("Fetch EBITDA")

    assert agent.validator_intercepted
    assert "requested_metric_missing:ebitda" in agent.validator_errors


@pytest.mark.asyncio
async def test_validator_gate_blocks_successful_execution_without_evidence():
    provider = _MockLLM(["resolve_cn_symbol"], {"resolve_cn_symbol": {"query": "600519.SH"}})
    agent = AblationAgent(
        variant="agent_tools_evidence_validator", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
        research_as_of="2025-04-01T00:00:00+08:00", requires_evidence=True,
    )
    await agent.run("Give a deterministic financial conclusion")

    assert agent.validator_intercepted
    assert agent.validator_errors == ["no_evidence"]


def test_validator_gate_does_not_reconstruct_unregistered_evidence():
    agent = AblationAgent(
        variant="agent_tools_evidence_validator", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=_MockLLM([], {}),
        research_as_of="2025-04-01T00:00:00+08:00",
        required_metrics=["close"],
    )
    state = ResearchState.create(
        query="Fetch the close", symbol="600519.SH",
        research_as_of="2025-04-01T00:00:00+08:00",
        intent="offline_ablation",
    )
    state.record_tool(
        tool_name="get_cn_prices", arguments={"ticker": "600519.SH"},
        started_at="2025-04-01T00:00:00+08:00", result_status="ok",
        provider="snapshot", evidence_ids=[],
    )

    agent._apply_validator_gate(state)

    assert agent.validator_intercepted
    assert "no_evidence" in agent.validator_errors


@pytest.mark.parametrize(
    ("available_at", "expected_error"),
    [
        (None, "availability_unknown:fact_close"),
        ("not-a-timestamp", "invalid_availability_timestamp:fact_close"),
    ],
)
def test_validator_gate_blocks_unverifiable_availability(available_at, expected_error):
    state = ResearchState.create(
        query="Fetch the close", symbol="600519.SH",
        research_as_of="2025-04-01T00:00:00+08:00",
    )
    record = {
        "evidence_id": "fact_close", "kind": "fact", "symbol": "600519.SH",
        "metric": "close", "value": 1.0, "currency": "CNY",
        "unit": "CNY/share", "fiscal_period": None, "period_basis": "RAW",
        "published_at": available_at, "available_at": available_at,
        "provider": "snapshot", "field_path": "bars.2025-03-31.close",
        "source_url": None, "input_ids": (), "operation": None,
    }
    result = ResearchGateValidator().validate(
        _MiniLedger([record]), state=state,
        snapshot_payload=json.loads(FIXTURE.read_text(encoding="utf-8")),
        research_as_of="2025-04-01T00:00:00+08:00",
        requirements=ResearchGateRequirements(
            required_metrics=("close",), requires_evidence=True,
        ),
    )

    assert not result.valid
    assert expected_error in result.errors


@pytest.mark.asyncio
async def test_validator_gate_blocks_inapplicable_bank_valuation_method():
    provider = _MockLLM(
        ["resolve_cn_symbol", "get_cn_financials"],
        {"resolve_cn_symbol": {"query": "600036.SH"}, "get_cn_financials": {"ticker": "600036.SH"}},
    )
    agent = AblationAgent(
        variant="agent_tools_evidence_validator", snapshot_path=BANK_FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
        research_as_of="2026-08-10T23:00:00+08:00",
        required_metrics=["revenue"], requires_evidence=True,
        requested_valuation_method="EV/EBITDA",
    )
    await agent.run("Use EV/EBITDA to value this bank")

    assert agent.validator_intercepted
    assert "industry_valuation_inapplicable:financial_institution:EV/EBITDA" in agent.validator_errors


@pytest.mark.asyncio
async def test_ablation_agent_handles_tool_error():
    """Agent should handle tool errors gracefully."""
    provider = _MockLLM(
        ["resolve_cn_symbol"],
        {"resolve_cn_symbol": {"query": "BADCODE"}},
    )
    agent = AblationAgent(
        variant="agent_tools_evidence", snapshot_path=FIXTURE,
        model_name="gpt-4o-mini", provider=provider,
    )
    state = await agent.run("查询 BADCODE 的价格")
    assert len(state.tool_trace) == 1
    assert state.tool_trace[0].result_status == "error"


@pytest.mark.asyncio
async def test_ablation_agent_all_variants_run_without_error():
    """All 4 variants should run without runtime errors."""
    cases = load_cases(ABLATION_CASES)
    for variant in ABLATION_VARIANTS:
        for case in cases[:2]:  # Just first 2 cases for speed
            provider = _MockLLM(case.expected_tools, case.required_arguments)
            from scripts.run_agent_ablation import _resolve_snapshot
            snapshot_path = _resolve_snapshot(case)
            agent = AblationAgent(
                variant=variant, snapshot_path=snapshot_path,
                model_name="gpt-4o-mini", provider=provider,
                research_as_of=case.research_as_of,
            )
            state = await agent.run(case.query)
            result = evaluate_research_state(case, state)
            assert "case_id" in result
            assert "passed" in result


# ---------------------------------------------------------------------------
# Script-level tests
# ---------------------------------------------------------------------------

def test_agent_ablation_script_list():
    from scripts.run_agent_ablation import main
    exit_code = main(["--list", "--cases", str(ABLATION_CASES)])
    assert exit_code == 0


def test_agent_ablation_script_requires_model():
    from scripts.run_agent_ablation import main
    exit_code = main(["--cases", str(ABLATION_CASES), "--output", str(Path.cwd())])
    assert exit_code == 2


def test_agent_ablation_script_dry_run():
    """Dry-run should execute without a real model."""
    from scripts.run_agent_ablation import main
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        exit_code = main([
            "--dry-run", "--cases", str(ABLATION_CASES), "--output", str(out),
        ])
        assert exit_code == 0
        assert (out / "ablation_results.json").exists()
        assert (out / "ablation_metrics.csv").exists()
        assert (out / "ablation_report.md").exists()


def test_agent_ablation_script_single_variant_dry_run():
    """--variant should run only one variant."""
    from scripts.run_agent_ablation import main
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        exit_code = main([
            "--dry-run", "--variant", "direct_llm",
            "--cases", str(ABLATION_CASES), "--output", str(out),
        ])
        assert exit_code == 0
        report = json.loads((out / "ablation_results.json").read_text(encoding="utf-8"))
        assert list(report["metrics"].keys()) == ["direct_llm"]


# ---------------------------------------------------------------------------
# Metrics computation tests
# ---------------------------------------------------------------------------

def test_compute_ablation_metrics_empty():
    metrics = compute_ablation_metrics({})
    assert metrics == {}


def test_compute_ablation_metrics_single_variant():
    results = {
        "agent_tools": [
            {
                "tool_f1": 1.0, "parameters_ok": True, "evidence_coverage": 1.0,
                "passed": True, "validator_intercepted": False,
                "error_conclusion_leakage": False, "cost_usd": 0.05,
                "latency_seconds": 10.0,
            },
        ]
    }
    metrics = compute_ablation_metrics(results)
    assert "agent_tools" in metrics
    m = metrics["agent_tools"]
    assert m["tool_f1"] == 1.0
    assert m["parameter_accuracy"] == 1.0
    assert m["evidence_coverage"] == 1.0
    assert m["e2e_success_rate"] == 1.0
    assert m["validator_intercept_rate"] == 0.0
    assert m["error_conclusion_leakage"] == 0.0
    assert m["total_cost_usd"] == 0.05


def test_compute_ablation_metrics_with_intercepts():
    results = {
        "agent_tools_evidence_validator": [
            {
                "tool_f1": 0.5, "parameters_ok": False, "evidence_coverage": 0.5,
                "passed": False, "validator_intercepted": True,
                "error_conclusion_leakage": False, "cost_usd": 0.02,
                "latency_seconds": 5.0,
            },
            {
                "tool_f1": 1.0, "parameters_ok": True, "evidence_coverage": 1.0,
                "passed": True, "validator_intercepted": False,
                "error_conclusion_leakage": False, "cost_usd": 0.03,
                "latency_seconds": 8.0,
            },
        ]
    }
    metrics = compute_ablation_metrics(results)
    m = metrics["agent_tools_evidence_validator"]
    assert m["cases"] == 2
    assert m["validator_intercept_rate"] == 0.5  # 1 out of 2
    assert m["error_conclusion_leakage"] == 0.0
    assert m["total_cost_usd"] == 0.05


# ---------------------------------------------------------------------------
# MiniLedger tests
# ---------------------------------------------------------------------------

def test_mini_ledger_attribute_access():
    record = _DictRecord({"evidence_id": "test_123", "value": 42.0, "available_at": "2025-01-01T00:00:00+08:00"})
    assert record.evidence_id == "test_123"
    assert record.value == 42.0
    assert record.available_at == "2025-01-01T00:00:00+08:00"
    assert record.metric is None  # missing attribute → None


def test_mini_ledger_with_validator():
    """Test that the FinancialValidator works with _MiniLedger."""
    from src.validation.financial_validator import FinancialValidator
    records = [
        {"evidence_id": "fact_1", "kind": "fact", "symbol": "600519.SH", "metric": "close",
         "value": 1.0, "currency": "CNY", "unit": "CNY/share", "fiscal_period": None,
         "period_basis": "RAW", "published_at": "2025-03-31T15:00:00+08:00",
         "available_at": "2025-03-31T15:00:00+08:00", "provider": "snapshot", "field_path": None,
         "source_url": None, "input_ids": (), "operation": None},
    ]
    validator = FinancialValidator(max_data_age_days=365)
    # Recent data → valid
    result = validator.validate(_MiniLedger(records), research_as_of="2025-04-01T00:00:00+08:00")
    assert result.valid
    # Expired data → invalid
    result2 = validator.validate(_MiniLedger(records), research_as_of="2026-08-10T00:00:00+08:00")
    assert not result2.valid
    assert any("expired" in e for e in result2.errors)


# ---------------------------------------------------------------------------
# End-to-end dry-run test
# ---------------------------------------------------------------------------

def test_agent_ablation_e2e_dry_run():
    """End-to-end dry-run should produce all expected output files."""
    from scripts.run_agent_ablation import main
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        exit_code = main([
            "--dry-run", "--cases", str(ABLATION_CASES), "--output", str(out),
        ])
        assert exit_code == 0
        # Check all output files
        assert (out / "ablation_results.json").exists()
        assert (out / "ablation_metrics.csv").exists()
        assert (out / "ablation_details.csv").exists()
        assert (out / "ablation_report.md").exists()
        # Validate JSON content
        report = json.loads((out / "ablation_results.json").read_text(encoding="utf-8"))
        assert report["dry_run"] is True
        assert len(report["variants"]) == 4
        for variant in ABLATION_VARIANTS:
            assert variant in report["metrics"]
            assert variant in report["detailed_results"]
            assert len(report["detailed_results"][variant]) == 7  # all 7 cases
