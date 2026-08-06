"""
Unified model registry — single source of truth for all LLM model metadata.

Design rules
------------
* **No imports from openai.py, claude.py, or config.py.**  This module is a pure
  data layer and must never cause a circular dependency.
* **Frozen dataclass.**  ``ModelInfo`` is immutable — all pricing, provider, and
  protocol metadata is set at registration time and never mutated at runtime.
* **provider ≠ api_style.**  ``provider`` identifies the vendor (openai, anthropic,
  deepseek, …); ``api_style`` tells the Agent which *message format* to use
  ("openai" or "anthropic").  DeepSeek uses ``provider="deepseek"`` with
  ``api_style="openai"`` because it speaks the OpenAI wire protocol.
* **api_model_id** is the concrete model string sent to the API.  For OpenAI this
  is usually the same as ``name``; for Anthropic it is the dated snapshot
  (e.g. ``"claude-3-5-sonnet-20241022"``).
* **Pricing is always USD per 1M tokens.**  Cost calculation in every call path
  multiplies token counts by these rates and produces a float in USD.
* **list_models / list_available_models preserve insertion order** (the order
  models appear in ``MODEL_REGISTRY``).  Callers that need sorted output should
  sort explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ModelInfo:
    """Immutable metadata for a single registered LLM model.

    Every field that influences runtime behaviour (API key, pricing, tool
    support) is captured here so that both the sync ``LLMProvider`` and the
    async ``AsyncLLMProvider`` read from the same source.
    """

    # -- Identity ---------------------------------------------------------------
    name: str
    """Logical name users select, e.g. ``"gpt-4o-mini"``."""

    provider: str
    """Vendor: ``"openai"`` | ``"anthropic"`` | ``"deepseek"`` | …"""

    api_style: str
    """Wire protocol: ``"openai"`` or ``"anthropic"``.

    Determines message format, tool-calling shape, and Agent transcript
    construction.  DeepSeek uses ``api_style="openai"``."""

    api_model_id: str
    """Concrete model string sent to the API, e.g. ``"claude-3-5-sonnet-20241022"``."""

    # -- Auth / endpoint --------------------------------------------------------
    api_key_env: str
    """Environment variable that holds the API key, e.g. ``"OPENAI_API_KEY"``."""

    base_url_env: Optional[str] = None
    """Env var for a custom base URL (OpenAI-compatible providers).  ``None``
    means use the SDK default."""

    default_base_url: Optional[str] = None
    """Fallback base URL when ``base_url_env`` is not set.  ``None`` for
    official OpenAI / Anthropic."""

    # -- Capabilities -----------------------------------------------------------
    supports_tools: bool = True
    """Native tool / function calling support."""

    supports_json: bool = False
    """``response_format={"type": "json_object"}`` support."""

    supports_thinking: bool = False
    """Whether the model can emit a reasoning / thinking block."""

    # -- Pricing (USD per 1M tokens) --------------------------------------------
    prompt_price_per_1m_usd: float = 0.0
    """Input / prompt price per 1M tokens, USD."""

    completion_price_per_1m_usd: float = 0.0
    """Output / completion price per 1M tokens, USD."""

    cache_hit_price_per_1m_usd: Optional[float] = None
    """Discounted input price when a cache hit occurs (DeepSeek).  ``None``
    means the provider does not expose cache-hit pricing."""


# ============================================================================
# Registry (single source of truth)
# Order is deliberate — list_models() preserves insertion order.
# ============================================================================

MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # -- OpenAI ----------------------------------------------------------------
    # gpt-4o-mini: Standard-tier pricing, source: platform.openai.com/docs/pricing
    "gpt-4o-mini": ModelInfo(
        name="gpt-4o-mini",
        provider="openai",
        api_style="openai",
        api_model_id="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        supports_tools=True,
        supports_json=True,
        supports_thinking=False,
        prompt_price_per_1m_usd=0.150,
        completion_price_per_1m_usd=0.600,
        cache_hit_price_per_1m_usd=0.075,
    ),
    "gpt-5.4-mini": ModelInfo(
        name="gpt-5.4-mini",
        provider="openai",
        api_style="openai",
        api_model_id="gpt-5.4-mini",
        api_key_env="OPENAI_API_KEY",
        supports_tools=True,
        supports_json=True,
        supports_thinking=False,
        prompt_price_per_1m_usd=0.75,
        completion_price_per_1m_usd=4.50,
        cache_hit_price_per_1m_usd=0.075,
    ),
    # -- Anthropic -------------------------------------------------------------
    "claude-3.5-sonnet": ModelInfo(
        name="claude-3.5-sonnet",
        provider="anthropic",
        api_style="anthropic",
        api_model_id="claude-3-5-sonnet-20241022",
        api_key_env="ANTHROPIC_API_KEY",
        supports_tools=True,
        supports_json=False,
        supports_thinking=False,
        prompt_price_per_1m_usd=3.0,
        completion_price_per_1m_usd=15.0,
    ),
    "claude-3.5-haiku": ModelInfo(
        name="claude-3.5-haiku",
        provider="anthropic",
        api_style="anthropic",
        api_model_id="claude-3-5-haiku-20241022",
        api_key_env="ANTHROPIC_API_KEY",
        supports_tools=True,
        supports_json=False,
        supports_thinking=False,
        prompt_price_per_1m_usd=0.80,
        completion_price_per_1m_usd=4.0,
    ),
    "claude-3-opus": ModelInfo(
        name="claude-3-opus",
        provider="anthropic",
        api_style="anthropic",
        api_model_id="claude-3-opus-20240229",
        api_key_env="ANTHROPIC_API_KEY",
        supports_tools=True,
        supports_json=False,
        supports_thinking=False,
        prompt_price_per_1m_usd=15.0,
        completion_price_per_1m_usd=75.0,
    ),
    # -- DeepSeek (OpenAI-compatible) -------------------------------------------
    "deepseek-v4-flash": ModelInfo(
        name="deepseek-v4-flash",
        provider="deepseek",
        api_style="openai",
        api_model_id="deepseek-v4-flash",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com",
        supports_tools=True,
        supports_json=True,
        supports_thinking=True,
        prompt_price_per_1m_usd=0.14,
        completion_price_per_1m_usd=0.28,
        cache_hit_price_per_1m_usd=0.0028,
    ),
    "deepseek-v4-pro": ModelInfo(
        name="deepseek-v4-pro",
        provider="deepseek",
        api_style="openai",
        api_model_id="deepseek-v4-pro",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com",
        supports_tools=True,
        supports_json=True,
        supports_thinking=True,
        prompt_price_per_1m_usd=0.435,
        completion_price_per_1m_usd=0.87,
        cache_hit_price_per_1m_usd=0.003625,
    ),
}


# ============================================================================
# Query helpers
# ============================================================================


def get_model_info(model_name: str) -> ModelInfo:
    """Return the ``ModelInfo`` for *model_name*.

    Raises:
        KeyError:  *model_name* is not registered.
    """
    if model_name not in MODEL_REGISTRY:
        raise KeyError(
            f"Unknown model '{model_name}'. "
            f"Registered models: {list(MODEL_REGISTRY.keys())}"
        )
    return MODEL_REGISTRY[model_name]


def list_models() -> List[str]:
    """Return all registered model names in insertion order."""
    return list(MODEL_REGISTRY.keys())


def list_available_models() -> List[str]:
    """Return models whose required API key is set in the environment.

    Preserves insertion order of ``MODEL_REGISTRY``.
    """
    available: List[str] = []
    for name, info in MODEL_REGISTRY.items():
        if os.getenv(info.api_key_env):
            available.append(name)
    return available