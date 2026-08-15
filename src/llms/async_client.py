"""
Async LLM client — additive, non-breaking counterpart to the synchronous
``get_llm()`` path in ``llms/config.py``.

Why this exists
---------------
The news pipeline analyses articles in independent batches, but the synchronous
client forces those batches to run one-after-another (see
``article_screener.analyze_all_articles``). Each batch is a self-contained LLM
call whose results are simply concatenated, so they are embarrassingly
parallelisable. This module exposes an ``async`` calling surface backed by
``AsyncAnthropic`` / ``AsyncOpenAI`` so callers can fan batches out with
``asyncio.gather`` under a concurrency cap.

Design guarantees
-----------------
* **Purely additive.** The sync ``LLMProvider`` in ``config.py`` is untouched;
  nothing here changes existing behaviour. Callers opt in via ``get_async_llm()``.
* **Same contract.** ``await get_async_llm()(messages, temperature)`` returns the
  same ``(text, cost)`` tuple as the sync path, using the same model selected by
  ``init_llm()`` and the same cost math.
* **Exponential backoff + jitter.** Replaces the old fixed 1-second retry, so a
  rate-limited call backs off (0.5s, 1s, 2s, 4s … + jitter) instead of hammering.
* **Circuit breaker.** After a run-wide threshold of consecutive hard failures the
  breaker opens and further calls fail fast for a cool-off window. This is the
  guard against the multi-hour "retry storm" tail runs, where recursive batch
  splitting multiplied calls against an already-saturated API.
* **Provider routing via registry.** All model metadata (provider, api_style,
  endpoint, pricing) is sourced from ``model_registry.get_model_info()``.
  ``_MODEL_TO_ANTHROPIC_ID`` and ``_OPENAI_MODELS`` have been removed.
* **DeepSeek has an independent async client.** ``AsyncOpenAI`` with
  ``DEEPSEEK_API_KEY`` and ``DEEPSEEK_BASE_URL`` (default ``https://api.deepseek.com``).
  Every DeepSeek request sends ``extra_body={"thinking": {"type": "disabled"}}``.
  OpenAI and Anthropic paths never receive DeepSeek-specific parameters.
* **Illegal tool arguments are NOT silently discarded.**  When JSON parsing of
  tool-call arguments fails, a ``ToolCall`` with ``parse_error`` is returned so
  the agent can report the error back to the model as a tool_result.
"""

from __future__ import annotations

import asyncio
import json as _json
import os
import random
import time
from typing import Dict, List, Optional, Tuple

from src.logger import get_logger

# Cost calculation is now sourced from the unified registry via cost_calculator.
from .cost_calculator import calculate_cost_openai, calculate_cost_anthropic
from .model_registry import get_model_info


# ---------------------------------------------------------------------------
# Circuit breaker (process-wide, best-effort)
# ---------------------------------------------------------------------------
class _CircuitBreaker:
    """
    Minimal consecutive-failure breaker.

    Trips open after ``fail_threshold`` consecutive failures and stays open for
    ``reset_after`` seconds, during which calls raise immediately instead of
    issuing a doomed network request. Any success closes it and resets the count.
    Deliberately simple and dependency-free.
    """

    def __init__(self, fail_threshold: int = 6, reset_after: float = 30.0):
        self.fail_threshold = fail_threshold
        self.reset_after = reset_after
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        # Cool-off elapsed → allow a trial call (half-open).
        if (time.monotonic() - self._opened_at) >= self.reset_after:
            self._opened_at = None
            self._consecutive_failures = 0
            return False
        return True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.fail_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()


# One breaker per process. The news fan-out shares it, so a genuine provider
# outage trips it once for everyone rather than each batch discovering it.
_breaker = _CircuitBreaker()


