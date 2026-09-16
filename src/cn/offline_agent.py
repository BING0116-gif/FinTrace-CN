"""Backward-compatible offline benchmark adapter.

The reusable implementation now lives in ``src.cn.research_agent.CnResearchAgent``
so the product path and the real-model benchmark share one agent.  This module
only re-exports the offline-compatible alias plus the symbols that existing
scripts and tests import.
"""

from __future__ import annotations

from .research_agent import (
    AGENT_EVENTS,
    CnResearchAgent,
    SYSTEM_PROMPT,
    ToolCallingProvider,
)

# Keep the historical class name resolving to the shared implementation; the
# constructor and ``run(query)`` contract are unchanged, so existing benchmark
# callers do not need to change.
OfflineCnAgent = CnResearchAgent

__all__ = ["CnResearchAgent", "OfflineCnAgent", "SYSTEM_PROMPT", "ToolCallingProvider", "AGENT_EVENTS"]