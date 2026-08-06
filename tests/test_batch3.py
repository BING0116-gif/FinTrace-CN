"""
Batch 3 tests: Agent & async call adaptation.

All tests use Mock — zero real API requests.
"""

import os
import sys
import json
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import openai as openai_module
import anthropic as anthropic_module

from llms.model_registry import MODEL_REGISTRY, get_model_info
from llms.config import LLMProvider, init_llm, _SYNC_MODEL_FUNCTIONS


# ---------------------------------------------------------------------------
# Helper: reset all cached async clients
# ---------------------------------------------------------------------------
def _reset_async_clients(monkeypatch):
    import llms.async_client as ac
    monkeypatch.setattr(ac, "_async_deepseek", None)
    monkeypatch.setattr(ac, "_async_openai", None)
    monkeypatch.setattr(ac, "_async_anthropic", None)


# ---------------------------------------------------------------------------
# Helper: install a fake AsyncOpenAI that captures kwargs and returns a
# canned response.  Returns (captured_kwargs_dict, create_calls_list).
# ---------------------------------------------------------------------------
def _fake_async_openai(monkeypatch, canned_response=None):
    """Patch openai.AsyncOpenAI with a fake that captures __init__ kwargs
    and returns canned responses from chat.completions.create()."""
    import llms.async_client as ac
    _reset_async_clients(monkeypatch)

    captured_init = {}
    create_calls = []
    _response = canned_response

    class FakeCompletions:
        async def create(self, **kwargs):
            create_calls.append(kwargs)
            if _response is not None:
                return _response
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="mock"))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            )

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured_init.update(kwargs)
        chat = FakeChat()

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    # Also patch inside async_client's namespace for any direct references
    monkeypatch.setattr(ac, "AsyncOpenAI", FakeAsyncOpenAI, raising=False)
    return captured_init, create_calls


def _fake_async_anthropic(monkeypatch, canned_response=None):
    """Patch anthropic.AsyncAnthropic with a fake."""
    import llms.async_client as ac
    _reset_async_clients(monkeypatch)

    captured_init = {}
    create_calls = []
    _response = canned_response

    class FakeMessages:
        @staticmethod
        async def create(**kwargs):
            create_calls.append(kwargs)
            if _response is not None:
                return _response
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Hello from Claude")],
                usage=SimpleNamespace(input_tokens=10, output_tokens=20),
            )

    class FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured_init.update(kwargs)
        messages = FakeMessages()

    monkeypatch.setattr(anthropic_module, "AsyncAnthropic", FakeAsyncAnthropic)
    monkeypatch.setattr(ac, "AsyncAnthropic", FakeAsyncAnthropic, raising=False)
    return captured_init, create_calls


# ============================================================================
# 1. _SYNC_MODEL_FUNCTIONS keys == MODEL_REGISTRY keys
# ============================================================================
def test_sync_model_functions_keys_equal_registry():
    """set(_SYNC_MODEL_FUNCTIONS) == set(MODEL_REGISTRY)."""
    assert set(_SYNC_MODEL_FUNCTIONS.keys()) == set(MODEL_REGISTRY.keys()), (
        f"Keys differ!\n"
        f"  In _SYNC_MODEL_FUNCTIONS but not registry: "
        f"{set(_SYNC_MODEL_FUNCTIONS) - set(MODEL_REGISTRY)}\n"
        f"  In registry but not _SYNC_MODEL_FUNCTIONS: "
        f"{set(MODEL_REGISTRY) - set(_SYNC_MODEL_FUNCTIONS)}"
    )


# ============================================================================
# 2. LLMProvider.MODELS is removed
# ============================================================================
def test_llm_provider_models_removed():
    """LLMProvider no longer has a public MODELS attribute."""
    assert not hasattr(LLMProvider, "MODELS"), (
        "LLMProvider.MODELS must be removed in batch 3"
    )


# ============================================================================
# 3. get_async_llm() does NOT depend on LLMProvider.MODELS
# ============================================================================
def test_get_async_llm_no_models_dependency(monkeypatch):
    """get_async_llm() validates via get_model_info(), not LLMProvider.MODELS."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    init_llm("gpt-4o-mini")

    from llms.async_client import get_async_llm
    provider = get_async_llm()
    assert provider is not None
    assert provider.model_name == "gpt-4o-mini"


# ============================================================================
# 4. DeepSeek async client — independent API key and Base URL
# ============================================================================
def test_deepseek_async_client_independent_key_and_url(monkeypatch):
    """DeepSeek async client uses DEEPSEEK_API_KEY and DEEPSEEK_BASE_URL,
    never OPENAI_API_KEY."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-async")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://custom-deepseek.example.com")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-different")

    captured_init, _ = _fake_async_openai(monkeypatch)

    import llms.async_client as ac
    ac._get_async_deepseek()

    assert captured_init["api_key"] == "sk-ds-async", (
        "DeepSeek async client must use DEEPSEEK_API_KEY"
    )
    assert captured_init["base_url"] == "https://custom-deepseek.example.com", (
        "DeepSeek async client must use DEEPSEEK_BASE_URL"
    )
    assert captured_init["api_key"] != "sk-openai-different", (
        "DeepSeek async client must NOT use OPENAI_API_KEY"
    )


def test_deepseek_async_client_default_base_url(monkeypatch):
    """When DEEPSEEK_BASE_URL is not set, fallback to https://api.deepseek.com."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-default")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    captured_init, _ = _fake_async_openai(monkeypatch)

    import llms.async_client as ac
    ac._get_async_deepseek()

    assert captured_init["base_url"] == "https://api.deepseek.com", (
        f"Default base_url mismatch: {captured_init.get('base_url')}"
    )


# ============================================================================
# 5. DeepSeek async client is separate from OpenAI async client
# ============================================================================
def test_deepseek_and_openai_async_clients_are_separate(monkeypatch):
    """DeepSeek and OpenAI async clients are different instances."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-sep")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-sep")

    instances = []

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            instances.append(kwargs)
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="x"))],
                        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                    )

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)

    import llms.async_client as ac
    monkeypatch.setattr(ac, "_async_deepseek", None)
    monkeypatch.setattr(ac, "_async_openai", None)

    ds = ac._get_async_deepseek()
    oai = ac._get_async_openai()

    assert len(instances) == 2
    assert instances[0] is not instances[1]
    assert instances[0].get("api_key") == "sk-ds-sep"
    # OpenAI has no explicit api_key (reads from env)
    assert "api_key" not in instances[1]


# ============================================================================
# 6. DeepSeek regular async request — extra_body with thinking disabled
# ============================================================================
@pytest.mark.asyncio
async def test_deepseek_async_regular_request_sends_extra_body(monkeypatch):
    """DeepSeek plain-text async request sends extra_body={'thinking': {'type': 'disabled'}}."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-eb")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    _, create_calls = _fake_async_openai(monkeypatch)

    from llms.async_client import _call_deepseek_async

    text, cost = await _call_deepseek_async(
        "deepseek-v4-flash",
        [{"role": "user", "content": "Hello"}],
        0.3,
    )

    assert text == "mock"
    assert create_calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}, (
        "DeepSeek async request must send extra_body"
    )
    assert "reasoning_effort" not in create_calls[0], (
        "DeepSeek async request must NOT send reasoning_effort"
    )


# ============================================================================
# 7. DeepSeek tool-call request — extra_body with thinking disabled
# ============================================================================
@pytest.mark.asyncio
async def test_deepseek_tool_call_sends_extra_body(monkeypatch):
    """DeepSeek tool-call request sends extra_body={'thinking': {'type': 'disabled'}}."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-tools")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    canned = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(
                    name="get_prices",
                    arguments='{"ticker": "AAPL"}',
                ),
            )],
        ))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )
    _, create_calls = _fake_async_openai(monkeypatch, canned_response=canned)

    from llms.async_client import _call_deepseek_tools

    resp = await _call_deepseek_tools(
        "deepseek-v4-flash",
        [{"role": "user", "content": "Get AAPL price"}],
        [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}],
        0.3,
    )

    assert create_calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}, (
        "DeepSeek tool-call request must send extra_body"
    )
    assert "reasoning_effort" not in create_calls[0], (
        "DeepSeek tool-call request must NOT send reasoning_effort"
    )
    assert resp.has_tool_calls
    assert resp.tool_calls[0].name == "get_prices"


