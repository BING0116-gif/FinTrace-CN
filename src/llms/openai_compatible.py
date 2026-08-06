"""
OpenAI-Compatible provider client.

Handles any LLM that speaks the OpenAI chat-completions wire protocol
(DeepSeek, Groq, Together, etc.).  Uses the OpenAI Python SDK for HTTP
transport but is completely independent of ``openai.py``.

Key design decisions
--------------------
* **No import from openai.py.**  This module is self-contained and does not
  share any logic with the native OpenAI client.
* **Thinking is explicitly disabled for DeepSeek.**  Every DeepSeek request
  sends ``extra_body={"thinking": {"type": "disabled"}}``.  Non-DeepSeek
  providers do NOT receive this parameter.
* **Cost is sourced from the registry.**  ``_calculate_cost`` reads per-token
  prices from ``model_registry.get_model_info()`` and accounts for
  ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens`` when available.
* **Retry / backoff matches existing conventions.**  3 attempts, 1 s sleep,
  same exception taxonomy as ``openai.py`` and ``claude.py``.
"""

from __future__ import annotations

import os
import time
from typing import Tuple, List, Dict

from openai import OpenAI
from openai import RateLimitError, APITimeoutError, APIConnectionError

from logger import get_logger
from .model_registry import get_model_info


# ---------------------------------------------------------------------------
# Cost calculation (registry-backed, cache-aware)
# ---------------------------------------------------------------------------

def _calculate_cost(response, model_name: str) -> float:
    """Calculate USD cost from the *response* usage and registry pricing.

    Pricing is always read from ``model_registry`` (single source of truth)
    so it stays in sync across sync and async paths.

    When ``prompt_cache_hit_tokens`` and ``prompt_cache_miss_tokens`` are
    available in the response (DeepSeek), the cache-hit portion is billed at
    the discounted rate.  When cache details are missing, ALL input tokens
    are treated as cache-miss (conservative).
    """
    info = get_model_info(model_name)
    usage = response.usage

    # -- Cache-aware input cost (DeepSeek exposes per-category breakdown) ---
    cache_hit_tokens = getattr(usage, "prompt_cache_hit_tokens", None)
    cache_miss_tokens = getattr(usage, "prompt_cache_miss_tokens", None)

    if (
        cache_hit_tokens is not None
        and cache_miss_tokens is not None
        and info.cache_hit_price_per_1m_usd is not None
    ):
        # DeepSeek provides cache detail — use the discounted rate for hits.
        input_cost = (
            cache_miss_tokens * info.prompt_price_per_1m_usd / 1_000_000
            + cache_hit_tokens * info.cache_hit_price_per_1m_usd / 1_000_000
        )
    else:
        # Conservative: treat all prompt tokens as cache-miss.
        input_cost = (
            usage.prompt_tokens * info.prompt_price_per_1m_usd / 1_000_000
        )

    output_cost = usage.completion_tokens * info.completion_price_per_1m_usd / 1_000_000
    return input_cost + output_cost


# ---------------------------------------------------------------------------
# Core call helper
# ---------------------------------------------------------------------------

def _call_openai_compatible(
    model_name: str,
    messages: List[Dict],
    temperature: float = 0.3,
) -> Tuple[str, float]:
    """Call an OpenAI-compatible chat model with retry logic.

    Parameters
    ----------
    model_name : str
        Logical name registered in ``MODEL_REGISTRY``, e.g.
        ``"deepseek-v4-flash"``.
    messages : List[Dict]
        OpenAI-format message list (``{"role": …, "content": …}``).
    temperature : float
        Sampling temperature.

    Returns
    -------
    Tuple[str, float]
        (response_text, cost_in_usd).
    """
    info = get_model_info(model_name)

    # -- Independent API key validation (client layer) ------------------------
    api_key = os.getenv(info.api_key_env)
    if not api_key:
        raise ValueError(
            f"API key '{info.api_key_env}' not found in environment. "
            f"Set {info.api_key_env} to use {info.provider} models."
        )

    # -- Resolve base URL: env var > default_base_url -------------------------
    base_url = (
        os.getenv(info.base_url_env)
        if info.base_url_env and os.getenv(info.base_url_env)
        else info.default_base_url
    )

    client_kwargs: Dict = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    # -- Retry loop -----------------------------------------------------------
    max_retries = 3
    logger = get_logger()
    last_error = None

    for attempt in range(max_retries):
        try:
            client = OpenAI(**client_kwargs)

            # Build create kwargs.  Only DeepSeek receives extra_body.
            create_kwargs: Dict = {
                "model": info.api_model_id,
                "messages": messages,
                "temperature": temperature,
                "timeout": 60,
            }
            if info.provider == "deepseek":
                create_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

            response = client.chat.completions.create(**create_kwargs)

            cost = _calculate_cost(response, model_name)
            if logger:
                logger.info(
                    f"LLM call succeeded (attempt {attempt + 1}/{max_retries})"
                )
                logger.llm_call(model_name, cost, response.usage.total_tokens)
            else:
                print(
                    f"[llm] LLM call succeeded (attempt {attempt + 1}/{max_retries})"
                )

            return response.choices[0].message.content, cost

        except RateLimitError as e:
            last_error = e
            if logger:
                logger.error(
                    f"Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {e}"
                )
            else:
                print(
                    f"[llm] Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {e}"
                )

        except (APITimeoutError, APIConnectionError) as e:
            last_error = e
            if logger:
                logger.error(
                    f"Connection/timeout error (attempt {attempt + 1}/{max_retries}): {e}"
                )
            else:
                print(
                    f"[llm] Connection/timeout error (attempt {attempt + 1}/{max_retries}): {e}"
                )

        except Exception as e:
            last_error = e
            error_type = type(e).__name__
            if logger:
                logger.error(
                    f"Unexpected error (attempt {attempt + 1}/{max_retries}): {error_type}: {e}"
                )
            else:
                print(
                    f"[llm] Unexpected error (attempt {attempt + 1}/{max_retries}): {error_type}: {e}"
                )

        if attempt < max_retries - 1:
            if logger:
                logger.info("Retrying in 1 seconds...")
            else:
                print("[llm] Retrying in 1 seconds...")
            time.sleep(1)
        else:
            provider = info.provider.upper()
            error_msg = (
                f"{provider} API call failed after {max_retries} attempts. "
                f"Last error: {type(last_error).__name__}: {last_error}"
            )
            if logger:
                logger.error(f"All {max_retries} attempts failed")
                logger.error(error_msg)
            else:
                print(f"[llm] All {max_retries} attempts failed")
            raise Exception(error_msg)


# ---------------------------------------------------------------------------
# Per-model convenience wrappers
# ---------------------------------------------------------------------------

def deepseek_v4_flash(
    messages: List[Dict], temperature: float = 0.3
) -> Tuple[str, float]:
    """Call DeepSeek V4 Flash (fast / cost-optimised tier)."""
    return _call_openai_compatible("deepseek-v4-flash", messages, temperature)


def deepseek_v4_pro(
    messages: List[Dict], temperature: float = 0.3
) -> Tuple[str, float]:
    """Call DeepSeek V4 Pro (premium reasoning tier)."""
    return _call_openai_compatible("deepseek-v4-pro", messages, temperature)