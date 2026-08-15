"""Minimal, observable ReAct runner for offline FinTrace-CN benchmarks.

The production generalist agent carries many live tools and UI side effects.
This runner intentionally exposes only the snapshot-backed ``cn_tools`` so a
benchmark measures the model's actual tool selection and arguments without
making a network request.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence

from src.agents.tools.base import ToolRegistry
from src.agents.tools.cn_tools import build_cn_snapshot_tools
from src.cn.providers.snapshot import SnapshotProvider
from src.cn.research import ResearchState
from src.validation.research_gate import (
    ResearchGateRequirements,
    ResearchGateValidator,
    SnapshotEvidenceLedger,
    snapshot_evidence_records,
)


SYSTEM_PROMPT = """You are an offline A-share research agent.
Use only the supplied tools. Snapshot data is historical, not live. Resolve an
A-share symbol before fetching its data, even when the query already contains a
canonical ticker. Preserve evidence IDs, and never invent financial figures.
For a point-in-time request, use the supplied complete ISO-8601 cutoff. Use the
minimum necessary tools; do not create a research plan unless the user asks for
one. If a tool errors, stop rather than retrying with guessed payloads."""


class ToolCallingProvider(Protocol):
    model_name: str
    api_style: str

    async def call_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
                              temperature: float = 0.0, **kwargs: Any) -> Any: ...


class OfflineCnAgent:
    """Execute one real model-and-tool trajectory against one pinned snapshot."""

    def __init__(self, *, snapshot_path: Path | str, model_name: str,
                 temperature: float = 0.0, max_steps: int = 6,
                 provider: ToolCallingProvider | None = None,
                 required_metrics: Sequence[str] = (),
                 requires_evidence: Optional[bool] = None,
                 requested_valuation_method: Optional[str] = None) -> None:
        self.snapshot_path = Path(snapshot_path)
        self.snapshot = SnapshotProvider(self.snapshot_path)
        self.model_name = model_name
        self.temperature = temperature
        self.max_steps = max_steps
        self.gate_requirements = ResearchGateRequirements(
            required_metrics=tuple(str(metric).lower() for metric in required_metrics),
            # This runner emits a research conclusion, so provenance is a
            # non-negotiable gate even when legacy benchmark metadata omitted
            # the flag.
            requires_evidence=True,
            requested_valuation_method=requested_valuation_method,
        )
        if provider is None:
            # The application imports its LLM package from ``src``. Keep that
            # optional dependency out of fixture-only test collection.
            from llms.async_client import AsyncLLMProvider
            provider = AsyncLLMProvider(model_name)
        self.provider = provider
        self.registry = ToolRegistry().register_all(build_cn_snapshot_tools(self.snapshot_path))
        self.answer = ""
        self.total_cost = 0.0
        self.llm_calls = 0

    async def run(self, query: str) -> ResearchState:
        symbol = str(self.snapshot._symbol)
        cutoff = self.snapshot._payload["research_as_of"]
        state = ResearchState.create(query=query, symbol=symbol, research_as_of=cutoff, intent="offline_benchmark")
        # Symbol parsing is a deterministic boundary, not an LLM judgement.
        # Run it before the model so the benchmark's stable path is explicitly
        # "parse code -> price -> evidence" even when a model elects to skip a
        # redundant resolver call for an already-canonical ticker.
        resolved_symbol = await self._resolve_symbol_preflight(query, state)
        is_openai_style = getattr(self.provider, "api_style", "openai") == "openai"
        tool_defs = self.registry.openai_defs() if is_openai_style else self.registry.anthropic_defs()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt(cutoff, resolved_symbol)},
            {"role": "user", "content": query},
        ]

        for _ in range(self.max_steps):
            self.llm_calls += 1
            response = await self.provider.call_with_tools(messages, tool_defs, temperature=self.temperature)
            self.total_cost += float(getattr(response, "cost", 0.0) or 0.0)
            if not response.has_tool_calls:
                self.answer = str(response.text or "")
                break
            messages.append(response.raw)
            anthropic_results: List[Dict[str, Any]] = []
            for call in response.tool_calls:
                started_at = datetime.now(timezone.utc).isoformat()
                if call.parse_error:
                    result_json = json.dumps({"status": "error", "error": call.parse_error}, ensure_ascii=False)
                else:
                    result_json = await self.registry.execute(call.name, call.arguments)
                payload = _decode_result(result_json)
                evidence_ids = _evidence_ids(payload)
                state.register_evidence(evidence_ids)
                state.record_tool(
                    tool_name=call.name, arguments=call.arguments, started_at=started_at,
                    result_status=str(payload.get("status", "error")), provider="snapshot",
                    evidence_ids=evidence_ids,
                )
                validation = payload.get("validation")
                if isinstance(validation, dict):
                    state.finalize_validation(validation)
                if is_openai_style:
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": result_json})
                else:
                    anthropic_results.append({"type": "tool_result", "tool_use_id": call.id, "content": result_json})
            if not is_openai_style and anthropic_results:
                messages.append({"role": "user", "content": anthropic_results})
        else:
            self.llm_calls += 1
            response = await self.provider.call_with_tools(messages, [], temperature=self.temperature)
            self.total_cost += float(getattr(response, "cost", 0.0) or 0.0)
            self.answer = str(response.text or "")

        self._apply_validator_gate(state)
        state.report = self.answer
        state.cost_trace.append({
            "model": self.model_name,
            "cost_usd": self.total_cost,
            "llm_calls": self.llm_calls,
            "steps": len(state.tool_trace),
        })
        return state

    @staticmethod
    def _system_prompt(cutoff: str, resolved_symbol: Optional[str] = None) -> str:
        preflight = ""
        if resolved_symbol:
            preflight = (
                f"\nPRE-FLIGHT: deterministic code has already resolved the request "
                f"to {resolved_symbol}. Do not repeat symbol resolution; fetch the "
                "requested snapshot data using that canonical ticker."
            )
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"RUN CONTEXT: The fixed research cutoff is {cutoff}. When any tool "
            "accepts research_as_of, use this exact value unless the user "
            f"explicitly supplies a different cutoff.{preflight}"
        )

    async def _resolve_symbol_preflight(self, query: str, state: ResearchState) -> Optional[str]:
        """Record deterministic canonical-code parsing when the query names this snapshot."""
        symbol = str(self.snapshot._symbol)
        if not re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", query.upper()):
            return None
        started_at = datetime.now(timezone.utc).isoformat()
        result_json = await self.registry.execute("resolve_cn_symbol", {"query": symbol})
        payload = _decode_result(result_json)
        state.record_tool(
            tool_name="resolve_cn_symbol", arguments={"query": symbol}, started_at=started_at,
            result_status=str(payload.get("status", "error")), provider="snapshot",
            evidence_ids=_evidence_ids(payload),
        )
        return symbol if payload.get("status") == "ok" else None

    def _apply_validator_gate(self, state: ResearchState) -> None:
        """Block deterministic prose unless captured execution is admissible."""
        records = snapshot_evidence_records(self.snapshot._payload, state=state)
        result = ResearchGateValidator(max_data_age_days=365).validate(
            SnapshotEvidenceLedger(records), state=state,
            snapshot_payload=self.snapshot._payload,
            research_as_of=state.research_as_of,
            requirements=self.gate_requirements,
        )
        if result.valid:
            state.finalize_validation({
                "valid": True, "errors": [], "missing_evidence": state.missing_evidence,
            })
            return

        self.answer = (
            "无法验证/拒绝结论：Validator 检测到执行或数据问题。\n"
            f"错误详情：{', '.join(result.errors)}\n"
            "请补齐有效工具结果、所需指标和证据，并确认截止时间与行业估值口径。"
        )
        state.finalize_validation({
            "valid": False, "errors": result.errors,
            "missing_evidence": state.missing_evidence,
        })


def _decode_result(result_json: str) -> Dict[str, Any]:
    try:
        value = json.loads(result_json)
    except json.JSONDecodeError:
        return {"status": "error", "error": "Tool returned invalid JSON."}
    return value if isinstance(value, dict) else {"status": "error", "error": "Tool returned non-object JSON."}


def _evidence_ids(payload: Dict[str, Any]) -> List[str]:
    ids = payload.get("evidence_ids", [])
    if not isinstance(ids, list):
        ids = []
    nested = payload.get("research_state")
    if isinstance(nested, dict):
        ids = [*ids, *(nested.get("facts") or []), *(nested.get("calculations") or [])]
    return [str(item) for item in ids]