# ============================================================================
# 8. OpenAI does NOT receive DeepSeek parameters
# ============================================================================
@pytest.mark.asyncio
async def test_openai_async_no_extra_body(monkeypatch):
    """OpenAI async request must NOT receive extra_body or reasoning_effort."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-async")

    _, create_calls = _fake_async_openai(monkeypatch)

    from llms.async_client import _call_openai_async

    text, cost = await _call_openai_async(
        "gpt-4o-mini",
        [{"role": "user", "content": "Hi"}],
        0.3,
    )

    assert text == "mock"
    assert "extra_body" not in create_calls[0], "OpenAI must NOT receive extra_body"
    assert "reasoning_effort" not in create_calls[0], "OpenAI must NOT receive reasoning_effort"


@pytest.mark.asyncio
async def test_openai_tools_no_extra_body(monkeypatch):
    """OpenAI tool-call request must NOT receive extra_body."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-tools")

    canned = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(
                id="c1",
                function=SimpleNamespace(name="f", arguments="{}"),
            )],
        ))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    _, create_calls = _fake_async_openai(monkeypatch, canned_response=canned)

    from llms.async_client import _call_openai_tools

    resp = await _call_openai_tools(
        "gpt-4o-mini",
        [{"role": "user", "content": "Hi"}],
        [{"type": "function", "function": {"name": "f", "parameters": {}}}],
        0.3,
    )

    assert "extra_body" not in create_calls[0], "OpenAI tools must NOT receive extra_body"
    assert "reasoning_effort" not in create_calls[0]


# ============================================================================
# 9. Anthropic path unchanged
# ============================================================================
@pytest.mark.asyncio
async def test_anthropic_async_path_unchanged(monkeypatch):
    """Anthropic async path still uses AsyncAnthropic, no extra_body."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-ok")

    _, create_calls = _fake_async_anthropic(monkeypatch)

    from llms.async_client import _call_anthropic_async

    text, cost = await _call_anthropic_async(
        "claude-3.5-sonnet",
        [{"role": "user", "content": "Hello"}],
        0.3,
    )

    assert text == "Hello from Claude"
    assert "extra_body" not in create_calls[0], "Anthropic must NOT receive extra_body"
    assert "reasoning_effort" not in create_calls[0]
    assert create_calls[0]["model"] == "claude-3-5-sonnet-20241022"


# ============================================================================
# 10. DeepSeek uses OpenAI message and Tool Schema (api_style="openai")
# ============================================================================
def test_deepseek_api_style_is_openai():
    """DeepSeek models have api_style='openai'."""
    for name in ("deepseek-v4-flash", "deepseek-v4-pro"):
        info = get_model_info(name)
        assert info.api_style == "openai", f"{name} must have api_style='openai'"


def test_deepseek_async_provider_is_openai_style():
    """AsyncLLMProvider.is_openai returns True for DeepSeek (api_style='openai')."""
    from llms.async_client import AsyncLLMProvider
    provider = AsyncLLMProvider("deepseek-v4-flash")
    assert provider.is_openai is True, (
        "DeepSeek must have is_openai=True (api_style='openai')"
    )
    assert provider._info.provider == "deepseek"


def test_claude_is_not_openai_style():
    """Claude models have api_style='anthropic', is_openai=False."""
    from llms.async_client import AsyncLLMProvider
    provider = AsyncLLMProvider("claude-3.5-sonnet")
    assert provider.is_openai is False, "Claude must have is_openai=False"
    assert provider._info.api_style == "anthropic"


# ============================================================================
# 11. Two-round DeepSeek tool call can round-trip correctly
# ============================================================================
@pytest.mark.asyncio
async def test_deepseek_two_round_tool_call_roundtrip(monkeypatch):
    """Two consecutive DeepSeek tool-call turns: round 1 returns tool_call,
    round 2 returns final answer."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-2round")

    call_count = [0]

    class FakeCompletions:
        async def create(self, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="Let me check the price.",
                        tool_calls=[SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="get_prices",
                                arguments='{"ticker": "AAPL"}',
                            ),
                        )],
                    ))],
                    usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                )
            else:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="The price of AAPL is $150.",
                        tool_calls=None,
                    ))],
                    usage=SimpleNamespace(prompt_tokens=200, completion_tokens=30, total_tokens=230),
                )

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            pass
        chat = FakeChat()

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    _reset_async_clients(monkeypatch)

    from llms.async_client import AsyncLLMProvider

    provider = AsyncLLMProvider("deepseek-v4-flash")

    # -- Round 1: tool call --
    tools = [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}]
    messages = [{"role": "user", "content": "What's AAPL price?"}]

    resp1 = await provider.call_with_tools(messages, tools, temperature=0.3)
    assert resp1.has_tool_calls
    assert resp1.tool_calls[0].name == "get_prices"
    assert resp1.tool_calls[0].arguments == {"ticker": "AAPL"}

    # Append assistant + tool result to transcript
    messages.append(resp1.raw)
    messages.append({
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"status": "ok", "price": 150}',
    })

    # -- Round 2: final answer --
    resp2 = await provider.call_with_tools(messages, [], temperature=0.3)
    assert not resp2.has_tool_calls
    assert "AAPL" in resp2.text
    assert call_count[0] == 2