def reset_circuit_breaker() -> None:
    """Test/ops hook: force the breaker closed."""
    _breaker.record_success()


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and a call is short-circuited."""


# ---------------------------------------------------------------------------
# Async clients (lazily constructed, cached per process)
# ---------------------------------------------------------------------------
_async_anthropic = None
_async_openai = None
_async_deepseek = None
_async_deepseek_model: Optional[str] = None  # track which model the cached client was built for


def _get_async_anthropic():
    global _async_anthropic
    if _async_anthropic is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "API key 'ANTHROPIC_API_KEY' not found in environment. "
                "Set ANTHROPIC_API_KEY to use Anthropic models."
            )
        from anthropic import AsyncAnthropic
        _async_anthropic = AsyncAnthropic(api_key=api_key)
    return _async_anthropic


def _get_async_openai():
    global _async_openai
    if _async_openai is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "API key 'OPENAI_API_KEY' not found in environment. "
                "Set OPENAI_API_KEY to use OpenAI models."
            )
        from openai import AsyncOpenAI
        _async_openai = AsyncOpenAI()
    return _async_openai


def _get_async_deepseek(model_name: str = "deepseek-v4-flash"):
    """DeepSeek has an INDEPENDENT async client — never shares OpenAI's client,
    API key, or base URL.

    Reads the current model's ``ModelInfo`` from the registry so that API key
    env var, base URL env var, and default base URL are resolved per-model
    (single source of truth), NOT hardcoded.  If the model changes between
    calls (e.g. flash → pro), the client is rebuilt.
    """
    global _async_deepseek, _async_deepseek_model
    if _async_deepseek is None or _async_deepseek_model != model_name:
        from openai import AsyncOpenAI
        # Resolve API key and base URL from the registry, not hardcoded strings.
        info = get_model_info(model_name)
        api_key = os.getenv(info.api_key_env)
        if not api_key:
            raise ValueError(
                f"API key '{info.api_key_env}' not found in environment. "
                f"Set {info.api_key_env} to use {info.provider} models."
            )
        base_url = (os.getenv(info.base_url_env) if info.base_url_env else None)
        _async_deepseek = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or info.default_base_url,
        )
        _async_deepseek_model = model_name
    return _async_deepseek


# ---------------------------------------------------------------------------
# Rate-limit detection
# ---------------------------------------------------------------------------
def _is_rate_limit_like(exc: Exception) -> bool:
    """True for errors that warrant a backoff-and-retry (rate/timeout/5xx)."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if any(k in name for k in ("ratelimit", "timeout", "connection", "apistatus", "internalserver")):
        return True
    return any(
        k in msg
        for k in (
            "rate limit", "rate_limit", "ratelimit", "429", "500", "502", "503",
            "overloaded", "timeout", "temporarily unavailable", "connection",
        )
    )


# ---------------------------------------------------------------------------
# Per-provider async call helpers
# ---------------------------------------------------------------------------

async def _call_anthropic_async(
    model_name: str, messages: List[Dict], temperature: float
) -> Tuple[str, float]:
    """One plain-text Anthropic turn (no tool calling)."""
    info = get_model_info(model_name)
    model_id = info.api_model_id

    system_message = None
    user_messages = []
    for message in messages:
        if message["role"] == "system":
            system_message = message["content"]
        elif message["role"] in ("user", "assistant"):
            user_messages.append({"role": message["role"], "content": message["content"]})

    kwargs = {
        "model": model_id,
        "messages": user_messages,
        "temperature": temperature,
        "max_tokens": 4096,
    }
    if system_message:
        kwargs["system"] = system_message

    client = _get_async_anthropic()
    response = await client.messages.create(**kwargs)
    cost = calculate_cost_anthropic(response, model_name)
    return response.content[0].text, cost


async def _call_openai_async(
    model_name: str, messages: List[Dict], temperature: float
) -> Tuple[str, float]:
    """One plain-text OpenAI turn (no tool calling)."""
    info = get_model_info(model_name)
    client = _get_async_openai()
    response = await client.chat.completions.create(
        model=info.api_model_id, messages=messages, temperature=temperature
    )
    cost = calculate_cost_openai(response, model_name)
    return response.choices[0].message.content, cost


async def _call_deepseek_async(
    model_name: str, messages: List[Dict], temperature: float
) -> Tuple[str, float]:
    """One plain-text DeepSeek turn (no tool calling).

    DeepSeek uses its OWN async client (``_get_async_deepseek()``), NEVER the
    OpenAI client.  Every request explicitly disables the thinking/reasoning
    block via ``extra_body``.
    """
    info = get_model_info(model_name)
    client = _get_async_deepseek(model_name)
    response = await client.chat.completions.create(
        model=info.api_model_id,
        messages=messages,
        temperature=temperature,
        extra_body={"thinking": {"type": "disabled"}},
    )
    cost = calculate_cost_openai(response, model_name)
    return response.choices[0].message.content, cost


