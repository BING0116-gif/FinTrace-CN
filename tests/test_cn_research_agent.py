"""Offline product-loop tests for the shared CnResearchAgent.

All providers are fakes — no network, no real LLM, no .env dependency.
These cover the behaviours the product workbench relies on: event callbacks,
cooperative cancellation, external research-as-of cutoffs, step limits,
invalid tool arguments, and Validator blocking.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.cn.offline_agent import OfflineCnAgent, SYSTEM_PROMPT
from src.cn.research_agent import CnResearchAgent


FIXTURE = Path(__file__).parent / "fixtures" / "cn" / "600519.SH_illustrative_v1.json"
CUTOFF = "2025-04-01T00:00:00+08:00"
PAST_CUTOFF = "2024-01-01T00:00:00+08:00"


def _call(name, arguments, parse_error=None, call_id="call-1"):
    return SimpleNamespace(id=call_id, name=name, arguments=arguments, parse_error=parse_error)


def _final(text="已完成。", cost=0.01):
    return SimpleNamespace(
        has_tool_calls=False, text=text, raw={"role": "assistant", "content": text},
        tool_calls=None, cost=cost,
    )


def _tool(text="", calls=None, cost=0.01):
    return SimpleNamespace(
        has_tool_calls=True, text=text,
        raw={"role": "assistant", "tool_calls": (calls or [])},
        tool_calls=calls or [], cost=cost,
    )


class _ScriptedProvider:
    """Return a scripted sequence of responses, optionally capturing prompts."""

    model_name = "gpt-4o-mini"
    api_style = "openai"

    def __init__(self, responses):
        self.responses = list(responses)
        self.messages_seen = []

    async def call_with_tools(self, messages, tools, temperature=0.0, **kwargs):
        self.messages_seen.append(messages)
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# Prices / normal success path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_research_agent_price_path_passes_validator():
    provider = _ScriptedProvider([
        _tool(calls=[_call("get_cn_prices", {"ticker": "600519.SH"})]),
        _final(),
    ])
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=4)
    state = await agent.run("查询 600519.SH 的价格")

    # Query names the canonical symbol, so deterministic pre-flight resolves it first.
    assert [t.tool_name for t in state.tool_trace] == ["resolve_cn_symbol", "get_cn_prices"]
    prices = next(t for t in state.tool_trace if t.tool_name == "get_cn_prices")
    assert prices.result_status == "ok"
    assert prices.evidence_ids == ["fact_600519_SH_close_2025-03-31_RAW"]
    assert state.validation_result == {"valid": True, "errors": [], "missing_evidence": []}


# ---------------------------------------------------------------------------
# Financials / external research-as-of forwarded to the tool
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_research_agent_forwards_external_cutoff_to_financials_tool():
    provider = _ScriptedProvider([
        _tool(calls=[_call("get_cn_financials", {"ticker": "600519.SH", "research_as_of": CUTOFF})]),
        _final(),
    ])
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=4)
    state = await agent.run("查询 600519.SH 的收入和净利润", research_as_of=CUTOFF)

    assert state.research_as_of == CUTOFF
    fin = next(t for t in state.tool_trace if t.tool_name == "get_cn_financials")
    assert fin.arguments["research_as_of"] == CUTOFF
    assert state.validation_result == {"valid": True, "errors": [], "missing_evidence": []}


@pytest.mark.asyncio
async def test_research_agent_injects_external_cutoff_into_system_prompt():
    provider = _ScriptedProvider([_tool(calls=[_call("get_cn_prices", {"ticker": "600519.SH"})]), _final()])
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=4)
    await agent.run("查询 600519.SH 的价格", research_as_of=CUTOFF)

    system = provider.messages_seen[0][0]["content"]
    assert CUTOFF in system
    assert f"The fixed research cutoff is {CUTOFF}" in system


# ---------------------------------------------------------------------------
# Future disclosure / point-in-time: figures published after the cutoff
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_research_agent_blocks_future_disclosure_at_past_cutoff():
    provider = _ScriptedProvider([
        _tool(calls=[_call("get_cn_financials", {"ticker": "600519.SH", "research_as_of": PAST_CUTOFF})]),
        _final("收入为 100 亿元，净利润为 50 亿元。"),
    ])
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=4)
    state = await agent.run("查询 600519.SH 的收入和净利润", research_as_of=PAST_CUTOFF)

    assert state.validation_result["valid"] is False
    assert "no_evidence" in state.validation_result["errors"]
    assert state.report.startswith("无法验证/拒绝结论")


# ---------------------------------------------------------------------------
# Missing evidence: a metric the snapshot never reports
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_research_agent_blocks_requested_metric_with_no_evidence():
    provider = _ScriptedProvider([
        _tool(calls=[_call("get_cn_financials", {"ticker": "600519.SH", "research_as_of": CUTOFF})]),
        _final(),
    ])
    agent = CnResearchAgent(
        snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=4,
        required_metrics=("ebitda",),
    )
    state = await agent.run("查询 600519.SH 的 EBITDA", research_as_of=CUTOFF)

    assert state.validation_result["valid"] is False
    assert "requested_metric_missing:ebitda" in state.validation_result["errors"]


# ---------------------------------------------------------------------------
# Wrong symbol: tool execution error must not produce a conclusion
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_research_agent_blocks_wrong_symbol_tool_error():
    provider = _ScriptedProvider([
        _tool(calls=[_call("get_cn_prices", {"ticker": "BADCODE"})]),
        _final("BADCODE has a definite conclusion."),
    ])
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=3)
    state = await agent.run("Give a conclusion for BADCODE")

    assert state.validation_result["valid"] is False
    assert any(e.startswith("tool_error:get_cn_prices") for e in state.validation_result["errors"])


# ---------------------------------------------------------------------------
# Max steps: agent must terminate and still return a visible answer
# ---------------------------------------------------------------------------
class _AlwaysToolProvider:
    model_name = "gpt-4o-mini"
    api_style = "openai"

    def __init__(self):
        self.calls = 0

    async def call_with_tools(self, messages, tools, temperature=0.0, **kwargs):
        self.calls += 1
        if self.calls <= 3:
            return _tool(calls=[_call("get_cn_prices", {"ticker": "600519.SH"})])
        return _final("已达步骤上限，给出最终答复。", cost=0.01)


@pytest.mark.asyncio
async def test_research_agent_stops_at_step_limit():
    provider = _AlwaysToolProvider()
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=3)
    state = await agent.run("分析价格走势")

    # 3 loop turns + 1 forced final turn when the loop reaches its bound.
    assert agent.llm_calls == 4
    assert state.report.strip()
    assert state.validation_result is not None


# ---------------------------------------------------------------------------
# Invalid tool arguments: record the parse error, never execute the tool
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_research_agent_records_tool_parse_error_without_executing():
    provider = _ScriptedProvider([
        _tool(calls=[_call("get_cn_prices", {}, parse_error="Missing required argument 'ticker'")]),
        _final("结果未知。"),
    ])
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=4)
    state = await agent.run("查询价格")

    assert state.tool_trace[0].tool_name == "get_cn_prices"
    assert state.tool_trace[0].result_status == "error"
    assert not state.tool_trace[0].evidence_ids
    assert state.validation_result["valid"] is False


# ---------------------------------------------------------------------------
# Cooperative cancellation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_research_agent_cancels_before_execution():
    events = []
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=_ScriptedProvider([]), max_steps=4)
    state = await agent.run(
        "查询价格", event_handler=lambda event: events.append(event["event"]),
        cancellation_check=lambda: True,
    )
    assert agent.answer == "研究任务已取消。"
    assert state.validation_result["valid"] is False
    assert "cancelled" in state.validation_result["errors"]
    assert "task_cancelled" in events


@pytest.mark.asyncio
async def test_research_agent_cooperatively_stops_mid_loop():
    provider = _ScriptedProvider([
        _tool(calls=[_call("get_cn_prices", {"ticker": "600519.SH"})]),
        _final(),
    ])
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=4)
    check_calls = {"n": 0}

    def cooperative_cancel():
        check_calls["n"] += 1
        return check_calls["n"] >= 3  # pre-flight check, iteration-0 check, then stop before iteration 1

    state = await agent.run("查询价格", cancellation_check=cooperative_cancel)

    assert len(state.tool_trace) == 1
    assert state.validation_result["valid"] is False
    assert "cancelled" in state.validation_result["errors"]


# ---------------------------------------------------------------------------
# Product / benchmark parity: one shared implementation
# ---------------------------------------------------------------------------
def test_offline_agent_is_the_shared_product_agent():
    assert OfflineCnAgent is CnResearchAgent
    assert SYSTEM_PROMPT  # shared system prompt exists


@pytest.mark.asyncio
async def test_event_callback_reports_deterministic_trail():
    events = []
    provider = _ScriptedProvider([
        _tool(calls=[_call("get_cn_prices", {"ticker": "600519.SH"})]),
        _final(),
    ])
    agent = CnResearchAgent(snapshot_path=FIXTURE, model_name="gpt-4o-mini", provider=provider, max_steps=4)
    await agent.run("查询 600519.SH 的价格", event_handler=lambda event: events.append(event))

    names = [event["event"] for event in events]
    for expected in ("agent_started", "llm_call_started", "llm_call_completed",
                     "tool_call_started", "tool_call_completed", "validation_started",
                     "validation_passed", "task_completed"):
        assert expected in names