# ============================================================================
# 12. Illegal tool arguments — NOT replaced with {}
# ============================================================================
@pytest.mark.asyncio
async def test_illegal_tool_args_not_replaced_with_empty(monkeypatch):
    """When tool arguments are invalid JSON, ToolCall has parse_error, NOT {}."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-bad")

    canned = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(
                id="bad_1",
                function=SimpleNamespace(
                    name="get_prices",
                    arguments='this is not json {{{',
                ),
            )],
        ))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    _, _ = _fake_async_openai(monkeypatch, canned_response=canned)

    from llms.async_client import _call_openai_tools

    resp = await _call_openai_tools(
        "gpt-4o-mini",
        [{"role": "user", "content": "Hi"}],
        [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}],
        0.3,
    )

    assert resp.has_tool_calls
    tc = resp.tool_calls[0]
    assert tc.parse_error is not None, "Invalid JSON must produce parse_error"
    assert "get_prices" in tc.parse_error, "parse_error must contain tool name"
    assert "this is not json" in tc.parse_error, "parse_error must contain raw args"
    assert tc.arguments == {}  # placeholder, but parse_error is set


# ============================================================================
# 13. Illegal tool args — agent returns error as tool_result, does NOT execute
# ============================================================================
@pytest.mark.asyncio
async def test_illegal_tool_args_agent_returns_error(monkeypatch):
    """Agent with parse_error returns error as tool_result, does NOT execute tool."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-agent")

    call_count = [0]

    class FakeCompletions:
        async def create(self, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="",
                        tool_calls=[SimpleNamespace(
                            id="bad_1",
                            function=SimpleNamespace(
                                name="get_prices",
                                arguments='not valid json !!!',
                            ),
                        )],
                    ))],
                    usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
                )
            else:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="I fixed the arguments.",
                        tool_calls=None,
                    ))],
                    usage=SimpleNamespace(prompt_tokens=5, completion_tokens=10, total_tokens=15),
                )

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            pass
        chat = FakeChat()

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    _reset_async_clients(monkeypatch)

    from llms.async_client import AsyncLLMProvider

    provider = AsyncLLMProvider("gpt-4o-mini")
    tools = [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}]
    messages = [{"role": "user", "content": "Get price"}]

    resp1 = await provider.call_with_tools(messages, tools, temperature=0.3)
    assert resp1.has_tool_calls
    tc = resp1.tool_calls[0]
    assert tc.parse_error is not None
    assert "not valid json" in tc.parse_error

    # Simulate what the agent does: append raw + tool_result with error
    messages.append(resp1.raw)
    messages.append({
        "role": "tool",
        "tool_call_id": tc.id,
        "content": json.dumps({"status": "error", "error": tc.parse_error, "tool": tc.name}),
    })

    # Round 2: model should fix and produce final answer
    resp2 = await provider.call_with_tools(messages, [], temperature=0.3)
    assert not resp2.has_tool_calls
    assert "I fixed" in resp2.text


# ============================================================================
# 14. Cost calculation — OpenAI
# ============================================================================
def test_openai_cost_precise():
    """OpenAI cost is calculated correctly from registry pricing."""
    from llms.cost_calculator import calculate_cost_openai

    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=500_000),
    )
    cost = calculate_cost_openai(response, "gpt-4o-mini")
    assert cost == pytest.approx(0.45, abs=0.001)


def test_gpt_5_4_mini_cost_precise():
    """gpt-5.4-mini cost is calculated correctly."""
    from llms.cost_calculator import calculate_cost_openai

    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=2_000_000, completion_tokens=1_000_000),
    )
    cost = calculate_cost_openai(response, "gpt-5.4-mini")
    assert cost == pytest.approx(6.00, abs=0.01)


# ============================================================================
# 15. Cost calculation — Anthropic
# ============================================================================
def test_anthropic_cost_precise():
    """Anthropic cost is calculated correctly from registry pricing."""
    from llms.cost_calculator import calculate_cost_anthropic

    response = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=500_000),
    )
    cost = calculate_cost_anthropic(response, "claude-3.5-sonnet")
    assert cost == pytest.approx(10.50, abs=0.01)


def test_claude_opus_cost_precise():
    """claude-3-opus cost is calculated correctly."""
    from llms.cost_calculator import calculate_cost_anthropic

    response = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=100_000, output_tokens=50_000),
    )
    cost = calculate_cost_anthropic(response, "claude-3-opus")
    assert cost == pytest.approx(1.50 + 3.75, abs=0.01)


# ============================================================================
# 16. Cost calculation — DeepSeek
# ============================================================================
def test_deepseek_cost_precise():
    """DeepSeek cost is calculated correctly."""
    from llms.cost_calculator import calculate_cost_openai

    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000),
    )
    cost = calculate_cost_openai(response, "deepseek-v4-flash")
    assert cost == pytest.approx(0.42, abs=0.01)


# ============================================================================
# 17. DeepSeek cache-hit cost — precise
# ============================================================================
def test_deepseek_cache_hit_cost_precise():
    """DeepSeek cache-hit cost uses discounted rate."""
    from llms.cost_calculator import calculate_cost_openai

    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
            total_tokens=1_500_000,
            prompt_cache_hit_tokens=800_000,
            prompt_cache_miss_tokens=200_000,
        ),
    )
    cost = calculate_cost_openai(response, "deepseek-v4-flash")
    assert cost == pytest.approx(0.17024, abs=0.001)


def test_deepseek_v4_pro_cache_hit_cost():
    """deepseek-v4-pro cache-hit cost uses discounted rate."""
    from llms.cost_calculator import calculate_cost_openai

    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            total_tokens=2_000_000,
            prompt_cache_hit_tokens=500_000,
            prompt_cache_miss_tokens=500_000,
        ),
    )
    cost = calculate_cost_openai(response, "deepseek-v4-pro")
    assert cost == pytest.approx(1.0893125, abs=0.001)


# ============================================================================
# 18. No cache detail → conservative cache-miss
# ============================================================================
def test_no_cache_detail_falls_back_to_cache_miss():
    """When cache tokens are missing, all prompt tokens are billed as cache-miss."""
    from llms.cost_calculator import calculate_cost_openai

    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=500_000, total_tokens=1_500_000),
    )
    cost = calculate_cost_openai(response, "deepseek-v4-flash")
    assert cost == pytest.approx(0.14 + 0.14, abs=0.01)


def test_no_cache_hit_price_falls_back():
    """When cache_hit_price_per_1m_usd is None, fallback to standard prompt rate."""
    from llms.cost_calculator import calculate_cost_anthropic

    response = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=500_000),
    )
    cost = calculate_cost_anthropic(response, "claude-3.5-sonnet")
    assert cost == pytest.approx(10.50, abs=0.01)


# ============================================================================
# 19. AsyncLLMProvider routes by provider, not by name prefix
# ============================================================================
def test_async_provider_routes_by_registry_provider():
    """AsyncLLMProvider uses get_model_info().provider for routing."""
    from llms.async_client import AsyncLLMProvider

    p = AsyncLLMProvider("deepseek-v4-flash")
    assert p._info.provider == "deepseek"

    p = AsyncLLMProvider("gpt-4o-mini")
    assert p._info.provider == "openai"

    p = AsyncLLMProvider("claude-3.5-sonnet")
    assert p._info.provider == "anthropic"


# ============================================================================
# 20. resolved_model_id() uses registry
# ============================================================================
def test_resolved_model_id_uses_registry():
    """resolved_model_id() returns api_model_id from registry."""
    from llms.async_client import AsyncLLMProvider

    assert AsyncLLMProvider("claude-3.5-sonnet").resolved_model_id() == "claude-3-5-sonnet-20241022"
    assert AsyncLLMProvider("gpt-4o-mini").resolved_model_id() == "gpt-4o-mini"
    assert AsyncLLMProvider("deepseek-v4-flash").resolved_model_id() == "deepseek-v4-flash"