# ---------------------------------------------------------------------------
# Tool-calling (native function calling) — used by the generalizable ReAct agent
# ---------------------------------------------------------------------------
_PARSE_ERROR_SENTINEL = object()


class ToolCallArgsTypeError(Exception):
    """Raised when tool-call arguments parse as valid JSON but are not a dict
    (e.g. a list, string, number, or null).  Caught in the tool-call handlers
    to produce a ``ToolCall`` with ``parse_error`` set."""


class ToolCall:
    """One tool invocation requested by the model.

    If ``parse_error`` is set, the model produced tool-call arguments that
    were not valid JSON.  The caller (agent) must NOT execute the tool and
    MUST instead return a tool_result describing the error so the model can
    correct its arguments.
    """

    __slots__ = ("id", "name", "arguments", "parse_error")

    def __init__(self, id: str, name: str, arguments: dict, parse_error: Optional[str] = None):
        self.id = id
        self.name = name
        self.arguments = arguments if arguments is not None else {}
        self.parse_error = parse_error  # None → valid; str → parse failure

    def __repr__(self):
        if self.parse_error:
            return f"ToolCall(name={self.name!r}, parse_error={self.parse_error!r})"
        return f"ToolCall(name={self.name!r}, args={self.arguments!r})"


class LLMToolResponse:
    """
    Normalized response from a tool-calling turn, uniform across providers.

    * ``text``       — any assistant prose in the turn (may be empty when the
                       model only requested tools).
    * ``tool_calls`` — list[ToolCall] the model wants executed (empty → it's done).
    * ``cost``       — USD for the turn.
    * ``raw``        — the provider-native assistant message, so the caller can
                       append it verbatim to the running transcript (important for
                       Anthropic, whose tool_use/tool_result blocks must round-trip).
    """

    __slots__ = ("text", "tool_calls", "cost", "raw")

    def __init__(self, text, tool_calls, cost, raw):
        self.text = text or ""
        self.tool_calls = tool_calls or []
        self.cost = cost
        self.raw = raw

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


async def _call_anthropic_tools(model_name, messages, tools, temperature, tool_choice=None):
    """
    One Anthropic tool-calling turn. `messages` is the running transcript in
    Anthropic shape (list of {role, content}); `tools` is a list of
    anthropic tool schemas (name/description/input_schema). Returns LLMToolResponse.
    """
    info = get_model_info(model_name)
    model_id = info.api_model_id

    system_message = None
    conv = []
    for m in messages:
        if m["role"] == "system":
            system_message = m["content"]
        else:
            conv.append({"role": m["role"], "content": m["content"]})

    kwargs = {
        "model": model_id,
        "messages": conv,
        "temperature": temperature,
        "max_tokens": 4096,
    }
    if tools:  # omit an empty tools array — Anthropic rejects it
        kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    if system_message:
        kwargs["system"] = system_message

    client = _get_async_anthropic()
    resp = await client.messages.create(**kwargs)
    cost = calculate_cost_anthropic(resp, model_name)

    text_parts, calls = [], []
    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {})))
    # The raw assistant message (list of content blocks) must be appended verbatim.
    raw_assistant = {"role": "assistant", "content": resp.content}
    return LLMToolResponse("\n".join(text_parts).strip(), calls, cost, raw_assistant)


async def _call_openai_tools(model_name, messages, tools, temperature, tool_choice=None):
    """One OpenAI tool-calling turn. `tools` is a list of openai function schemas.

    When a tool-call's ``function.arguments`` is not valid JSON, a ``ToolCall``
    with ``parse_error`` is returned instead of silently substituting ``{}``.
    The agent must report the error back to the model as a tool_result.
    """
    info = get_model_info(model_name)
    client = _get_async_openai()

    kwargs = {
        "model": info.api_model_id,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:  # omit empty tools array
        kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    resp = await client.chat.completions.create(**kwargs)
    cost = calculate_cost_openai(resp, model_name)

    msg = resp.choices[0].message
    calls = []
    for tc in (msg.tool_calls or []):
        raw_args = tc.function.arguments or "{}"
        try:
            args = _json.loads(raw_args)
            if not isinstance(args, dict):
                # Tool arguments MUST be a dict — reject list, str, number, null.
                raise ToolCallArgsTypeError(
                    f"Tool arguments must be a JSON object (dict), got {type(args).__name__}: {args!r}"
                )
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        except ToolCallArgsTypeError as exc:
            calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments={},
                parse_error=(
                    f"Tool '{tc.function.name}' received non-dict arguments. "
                    f"{exc}. Raw arguments: {raw_args!r}"
                ),
            ))
        except Exception as exc:
            # Do NOT silently substitute {} — surface the error to the agent.
            calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments={},
                parse_error=(
                    f"Tool '{tc.function.name}' received invalid JSON arguments. "
                    f"Parse error: {exc}. Raw arguments: {raw_args!r}"
                ),
            ))
    # Raw assistant message for transcript round-tripping.
    raw_assistant = {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": msg.tool_calls,
    }
    return LLMToolResponse(msg.content or "", calls, cost, raw_assistant)


