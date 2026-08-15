from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.cn.benchmark import BenchmarkCase, evaluate_research_state
from src.cn.offline_agent import OfflineCnAgent


FIXTURE = Path(__file__).parent / "fixtures" / "cn" / "600519.SH_illustrative_v1.json"


class _Provider:
    model_name = "gpt-4o-mini"
    api_style = "openai"

    def __init__(self):
        self.turn = 0

    async def call_with_tools(self, messages, tools, temperature=0.0, **kwargs):
        self.turn += 1
        if self.turn == 1:
            calls = [SimpleNamespace(id="call-1", name="get_cn_prices", arguments={"ticker": "600519.SH"}, parse_error=None)]
        else:
            return SimpleNamespace(has_tool_calls=False, text="已完成。", raw={"role": "assistant", "content": "已完成。"}, cost=0.02)
        return SimpleNamespace(has_tool_calls=True, text="", raw={"role": "assistant", "tool_calls": []}, tool_calls=calls, cost=0.01)


class _ErrorProvider:
    model_name = "gpt-4o-mini"
    api_style = "openai"

    def __init__(self):
        self.turn = 0

    async def call_with_tools(self, messages, tools, temperature=0.0, **kwargs):
        self.turn += 1
        if self.turn == 1:
            call = SimpleNamespace(id="call-1", name="resolve_cn_symbol", arguments={"query": "BADCODE"}, parse_error=None)
            return SimpleNamespace(has_tool_calls=True, text="", raw={"role": "assistant", "tool_calls": []}, tool_calls=[call], cost=0.01)
        return SimpleNamespace(has_tool_calls=False, text="BADCODE has a definite conclusion.", raw={"role": "assistant", "content": "done"}, cost=0.01)


@pytest.mark.asyncio
async def test_offline_agent_executes_real_cn_tools_and_records_trace_and_evidence():
    provider = _Provider()
    agent = OfflineCnAgent(snapshot_path=FIXTURE, model_name=provider.model_name, provider=provider, max_steps=4)
    state = await agent.run("查询 600519.SH 的价格")

    assert [trace.tool_name for trace in state.tool_trace] == ["resolve_cn_symbol", "get_cn_prices"]
    assert state.tool_trace[1].arguments == {"ticker": "600519.SH"}
    assert state.tool_trace[1].result_status == "ok"
    assert state.tool_trace[1].evidence_ids == ["fact_600519_SH_close_2025-03-31_RAW"]
    assert state.validation_result == {"valid": True, "errors": [], "missing_evidence": []}
    assert state.cost_trace == [{"model": "gpt-4o-mini", "cost_usd": 0.03, "llm_calls": 2, "steps": 2}]

    case = BenchmarkCase("case", "routing", state.query, ["resolve_cn_symbol", "get_cn_prices"],
                         {"resolve_cn_symbol": {"query": "600519.SH"}, "get_cn_prices": {"ticker": "600519.SH"}},
                         ["fact_600519_SH_close_2025-03-31_RAW"])
    result = evaluate_research_state(case, state)
    assert result["passed"]
    assert result["llm_calls"] == 2
    assert result["cost_usd"] == 0.03
    assert result["research_state"]["tool_trace"][1]["evidence_ids"] == ["fact_600519_SH_close_2025-03-31_RAW"]


@pytest.mark.asyncio
async def test_offline_agent_gate_rejects_tool_error_without_evidence():
    agent = OfflineCnAgent(
        snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=_ErrorProvider(), max_steps=3,
    )

    state = await agent.run("Give a deterministic conclusion for BADCODE")

    assert state.validation_result is not None
    assert state.validation_result["valid"] is False
    assert "tool_error:resolve_cn_symbol" in state.validation_result["errors"]
    assert "no_evidence" in state.validation_result["errors"]
    assert state.report is not None and state.report.startswith("无法验证/拒绝结论")


def test_all_snapshot_case_builder_covers_each_local_snapshot():
    from scripts.run_benchmark import _all_snapshot_cases

    snapshot_dir = Path(__file__).parents[1] / "data" / "snapshots" / "cn"
    snapshot_paths = list(snapshot_dir.glob("*.json"))
    cases = _all_snapshot_cases(snapshot_dir)
    assert snapshot_paths
    assert len(cases) == len(snapshot_paths)
    assert all(case.snapshot_path and case.required_evidence for case in cases)