# ============================================================================
# 21. init_llm works without MODELS
# ============================================================================
def test_init_llm_works_without_models_dict(monkeypatch):
    """init_llm works after MODELS removal — validates via registry."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")

    for model_name in MODEL_REGISTRY:
        provider = init_llm(model_name)
        assert provider.current_model == model_name
        assert provider.current_llm is not None
        assert provider.model_info is get_model_info(model_name)


# ============================================================================
# 22. _SYNC_MODEL_FUNCTIONS contains no metadata beyond callable
# ============================================================================
def test_sync_model_functions_only_callables():
    """_SYNC_MODEL_FUNCTIONS values are all callables (no metadata dicts)."""
    for name, value in _SYNC_MODEL_FUNCTIONS.items():
        assert callable(value), (
            f"_SYNC_MODEL_FUNCTIONS['{name}'] must be a callable, got {type(value)}"
        )


def test_sync_model_functions_are_functions():
    """_SYNC_MODEL_FUNCTIONS values are actual functions, not dicts."""
    import types
    for name, value in _SYNC_MODEL_FUNCTIONS.items():
        assert isinstance(value, types.FunctionType), (
            f"_SYNC_MODEL_FUNCTIONS['{name}'] must be a function, got {type(value)}"
        )


# ============================================================================
# 23. Cost calculation always returns USD float
# ============================================================================
def test_cost_calculation_returns_float():
    """All cost calculations return a float (not int, not str, not None)."""
    from llms.cost_calculator import calculate_cost_openai, calculate_cost_anthropic

    oai_resp = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=200),
    )
    ant_resp = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )

    for model_name in MODEL_REGISTRY:
        info = get_model_info(model_name)
        if info.api_style == "openai":
            cost = calculate_cost_openai(oai_resp, model_name)
        else:
            cost = calculate_cost_anthropic(ant_resp, model_name)
        assert isinstance(cost, float), f"{model_name}: cost must be float, got {type(cost)}"
        assert cost >= 0, f"{model_name}: cost must be >= 0"


# ============================================================================
# 24. Anthropic regression — cost is still correct
# ============================================================================
def test_anthropic_regression_cost():
    """After migration, Anthropic cost calculation is unchanged."""
    from llms.cost_calculator import calculate_cost_anthropic

    response = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=500_000),
    )
    cost = calculate_cost_anthropic(response, "claude-3.5-haiku")
    assert cost == pytest.approx(0.80 + 2.0, abs=0.01)


# ============================================================================
# 25. DeepSeek async provider uses correct provider routing
# ============================================================================
@pytest.mark.asyncio
async def test_async_llm_provider_routes_deepseek_to_deepseek_client(monkeypatch):
    """AsyncLLMProvider.__call__ routes DeepSeek to _call_deepseek_async."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-route")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    create_calls = []

    class FakeCompletions:
        async def create(self, **kwargs):
            create_calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="deepseek"))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            )

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kw):
            pass
        chat = FakeChat()

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    _reset_async_clients(monkeypatch)

    import llms.async_client as ac
    provider = ac.AsyncLLMProvider("deepseek-v4-flash")
    text, cost = await provider([{"role": "user", "content": "Hi"}], 0.3)

    assert text == "deepseek"
    assert create_calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in create_calls[0]


# ============================================================================
# 26. OpenAI cost from registry (sync path)
# ============================================================================
def test_openai_sync_cost_from_registry(monkeypatch):
    """Sync openai.py calculate_cost uses registry (via cost_calculator)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    from llms.openai import calculate_cost

    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=500_000),
    )
    cost = calculate_cost(response, "gpt-4o-mini")
    assert cost == pytest.approx(0.45, abs=0.001)


# ============================================================================
# 27. Claude cost from registry (sync path)
# ============================================================================
def test_claude_sync_cost_from_registry(monkeypatch):
    """Sync claude.py calculate_cost uses registry (via cost_calculator)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    from llms.claude import calculate_cost

    response = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=500_000),
    )
    cost = calculate_cost(response, "claude-3.5-sonnet")
    assert cost == pytest.approx(10.50, abs=0.01)


# ============================================================================
# 28. DeepSeek v4 pro cost
# ============================================================================
def test_deepseek_v4_pro_cost_precise():
    """deepseek-v4-pro cost is calculated correctly."""
    from llms.cost_calculator import calculate_cost_openai

    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000),
    )
    cost = calculate_cost_openai(response, "deepseek-v4-pro")
    assert cost == pytest.approx(1.305, abs=0.01)


# ============================================================================
# 29. OpenAI two-round tool call → final answer (continuous tool use)
# ============================================================================
@pytest.mark.asyncio
async def test_openai_two_round_tool_call_final_answer(monkeypatch):
    """Two consecutive OpenAI tool-call turns: round 1 returns tool_call,
    tool executes, round 2 returns final answer.  This is the real agent loop:
    the model calls a tool, receives its result, then synthesises the answer."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-2round")

    call_count = [0]

    class FakeCompletions:
        async def create(self, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Round 1: model requests a tool call
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="Let me check the price data.",
                        tool_calls=[SimpleNamespace(
                            id="call_oai_1",
                            function=SimpleNamespace(
                                name="get_prices",
                                arguments='{"ticker": "AAPL", "period": "1mo"}',
                            ),
                        )],
                    ))],
                    usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                )
            else:
                # Round 2: model produces final answer (no more tool calls)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="The price of AAPL is $150 over the last month.",
                        tool_calls=None,
                    ))],
                    usage=SimpleNamespace(prompt_tokens=200, completion_tokens=30, total_tokens=230),
                )

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            pass
        chat = FakeChat()

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    _reset_async_clients(monkeypatch)

    from llms.async_client import AsyncLLMProvider

    provider = AsyncLLMProvider("gpt-4o-mini")

    # -- Round 1: tool call --
    tools = [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}]
    messages = [{"role": "user", "content": "What's the AAPL price over the last month?"}]

    resp1 = await provider.call_with_tools(messages, tools, temperature=0.3)
    assert resp1.has_tool_calls
    assert resp1.tool_calls[0].name == "get_prices"
    assert resp1.tool_calls[0].arguments == {"ticker": "AAPL", "period": "1mo"}
    assert resp1.tool_calls[0].parse_error is None

    # Append assistant + tool result to transcript
    messages.append(resp1.raw)
    messages.append({
        "role": "tool",
        "tool_call_id": "call_oai_1",
        "content": '{"status": "ok", "price": 150, "currency": "USD"}',
    })

    # -- Round 2: final answer --
    resp2 = await provider.call_with_tools(messages, [], temperature=0.3)
    assert not resp2.has_tool_calls
    assert "AAPL" in resp2.text
    assert "$150" in resp2.text
    assert call_count[0] == 2


# ============================================================================
# 30. Recovery: illegal args → model corrects → tool executes → final answer
# ============================================================================
@pytest.mark.asyncio
async def test_illegal_args_model_corrects_tool_executes(monkeypatch):
    """Full recovery test: (1) model produces invalid JSON args → parse_error,
    (2) error is fed back as tool_result, model corrects with valid JSON,
    tool executes successfully, (3) model produces final answer.

    This is the real agent resilience path — the model is NOT asked to give
    up after a parse error; it is given the chance to fix its arguments."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-recovery")

    call_count = [0]
    tool_executed = [False]

    class FakeCompletions:
        async def create(self, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Round 1: model produces invalid JSON arguments
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="",
                        tool_calls=[SimpleNamespace(
                            id="bad_call_1",
                            function=SimpleNamespace(
                                name="get_prices",
                                arguments='invalid {{{ json !!!',
                            ),
                        )],
                    ))],
                    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                )
            elif call_count[0] == 2:
                # Round 2: model corrects — produces valid JSON args
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="Let me fix the arguments.",
                        tool_calls=[SimpleNamespace(
                            id="good_call_1",
                            function=SimpleNamespace(
                                name="get_prices",
                                arguments='{"ticker": "AAPL", "period": "1mo"}',
                            ),
                        )],
                    ))],
                    usage=SimpleNamespace(prompt_tokens=20, completion_tokens=20, total_tokens=40),
                )
            else:
                # Round 3: model produces final answer after tool success
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="AAPL is trading at $150. The recovery path worked.",
                        tool_calls=None,
                    ))],
                    usage=SimpleNamespace(prompt_tokens=30, completion_tokens=20, total_tokens=50),
                )

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            pass
        chat = FakeChat()

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    _reset_async_clients(monkeypatch)

    from llms.async_client import AsyncLLMProvider

    provider = AsyncLLMProvider("gpt-4o-mini")
    tools = [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}]
    messages = [{"role": "user", "content": "Get AAPL price"}]

    # -- Round 1: model returns bad args --
    resp1 = await provider.call_with_tools(messages, tools, temperature=0.3)
    assert resp1.has_tool_calls
    tc1 = resp1.tool_calls[0]
    assert tc1.parse_error is not None
    assert "invalid" in tc1.parse_error
    assert tc1.name == "get_prices"

    # Agent: report error as tool_result (do NOT execute)
    messages.append(resp1.raw)
    messages.append({
        "role": "tool",
        "tool_call_id": tc1.id,
        "content": json.dumps({"status": "error", "error": tc1.parse_error, "tool": tc1.name}),
    })

    # -- Round 2: model corrects with valid args --
    resp2 = await provider.call_with_tools(messages, tools, temperature=0.3)
    assert resp2.has_tool_calls
    tc2 = resp2.tool_calls[0]
    assert tc2.parse_error is None, "Second round must produce valid JSON args"
    assert tc2.name == "get_prices"
    assert tc2.arguments == {"ticker": "AAPL", "period": "1mo"}

    # Agent: execute tool successfully
    messages.append(resp2.raw)
    messages.append({
        "role": "tool",
        "tool_call_id": tc2.id,
        "content": json.dumps({"status": "ok", "price": 150, "currency": "USD"}),
    })
    tool_executed[0] = True

    # -- Round 3: model produces final answer --
    resp3 = await provider.call_with_tools(messages, [], temperature=0.3)
    assert not resp3.has_tool_calls
    assert "AAPL" in resp3.text
    assert "$150" in resp3.text
    assert "recovery" in resp3.text.lower()
    assert call_count[0] == 3
    assert tool_executed[0] is True


