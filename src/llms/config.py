"""
LLM Provider - Unified LLM configuration and provider system.

Model metadata is now sourced exclusively from ``model_registry.py`` (single
source of truth).  The public ``MODELS`` dict has been removed (batch 3); the
private ``_SYNC_MODEL_FUNCTIONS`` mapping only stores model-name → callable
and carries no duplicate metadata.
"""

import os
from typing import Callable, Tuple, List, Dict

# Import all available models (sync callables)
from .openai import gpt_4o_mini, gpt_5_4_mini
from .claude import claude_3_5_sonnet, claude_3_5_haiku, claude_3_opus
from .openai_compatible import deepseek_v4_flash, deepseek_v4_pro

# Unified model registry (single source of truth for all model metadata)
from .model_registry import (
    get_model_info,
    ModelInfo,
    list_models as _registry_list_models,
    list_available_models as _registry_list_available,
)

# ---------------------------------------------------------------------------
# Private mapping: model-name → sync callable.  This is the ONLY reason the
# sync path still needs a lookup — to resolve the function to call.  It must
# NOT duplicate API keys, providers, api_styles, api_model_ids, base URLs,
# or prices.  All of that lives in MODEL_REGISTRY.
# ---------------------------------------------------------------------------
_SYNC_MODEL_FUNCTIONS: Dict[str, Callable] = {
    "gpt-4o-mini": gpt_4o_mini,
    "gpt-5.4-mini": gpt_5_4_mini,
    "claude-3.5-sonnet": claude_3_5_sonnet,
    "claude-3.5-haiku": claude_3_5_haiku,
    "claude-3-opus": claude_3_opus,
    "deepseek-v4-flash": deepseek_v4_flash,
    "deepseek-v4-pro": deepseek_v4_pro,
}


class LLMProvider:
    """Unified LLM provider with simple model switching."""

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self._model_info = None
        self.current_model = None
        self.current_llm = None
        self._init_model(model_name)

    def _init_model(self, model_name: str):
        """Validate *model_name* and resolve all state — used by __init__ and
        set_model so that validation happens atomically before any mutation."""
        # -- Validate model exists in the registry ---------------------------
        try:
            new_info = get_model_info(model_name)
        except KeyError:
            raise ValueError(
                f"Model '{model_name}' not available. "
                f"Available: {_registry_list_models()}"
            )

        # -- Validate API key is present -------------------------------------
        if not os.getenv(new_info.api_key_env):
            raise ValueError(
                f"API key '{new_info.api_key_env}' not found in "
                f"environment variables"
            )

        # -- Validate model is in the sync function map ----------------------
        if model_name not in _SYNC_MODEL_FUNCTIONS:
            raise ValueError(
                f"Model '{model_name}' has no sync callable registered in "
                f"_SYNC_MODEL_FUNCTIONS."
            )

        # -- DEEPSEEK_THINKING_ENABLED guard (v1 does not support thinking) --
        if new_info.provider == "deepseek":
            thinking_enabled = os.getenv("DEEPSEEK_THINKING_ENABLED", "false").lower()
            if thinking_enabled == "true":
                raise ValueError(
                    "DEEPSEEK_THINKING_ENABLED=true is not supported in v1. "
                    "Thinking mode for DeepSeek models is not yet implemented."
                )

        # -- All validations passed — atomically update state ---------------
        self._model_info = new_info
        self.current_model = model_name
        self.current_llm = _SYNC_MODEL_FUNCTIONS[model_name]

    @property
    def model_info(self) -> ModelInfo:
        """Read-only access to the unified model metadata."""
        return self._model_info

    def set_model(self, model_name: str):
        """Set the current model with API key verification.

        All validation happens *before* any state mutation.  If validation
        fails the provider is left in its previous state.
        """
        self._init_model(model_name)

    def __call__(self, messages: List[Dict], temperature: float = 0.3) -> Tuple[str, float]:
        """Call the current LLM."""
        return self.current_llm(messages, temperature)

    @classmethod
    def list_models(cls) -> List[str]:
        """List all registered models (from the unified registry)."""
        return _registry_list_models()

    @classmethod
    def list_available_models(cls) -> List[str]:
        """List models that have API keys available (from the registry)."""
        return _registry_list_available()


# Global provider instance
_global_provider = None

def init_llm(model_name: str = "gpt-4o-mini") -> LLMProvider:
    """Initialize the global LLM provider."""
    global _global_provider
    _global_provider = LLMProvider(model_name)
    return _global_provider

def get_llm() -> Callable:
    """Get the current LLM function."""
    if _global_provider is None:
        init_llm()
    return _global_provider

def list_models() -> List[str]:
    """List available models."""
    return LLMProvider.list_models()

def list_available_models() -> List[str]:
    """List models with API keys available."""
    return LLMProvider.list_available_models()