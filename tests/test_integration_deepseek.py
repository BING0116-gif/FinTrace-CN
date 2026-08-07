"""
Real DeepSeek integration tests (Batch 4).

These tests call the REAL DeepSeek API and incur (small) cost. They are marked
``integration`` and are skipped automatically when ``DEEPSEEK_API_KEY`` is not
set, so the default ``pytest -q`` stays free and CI-safe.

Run them explicitly (requires a key):
    pytest -m integration -v

To guarantee zero cost even when a key is present:
    pytest -q -m "not integration"

Coverage (per the batch-4 spec — "first version calls Flash only"):
  1. test_deepseek_plain_chat   — one normal conversation (sync, no tools)
  2. test_deepseek_tool_call    — one tool-calling flow (async)
  3. test_aapl_lightweight_e2e  — AAPL price question via GeneralistAgent
"""

from __future__ import annotations

import os
import sys
import time

import pytest

# ---------------------------------------------------------------------------
# sys.path setup — same convention as test_model_registry.py / test_batch3.py
# ---------------------------------------------------------------------------
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# File-level marker: every test in this module is a real integration test.
pytestmark = pytest.mark.integration

# Skip the whole module when no key is present — no cost, no network.
_skip_no_key = pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="DEEPSEEK_API_KEY not set; skipping real DeepSeek integration tests",
)


# ============================================================================
# 1. Plain chat (sync, no tools)
# ============================================================================
@_skip_no_key
def test_deepseek_plain_chat():
    """One real DeepSeek conversation via the sync client — no tool calling."""
    from llms.openai_compatible import deepseek_v4_flash

    messages = [{"role": "user", "content": "Reply with exactly one word: pong"}]
    text, cost = deepseek_v4_flash(messages, 0.0)

    assert "pong" in text.lower(), f"Expected 'pong' in response, got: {text!r}"
    assert cost > 0, "Cost must be positive for a real API call"
    print(f"\n[plain_chat] cost=${cost:.6f} | response={text!r}")


# ============================================================================
# 2. Tool-calling flow (async)
# ============================================================================
@_skip_no_key
@pytest.mark.asyncio
async def test_deepseek_tool_call():
    """One real DeepSeek tool-calling turn via the async provider."""
    from llms.config import init_llm
    from llms.async_client import AsyncLLMProvider

    # get_async_llm() reads the sync global provider's current_model, so init it
    # to deepseek-v4-flash before constructing the async provider.
    init_llm("deepseek-v4-flash")
    provider = AsyncLLMProvider("deepseek-v4-flash")

    # A trivial tool in OpenAI function-calling schema (DeepSeek speaks the
    # OpenAI wire protocol, api_style="openai").
    echo_tool = [{
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Echo back the given text verbatim.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to echo"}
                },
                "required": ["text"],
            },
        },
    }]
    messages = [{"role": "user", "content": "Call the echo tool with text 'hello'."}]

    resp = await provider.call_with_tools(messages, echo_tool, temperature=0.0)

    assert resp.has_tool_calls, "Model should request the echo tool"
    call = resp.tool_calls[0]
    assert call.name == "echo", f"Expected tool 'echo', got {call.name!r}"
    assert call.arguments.get("text") == "hello", (
        f"Expected text='hello', got {call.arguments!r}"
    )
    assert resp.cost > 0, "Cost must be positive for a real API call"
    print(
        f"\n[tool_call] cost=${resp.cost:.6f} | tool={call.name} | args={call.arguments}"
    )


# ============================================================================
# 3. AAPL lightweight E2E (via GeneralistAgent — keyless get_prices tool)
# ============================================================================
@_skip_no_key
@pytest.mark.asyncio
async def test_aapl_lightweight_e2e():
    """AAPL price question through the full GeneralistAgent ReAct loop.

    Triggers the keyless ``get_prices`` tool (yfinance, no API key needed).
    Captures cost, latency, and the tool trajectory (``agent._tools_used``).
    Tool selection is NOT hard-asserted (model behaviour is non-deterministic);
    only status / answer / cost are hard-asserted.
    """
    from llms.config import init_llm
    from agents.generalist_agent import GeneralistAgent

    init_llm("deepseek-v4-flash")

    agent = GeneralistAgent(
        email="integration-test@example.com",
        timestamp="20260806_120000",
        user_prompt=(
            "Use the get_prices tool to find Apple's (AAPL) current stock "
            "price, then answer in one line."
        ),
        session_id=None,
        max_iterations=4,  # cost cap — a price question finishes in 1-2 rounds
    )

    t0 = time.perf_counter()
    result = await agent.run()
    latency = time.perf_counter() - t0

    assert result["status"] == "completed", (
        f"Expected status='completed', got {result.get('status')!r}"
    )
    assert result.get("answer"), "Final answer must be non-empty"
    assert result.get("total_cost", 0) > 0, "Cost must be positive for a real run"
    assert latency < 120, f"E2E run too slow: {latency:.1f}s (expected < 120s)"

    tools_used = sorted(agent._tools_used)
    print(
        f"\n[aapl_e2e] cost=${result['total_cost']:.6f} | latency={latency:.1f}s "
        f"| tools={tools_used} | answer={result['answer'][:200]!r}"
    )
