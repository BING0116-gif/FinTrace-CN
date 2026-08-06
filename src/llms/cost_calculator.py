"""
Deterministic cost calculation helpers — zero model metadata stored here.

All pricing is read from ``model_registry.get_model_info()`` at call time,
so the single source of truth (``MODEL_REGISTRY``) is the only place that
holds per-model prices.  This module contains **only** the arithmetic:
token counts × per-1M-USD rates → USD float.

Cache-aware billing (DeepSeek)
------------------------------
When ``prompt_cache_hit_tokens`` and ``prompt_cache_miss_tokens`` are present
on the response usage, the cache-hit portion is billed at the discounted
``cache_hit_price_per_1m_usd`` rate.  When cache detail is missing, **all**
input tokens are treated as cache-miss (conservative estimate).

No model metadata
-----------------
This module imports ``get_model_info`` (a pure lookup function) but does NOT
store, duplicate, or define any model names, prices, providers, API keys, or
API styles.  Those belong exclusively in ``model_registry.py``.
"""

from __future__ import annotations

from .model_registry import get_model_info


def calculate_cost_openai(response, model_name: str) -> float:
    """Calculate USD cost for an OpenAI or OpenAI-compatible API response.

    Works for OpenAI native and DeepSeek (both use the OpenAI SDK shape:
    ``response.usage.prompt_tokens`` / ``completion_tokens``).

    When ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens`` are
    available (DeepSeek), the cache-hit portion is billed at the discounted
    rate.  Without cache detail, all prompt tokens are billed as cache-miss.
    """
    info = get_model_info(model_name)
    usage = response.usage

    # -- Cache-aware input cost ------------------------------------------------
    cache_hit_tokens = getattr(usage, "prompt_cache_hit_tokens", None)
    cache_miss_tokens = getattr(usage, "prompt_cache_miss_tokens", None)

    if (
        cache_hit_tokens is not None
        and cache_miss_tokens is not None
        and info.cache_hit_price_per_1m_usd is not None
    ):
        # DeepSeek exposes per-category breakdown → use discounted rate for hits.
        input_cost = (
            cache_miss_tokens * info.prompt_price_per_1m_usd / 1_000_000
            + cache_hit_tokens * info.cache_hit_price_per_1m_usd / 1_000_000
        )
    else:
        # Conservative: treat all prompt tokens as cache-miss.
        input_cost = (
            usage.prompt_tokens * info.prompt_price_per_1m_usd / 1_000_000
        )

    output_cost = (
        usage.completion_tokens * info.completion_price_per_1m_usd / 1_000_000
    )
    return input_cost + output_cost


def calculate_cost_anthropic(response, model_name: str) -> float:
    """Calculate USD cost for an Anthropic API response.

    Uses ``response.usage.input_tokens`` / ``output_tokens`` (Anthropic shape).
    Anthropic does not expose cache-hit pricing, so all input is billed at the
    standard prompt rate.
    """
    info = get_model_info(model_name)
    usage = response.usage

    input_cost = usage.input_tokens * info.prompt_price_per_1m_usd / 1_000_000
    output_cost = usage.output_tokens * info.completion_price_per_1m_usd / 1_000_000
    return input_cost + output_cost