# ============================================================================
# 31. DeepSeek 3-round agent test — two legal tools, then final answer
#     (driven through GeneralistAgent.run())
# ============================================================================
@pytest.mark.asyncio
async def test_deepseek_agent_three_round_tool_call(monkeypatch):
    """Three-round DeepSeek agent test via GeneralistAgent.run():
    LLM response 1 → tool_call (get_prices),
    LLM response 2 → tool_call (get_technicals),
    LLM response 3 → final answer.

    The entire loop is driven through GeneralistAgent.run() with mocked
    get_async_llm and ToolRegistry.execute — zero real API calls."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-agent-3r")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    # -- Set up the sync provider so get_async_llm can read current_model ------
    from llms.config import init_llm
    init_llm("deepseek-v4-flash")

    # -- Build the sequence of mock LLM responses --------------------------------
    from llms.async_client import LLMToolResponse, ToolCall

    call_idx = [0]

    # Track what the model received so we can verify message flow
    llm_turns = []

    class MockProvider:
        model_name = "deepseek-v4-flash"

        async def call_with_tools(self, messages, tools, temperature=0.4, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            # Snapshot the transcript length for verification
            llm_turns.append({
                "index": idx,
                "msg_count": len(messages),
                "has_tools": bool(tools),
            })

            if idx == 0:
                # Round 1: model requests get_prices
                return LLMToolResponse(
                    text="Let me check the price.",
                    tool_calls=[
                        ToolCall(id="ds_call_1", name="get_prices",
                                 arguments={"ticker": "AAPL"}),
                    ],
                    cost=0.01,
                    raw={
                        "role": "assistant",
                        "content": "Let me check the price.",
                        "tool_calls": [
                            SimpleNamespace(
                                id="ds_call_1",
                                function=SimpleNamespace(
                                    name="get_prices",
                                    arguments='{"ticker": "AAPL"}',
                                ),
                            )
                        ],
                    },
                )
            elif idx == 1:
                # Round 2: model requests get_technicals
                return LLMToolResponse(
                    text="Now let me check the technicals.",
                    tool_calls=[
                        ToolCall(id="ds_call_2", name="get_technicals",
                                 arguments={"ticker": "AAPL"}),
                    ],
                    cost=0.01,
                    raw={
                        "role": "assistant",
                        "content": "Now let me check the technicals.",
                        "tool_calls": [
                            SimpleNamespace(
                                id="ds_call_2",
                                function=SimpleNamespace(
                                    name="get_technicals",
                                    arguments='{"ticker": "AAPL"}',
                                ),
                            )
                        ],
                    },
                )
            else:
                # Round 3: final answer
                return LLMToolResponse(
                    text="AAPL is trading at $150 with an RSI of 55 and neutral momentum.",
                    tool_calls=[],
                    cost=0.01,
                    raw={
                        "role": "assistant",
                        "content": "AAPL is trading at $150 with an RSI of 55 and neutral momentum.",
                        "tool_calls": None,
                    },
                )

    # -- Mock get_async_llm to return our MockProvider ---------------------------
    import llms.async_client as ac
    _mock_provider = MockProvider()
    monkeypatch.setattr(ac, "get_async_llm", lambda: _mock_provider)
    # Also patch in the agent's namespace (agent imports get_async_llm directly)
    from agents import generalist_agent as ga_mod
    monkeypatch.setattr(ga_mod, "get_async_llm", lambda: _mock_provider)

    # -- Mock ToolRegistry.execute to return canned tool results -----------------
    from agents.tools.base import ToolRegistry
    execute_log = []

    async def _mock_execute(self, name, params):
        execute_log.append({"name": name, "params": params})
        if name == "get_prices":
            return json.dumps({"status": "ok", "price": 150, "currency": "USD"})
        elif name == "get_technicals":
            return json.dumps({"status": "ok", "rsi": 55, "macd": "neutral"})
        return json.dumps({"status": "ok"})

    monkeypatch.setattr(ToolRegistry, "execute", _mock_execute)

    # -- Mock AgentContext.ensure_base_logger to avoid filesystem ----------------
    from agents.tools.analysis_tools import AgentContext
    monkeypatch.setattr(AgentContext, "ensure_base_logger", lambda self: None)

    # -- Mock GeneralistAgent._save_session to avoid SessionManager --------------
    from agents.generalist_agent import GeneralistAgent
    monkeypatch.setattr(GeneralistAgent, "_save_session", lambda self, text: None)

    # -- Mock tool builders to avoid real tool registration ----------------------
    monkeypatch.setattr(
        "agents.tools.analysis_tools.build_analysis_tools", lambda ctx: []
    )
    monkeypatch.setattr("agents.tools.data_tools.build_data_tools", lambda: [])
    monkeypatch.setattr(
        "agents.tools.capital_markets_tools.build_capital_markets_tools", lambda: []
    )
    monkeypatch.setattr(
        "agents.tools.prediction_market_tools.build_prediction_market_tools", lambda: []
    )

    # -- Run the agent -----------------------------------------------------------
    agent = GeneralistAgent(
        email="test@test.com",
        timestamp="20260806",
        user_prompt="What's the AAPL price and technicals?",
        session_id="test-session-3r",
    )
    result = await agent.run()

    # -- Assertions --------------------------------------------------------------
    assert result["status"] == "completed"
    assert "$150" in result["answer"]
    assert "RSI" in result["answer"] or "55" in result["answer"]
    assert call_idx[0] == 3, "Three LLM turns must have occurred"

    # Both tools were executed
    assert len(execute_log) == 2
    assert execute_log[0]["name"] == "get_prices"
    assert execute_log[0]["params"] == {"ticker": "AAPL"}
    assert execute_log[1]["name"] == "get_technicals"
    assert execute_log[1]["params"] == {"ticker": "AAPL"}

    # Tool arguments are dicts
    for entry in execute_log:
        assert isinstance(entry["params"], dict), (
            f"Tool arguments must be dict, got {type(entry['params'])}"
        )

    # LLM turns had increasing message counts (transcript grows)
    assert llm_turns[0]["msg_count"] < llm_turns[1]["msg_count"] < llm_turns[2]["msg_count"]


# ============================================================================
# 32. Agent-level illegal-args recovery test with registry.execute() mock
# ============================================================================
@pytest.mark.asyncio
async def test_agent_illegal_args_recovery_with_execute_tracking(monkeypatch):
    """Agent-level recovery test: model produces invalid JSON args (round 1),
    agent sends error as tool_result, model corrects with valid args (round 2),
    agent executes tool (round 2), model produces final answer (round 3).

    Key assertions:
    - registry.execute() called 0 times during the illegal-args phase
    - registry.execute() called 1 time after correction
    - Two tool_call_ids correctly propagated
    - Final answer successfully generated
    - Tool arguments after parsing are dict
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-agent-recovery")

    from llms.config import init_llm
    init_llm("gpt-4o-mini")

    from llms.async_client import LLMToolResponse, ToolCall

    call_idx = [0]
    # Capture messages passed to each LLM turn for tool_call_id verification
    captured_tool_ids = []

    class MockProvider:
        model_name = "gpt-4o-mini"

        async def call_with_tools(self, messages, tools, temperature=0.4, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1

            if idx == 0:
                # Round 1: model returns INVALID JSON args
                return LLMToolResponse(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="bad_id_1",
                            name="get_prices",
                            arguments={},
                            parse_error="Tool 'get_prices' received invalid JSON arguments. "
                                        "Parse error: bad json. Raw arguments: 'not valid json'",
                        ),
                    ],
                    cost=0.005,
                    raw={
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            SimpleNamespace(
                                id="bad_id_1",
                                function=SimpleNamespace(
                                    name="get_prices",
                                    arguments="not valid json",
                                ),
                            )
                        ],
                    },
                )
            elif idx == 1:
                # Round 2: model corrects with VALID JSON args
                # Verify the error tool_result was correctly attached
                tool_msgs = [m for m in messages if m.get("role") == "tool"]
                if tool_msgs:
                    captured_tool_ids.append(tool_msgs[-1].get("tool_call_id"))
                return LLMToolResponse(
                    text="Let me fix the arguments.",
                    tool_calls=[
                        ToolCall(id="good_id_1", name="get_prices",
                                 arguments={"ticker": "AAPL"}),
                    ],
                    cost=0.01,
                    raw={
                        "role": "assistant",
                        "content": "Let me fix the arguments.",
                        "tool_calls": [
                            SimpleNamespace(
                                id="good_id_1",
                                function=SimpleNamespace(
                                    name="get_prices",
                                    arguments='{"ticker": "AAPL"}',
                                ),
                            )
                        ],
                    },
                )
            else:
                # Round 3: final answer
                tool_msgs = [m for m in messages if m.get("role") == "tool"]
                if tool_msgs:
                    captured_tool_ids.append(tool_msgs[-1].get("tool_call_id"))
                return LLMToolResponse(
                    text="AAPL is trading at $150. The recovery path worked.",
                    tool_calls=[],
                    cost=0.01,
                    raw={
                        "role": "assistant",
                        "content": "AAPL is trading at $150. The recovery path worked.",
                        "tool_calls": None,
                    },
                )

    import llms.async_client as ac
    _mock_provider = MockProvider()
    monkeypatch.setattr(ac, "get_async_llm", lambda: _mock_provider)
    # Also patch in the agent's namespace (agent imports get_async_llm directly)
    from agents import generalist_agent as ga_mod2
    monkeypatch.setattr(ga_mod2, "get_async_llm", lambda: _mock_provider)

    # -- Mock ToolRegistry.execute to track calls --------------------------------
    from agents.tools.base import ToolRegistry
    execute_log = []

    async def _mock_execute(self, name, params):
        execute_log.append({"name": name, "params": params})
        return json.dumps({"status": "ok", "price": 150})

    monkeypatch.setattr(ToolRegistry, "execute", _mock_execute)

    # -- Mock AgentContext / _save_session / tool builders -----------------------
    from agents.tools.analysis_tools import AgentContext
    monkeypatch.setattr(AgentContext, "ensure_base_logger", lambda self: None)

    from agents.generalist_agent import GeneralistAgent
    monkeypatch.setattr(GeneralistAgent, "_save_session", lambda self, text: None)

    monkeypatch.setattr(
        "agents.tools.analysis_tools.build_analysis_tools", lambda ctx: []
    )
    monkeypatch.setattr("agents.tools.data_tools.build_data_tools", lambda: [])
    monkeypatch.setattr(
        "agents.tools.capital_markets_tools.build_capital_markets_tools", lambda: []
    )
    monkeypatch.setattr(
        "agents.tools.prediction_market_tools.build_prediction_market_tools", lambda: []
    )

    # -- Run the agent -----------------------------------------------------------
    agent = GeneralistAgent(
        email="test@test.com",
        timestamp="20260806",
        user_prompt="Get AAPL price",
        session_id="test-recovery",
    )
    result = await agent.run()

    # -- Assertions --------------------------------------------------------------

    # 1. Final answer successfully generated
    assert result["status"] == "completed"
    assert "AAPL" in result["answer"]

    # 2. Three LLM turns occurred
    assert call_idx[0] == 3

    # 3. registry.execute() called 0 times during illegal-args phase (round 1)
    #    and 1 time after correction (round 2)
    assert len(execute_log) == 1, (
        f"Expected 1 execute call (after correction), got {len(execute_log)}. "
        f"Execute log: {execute_log}"
    )
    assert execute_log[0]["name"] == "get_prices"

    # 4. Tool arguments after parsing are dict
    assert isinstance(execute_log[0]["params"], dict)
    assert execute_log[0]["params"] == {"ticker": "AAPL"}

    # 5. Two tool_call_ids correctly propagated
    assert "bad_id_1" in captured_tool_ids, (
        f"bad_id_1 not found in captured_tool_ids: {captured_tool_ids}"
    )
    assert "good_id_1" in captured_tool_ids, (
        f"good_id_1 not found in captured_tool_ids: {captured_tool_ids}"
    )