async def _call_deepseek_tools(model_name, messages, tools, temperature, tool_choice=None):
    """One DeepSeek tool-calling turn.

    DeepSeek uses its OWN async client (``_get_async_deepseek()``), NEVER the
    OpenAI client.  Every request explicitly disables the thinking/reasoning
    block via ``extra_body``.

    Same illegal-argument handling as ``_call_openai_tools``: parse failures
    become ``ToolCall.parse_error``, never silently ``{}``.
    """
    info = get_model_info(model_name)
    client = _get_async_deepseek(model_name)

    kwargs = {
        "model": info.api_model_id,
        "messages": messages,
        "temperature": temperature,
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    if tools:
        kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    resp = await client.chat.completions.create(**kwargs)
    cost = calculate_cost_openai(resp, model_name)

    msg = resp.choices[0].message
    calls = []
    for tc in (msg.tool_calls or []):
        raw_args = tc.function.arguments or "{}"
        try:
            args = _json.loads(raw_args)
            if not isinstance(args, dict):
                raise ToolCallArgsTypeError(
                    f"Tool arguments must be a JSON object (dict), got {type(args).__name__}: {args!r}"
                )
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        except ToolCallArgsTypeError as exc:
            calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments={},
                parse_error=(
                    f"Tool '{tc.function.name}' received non-dict arguments. "
                    f"{exc}. Raw arguments: {raw_args!r}"
                ),
            ))
        except Exception as exc:
            calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments={},
                parse_error=(
                    f"Tool '{tc.function.name}' received invalid JSON arguments. "
                    f"Parse error: {exc}. Raw arguments: {raw_args!r}"
                ),
            ))
    raw_assistant = {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": msg.tool_calls,
    }
    return LLMToolResponse(msg.content or "", calls, cost, raw_assistant)


# ---------------------------------------------------------------------------
# AsyncLLMProvider — routes by provider (from registry), not by name prefix
# ---------------------------------------------------------------------------

