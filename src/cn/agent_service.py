"""Application service tying the shared CnResearchAgent into workbench tasks.

This layer:
* validates a product request (query length, model configuration, symbol, snapshot);
* queues an ``agent_research`` task and runs the real LLM agent in the shared
  bounded worker pool;
* persists a safe, structured event stream, the final ``ResearchState``, the
  Validator result, and cost / latency usage back onto the task;
* never leaks API keys, absolute server paths, or raw SDK tracebacks.

``blocked`` is a first-class, trusted outcome produced by the Validator — it is
never treated as a system failure.  ``cancelled`` reflects a cooperative stop.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from src.cn import workbench_service
from src.cn.research_agent import CnResearchAgent
from src.cn.symbols import normalize_cn_symbol
from src.llms.model_registry import get_model_info


class AgentResearchError(ValueError):
    """Raised for invalid agent-research requests; mapped to typed API errors."""


TERMINAL_AGENT_STATUSES = {"succeeded", "blocked", "failed", "cancelled"}
ACTIVE_AGENT_STATUSES = {"queued", "running"}


@dataclass(frozen=True)
class AgentResearchRequest:
    query: str
    symbol: str
    snapshot_id: str
    research_as_of: Optional[str] = None
    model_name: str = ""
    temperature: float = 0.0
    max_steps: int = 6
    required_metrics: tuple[str, ...] = ()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_query(query: str) -> str:
    text = (query or "").strip()
    if len(text) < 3:
        raise AgentResearchError("query must be at least 3 characters.")
    if len(text) > 2000:
        raise AgentResearchError("query must be at most 2000 characters.")
    return text


def _validate_research_cutoff(value: str) -> str:
    try:
        datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise AgentResearchError(f"Invalid research_as_of timestamp: {value}") from exc
    return value


def _require_model_configured(model_name: str) -> None:
    """Refuse to launch when the model is unknown or its key is not configured.

    The service never silently switches to another model or to mock, because
    that would make product and benchmark results non-reproducible.
    """
    try:
        info = get_model_info(model_name)
    except KeyError as exc:
        raise AgentResearchError(
            f"Unknown model '{model_name}'. Configure a registered model before running the Agent."
        ) from exc
    if not info.supports_tools:
        raise AgentResearchError(f"Model '{model_name}' does not support tool calling.")
    if not os.getenv(info.api_key_env):
        raise AgentResearchError(
            f"Model '{model_name}' is not configured. Set {info.api_key_env} to enable real-model runs."
        )


def _snapshot_path_for(snapshot_id: str):
    """Locate a snapshot in the workbench snapshot dir (raises KeyError)."""
    return workbench_service._snapshot_path(snapshot_id)


def _resolve_snapshot_payload(snapshot_id: str) -> dict[str, Any]:
    return workbench_service.load_snapshot(snapshot_id)


def start_agent_research(request: AgentResearchRequest) -> dict[str, Any]:
    """Validate and queue a real-model agent-research task.

    Returns the persisted task.  Validation failures raise ``AgentResearchError``
    (mapped by the API) except an unknown snapshot, raised as ``KeyError``.
    """
    query = _validate_query(request.query)
    _require_model_configured(request.model_name)

    symbol_text = request.symbol.strip()
    try:
        symbol = str(normalize_cn_symbol(symbol_text))
    except Exception as exc:
        raise AgentResearchError(f"Invalid A-share symbol: {symbol_text}") from exc

    # Locate the snapshot before queueing so unknown snapshots fail eagerly.
    path = _snapshot_path_for(request.snapshot_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("symbol") != symbol:
        raise AgentResearchError(
            f"Snapshot {request.snapshot_id} covers {payload.get('symbol')}, not {symbol}."
        )

    research_as_of = _validate_research_cutoff(request.research_as_of) if request.research_as_of else None
    metrics = tuple(str(m).strip() for m in request.required_metrics if str(m).strip())

    task = workbench_service._new_task(symbol, "agent_research")
    task.update({
        "status": "queued", "message": "Agent 研究任务已排队。",
        "snapshot_id": request.snapshot_id, "research_as_of": research_as_of,
        "query": query, "model_name": request.model_name,
        "temperature": request.temperature, "max_steps": int(request.max_steps),
        "required_metrics": list(metrics),
        "progress_percent": 0, "events": [],
    })
    workbench_service._record_event(task, "queued", status="queued",
                                    detail="Agent 研究任务已排队，等待真实 LLM 执行。")
    workbench_service._save_task(task)
    workbench_service.TASK_EXECUTOR.submit(_execute_agent_research_task, task["id"])
    return task


def get_agent_task(task_id: str) -> dict[str, Any]:
    """Return the browser-safe public view of one agent-research task."""
    task = workbench_service.get_task(task_id)
    if task.get("kind") != "agent_research":
        raise KeyError(f"Unknown agent_research task_id: {task_id}")
    return _public_agent_task(task)


def agent_task_events(task_id: str) -> dict[str, Any]:
    """Return the structured, credential-free event stream for a task.

    Workbench status transitions are persisted in ``trace`` while in-flight
    agent events land in ``events``; both are normalised and merged into one
    chronological stream so the UI can render a single timeline.
    """
    task = workbench_service.get_task(task_id)
    if task.get("kind") != "agent_research":
        raise KeyError(f"Unknown agent_research task_id: {task_id}")
    trace_events = [
        {
            "timestamp": entry.get("at"),
            "event": entry.get("event"),
            "status": entry.get("status"),
            "detail": entry.get("detail", ""),
            "metadata": {"evidence_ids": entry.get("evidence_ids") or []},
        }
        for entry in task.get("trace", []) or []
    ]
    rich_events = task.get("events", []) or []
    timeline = sorted(
        [*trace_events, *rich_events],
        key=lambda event: str(event.get("timestamp") or ""),
    )
    return {
        "task_id": task_id,
        "status": task.get("status"),
        "events": timeline,
        "tool_trace": list(task.get("research_state", {}).get("tool_trace", []) or []),
    }


def _public_agent_task(task: dict[str, Any]) -> dict[str, Any]:
    """Strip server internals and bound error text from a task before showing it."""
    public = {key: value for key, value in task.items()
              if key not in {"report_path", "metadata_path", "snapshot_path", "probe_dir"}}
    error = public.get("error")
    if error:
        public["error"] = str(error)[-1000:]
    usage = public.get("usage") or {}
    if isinstance(usage, dict):
        for key in ("cost_usd", "latency_seconds", "llm_calls", "tool_calls"):
            usage.setdefault(key, None)
    public.setdefault("usage", usage)
    return public


# ---------------------------------------------------------------------------
# Worker (runs on the shared bounded executor)
# ---------------------------------------------------------------------------

def _execute_agent_research_task(task_id: str) -> None:
    with workbench_service.TASK_LOCK:
        task = workbench_service.get_task(task_id)
        if task.get("status") != "queued":
            return
        workbench_service._transition(task, "running", step="agent_started",
                                      message="正在进行真实 LLM Agent 分析。")
    try:
        asyncio.run(_run_agent_research(task_id))
    except Exception as exc:  # noqa: BLE001 — persist a safe, observable failure
        with workbench_service.TASK_LOCK:
            task = workbench_service.get_task(task_id)
            task["error_type"] = type(exc).__name__
            task["error"] = f"{type(exc).__name__}: {exc}"
            task["progress_percent"] = 100
            _append_event(task, "task_failed", status="error",
                          detail="Agent 执行异常终止；原始异常不会在 API 中回显。")
            workbench_service._transition(task, "failed", step="task_failed",
                                          message="Agent 执行异常终止；可在解决后重试。")


async def _run_agent_research(task_id: str) -> None:
    task = workbench_service.get_task(task_id)
    snapshot_path = _snapshot_path_for(task["snapshot_id"])
    research_as_of = task.get("research_as_of")

    agent = CnResearchAgent(
        snapshot_path=snapshot_path,
        model_name=task["model_name"],
        temperature=float(task.get("temperature", 0.0)),
        max_steps=int(task.get("max_steps", 6)),
        required_metrics=task.get("required_metrics", []) or [],
    )

    started = time.perf_counter()

    def emit(event: dict[str, Any]) -> None:
        if event.get("event") == "task_completed":
            return  # terminal transition is persisted by the caller with the results
        with workbench_service.TASK_LOCK:
            current = workbench_service.get_task(task_id)
            _append_event(current, event["event"], status=event.get("status", "ok"),
                          detail=event.get("detail", ""), metadata=event.get("metadata", {}))
            current["current_step"] = event["event"]
            current["updated_at"] = _now()
            workbench_service._save_task(current)

    def cancellation_requested() -> bool:
        try:
            return bool(workbench_service.get_task(task_id).get("cancellation_requested"))
        except KeyError:
            return False

    state = await agent.run(
        task["query"], research_as_of=research_as_of,
        event_handler=emit, cancellation_check=cancellation_requested,
    )

    latency = time.perf_counter() - started
    validation = dict(state.validation_result or {})
    requested_cancel = bool(workbench_service.get_task(task_id).get("cancellation_requested"))

    if requested_cancel:
        status, step, message = "cancelled", "task_cancelled", "Agent 已被取消。"
    elif validation.get("valid"):
        status, step, message = "succeeded", "task_completed", "Agent 结论已通过 Validator。"
    else:
        status, step, message = "blocked", "validation_blocked", "Validator 未通过；结论已阻断。"

    with workbench_service.TASK_LOCK:
        current = workbench_service.get_task(task_id)
        current["research_state"] = state.to_dict()
        current["answer"] = agent.answer or state.report
        current["validation"] = validation
        current["usage"] = {
            "llm_calls": agent.llm_calls,
            "tool_calls": len(state.tool_trace),
            "cost_usd": round(agent.total_cost, 6),
            "latency_seconds": round(latency, 3),
        }
        current["progress_percent"] = 100
        _append_event(current, step, status=status,
                      detail=message, metadata={"status": status})
        workbench_service._transition(current, status, step=step, message=message)


def _append_event(task: dict[str, Any], event: str, *, status: str = "ok",
                  detail: str = "", metadata: dict[str, Any] | None = None,
                  evidence_count: int | None = None) -> None:
    payload = {"timestamp": _now(), "event": event, "status": status,
               "detail": detail, "metadata": metadata or {}}
    task.setdefault("events", []).append(payload)


def agent_research_snapshots() -> list[dict[str, str]]:
    """Return reseachable snapshots for the workbench form (reuses workbench listings)."""
    return workbench_service.list_research()