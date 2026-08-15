"""Configurable agent for real LLM ablation across four variants.

Each variant runs the same model, prompt, temperature, and max steps against
the same fixture cases.  The only difference is which components are active:

- ``direct_llm``        — LLM only, no tools, no evidence, no validator.
- ``agent_tools``       — LLM + ReAct tools, but evidence IDs are stripped.
- ``agent_tools_evidence`` — LLM + tools + evidence ledger.
- ``agent_tools_evidence_validator`` — Full pipeline with validator as
  blocking gate: when the FinancialValidator fails, the agent MUST return a
  rejection message instead of a financial conclusion.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from src.agents.tools.base import ToolRegistry
from src.agents.tools.cn_tools import build_cn_snapshot_tools
from src.cn.benchmark import METRIC_KEYS
from src.cn.evidence import EvidenceLedger
from src.cn.providers.snapshot import SnapshotProvider
from src.cn.research import ResearchState
from src.validation.research_gate import ResearchGateRequirements, ResearchGateValidator

ABLATION_VARIANTS = (
    "direct_llm",
    "agent_tools",
    "agent_tools_evidence",
    "agent_tools_evidence_validator",
)

SYSTEM_PROMPT = """You are an offline A-share research agent.
Use only the supplied tools. Snapshot data is historical, not live. Resolve an
A-share symbol before fetching its data, even when the query already contains a
canonical ticker. Preserve evidence IDs, and never invent financial figures.
For a point-in-time request, pass the supplied research cutoff as the complete
ISO-8601 ``research_as_of`` value (including time and UTC offset). If a tool
returns an error, do not retry with a guessed payload: stop and explain the
limitation. Use the minimum necessary tools; do not create a research plan
unless the user explicitly asks for one. Stop after you have answered the
user's request."""


class ToolCallingProvider(Protocol):
    """Protocol for an async LLM provider that supports tool calling."""

    model_name: str
    api_style: str

    async def call_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
                              temperature: float = 0.0, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Ablation Agent
# ---------------------------------------------------------------------------