# ============================================================================
# 33. DeepSeek async client reads Key/Base URL from registry (not hardcoded)
# ============================================================================
def test_deepseek_async_reads_config_from_registry(monkeypatch):
    """DeepSeek async client reads api_key_env and base_url_env from the registry,
    not hardcoded env var names."""
    from llms.model_registry import MODEL_REGISTRY, ModelInfo

    # Create a registry entry with CUSTOM env var names
    custom_info = ModelInfo(
        name="deepseek-v4-flash",
        provider="deepseek",
        api_style="openai",
        api_model_id="deepseek-v4-flash",
        api_key_env="CUSTOM_DS_KEY",
        base_url_env="CUSTOM_DS_URL",
        default_base_url="https://api.deepseek.com",
        supports_tools=True,
        supports_json=True,
        supports_thinking=True,
        prompt_price_per_1m_usd=0.14,
        completion_price_per_1m_usd=0.28,
        cache_hit_price_per_1m_usd=0.0028,
    )

    # Set the custom env vars
    monkeypatch.setenv("CUSTOM_DS_KEY", "sk-custom-from-registry")
    monkeypatch.setenv("CUSTOM_DS_URL", "https://custom-from-registry.example.com")

    # Patch the registry
    monkeypatch.setitem(MODEL_REGISTRY, "deepseek-v4-flash", custom_info)

    captured_init = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured_init.update(kwargs)

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    _reset_async_clients(monkeypatch)

    import llms.async_client as ac
    ac._get_async_deepseek()

    assert captured_init["api_key"] == "sk-custom-from-registry", (
        "DeepSeek async client must read api_key_env from registry"
    )
    assert captured_init["base_url"] == "https://custom-from-registry.example.com", (
        "DeepSeek async client must read base_url_env from registry"
    )