class AsyncLLMProvider:
    """
    Async mirror of ``LLMProvider``. Resolves the currently-selected model name
    (from the global sync provider, so ``init_llm("...")`` governs both paths)
    and routes to the correct async SDK based on ``get_model_info().provider``.

    **Provider routing** (from registry, not name prefix):
    * ``provider="openai"`` → ``_get_async_openai()`` / ``_call_openai_*``
    * ``provider="anthropic"`` → ``_get_async_anthropic()`` / ``_call_anthropic_*``
    * ``provider="deepseek"`` → ``_get_async_deepseek()`` / ``_call_deepseek_*``

    **is_openai** (if retained) only means ``api_style == "openai"`` — it is
    used for message-format / tool-schema selection, NOT for client routing.
    """

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._info = get_model_info(model_name)

    @property
    def is_openai(self) -> bool:
        """``True`` when the model speaks the OpenAI wire protocol.

        This is determined by ``api_style``, NOT by provider.  DeepSeek uses
        ``api_style="openai"`` so this returns ``True`` for DeepSeek models.
        Callers use this to choose message format and tool schemas, NOT to
        decide which client SDK to use.
        """
        return self._info.api_style == "openai"

    def resolved_model_id(self) -> str:
        return self._info.api_model_id

    async def __call__(
        self, messages: List[Dict], temperature: float = 0.3, *, max_retries: int = 4
    ) -> Tuple[str, float]:
        logger = get_logger()

        if _breaker.is_open():
            raise CircuitOpenError(
                "LLM circuit breaker is open (too many consecutive failures); "
                "skipping call to avoid a retry storm."
            )

        provider = self._info.provider
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                if provider == "openai":
                    text, cost = await _call_openai_async(self.model_name, messages, temperature)
                elif provider == "deepseek":
                    text, cost = await _call_deepseek_async(self.model_name, messages, temperature)
                elif provider == "anthropic":
                    text, cost = await _call_anthropic_async(self.model_name, messages, temperature)
                else:
                    raise ValueError(f"Unknown provider '{provider}' for model '{self.model_name}'")

                _breaker.record_success()
                if logger:
                    logger.llm_call(self.model_name, cost, 0)
                return text, cost

            except Exception as exc:  # noqa: BLE001 — we re-raise below
                last_error = exc
                retryable = _is_rate_limit_like(exc)
                if logger:
                    logger.error(
                        f"[async-llm] {type(exc).__name__} on attempt "
                        f"{attempt + 1}/{max_retries} (retryable={retryable}): {exc}"
                    )
                if not retryable or attempt == max_retries - 1:
                    _breaker.record_failure()
                    break
                base = 0.5 * (2 ** attempt)
                await asyncio.sleep(base + random.uniform(0, base))

        raise Exception(
            f"Async LLM call failed after {max_retries} attempts. "
            f"Last error: {type(last_error).__name__}: {last_error}"
        )

    async def call_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        temperature: float = 0.3,
        *,
        tool_choice=None,
        max_retries: int = 4,
    ) -> "LLMToolResponse":
        """
        One tool-calling turn (the primitive the ReAct loop drives).

        ``messages`` and ``tools`` must already be in the shape the selected
        provider expects (the caller builds them per ``api_style`` — see the agent).
        Same backoff + circuit-breaker behaviour as ``__call__``.
        """
        logger = get_logger()
        if _breaker.is_open():
            raise CircuitOpenError(
                "LLM circuit breaker is open (too many consecutive failures)."
            )

        provider = self._info.provider
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                if provider == "openai":
                    resp = await _call_openai_tools(
                        self.model_name, messages, tools, temperature, tool_choice
                    )
                elif provider == "deepseek":
                    resp = await _call_deepseek_tools(
                        self.model_name, messages, tools, temperature, tool_choice
                    )
                elif provider == "anthropic":
                    resp = await _call_anthropic_tools(
                        self.model_name, messages, tools, temperature, tool_choice
                    )
                else:
                    raise ValueError(f"Unknown provider '{provider}' for model '{self.model_name}'")

                _breaker.record_success()
                if logger:
                    logger.llm_call(self.model_name, resp.cost, 0)
                return resp
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                retryable = _is_rate_limit_like(exc)
                if logger:
                    logger.error(
                        f"[async-llm/tools] {type(exc).__name__} attempt "
                        f"{attempt + 1}/{max_retries} (retryable={retryable}): {exc}"
                    )
                if not retryable or attempt == max_retries - 1:
                    _breaker.record_failure()
                    break
                base = 0.5 * (2 ** attempt)
                await asyncio.sleep(base + random.uniform(0, base))

        raise Exception(
            f"Async tool call failed after {max_retries} attempts. "
            f"Last error: {type(last_error).__name__}: {last_error}"
        )


# ---------------------------------------------------------------------------
# Global async provider
# ---------------------------------------------------------------------------

_global_async_provider: Optional[AsyncLLMProvider] = None
_global_async_model: Optional[str] = None


def get_async_llm() -> AsyncLLMProvider:
    """
    Return an async callable for the *currently selected* model.

    The model is whatever ``init_llm()`` set on the sync global provider, so a
    single ``init_llm("claude-...")`` at startup governs both the sync and async
    paths. Rebuilds if the selected model changed.

    Validation is done against ``model_registry`` (NOT ``LLMProvider.MODELS``).
    """
    global _global_async_provider, _global_async_model
    from .config import _global_provider  # local import to avoid cycle at import time

    model_name = _global_provider.current_model if _global_provider else "gpt-4o-mini"
    if _global_async_provider is None or _global_async_model != model_name:
        # Validate against the unified registry (single source of truth).
        get_model_info(model_name)  # raises KeyError if unknown
        _global_async_provider = AsyncLLMProvider(model_name)
        _global_async_model = model_name
    return _global_async_provider