class AblationAgent:
    """Run one real LLM trajectory in one of four ablation variants.

    Usage::

        agent = AblationAgent(
            variant="agent_tools_evidence_validator",
            snapshot_path="tests/fixtures/cn/600519.SH_illustrative_v1.json",
            model_name="gpt-4o-mini",
        )
        state = await agent.run("查询 600519.SH 的价格")
    """

    def __init__(
        self,
        *,
        variant: str,
        snapshot_path: Path | str,
        model_name: str,
        temperature: float = 0.0,
        max_steps: int = 6,
        provider: Optional[ToolCallingProvider] = None,
        research_as_of: Optional[str] = None,
        required_metrics: Sequence[str] = (),
        requires_evidence: Optional[bool] = None,
        requested_valuation_method: Optional[str] = None,
    ) -> None:
        if variant not in ABLATION_VARIANTS:
            raise ValueError(f"Unknown ablation variant: {variant}. Choose from {ABLATION_VARIANTS}")
        self.variant = variant
        self.snapshot_path = Path(snapshot_path)
        self.snapshot = SnapshotProvider(self.snapshot_path)
        self.model_name = model_name
        self.temperature = temperature
        self.max_steps = max_steps
        self._research_as_of = research_as_of or self.snapshot._payload.get("research_as_of", "")
        self.gate_requirements = ResearchGateRequirements(
            required_metrics=tuple(str(metric).lower() for metric in required_metrics),
            # A full financial-conclusion run may never opt out of provenance.
            # The optional argument remains useful to stricter non-full test
            # configurations, but ``False`` cannot disable the full gate.
            requires_evidence=(
                variant == "agent_tools_evidence_validator" or bool(requires_evidence)
            ),
            requested_valuation_method=requested_valuation_method,
        )
        if provider is None:
            from src.llms.async_client import AsyncLLMProvider
            provider = AsyncLLMProvider(model_name)
        self.provider = provider
        self.registry = ToolRegistry().register_all(build_cn_snapshot_tools(self.snapshot_path))
        self.answer = ""
        self.total_cost = 0.0
        # Per-step latency tracking
        self.step_times: List[float] = []
        # Validator intercept tracking
        self.validator_intercepted: bool = False
        self.validator_errors: List[str] = []

    @property
    def research_as_of(self) -> str:
        return self._research_as_of

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, query: str) -> ResearchState:
        symbol = str(self.snapshot._symbol)
        state = ResearchState.create(
            query=query, symbol=symbol, research_as_of=self.research_as_of,
            intent="offline_ablation",
        )

        if self.variant == "direct_llm":
            return await self._run_direct_llm(query, state)

        # For all tool-enabled variants, run the ReAct loop
        is_openai_style = getattr(self.provider, "api_style", "openai") == "openai"
        tool_defs = self.registry.openai_defs() if is_openai_style else self.registry.anthropic_defs()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": query},
        ]

        for step in range(self.max_steps):
            step_start = time.monotonic()
            response = await self.provider.call_with_tools(messages, tool_defs, temperature=self.temperature)
            self.total_cost += float(getattr(response, "cost", 0.0) or 0.0)
            self.step_times.append(time.monotonic() - step_start)

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
                evidence_ids = _evidence_ids(payload) if self.variant != "agent_tools" else []
                # In agent_tools variant, strip evidence but still record tool calls
                state.register_evidence(evidence_ids)
                state.record_tool(
                    tool_name=call.name, arguments=call.arguments, started_at=started_at,
                    result_status=str(payload.get("status", "error")), provider="snapshot",
                    evidence_ids=evidence_ids,
                )
                # Extract validation from tool results
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
            # Max steps reached without a final answer — force one more plain-text call
            response = await self.provider.call_with_tools(messages, [], temperature=self.temperature)
            self.total_cost += float(getattr(response, "cost", 0.0) or 0.0)
            self.answer = str(response.text or "")

        # After the ReAct loop, apply the validator gate for the full variant
        if self.variant == "agent_tools_evidence_validator":
            self._apply_validator_gate(state)

        # Finalize state
        if state.validation_result is None:
            state.finalize_validation({"valid": not state.missing_evidence, "missing_evidence": state.missing_evidence})
        state.report = self.answer
        state.cost_trace.append({
            "model": self.model_name,
            "cost_usd": self.total_cost,
            "steps": len(state.tool_trace),
            "variant": self.variant,
        })
        return state

    # ------------------------------------------------------------------
    # Direct LLM variant
    # ------------------------------------------------------------------

    async def _run_direct_llm(self, query: str, state: ResearchState) -> ResearchState:
        """Call the LLM without any tools — the model must answer from knowledge."""
        step_start = time.monotonic()
        is_openai_style = getattr(self.provider, "api_style", "openai") == "openai"
        prompt = self._system_prompt() + (
            "\n\nYou do NOT have any tools available. Answer the user's query based on your "
            "knowledge alone. Do not make up specific financial figures."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]
        if is_openai_style:
            response = await self.provider.call_with_tools(messages, [], temperature=self.temperature)
        else:
            from src.llms.async_client import LLMToolResponse
            # Use the __call__ method for plain text
            text, cost = await self.provider(messages, temperature=self.temperature)
            response = LLMToolResponse(text, [], cost, {"role": "assistant", "content": text})

        self.total_cost += float(getattr(response, "cost", 0.0) or 0.0)
        self.step_times.append(time.monotonic() - step_start)
        self.answer = str(getattr(response, "text", "") or "")
        state.report = self.answer
        return state

    def _system_prompt(self) -> str:
        """Bind the pinned cutoff into every trajectory's system context."""
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"RUN CONTEXT: The fixed research cutoff is {self.research_as_of}. "
            "When any tool accepts research_as_of, use this exact value unless "
            "the user explicitly supplies a different cutoff."
        )

    # ------------------------------------------------------------------
    # Validator Gate
    # ------------------------------------------------------------------

    def _apply_validator_gate(self, state: ResearchState) -> None:
        """Run the FinancialValidator against collected evidence.

        If validation fails, the agent's answer is replaced with a rejection
        message — the validator acts as a real blocking gate.
        """
        # Collect evidence from tool results
        records = self._extract_evidence_records(state)
        validator = ResearchGateValidator(max_data_age_days=365)
        result = validator.validate(
            _MiniLedger(records),
            state=state,
            snapshot_payload=self.snapshot._payload,
            research_as_of=self.research_as_of,
            requirements=self.gate_requirements,
        )

        self.validator_errors = list(result.errors)
        if not result.valid:
            self.validator_intercepted = True
            self.answer = (
                "无法验证/拒绝结论：Validator 检测到执行或数据问题。\n"
                f"错误详情：{'；'.join(result.errors)}\n"
                "请补齐有效工具结果、所需指标和证据，并确认截止时间与行业估值口径。"
            )
            state.report = self.answer
            state.finalize_validation({
                "valid": False,
                "errors": result.errors,
                "missing_evidence": state.missing_evidence,
            })
        else:
            state.finalize_validation({
                "valid": True,
                "errors": [],
                "missing_evidence": state.missing_evidence,
            })

    def _extract_evidence_records(self, state: ResearchState) -> List[Dict[str, Any]]:
        """Parse tool results into evidence records for the FinancialValidator.

        Each record is a dict with keys expected by the validator:
        evidence_id, kind, symbol, metric, value, currency, unit,
        fiscal_period, period_basis, published_at, available_at, provider.
        """
        records: List[Dict[str, Any]] = []

        # Snapshot reconstruction is only an adapter for validator input; it
        # must never invent provenance.  Accept a reconstructed record only if
        # an actually successful tool result returned and registered that ID.
        registered_ids = {*state.facts, *state.calculations}
        successful_trace_ids = {
            evidence_id
            for trace in state.tool_trace
            if trace.result_status == "ok"
            for evidence_id in trace.evidence_ids
        }
        trusted_ids = registered_ids & successful_trace_ids

        # Reconstruct evidence from the snapshot for the tools that were called
        for trace in state.tool_trace:
            if trace.result_status != "ok":
                continue
            if trace.tool_name == "get_cn_prices":
                records.extend(self._reconstruct_price_evidence(trace.arguments))
            elif trace.tool_name == "get_cn_financials":
                records.extend(self._reconstruct_financial_evidence(trace.arguments))
            elif trace.tool_name == "generate_cn_research_report":
                records.extend(self._reconstruct_report_evidence(trace.arguments))

        return [record for record in records if record["evidence_id"] in trusted_ids]

    def _reconstruct_price_evidence(self, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Reconstruct price evidence records from snapshot data."""
        ticker = arguments.get("ticker", "")
        if not ticker:
            return []
        try:
            from src.cn.symbols import normalize_cn_symbol
            symbol = normalize_cn_symbol(ticker)
            bars = self.snapshot.get_daily_bars(symbol)
        except Exception:
            return []
        if not bars:
            return []
        latest = max(bars, key=lambda item: item.trade_date)
        evidence_id = f"fact_{str(symbol).replace('.', '_')}_close_{latest.trade_date}_RAW"
        available = f"{latest.trade_date}T15:00:00+08:00"
        return [{
            "evidence_id": evidence_id,
            "kind": "fact",
            "symbol": str(symbol),
            "metric": "close",
            "value": latest.close,
            "currency": "CNY",
            "unit": "CNY/share",
            "fiscal_period": None,
            "period_basis": "RAW",
            "published_at": available,
            "available_at": available,
            "provider": "snapshot",
        }]

    def _reconstruct_financial_evidence(self, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Reconstruct financial evidence records from snapshot data."""
        ticker = arguments.get("ticker", "")
        research_as_of = arguments.get("research_as_of", self.research_as_of)
        if not ticker:
            return []
        try:
            from src.cn.symbols import normalize_cn_symbol
            symbol = normalize_cn_symbol(ticker)
            statements = self.snapshot.get_financial_statements(symbol, research_as_of=research_as_of)
        except Exception:
            return []
        records = []
        for stmt in statements:
            for metric, value in stmt.values.items():
                if value is None:
                    continue
                evidence_id = f"fact_{str(symbol).replace('.', '_')}_{metric}_{stmt.fiscal_period}"
                records.append({
                    "evidence_id": evidence_id,
                    "kind": "fact",
                    "symbol": str(symbol),
                    "metric": metric,
                    "value": value,
                    "currency": stmt.currency,
                    "unit": stmt.unit,
                    "fiscal_period": stmt.fiscal_period,
                    "period_basis": stmt.period_basis,
                    "published_at": stmt.published_at,
                    "available_at": stmt.available_at,
                    "provider": "snapshot",
                })
        return records

    def _reconstruct_report_evidence(self, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Reconstruct report evidence from the snapshot."""
        return [
            *self._reconstruct_price_evidence(arguments),
            *self._reconstruct_financial_evidence(arguments),
        ]


# ---------------------------------------------------------------------------
# MiniLedger — a dict-based adapter for FinancialValidator
# ---------------------------------------------------------------------------

class _MiniLedger:
    """Minimal adapter so FinancialValidator.validate() can be called on
    a list of dict-based evidence records without constructing a full
    EvidenceLedger."""

    def __init__(self, records: List[Dict[str, Any]]):
        self._records = records

    def records(self) -> List[Any]:
        """Return EvidenceRecord-like objects with attribute access."""
        return [_DictRecord(r) for r in self._records]


class _DictRecord:
    """Adapter that makes a dict accessible as an object with attributes."""

    def __init__(self, data: Dict[str, Any]):
        self.__dict__["_data"] = data

    def __getattr__(self, name: str) -> Any:
        return self._data.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self._data[name] = value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Aggregate metrics for ablation comparison
# ---------------------------------------------------------------------------

def compute_ablation_metrics(
    results: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Compute per-variant aggregate metrics from the ablation results.

    Returns a dict mapping variant name → {metric_key: value}.
    """
    metrics: Dict[str, Dict[str, Any]] = {}
    for variant, rows in results.items():
        if not rows:
            metrics[variant] = {m: 0.0 for m in METRIC_KEYS}
            metrics[variant]["validator_intercept_rate"] = 0.0
            metrics[variant]["error_conclusion_leakage"] = 0.0
            metrics[variant]["avg_latency_seconds"] = 0.0
            metrics[variant]["total_cost_usd"] = 0.0
            continue

        n = len(rows)
        avg_f1 = sum(r["tool_f1"] for r in rows) / n
        avg_param = sum(1 for r in rows if r["parameters_ok"]) / n
        avg_evidence = sum(r["evidence_coverage"] for r in rows) / n
        avg_e2e = sum(1 for r in rows if r["passed"]) / n
        intercepts = sum(1 for r in rows if r.get("validator_intercepted", False))
        leakages = sum(1 for r in rows if r.get("error_conclusion_leakage", False))
        total_cost = sum(r.get("cost_usd", 0.0) for r in rows)
        latencies = [r.get("latency_seconds", 0.0) for r in rows if r.get("latency_seconds") is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        metrics[variant] = {
            "tool_f1": round(avg_f1, 4),
            "parameter_accuracy": round(avg_param, 4),
            "evidence_coverage": round(avg_evidence, 4),
            "e2e_success_rate": round(avg_e2e, 4),
            "validator_intercept_rate": round(intercepts / n, 4),
            "error_conclusion_leakage": round(leakages / n, 4),
            "avg_latency_seconds": round(avg_latency, 2),
            "total_cost_usd": round(total_cost, 6),
            "cases": n,
        }
    return metrics