# ============================================================================
# 34. Claude sync API model ID sourced from registry
# ============================================================================
def test_claude_sync_api_model_id_from_registry(monkeypatch):
    """Claude sync functions use api_model_id from the registry, not hardcoded."""
    from llms.model_registry import MODEL_REGISTRY, ModelInfo

    # Modify the registry to use a different api_model_id
    custom_sonnet = ModelInfo(
        name="claude-3.5-sonnet",
        provider="anthropic",
        api_style="anthropic",
        api_model_id="custom-sonnet-id-20260101",
        api_key_env="ANTHROPIC_API_KEY",
        supports_tools=True,
        supports_json=False,
        supports_thinking=False,
        prompt_price_per_1m_usd=3.0,
        completion_price_per_1m_usd=15.0,
    )
    monkeypatch.setitem(MODEL_REGISTRY, "claude-3.5-sonnet", custom_sonnet)

    # Re-read the module-level variable (it was set at import time, so we need
    # to patch it directly in the module namespace)
    import llms.claude as claude_module
    monkeypatch.setattr(claude_module, "_SONNET_MODEL_ID", "custom-sonnet-id-20260101")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-registry-test")

    captured_kwargs = {}

    class FakeMessages:
        @staticmethod
        def create(**kwargs):
            captured_kwargs.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Hello from custom ID")],
                usage=SimpleNamespace(input_tokens=10, output_tokens=10),
            )

    class FakeAnthropic:
        def __init__(self, **kw):
            pass
        messages = FakeMessages()

    monkeypatch.setattr(anthropic_module, "Anthropic", FakeAnthropic)

    # Also patch in claude module's namespace (it imports Anthropic directly)
    import llms.claude as claude_mod
    monkeypatch.setattr(claude_mod, "Anthropic", FakeAnthropic)

    from llms.claude import claude_3_5_sonnet
    claude_3_5_sonnet([{"role": "user", "content": "Hi"}])

    assert captured_kwargs["model"] == "custom-sonnet-id-20260101", (
        f"Expected custom-sonnet-id-20260101, got {captured_kwargs.get('model')}. "
        "Claude sync must use api_model_id from registry."
    )


# ============================================================================
# 35. _get_async_deepseek(model_name) reads the current model's ModelInfo
# ============================================================================
def test_get_async_deepseek_reads_model_info(monkeypatch):
    """_get_async_deepseek(model_name) reads the specified model's ModelInfo,
    not hardcoded 'deepseek-v4-flash'."""
    from llms.model_registry import MODEL_REGISTRY, ModelInfo

    # Create a registry entry for deepseek-v4-pro with CUSTOM env vars
    custom_pro = ModelInfo(
        name="deepseek-v4-pro",
        provider="deepseek",
        api_style="openai",
        api_model_id="deepseek-v4-pro",
        api_key_env="CUSTOM_PRO_KEY",
        base_url_env="CUSTOM_PRO_URL",
        default_base_url="https://api.deepseek.com",
        supports_tools=True,
        supports_json=True,
        supports_thinking=True,
        prompt_price_per_1m_usd=0.435,
        completion_price_per_1m_usd=0.87,
        cache_hit_price_per_1m_usd=0.003625,
    )

    monkeypatch.setitem(MODEL_REGISTRY, "deepseek-v4-pro", custom_pro)
    monkeypatch.setenv("CUSTOM_PRO_KEY", "sk-pro-from-registry")
    monkeypatch.setenv("CUSTOM_PRO_URL", "https://pro-endpoint.example.com")

    captured_init = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured_init.update(kwargs)

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    _reset_async_clients(monkeypatch)

    import llms.async_client as ac
    # Reset the model tracker as well
    monkeypatch.setattr(ac, "_async_deepseek_model", None)

    ac._get_async_deepseek("deepseek-v4-pro")

    assert captured_init["api_key"] == "sk-pro-from-registry", (
        "DeepSeek async client must read api_key_env from the specified model's registry"
    )
    assert captured_init["base_url"] == "https://pro-endpoint.example.com", (
        "DeepSeek async client must read base_url_env from the specified model's registry"
    )


def test_get_async_deepseek_rebuilds_on_model_change(monkeypatch):
    """When the model changes between calls, the DeepSeek client is rebuilt."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-rebuild")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    build_count = [0]

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            build_count[0] += 1

    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    _reset_async_clients(monkeypatch)

    import llms.async_client as ac
    monkeypatch.setattr(ac, "_async_deepseek_model", None)

    # First call — build for flash
    ac._get_async_deepseek("deepseek-v4-flash")
    assert build_count[0] == 1

    # Same model — no rebuild
    ac._get_async_deepseek("deepseek-v4-flash")
    assert build_count[0] == 1

    # Different model — rebuild
    ac._get_async_deepseek("deepseek-v4-pro")
    assert build_count[0] == 2


# ============================================================================
# 36. Async clients explicitly check API keys
# ============================================================================
def test_async_anthropic_checks_api_key(monkeypatch):
    """_get_async_anthropic raises ValueError when ANTHROPIC_API_KEY is missing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _reset_async_clients(monkeypatch)

    import llms.async_client as ac
    monkeypatch.setattr(ac, "_async_anthropic", None)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        ac._get_async_anthropic()


def test_async_openai_checks_api_key(monkeypatch):
    """_get_async_openai raises ValueError when OPENAI_API_KEY is missing."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _reset_async_clients(monkeypatch)

    import llms.async_client as ac
    monkeypatch.setattr(ac, "_async_openai", None)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        ac._get_async_openai()


def test_async_deepseek_checks_api_key(monkeypatch):
    """_get_async_deepseek raises ValueError when DEEPSEEK_API_KEY is missing."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    _reset_async_clients(monkeypatch)

    import llms.async_client as ac
    monkeypatch.setattr(ac, "_async_deepseek", None)
    monkeypatch.setattr(ac, "_async_deepseek_model", None)

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        ac._get_async_deepseek("deepseek-v4-flash")


