"""
LLMs package - Multi-provider LLM integration for stock analysis.

This package provides unified interfaces for different LLM providers:
- OpenAI (GPT-4o, GPT-4o-mini, GPT-4, GPT-3.5-turbo)
- Anthropic Claude (Claude-3.5-Sonnet, Claude-3.5-Haiku, Claude-3-Opus)
- OpenAI-compatible providers (DeepSeek)

All functions follow the same interface:
- Input: List of messages, temperature
- Output: Tuple of (response_text, cost_in_usd)
- Error handling: Retry logic with exponential backoff
- Logging: Integrated with the stock analyst logger

Importing this package (or any ``src.llms.*`` submodule, e.g.
``model_registry``) is deliberately cheap: the provider SDKs (``openai`` /
``anthropic``) are imported lazily, only when a model callable or the sync
provider configuration is actually accessed.

Usage:
    # Configurable usage
    from src.llms import get_llm, init_llm

    init_llm("deepseek-v4-flash")
    llm = get_llm()  # Returns the selected model callable

    # Direct model usage
    from src.llms import gpt_4o_mini, claude_3_5_sonnet
"""

from importlib import import_module

# ---------------------------------------------------------------------------
# Lazy exports (PEP 562).  Each public name maps to (submodule, attribute);
# the submodule — and its provider SDK — loads on first attribute access.
# The two ``calculate_*_cost`` names are aliases of each module's own
# ``calculate_cost``, matching the previous eager ``as`` re-exports.
# ---------------------------------------------------------------------------
_LAZY_EXPORTS = {
    # OpenAI models
    "gpt_4o_mini": (".openai", "gpt_4o_mini"),
    "gpt_5_4_mini": (".openai", "gpt_5_4_mini"),
    "calculate_openai_cost": (".openai", "calculate_cost"),
    # Anthropic Claude models
    "claude_3_5_sonnet": (".claude", "claude_3_5_sonnet"),
    "claude_3_5_haiku": (".claude", "claude_3_5_haiku"),
    "claude_3_opus": (".claude", "claude_3_opus"),
    "calculate_claude_cost": (".claude", "calculate_cost"),
    # OpenAI-compatible providers (DeepSeek, etc.)
    "deepseek_v4_flash": (".openai_compatible", "deepseek_v4_flash"),
    "deepseek_v4_pro": (".openai_compatible", "deepseek_v4_pro"),
    # Configuration and utilities
    "init_llm": (".config", "init_llm"),
    "get_llm": (".config", "get_llm"),
    "list_models": (".config", "list_models"),
}

# Convenience aliases for quick model switching.
_LAZY_ALIASES = {
    "default_model": "gpt_4o_mini",
    "premium_model": "claude_3_5_sonnet",
    "budget_model": "claude_3_5_haiku",
    "flagship_model": "claude_3_opus",
}


def _load(name: str):
    if name in _LAZY_EXPORTS:
        module_name, attribute = _LAZY_EXPORTS[name]
        value = getattr(import_module(module_name, __package__), attribute)
    elif name in _LAZY_ALIASES:
        target = _LAZY_ALIASES[name]
        value = globals().get(target)
        if value is None:
            value = _load(target)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value  # cache so later lookups skip __getattr__
    return value


def __getattr__(name: str):
    return _load(name)


def __dir__():
    return sorted({*globals(), *_LAZY_EXPORTS, *_LAZY_ALIASES})


__all__ = [
    # OpenAI
    'gpt_4o_mini',
    'calculate_openai_cost',

    # Claude
    'claude_3_5_sonnet',
    'claude_3_5_haiku',
    'claude_3_opus',
    'calculate_claude_cost',

    # DeepSeek (OpenAI-compatible)
    'deepseek_v4_flash',
    'deepseek_v4_pro',

    # Configuration
    'init_llm',
    'get_llm',
    'list_models',
]