# ============================================================================
# 37. Tool arguments that parse as list → parse_error
# ============================================================================
@pytest.mark.asyncio
async def test_tool_args_reject_list(monkeypatch):
    """Tool arguments that parse as a JSON list produce parse_error."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-list")

    canned = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(
                id="list_1",
                function=SimpleNamespace(
                    name="get_prices",
                    arguments='[1, 2, 3]',
                ),
            )],
        ))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    _, _ = _fake_async_openai(monkeypatch, canned_response=canned)

    from llms.async_client import _call_openai_tools

    resp = await _call_openai_tools(
        "gpt-4o-mini",
        [{"role": "user", "content": "Hi"}],
        [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}],
        0.3,
    )

    assert resp.has_tool_calls
    tc = resp.tool_calls[0]
    assert tc.parse_error is not None, "List arguments must produce parse_error"
    assert "non-dict" in tc.parse_error or "list" in tc.parse_error.lower()
    assert tc.arguments == {}


# ============================================================================
# 38. Tool arguments that parse as string → parse_error
# ============================================================================
@pytest.mark.asyncio
async def test_tool_args_reject_string(monkeypatch):
    """Tool arguments that parse as a JSON string produce parse_error."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-str")

    canned = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(
                id="str_1",
                function=SimpleNamespace(
                    name="get_prices",
                    arguments='"hello"',
                ),
            )],
        ))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    _, _ = _fake_async_openai(monkeypatch, canned_response=canned)

    from llms.async_client import _call_openai_tools

    resp = await _call_openai_tools(
        "gpt-4o-mini",
        [{"role": "user", "content": "Hi"}],
        [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}],
        0.3,
    )

    assert resp.has_tool_calls
    tc = resp.tool_calls[0]
    assert tc.parse_error is not None, "String arguments must produce parse_error"
    assert "non-dict" in tc.parse_error or "str" in tc.parse_error.lower()
    assert tc.arguments == {}


# ============================================================================
# 39. Tool arguments that parse as number → parse_error
# ============================================================================
@pytest.mark.asyncio
async def test_tool_args_reject_number(monkeypatch):
    """Tool arguments that parse as a JSON number produce parse_error."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-num")

    canned = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(
                id="num_1",
                function=SimpleNamespace(
                    name="get_prices",
                    arguments='42',
                ),
            )],
        ))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    _, _ = _fake_async_openai(monkeypatch, canned_response=canned)

    from llms.async_client import _call_openai_tools

    resp = await _call_openai_tools(
        "gpt-4o-mini",
        [{"role": "user", "content": "Hi"}],
        [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}],
        0.3,
    )

    assert resp.has_tool_calls
    tc = resp.tool_calls[0]
    assert tc.parse_error is not None, "Number arguments must produce parse_error"
    assert "non-dict" in tc.parse_error or "int" in tc.parse_error.lower()
    assert tc.arguments == {}


# ============================================================================
# 40. Tool arguments that parse as null → parse_error
# ============================================================================
@pytest.mark.asyncio
async def test_tool_args_reject_null(monkeypatch):
    """Tool arguments that parse as JSON null produce parse_error."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-null")

    canned = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(
                id="null_1",
                function=SimpleNamespace(
                    name="get_prices",
                    arguments='null',
                ),
            )],
        ))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    _, _ = _fake_async_openai(monkeypatch, canned_response=canned)

    from llms.async_client import _call_openai_tools

    resp = await _call_openai_tools(
        "gpt-4o-mini",
        [{"role": "user", "content": "Hi"}],
        [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}],
        0.3,
    )

    assert resp.has_tool_calls
    tc = resp.tool_calls[0]
    assert tc.parse_error is not None, "Null arguments must produce parse_error"
    assert "non-dict" in tc.parse_error or "nonetype" in tc.parse_error.lower()
    assert tc.arguments == {}


# ============================================================================
# 41. DeepSeek tool args also reject non-dict (same guard)
# ============================================================================
@pytest.mark.asyncio
async def test_deepseek_tool_args_reject_list(monkeypatch):
    """DeepSeek tool arguments that parse as a JSON list produce parse_error."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-list")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    canned = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(
                id="ds_list_1",
                function=SimpleNamespace(
                    name="get_prices",
                    arguments='["AAPL", "MSFT"]',
                ),
            )],
        ))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    _, _ = _fake_async_openai(monkeypatch, canned_response=canned)

    from llms.async_client import _call_deepseek_tools

    resp = await _call_deepseek_tools(
        "deepseek-v4-flash",
        [{"role": "user", "content": "Hi"}],
        [{"type": "function", "function": {"name": "get_prices", "parameters": {}}}],
        0.3,
    )

    assert resp.has_tool_calls
    tc = resp.tool_calls[0]
    assert tc.parse_error is not None, "List arguments must produce parse_error for DeepSeek"
    assert "non-dict" in tc.parse_error or "list" in tc.parse_error.lower()


# ============================================================================
# 42. parse_error NOT recorded in _tools_used by GeneralistAgent
# ============================================================================
@pytest.mark.asyncio
async def test_parse_error_not_recorded_in_tools_used(monkeypatch):
    """When a tool call has parse_error, GeneralistAgent does NOT add it to
    _tools_used (the tool was NOT executed successfully)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-no-record")

    from llms.config import init_llm
    init_llm("gpt-4o-mini")

    from llms.async_client import LLMToolResponse, ToolCall

    call_idx = [0]

    class MockProvider:
        model_name = "gpt-4o-mini"

        async def call_with_tools(self, messages, tools, temperature=0.4, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                # Round 1: model returns INVALID JSON args → parse_error
                return LLMToolResponse(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="bad_no_record",
                            name="get_prices",
                            arguments={},
                            parse_error="Tool 'get_prices' received invalid JSON arguments.",
                        ),
                    ],
                    cost=0.005,
                    raw={
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            SimpleNamespace(
                                id="bad_no_record",
                                function=SimpleNamespace(
                                    name="get_prices",
                                    arguments="bad json",
                                ),
                            )
                        ],
                    },
                )
            else:
                # Round 2: final answer
                return LLMToolResponse(
                    text="Here is the answer after the error.",
                    tool_calls=[],
                    cost=0.01,
                    raw={
                        "role": "assistant",
                        "content": "Here is the answer after the error.",
                        "tool_calls": None,
                    },
                )

    import llms.async_client as ac
    _mock_provider = MockProvider()
    monkeypatch.setattr(ac, "get_async_llm", lambda: _mock_provider)
    from agents import generalist_agent as ga_mod3
    monkeypatch.setattr(ga_mod3, "get_async_llm", lambda: _mock_provider)

    # Mock ToolRegistry.execute (should NOT be called)
    from agents.tools.base import ToolRegistry
    execute_log = []

    async def _mock_execute(self, name, params):
        execute_log.append({"name": name, "params": params})
        return json.dumps({"status": "ok"})

    monkeypatch.setattr(ToolRegistry, "execute", _mock_execute)

    from agents.tools.analysis_tools import AgentContext
    monkeypatch.setattr(AgentContext, "ensure_base_logger", lambda self: None)

    from agents.generalist_agent import GeneralistAgent
    monkeypatch.setattr(GeneralistAgent, "_save_session", lambda self, text: None)

    monkeypatch.setattr(
        "agents.tools.analysis_tools.build_analysis_tools", lambda ctx: []
    )
    monkeypatch.setattr("agents.tools.data_tools.build_data_tools", lambda: [])
    monkeypatch.setattr(
        "agents.tools.capital_markets_tools.build_capital_markets_tools", lambda: []
    )
    monkeypatch.setattr(
        "agents.tools.prediction_market_tools.build_prediction_market_tools", lambda: []
    )

    agent = GeneralistAgent(
        email="test@test.com",
        timestamp="20260806",
        user_prompt="Test parse_error not recorded",
        session_id="test-no-record",
    )
    result = await agent.run()

    # The tool was NOT executed (parse_error)
    assert len(execute_log) == 0, (
        f"Expected 0 execute calls, got {len(execute_log)}"
    )

    # _tools_used should NOT contain the failed tool name
    assert "get_prices" not in agent._tools_used, (
        f"parse_error tool should NOT be in _tools_used, got {agent._tools_used}"
    )

    # Final answer was generated
    assert result["status"] == "completed"