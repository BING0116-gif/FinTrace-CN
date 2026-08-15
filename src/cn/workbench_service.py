"""Read-only query service for versioned FinTrace-CN research snapshots.

This module deliberately exposes stored facts and deterministic calculations;
it never calls a live provider and never manufactures missing peer valuation.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from .domain import FinancialStatement
from .industries import get_industry_code, is_financial_institution
from .peer_workflow import PeerCandidate, result_to_dict, value_with_peers
from .periods import FinancialPeriodEngine
from .providers.snapshot import SnapshotProvider
from .report import CnResearchReportBuilder
from .symbols import normalize_cn_symbol
from .valuation import PeerValuationInput, calculate_multiple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots" / "cn"
OUTPUT_DIR = PROJECT_ROOT / "output"
EVALUATION_DIR = OUTPUT_DIR
TASK_DIR = OUTPUT_DIR / "workbench_tasks"
PROBE_SCRIPT = PROJECT_ROOT / "scripts" / "probe_tushare_cn0.py"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_cn_snapshot_from_probe.py"
TASK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fintrace-task")
TASK_LOCK = Lock()
ACTIVE_TASK_STATUSES = {"queued", "running"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=64)
def load_snapshot(snapshot_id: str) -> dict[str, Any]:
    for path in SNAPSHOT_DIR.glob("*.json"):
        payload = _read_json(path)
        if payload.get("snapshot_id") == snapshot_id:
            return payload
    raise KeyError(f"Unknown snapshot_id: {snapshot_id}")


def _snapshot_path(snapshot_id: str) -> Path:
    for path in SNAPSHOT_DIR.glob("*.json"):
        if _read_json(path).get("snapshot_id") == snapshot_id:
            return path
    raise KeyError(f"Unknown snapshot_id: {snapshot_id}")


def _ledger_validation(payload: dict[str, Any]):
    return CnResearchReportBuilder(SnapshotProvider(_snapshot_path(payload["snapshot_id"]))).build(
        normalize_cn_symbol(payload["symbol"]), research_as_of=payload["research_as_of"]
    ).validation


def list_research() -> list[dict[str, str]]:
    items = []
    for path in sorted(SNAPSHOT_DIR.glob("*.json")):
        payload = _read_json(path)
        profile = payload.get("data", {}).get("profile", {})
        items.append({
            "id": payload["snapshot_id"], "symbol": payload["symbol"],
            "name": profile.get("name", payload["symbol"]),
            "industry": profile.get("industry_name", "未覆盖"),
            "research_as_of": payload["research_as_of"],
        })
    return items


def find_snapshot_for_symbol(symbol_text: str) -> dict[str, str] | None:
    """Return the newest local snapshot for one canonical symbol, if any."""
    symbol = str(normalize_cn_symbol(symbol_text))
    matches = [item for item in list_research() if item["symbol"] == symbol]
    return max(matches, key=lambda item: item["research_as_of"], default=None)


def _task_path(task_id: str) -> Path:
    return TASK_DIR / f"{task_id}.json"


def _save_task(task: dict[str, Any]) -> dict[str, Any]:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    _task_path(task["id"]).write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return task


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_event(task: dict[str, Any], event: str, *, status: str, detail: str,
                  evidence_ids: list[str] | None = None) -> None:
    """Append a safe, persisted task event; credentials are never serialized."""
    task.setdefault("trace", []).append({"at": _now(), "event": event, "status": status,
                                          "detail": detail, "evidence_ids": evidence_ids or []})


def _transition(task: dict[str, Any], status: str, *, step: str, message: str,
                evidence_ids: list[str] | None = None) -> dict[str, Any]:
    task.update({"status": status, "current_step": step, "message": message, "updated_at": _now()})
    _record_event(task, step, status=status, detail=message, evidence_ids=evidence_ids)
    return _save_task(task)


def _new_task(symbol: str, kind: str) -> dict[str, Any]:
    created_at = _now()
    return {
        "id": f"{kind}_{symbol.replace('.', '_')}_{uuid4().hex[:12]}",
        "symbol": symbol, "kind": kind, "created_at": created_at, "updated_at": created_at,
        "retry_count": 0, "trace": [], "cost": None, "token_usage": None,
    }


def list_tasks() -> list[dict[str, Any]]:
    if not TASK_DIR.exists():
        return []
    return sorted((_read_json(path) for path in TASK_DIR.glob("*.json")), key=lambda item: item["created_at"], reverse=True)


def get_task(task_id: str) -> dict[str, Any]:
    """Return one persisted task without exposing unrecorded progress."""
    path = _task_path(task_id)
    if not path.exists():
        raise KeyError(f"Unknown task_id: {task_id}")
    return _read_json(path)


def get_task_progress(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    progress_by_status = {
        "queued": 0, "running": task.get("progress_percent", 0), "completed": 100,
        "succeeded": 100, "failed": 100, "blocked": 100, "needs_snapshot": 100, "cancelled": 100,
    }
    return {
        "task_id": task_id, "status": task.get("status", "unknown"),
        "progress_percent": progress_by_status.get(task.get("status")),
        "current_step": task.get("current_step"), "updated_at": task.get("updated_at"),
        "retry_count": task.get("retry_count"), "message": task.get("message"),
    }


def cancel_task(task_id: str) -> dict[str, Any]:
    """Cancel queued work immediately or request a safe stop between running steps."""
    with TASK_LOCK:
        task = get_task(task_id)
        status = task.get("status")
        if status == "queued":
            task["progress_percent"] = 100
            return _transition(task, "cancelled", step="cancelled", message="任务在执行前已取消。")
        if status != "running":
            raise ValueError("Only queued or running tasks can be cancelled.")
        task["cancellation_requested"] = True
        _record_event(task, "cancellation_requested", status="running",
                      detail="已请求在当前受控步骤结束后停止后续执行。")
        return _save_task(task)


def _cancellation_requested(task_id: str) -> bool:
    return bool(get_task(task_id).get("cancellation_requested"))


def task_diagnostics(task_id: str) -> dict[str, Any]:
    """Return a browser-safe, bounded diagnostic summary for one persisted task."""
    task = get_task(task_id)
    error = task.get("error")
    if error:
        error = str(error).replace(str(PROJECT_ROOT), "<project>")[-1000:]
    return {
        "task_id": task_id,
        "kind": task.get("kind"),
        "status": task.get("status"),
        "current_step": task.get("current_step"),
        "updated_at": task.get("updated_at"),
        "retry_count": task.get("retry_count", 0),
        "call_budget": task.get("call_budget"),
        "probe_calls": task.get("probe_calls"),
        "error_type": task.get("error_type"),
        "error_summary": error,
        "cancellation_requested": bool(task.get("cancellation_requested")),
        "trace": task.get("trace", [])[-20:],
    }


def _evaluation_files() -> dict[str, Path]:
    files: dict[str, Path] = {}
    for kind, filename in (("benchmark", "results.json"), ("ablation", "ablation.json"),
                           ("agent_ablation", "ablation_results.json")):
        directory = EVALUATION_DIR / kind
        if not directory.exists():
            continue
        for path in directory.rglob(filename):
            relative = path.relative_to(EVALUATION_DIR).as_posix()
            files[relative] = path
    return files


def list_evaluations() -> list[dict[str, Any]]:
    """Inventory measured local evaluation artifacts without fabricating absent scores."""
    items = []
    for evaluation_id, path in _evaluation_files().items():
        payload = _read_json(path)
        kind = evaluation_id.split("/", 1)[0]
        items.append({
            "id": evaluation_id, "kind": kind, "filename": path.name,
            "benchmark_version": payload.get("metadata", {}).get("benchmark_version"),
            "run_at": payload.get("metadata", {}).get("run_at"),
            "available": True,
        })
    return sorted(items, key=lambda item: (item["kind"], item["id"]), reverse=True)


def evaluation_detail(evaluation_id: str) -> dict[str, Any]:
    path = _evaluation_files().get(evaluation_id)
    if path is None:
        raise KeyError(f"Unknown evaluation artifact: {evaluation_id}")
    payload = _read_json(path)
    kind = evaluation_id.split("/", 1)[0]
    if kind == "ablation":
        return {
            "id": evaluation_id, "kind": kind, "metadata": payload.get("metadata", {}),
            "variants": payload.get("variants", []),
            "missing_variants": payload.get("missing_variants", []),
        }
    if kind == "agent_ablation":
        metrics = payload.get("metrics", {})
        return {
            "id": evaluation_id, "kind": "ablation", "metadata": {
                "benchmark_version": payload.get("benchmark_version"), "model": payload.get("model"),
                "dry_run": payload.get("dry_run"), "run_at": payload.get("run_at"),
            },
            "variants": [{"variant": name, **values} for name, values in metrics.items()],
            "missing_variants": [name for name in (
                "direct_llm", "agent_tools", "agent_tools_evidence", "agent_tools_evidence_validator"
            ) if name not in metrics],
            "detailed_results": payload.get("detailed_results", {}),
        }
    return {
        "id": evaluation_id, "kind": kind, "metadata": payload.get("metadata", {}),
        "summary": payload.get("summary", {}), "regression": payload.get("regression"),
        "results": payload.get("results", []),
    }


def _active_task(kind: str, symbol: str, snapshot_id: str | None) -> dict[str, Any] | None:
    for task in list_tasks():
        if (task.get("kind") == kind and task.get("symbol") == symbol
                and task.get("snapshot_id") == snapshot_id
                and task.get("status") in ACTIVE_TASK_STATUSES):
            return task
    return None


def _execute_research_task(task_id: str) -> None:
    """Generate a report from one persisted snapshot in a bounded worker."""
    with TASK_LOCK:
        task = get_task(task_id)
        if task.get("status") != "queued":
            return
        _transition(task, "running", step="load_snapshot", message="正在加载版本化快照。")
    try:
        payload = load_snapshot(task["snapshot_id"])
        with TASK_LOCK:
            task = get_task(task_id)
            task["progress_percent"] = 35
            _transition(task, "running", step="build_report", message="正在执行确定性计算并生成报告。")
        report = CnResearchReportBuilder(SnapshotProvider(_snapshot_path(task["snapshot_id"]))).build(
            normalize_cn_symbol(task["symbol"]), research_as_of=payload["research_as_of"]
        )
        if _cancellation_requested(task_id):
            with TASK_LOCK:
                task = get_task(task_id)
                task["progress_percent"] = 100
                _transition(task, "cancelled", step="cancelled", message="任务已在当前计算步骤后停止。")
            return
        report_path = OUTPUT_DIR / f"{task['symbol']}_research_report.md"
        report_path.write_text(report.markdown, encoding="utf-8")
        metadata = research_summary(task["snapshot_id"])
        metadata.update({"validation": {"valid": report.validation.valid, "errors": report.validation.errors,
                                         "ledger_valid": report.validation.valid}, "report_path": str(report_path)})
        metadata_path = OUTPUT_DIR / f"{task['symbol']}_cn_report.metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        evidence_ids = [value for value in metadata.get("evidence_ids", {}).values() if value]
        with TASK_LOCK:
            task = get_task(task_id)
            task.update({"progress_percent": 100, "report_path": str(report_path),
                         "metadata_path": str(metadata_path), "validation": metadata["validation"]})
            _transition(task, "succeeded" if report.validation.valid else "blocked", step="validator",
                        evidence_ids=evidence_ids,
                        message="研究报告已生成，校验通过。" if report.validation.valid else "校验未通过，研究结论已阻断。")
    except Exception as exc:
        with TASK_LOCK:
            task = get_task(task_id)
            task.update({"progress_percent": 100, "error_type": type(exc).__name__, "error": str(exc)})
            _transition(task, "failed", step="failed", message="研究任务失败；可在修复原因后安全重跑。")


def _submit_research_task(task: dict[str, Any]) -> None:
    TASK_EXECUTOR.submit(_execute_research_task, task["id"])


def start_research(symbol_text: str) -> dict[str, Any]:
    """Queue a snapshot-backed task; never make provider calls or invent facts."""
    symbol = str(normalize_cn_symbol(symbol_text))
    existing = find_snapshot_for_symbol(symbol)
    if not existing:
        task = _new_task(symbol, "offline_research")
        task.update({"status": "needs_snapshot", "current_step": "preflight",
                     "message": "未找到本地版本化快照；未生成研究结论。",
                     "next_step": "Create a controlled snapshot, then submit research again."})
        _record_event(task, "preflight", status="needs_snapshot", detail=task["message"])
        return _save_task(task)
    with TASK_LOCK:
        duplicate = _active_task("offline_research", symbol, existing["id"])
        if duplicate:
            return {**duplicate, "idempotent_reuse": True}
        task = _new_task(symbol, "offline_research")
        task.update({"snapshot_id": existing["id"], "status": "queued", "progress_percent": 0,
                     "trace_id": f"trace_{uuid4().hex[:12]}",
                     "idempotency_key": f"offline_research:{existing['id']}"})
        _record_event(task, "queued", status="queued", detail="任务已排队，等待受控离线研究执行。")
        _save_task(task)
    _submit_research_task(task)
    return task


def rerun_task(task_id: str) -> dict[str, Any]:
    """Safely retry a failed or blocked snapshot-backed research task."""
    previous = get_task(task_id)
    if previous.get("kind") == "snapshot_acquisition" and previous.get("status") in {"failed", "blocked"}:
        return collect_snapshot(
            previous["symbol"], start_date=previous["start_date"], end_date=previous["end_date"],
            retry_of=task_id, retry_count=previous.get("retry_count", 0) + 1,
        )
    if previous.get("kind") != "offline_research" or previous.get("status") not in {"failed", "blocked"}:
        raise ValueError("Only failed or blocked offline research or snapshot tasks can be rerun.")
    snapshot_id = previous.get("snapshot_id")
    if not snapshot_id:
        raise ValueError("The task has no versioned snapshot and cannot be rerun safely.")
    with TASK_LOCK:
        duplicate = _active_task("offline_research", previous["symbol"], snapshot_id)
        if duplicate:
            return {**duplicate, "idempotent_reuse": True}
        task = _new_task(previous["symbol"], "offline_research")
        task.update({"snapshot_id": snapshot_id, "status": "queued", "progress_percent": 0,
                     "retry_of": task_id, "retry_count": previous.get("retry_count", 0) + 1,
                     "trace_id": f"trace_{uuid4().hex[:12]}",
                     "idempotency_key": f"offline_research:{snapshot_id}"})
        _record_event(task, "queued", status="queued", detail=f"从任务 {task_id} 安全重跑。")
        _save_task(task)
    _submit_research_task(task)
    return task


def _start_research_sync_legacy(symbol_text: str) -> dict[str, Any]:
    """Create an auditable task from a local snapshot, without provider calls.

    An absent snapshot becomes a `needs_snapshot` task rather than a fabricated
    report.  The caller can show its deterministic acquisition instructions.
    """
    symbol = str(normalize_cn_symbol(symbol_text))
    existing = find_snapshot_for_symbol(symbol)
    task = _new_task(symbol, "offline_research")
    if not existing:
        task.update({
            "status": "needs_snapshot",
            "message": "未找到本地版本化快照；未生成研究结论。请先通过受控数据采集流程创建快照。",
            "next_step": "probe_tushare_cn0.py -> build_cn_snapshot_from_probe.py -> POST /api/research",
        })
        return _save_task(task)

    task.update({"status": "running", "snapshot_id": existing["id"], "message": "正在从本地快照生成受控研究报告。"})
    _save_task(task)
    try:
        payload = load_snapshot(existing["id"])
        provider = SnapshotProvider(next(path for path in SNAPSHOT_DIR.glob("*.json") if _read_json(path).get("snapshot_id") == existing["id"]))
        report = CnResearchReportBuilder(provider).build(normalize_cn_symbol(symbol), research_as_of=payload["research_as_of"])
        report_path = OUTPUT_DIR / f"{symbol}_research_report.md"
        report_path.write_text(report.markdown, encoding="utf-8")
        metadata = research_summary(existing["id"])
        metadata.update({"validation": {"valid": report.validation.valid, "errors": report.validation.errors, "ledger_valid": report.validation.valid}, "report_path": str(report_path)})
        metadata_path = OUTPUT_DIR / f"{symbol}_cn_report.metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        task.update({"status": "completed" if report.validation.valid else "blocked", "updated_at": datetime.now(timezone.utc).isoformat(), "message": "研究报告已生成。" if report.validation.valid else "校验未通过，研究结论已阻断。", "report_path": str(report_path), "metadata_path": str(metadata_path), "validation": metadata["validation"]})
    except Exception as exc:  # Task state must make failures visible instead of masking them.
        task.update({"status": "failed", "updated_at": datetime.now(timezone.utc).isoformat(), "message": "研究任务失败。", "error_type": type(exc).__name__, "error": str(exc)})
    return _save_task(task)


def _collect_snapshot_sync_legacy(symbol_text: str, *, start_date: str, end_date: str,
                                  runner=subprocess.run, task: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the bounded server-side Tushare acquisition and normalize its output.

    The token is only read by the probe script from the project `.env`; it is
    never returned, logged, or accepted by this API.  Probe failures terminate
    immediately before normalization, preserving the raw diagnostic directory.
    """
    symbol = str(normalize_cn_symbol(symbol_text))
    if not (len(start_date) == len(end_date) == 8 and start_date.isdigit() and end_date.isdigit() and start_date <= end_date):
        raise ValueError("start_date/end_date must be YYYYMMDD and start_date must not exceed end_date.")
    task = task or _new_task(symbol, "snapshot_acquisition")
    task.update({"status": "running", "message": "正在运行受限 Tushare 采集（最多 6 次调用，首次失败即停止）。", "call_budget": 6, "retry_policy": "no_retry_stop_on_first_failure", "start_date": start_date, "end_date": end_date})
    _save_task(task)
    # Do not inspect or serialize the token. Checking presence only avoids a
    # network attempt that is guaranteed to fail and provides an actionable state.
    env_path = PROJECT_ROOT / ".env"
    token_configured = any(
        line.strip().startswith("TUSHARE_TOKEN=") and bool(line.split("=", 1)[1].strip())
        for line in env_path.read_text(encoding="utf-8").splitlines()
    ) if env_path.exists() else False
    if not token_configured:
        task.update({"status": "blocked", "updated_at": datetime.now(timezone.utc).isoformat(), "message": "未配置 TUSHARE_TOKEN；采集未启动。请仅在服务器 .env 中配置 Token。"})
        return _save_task(task)
    before = {path.resolve() for path in (PROJECT_ROOT / "data" / "provider_probes" / "cn0").glob(f"{symbol}_*")}
    try:
        probe = runner([sys.executable, str(PROBE_SCRIPT), "--symbol", symbol, "--start-date", start_date, "--end-date", end_date], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120)
        after = {path.resolve() for path in (PROJECT_ROOT / "data" / "provider_probes" / "cn0").glob(f"{symbol}_*")}
        probe_dirs = sorted(after - before, key=lambda path: path.name)
        probe_dir = probe_dirs[-1] if probe_dirs else None
        task["probe_returncode"] = probe.returncode
        task["probe_dir"] = str(probe_dir) if probe_dir else None
        if probe.returncode != 0 or probe_dir is None:
            task.update({"status": "failed", "updated_at": datetime.now(timezone.utc).isoformat(), "message": "采集失败，未生成快照；请查看本地诊断工件。", "error": (probe.stderr or probe.stdout)[-1000:]})
            return _save_task(task)
        research_as_of = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}T23:00:00+08:00"
        output = SNAPSHOT_DIR / f"{symbol}_{end_date}_tushare_v1.json"
        build = runner([sys.executable, str(BUILD_SCRIPT), str(probe_dir), "--output", str(output), "--research-as-of", research_as_of], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120)
        if build.returncode != 0 or not output.exists():
            task.update({"status": "failed", "updated_at": datetime.now(timezone.utc).isoformat(), "message": "原始数据已保留，但标准化快照失败。", "error": (build.stderr or build.stdout)[-1000:]})
            return _save_task(task)
        load_snapshot.cache_clear()
        task.update({"status": "completed", "updated_at": datetime.now(timezone.utc).isoformat(), "message": "快照已创建，可发起离线研究。", "snapshot_path": str(output), "snapshot_id": _read_json(output)["snapshot_id"], "probe_calls": 6})
    except subprocess.TimeoutExpired:
        task.update({"status": "failed", "updated_at": datetime.now(timezone.utc).isoformat(), "message": "采集超时，已停止。", "error_type": "TimeoutExpired"})
    except Exception as exc:
        task.update({"status": "failed", "updated_at": datetime.now(timezone.utc).isoformat(), "message": "采集任务异常终止。", "error_type": type(exc).__name__, "error": str(exc)})
    return _save_task(task)


def _execute_snapshot_task(task_id: str, runner=subprocess.run) -> None:
    """Run bounded acquisition off the request thread and persist its terminal state."""
    with TASK_LOCK:
        task = get_task(task_id)
        if task.get("status") != "queued":
            return
        task["progress_percent"] = 5
        _transition(task, "running", step="preflight", message="正在进行采集前检查。")
    result = _collect_snapshot_sync_legacy(
        task["symbol"], start_date=task["start_date"], end_date=task["end_date"],
        runner=runner, task=task,
    )
    with TASK_LOCK:
        task = get_task(task_id)
        if task.get("cancellation_requested"):
            task["progress_percent"] = 100
            _transition(task, "cancelled", step="cancelled", message="当前采集步骤已结束，后续步骤已停止。")
            return
        final_status = {"completed": "succeeded", "succeeded": "succeeded", "blocked": "blocked"}.get(
            result.get("status"), "failed"
        )
        task["progress_percent"] = 100
        _transition(
            task, final_status, step="complete" if final_status == "succeeded" else final_status,
            message=("快照已创建，可发起离线研究。" if final_status == "succeeded"
                     else result.get("message", "快照采集未完成。")),
        )


def _submit_snapshot_task(task: dict[str, Any], runner=subprocess.run) -> None:
    TASK_EXECUTOR.submit(_execute_snapshot_task, task["id"], runner)


def collect_snapshot(symbol_text: str, *, start_date: str, end_date: str, runner=subprocess.run,
                     retry_of: str | None = None, retry_count: int = 0) -> dict[str, Any]:
    """Queue bounded server-side collection; credentials never enter the task payload."""
    symbol = str(normalize_cn_symbol(symbol_text))
    if not (len(start_date) == len(end_date) == 8 and start_date.isdigit() and end_date.isdigit() and start_date <= end_date):
        raise ValueError("start_date/end_date must be YYYYMMDD and start_date must not exceed end_date.")
    with TASK_LOCK:
        duplicate = _active_task("snapshot_acquisition", symbol, None)
        if duplicate and duplicate.get("start_date") == start_date and duplicate.get("end_date") == end_date:
            return {**duplicate, "idempotent_reuse": True}
        task = _new_task(symbol, "snapshot_acquisition")
        task.update({"status": "queued", "progress_percent": 0, "start_date": start_date,
                     "end_date": end_date, "call_budget": 6,
                     "retry_policy": "no_retry_stop_on_first_failure",
                     "retry_of": retry_of, "retry_count": retry_count,
                     "idempotency_key": f"snapshot_acquisition:{symbol}:{start_date}:{end_date}"})
        _record_event(task, "queued", status="queued", detail="快照采集任务已排队。")
        _save_task(task)
    _submit_snapshot_task(task, runner)
    return task


def _latest_value(statements: list[dict[str, Any]], metric: str) -> float | None:
    ranked = [(item["fiscal_period"], item["values"].get(metric)) for item in statements if item["values"].get(metric) is not None]
    return max(ranked, default=("", None))[1]


def _latest_statement_value(statements: list[dict[str, Any]], statement_type: str, metric: str) -> float | None:
    """Return a balance-sheet fact from the latest available reporting period."""
    ranked = [
        (item.get("fiscal_period", ""), item.get("values", {}).get(metric))
        for item in statements
        if item.get("statement_type") == statement_type and item.get("values", {}).get(metric) is not None
    ]
    return max(ranked, default=("", None))[1]


def _ttm_value(statements: list[dict[str, Any]], metric: str) -> float | None:
    ttm = FinancialPeriodEngine.derive_ttm([FinancialStatement(**item) for item in statements], "income")
    latest = max(ttm, key=lambda item: item.fiscal_period, default=None)
    return latest.values.get(metric) if latest else None


def _latest_fact_period(statements: list[dict[str, Any]], statement_type: str, metric: str) -> str | None:
    periods = [
        item.get("fiscal_period") for item in statements
        if item.get("statement_type") == statement_type and item.get("values", {}).get(metric) is not None
    ]
    return max(periods, default=None)


def _peer_candidate(payload: dict[str, Any], cutoff: str) -> PeerCandidate | None:
    """Create a peer candidate from local snapshot facts only."""
    symbol = payload["symbol"]
    code = symbol.split(".")[0]
    industry_code = get_industry_code(code)
    if industry_code is None:
        return None
    statements = payload["data"].get("statements", [])
    bars = [bar for bar in payload["data"].get("bars", []) if bar.get("adjustment") == "RAW" and bar["trade_date"] <= cutoff[:10]]
    latest_bar = max(bars, key=lambda item: item["trade_date"], default=None)
    if latest_bar is None:
        return None
    shares = _latest_statement_value(statements, "balance", "total_shares")
    profit = _ttm_value(statements, "net_profit")
    equity = _latest_statement_value(statements, "balance", "equity")
    revenue = _ttm_value(statements, "revenue")
    symbol_key = symbol.replace(".", "_")
    ttm = FinancialPeriodEngine.derive_ttm([FinancialStatement(**item) for item in statements], "income")
    latest_ttm = max(ttm, key=lambda item: item.fiscal_period, default=None)
    evidence_ids = {"price": f"fact_{symbol_key}_close_{latest_bar['trade_date']}_RAW"}
    shares_period = _latest_fact_period(statements, "balance", "total_shares")
    equity_period = _latest_fact_period(statements, "balance", "equity")
    if shares is not None and shares_period:
        evidence_ids["shares"] = f"fact_{symbol_key}_total_shares_{shares_period}"
    if equity is not None and equity_period:
        evidence_ids["equity"] = f"fact_{symbol_key}_equity_{equity_period}"
    if latest_ttm:
        for key, metric, value in (("profit", "net_profit", profit), ("revenue", "revenue", revenue)):
            if value is None:
                continue
            evidence_ids[key] = (
                f"fact_{symbol_key}_{metric}_{latest_ttm.source_periods[0]}"
                if len(latest_ttm.source_periods) == 1 else f"calc_ttm_{metric}_{latest_ttm.fiscal_period}"
            )
    return PeerCandidate(
        valuation=PeerValuationInput(symbol, latest_bar["close"], shares or 0.0, profit, equity, revenue, "TTM_SNAPSHOT_AS_OF"),
        industry_code=industry_code,
        evidence_ids=evidence_ids,
        is_bank_or_insurer=is_financial_institution(code),
    )


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload["data"]
    bars = [bar for bar in data.get("bars", []) if bar.get("adjustment") == "RAW" and bar["trade_date"] <= payload["research_as_of"][:10]]
    latest = max(bars, key=lambda item: item["trade_date"]) if bars else None
    statements = data.get("statements", [])
    ttm = FinancialPeriodEngine.derive_ttm(
        [FinancialStatement(**item) for item in statements], "income"
    )
    latest_ttm = max(ttm, key=lambda item: item.fiscal_period, default=None)
    shares = _latest_value(statements, "total_shares")
    price = latest["close"] if latest else None
    market_cap = price * shares if price is not None and shares is not None else None
    ttm_profit = latest_ttm.values.get("net_profit") if latest_ttm else None
    ttm_revenue = latest_ttm.values.get("revenue") if latest_ttm else None
    pe_ttm = market_cap / ttm_profit if market_cap is not None and ttm_profit is not None and ttm_profit > 0 else None
    book_equity = _latest_value(statements, "equity")
    ledger_validation = _ledger_validation(payload)
    return {
        "snapshot_id": payload["snapshot_id"], "symbol": payload["symbol"], "profile": data.get("profile", {}),
        "research_as_of": payload["research_as_of"], "provider": payload.get("provider", "snapshot"),
        "validation": {
            "valid": ledger_validation.valid, "errors": ledger_validation.errors,
            "ledger_valid": ledger_validation.valid, "source": "evidence_ledger",
        },
        "key_metrics": {
            "price": price, "total_shares": shares, "market_cap": market_cap,
            "ttm_net_profit": ttm_profit, "ttm_revenue": ttm_revenue,
            "book_equity": book_equity, "pe_ttm": pe_ttm,
        },
        "evidence_ids": {
            "price": f"fact_{payload['symbol'].replace('.', '_')}_close_{latest['trade_date']}_RAW" if latest else None,
            "market_cap": "calc_market_cap" if market_cap is not None else None,
            "ttm_net_profit": (
                f"fact_{payload['symbol'].replace('.', '_')}_net_profit_{latest_ttm.source_periods[0]}"
                if latest_ttm and len(latest_ttm.source_periods) == 1
                else f"calc_ttm_net_profit_{latest_ttm.fiscal_period}" if latest_ttm else None
            ),
            "pe_ttm": "calc_pe_ttm" if market_cap is not None and ttm_profit is not None and ttm_profit > 0 else None,
        },
    }


def research_summary(snapshot_id: str) -> dict[str, Any]:
    return _summary(load_snapshot(snapshot_id))


def research_market(snapshot_id: str, adjustment: str = "RAW") -> dict[str, Any]:
    if adjustment not in {"RAW", "QFQ", "HFQ"}:
        raise ValueError(f"Unsupported adjustment: {adjustment}")
    payload = load_snapshot(snapshot_id)
    cutoff = payload["research_as_of"][:10]
    symbol_key = payload["symbol"].replace(".", "_")
    bars = []
    for raw in payload["data"].get("bars", []):
        if adjustment != raw.get("adjustment", "RAW") or raw.get("trade_date", "") > cutoff:
            continue
        bar = dict(raw)
        bar.update({
            "evidence_id": f"fact_{symbol_key}_close_{raw['trade_date']}_{adjustment}",
            "price_basis": adjustment,
            "provider": payload.get("provider", "snapshot"),
            "published_at": f"{raw['trade_date']}T15:00:00+08:00",
            "field_path": f"bars.{raw['trade_date']}.close",
        })
        bars.append(bar)
    available_adjustments = sorted({
        item.get("adjustment", "RAW") for item in payload["data"].get("bars", [])
        if item.get("trade_date", "") <= cutoff
    })
    latest_raw = max(
        (item for item in bars if item.get("trade_date") <= cutoff),
        key=lambda item: item["trade_date"],
        default=None,
    )
    profile = payload["data"].get("profile", {})
    security_name = str(profile.get("name", ""))
    security_flags = {
        "exchange": snapshot_id.split("_")[0].split(".")[-1] if "." in snapshot_id else None,
        "beijing_exchange": payload.get("symbol", "").endswith(".BJ"),
        "special_treatment_name_flag": "ST" in security_name.upper(),
        "latest_trading_status": latest_raw.get("trading_status") if latest_raw else None,
        "latest_trade_date": latest_raw.get("trade_date") if latest_raw else None,
    }
    return {
        "snapshot_id": snapshot_id, "research_as_of": payload["research_as_of"],
        "provider": payload.get("provider", "snapshot"), "adjustment": adjustment, "bars": bars,
        "adjustment_coverage": {basis: basis in available_adjustments for basis in ("RAW", "QFQ", "HFQ")},
        "currency": payload["data"].get("profile", {}).get("currency", "CNY"),
        "unit": "CNY/share", "volume_unit": "lot",
        "security_flags": security_flags,
    }


def research_financials(snapshot_id: str) -> dict[str, Any]:
    payload = load_snapshot(snapshot_id)
    cutoff = payload["research_as_of"]
    symbol_key = payload["symbol"].replace(".", "_")
    statements, issues = [], []
    for raw in payload["data"].get("statements", []):
        statement = dict(raw)
        published_at = statement.get("published_at")
        is_future = bool(published_at and published_at > cutoff)
        values = statement.get("values") if isinstance(statement.get("values"), dict) else {}
        evidence_ids = {
            metric: f"fact_{symbol_key}_{metric}_{statement['fiscal_period']}"
            for metric, value in values.items() if value is not None
        }
        if values.get("revenue") not in (None, 0) and values.get("net_profit") is not None:
            evidence_ids["net_margin"] = f"calc_net_margin_{statement['fiscal_period']}"
        statement.update({"evidence_ids": evidence_ids, "available_as_of": not is_future})
        statements.append(statement)
        if is_future:
            issues.append({"code": "future_disclosure", "status": "blocked", "period": statement["fiscal_period"], "published_at": published_at})
        for metric, value in values.items():
            if value is None:
                issues.append({"code": "missing_value", "status": "warning", "period": statement["fiscal_period"], "metric": metric})
    return {
        "snapshot_id": snapshot_id, "research_as_of": cutoff,
        "currency": payload["data"].get("profile", {}).get("currency", "CNY"),
        "provider": payload.get("provider", "snapshot"), "statements": statements, "issues": issues,
    }


def research_financial_trends(snapshot_id: str, period_basis: str = "FY") -> dict[str, Any]:
    """Return presentation-ready financial points without UI-side calculations."""
    if period_basis not in {"FY", "Q1", "H1", "9M", "TTM"}:
        raise ValueError(f"Unsupported period_basis: {period_basis}")
    payload = load_snapshot(snapshot_id)
    financials = research_financials(snapshot_id)
    symbol_key = payload["symbol"].replace(".", "_")
    eligible = [
        item for item in financials["statements"]
        if item["available_as_of"] and item.get("statement_type") == "income"
    ]
    published = {item["fiscal_period"]: item.get("published_at") for item in eligible}
    points = []
    if period_basis == "TTM":
        derived = FinancialPeriodEngine.derive_ttm([FinancialStatement(**{
            key: value for key, value in item.items() if key not in {"evidence_ids", "available_as_of"}
        }) for item in eligible], "income")
        source_rows = [(item.fiscal_period, item.values, item.source_periods) for item in derived]
    else:
        source_rows = [
            (item["fiscal_period"], item.get("values", {}), (item["fiscal_period"],))
            for item in eligible if item["fiscal_period"].endswith(period_basis)
        ]
    for fiscal_period, values, source_periods in source_rows:
        disclosure_times = [published.get(period) for period in source_periods if published.get(period)]
        source_ids = {
            metric: [f"fact_{symbol_key}_{metric}_{period}" for period in source_periods]
            for metric in ("revenue", "net_profit")
        }
        metric_ids = {}
        for metric in ("revenue", "net_profit"):
            if values.get(metric) is None:
                metric_ids[metric] = None
            elif period_basis != "TTM" or len(source_periods) == 1:
                metric_ids[metric] = source_ids[metric][0]
            else:
                metric_ids[metric] = f"calc_ttm_{metric}_{fiscal_period}"
        metric_ids["net_margin"] = (
            (f"calc_net_margin_{fiscal_period}" if period_basis != "TTM" else f"calc_net_margin_TTM_{fiscal_period}")
            if values.get("revenue") not in (None, 0) and values.get("net_profit") is not None else None
        )
        points.append({
            "fiscal_period": fiscal_period, "period_basis": period_basis,
            "published_at": max(disclosure_times, default=None),
            "revenue": values.get("revenue"), "net_profit": values.get("net_profit"),
            "net_margin": (
                values["net_profit"] / values["revenue"] * 100
                if values.get("revenue") not in (None, 0) and values.get("net_profit") is not None else None
            ),
            "evidence_ids": metric_ids, "source_evidence_ids": source_ids,
            "provider": payload.get("provider", "snapshot"),
        })
    return {
        "snapshot_id": snapshot_id, "research_as_of": payload["research_as_of"],
        "provider": payload.get("provider", "snapshot"), "currency": financials["currency"],
        "unit": {"revenue": "CNY", "net_profit": "CNY", "net_margin": "percent"},
        "period_basis": period_basis, "points": sorted(points, key=lambda item: item["fiscal_period"]),
        "issues": financials["issues"],
    }


def research_display_guardrails(snapshot_id: str) -> dict[str, Any]:
    """Return deterministic negative UI states; callers must not infer values."""
    financials = research_financials(snapshot_id)
    validation = research_validation(snapshot_id)
    missing = [issue for issue in financials["issues"] if issue["code"] == "missing_value"]
    future = [issue for issue in financials["issues"] if issue["code"] == "future_disclosure"]
    return {
        "missing_data": {"visible": bool(missing), "count": len(missing), "action": "show_unavailable"},
        "future_data": {"visible": bool(future), "count": len(future), "action": "exclude_from_charts"},
        "validation_block": {
            "visible": validation["status"] == "blocked",
            "conclusion_allowed": validation["conclusion_allowed"],
            "action": "hide_deterministic_conclusions" if not validation["conclusion_allowed"] else "allow",
        },
    }


def research_overview_insights(snapshot_id: str) -> dict[str, Any]:
    """Return deterministic overview deltas and a validator-gated status."""
    trends = research_financial_trends(snapshot_id, "FY")
    comparable = [
        point for point in trends["points"]
        if point["revenue"] is not None and point["net_profit"] is not None
    ][-2:]
    revenue_change = profit_change = None
    if len(comparable) == 2:
        previous, current = comparable
        if previous["revenue"] != 0:
            revenue_change = (current["revenue"] / previous["revenue"] - 1) * 100
        if previous["net_profit"] != 0:
            profit_change = (current["net_profit"] / previous["net_profit"] - 1) * 100
    if revenue_change is None or profit_change is None:
        performance_status = "insufficient_data"
    elif revenue_change > 0 and profit_change > 0:
        performance_status = "improving"
    elif revenue_change < 0 and profit_change < 0:
        performance_status = "under_pressure"
    else:
        performance_status = "diverging"
    validation = research_validation(snapshot_id)
    return {
        "snapshot_id": snapshot_id, "research_as_of": trends["research_as_of"],
        "provider": trends["provider"], "currency": trends["currency"], "period_basis": "FY",
        "latest_period": comparable[-1]["fiscal_period"] if comparable else None,
        "revenue_change_percent": revenue_change, "net_profit_change_percent": profit_change,
        "performance_status": performance_status,
        "validation_status": validation["status"], "conclusion_allowed": validation["conclusion_allowed"],
    }


def research_peer_valuation(snapshot_id: str) -> dict[str, Any]:
    """Value a snapshot against compatible local-snapshot peers, or explain why not.

    No live prices are fetched and no different-date snapshot is treated as a
    compatible peer.  A date gap of over three days is surfaced as exclusion.
    """
    target_payload = load_snapshot(snapshot_id)
    cutoff = target_payload["research_as_of"]
    target = _peer_candidate(target_payload, cutoff)
    if target is None:
        return {"snapshot_id": snapshot_id, "available": False, "reason": "target_snapshot_missing_peer_inputs"}
    candidates: list[PeerCandidate] = []
    candidate_context: dict[str, dict[str, Any]] = {}
    names = {target.valuation.symbol: target_payload["data"].get("profile", {}).get("name", target.valuation.symbol)}
    excluded_for_date = []
    target_date = cutoff[:10]
    for path in SNAPSHOT_DIR.glob("*.json"):
        payload = _read_json(path)
        if payload["snapshot_id"] == snapshot_id:
            continue
        date_gap = abs((datetime.fromisoformat(payload["research_as_of"][:10]).date() - datetime.fromisoformat(target_date).date()).days)
        if date_gap > 3:
            excluded_for_date.append(payload["symbol"])
            continue
        candidate = _peer_candidate(payload, cutoff)
        if candidate is not None:
            candidates.append(candidate)
            names[candidate.valuation.symbol] = payload["data"].get("profile", {}).get("name", candidate.valuation.symbol)
            candidate_context[candidate.valuation.symbol] = {
                "snapshot_id": payload["snapshot_id"], "research_as_of": payload["research_as_of"],
                "evidence_ids": candidate.evidence_ids,
            }
    result = value_with_peers(target, candidates)
    serialized = result_to_dict(result)
    selected = [item.symbol for item in result.decisions if item.included]
    target_multiples = {
        name: calculate_multiple(target.valuation, name).value for name in serialized["multiples"]
    }
    selected_candidates = {item.valuation.symbol: item for item in candidates if item.valuation.symbol in selected}
    denominator_key = {"PE": "profit", "PB": "equity", "PS": "revenue"}
    denominator_value = {"PE": target.valuation.net_profit, "PB": target.valuation.book_equity, "PS": target.valuation.revenue}
    distributions: dict[str, list[dict[str, Any]]] = {}
    valuation_ranges: dict[str, dict[str, float | None]] = {}
    formulas: dict[str, dict[str, Any]] = {}
    for name, multiple_result in serialized["multiples"].items():
        rows = []
        for symbol, candidate in selected_candidates.items():
            computed = calculate_multiple(candidate.valuation, name)
            reason = multiple_result.get("excluded", {}).get(symbol) or computed.exclusion_reason
            rows.append({
                "symbol": symbol, "name": names.get(symbol, symbol), "value": computed.value,
                "included": symbol in multiple_result.get("included_symbols", []),
                "exclusion_reason": reason, "iqr_outlier": reason == "iqr_outlier",
                "snapshot_id": candidate_context[symbol]["snapshot_id"],
                "research_as_of": candidate_context[symbol]["research_as_of"],
                "price_basis": "RAW", "period_basis": candidate.valuation.period_basis,
                "evidence_ids": candidate_context[symbol]["evidence_ids"],
            })
        distributions[name] = rows
        included_values = sorted(float(row["value"]) for row in rows if row["included"] and row["value"] is not None)
        def percentile(fraction: float) -> float | None:
            if not included_values:
                return None
            position = (len(included_values) - 1) * fraction
            lower, upper = math.floor(position), math.ceil(position)
            if lower == upper:
                return included_values[lower]
            return included_values[lower] + (included_values[upper] - included_values[lower]) * (position - lower)
        p25, p75 = percentile(0.25), percentile(0.75)
        denominator = denominator_value[name]
        low_price = p25 * denominator / target.valuation.total_shares if p25 is not None and denominator and target.valuation.total_shares > 0 else None
        high_price = p75 * denominator / target.valuation.total_shares if p75 is not None and denominator and target.valuation.total_shares > 0 else None
        valuation_ranges[name] = {"p25": p25, "median": multiple_result.get("median"), "p75": p75, "implied_price_low": low_price, "implied_price_median": multiple_result.get("implied_price"), "implied_price_high": high_price}
        input_key = denominator_key[name]
        formulas[name] = {
            "target_multiple": "market_cap / denominator",
            "implied_price": "peer_multiple * target_denominator / total_shares",
            "target_input_evidence_ids": [
                evidence_id for evidence_id in (
                    target.evidence_ids.get("price"), target.evidence_ids.get("shares"), target.evidence_ids.get(input_key)
                ) if evidence_id
            ],
            "peer_input_evidence_ids": sorted({
                evidence_id for row in rows if row["included"]
                for evidence_id in row["evidence_ids"].values()
            }),
        }
    return {
        "snapshot_id": snapshot_id,
        "available": bool(selected),
        "target_price": target.valuation.raw_price,
        "industry_code": target.industry_code,
        "peer_count": len(selected),
        "peer_names": {symbol: names.get(symbol, symbol) for symbol in selected},
        "date_excluded_symbols": excluded_for_date,
        "target_multiples": target_multiples,
        "period_basis": target.valuation.period_basis,
        "price_basis": "RAW",
        "method_boundary": "financial_institution_pe_pb_only" if target.is_bank_or_insurer else None,
        "distributions": distributions, "valuation_ranges": valuation_ranges, "formulas": formulas,
        "evidence_ids": sorted({
            evidence_id for formula in formulas.values()
            for evidence_id in formula["target_input_evidence_ids"] + formula["peer_input_evidence_ids"]
        }),
        **serialized,
    }


def research_valuation(snapshot_id: str) -> dict[str, Any]:
    """Return peer valuation with global Validator gating applied."""
    result = deepcopy(research_peer_valuation(snapshot_id))
    validation = research_validation(snapshot_id)
    result["validation_status"] = validation["status"]
    result["conclusion_allowed"] = validation["conclusion_allowed"]
    if not validation["conclusion_allowed"]:
        for multiple in result.get("multiples", {}).values():
            multiple["implied_price"] = None
        for interval in result.get("valuation_ranges", {}).values():
            interval["implied_price_low"] = None
            interval["implied_price_median"] = None
            interval["implied_price_high"] = None
        result["gated_reason"] = "validator_blocked"
    else:
        result["gated_reason"] = None
    return result


def research_readiness(snapshot_id: str) -> dict[str, Any]:
    """Return explicit data-quality gates for one read-only research snapshot."""
    payload = load_snapshot(snapshot_id)
    statements = payload["data"].get("statements", [])
    annual_income = [
        item for item in statements
        if item.get("statement_type") == "income" and str(item.get("fiscal_period", "")).endswith("FY")
    ]
    missing_annual_metrics = [
        item["fiscal_period"] for item in annual_income
        if item.get("values", {}).get("revenue") is None or item.get("values", {}).get("net_profit") is None
    ]
    key_metrics = research_summary(snapshot_id)["key_metrics"]
    missing_key_metrics = [name for name, value in key_metrics.items() if name in {"price", "total_shares", "ttm_net_profit", "ttm_revenue", "book_equity"} and value is None]
    peer = research_peer_valuation(snapshot_id)
    cutoff_date = datetime.fromisoformat(payload["research_as_of"][:10]).date()
    age_days = (datetime.now(timezone.utc).date() - cutoff_date).days
    checks = {
        "snapshot_freshness": {"status": "pass" if age_days <= 7 else "warning", "detail": f"snapshot_age_days={age_days}"},
        "annual_financial_coverage": {"status": "pass" if not missing_annual_metrics else "warning", "detail": f"missing_periods={','.join(missing_annual_metrics)}" if missing_annual_metrics else "complete"},
        "key_metrics": {"status": "pass" if not missing_key_metrics else "blocked", "detail": f"missing={','.join(missing_key_metrics)}" if missing_key_metrics else "complete"},
        "peer_coverage": {"status": "pass" if peer.get("peer_count", 0) >= 4 else "warning", "detail": f"compatible_peer_count={peer.get('peer_count', 0)}"},
    }
    blocked = [name for name, check in checks.items() if check["status"] == "blocked"]
    warnings = [name for name, check in checks.items() if check["status"] == "warning"]
    return {
        "snapshot_id": snapshot_id,
        "status": "blocked" if blocked else "limited" if warnings else "ready",
        "blocked": blocked,
        "warnings": warnings,
        "checks": checks,
    }


def research_validation(snapshot_id: str) -> dict[str, Any]:
    """Combine deterministic ledger validation with explicit research gates."""
    payload = load_snapshot(snapshot_id)
    ledger_validation = _ledger_validation(payload)
    readiness = research_readiness(snapshot_id)
    labels = {
        "ledger": ("证据账本", "检查事实时点与计算依赖", "重新生成快照或修复证据依赖。"),
        "snapshot_freshness": ("快照时效", "检查研究时点与快照日期", "更新版本化快照后重新运行研究。"),
        "annual_financial_coverage": ("年度财报覆盖", "检查年度收入和归母净利润", "补充已披露且不晚于研究时点的财报。"),
        "key_metrics": ("关键估值输入", "检查价格、股本、TTM 财务和权益", "补齐缺失输入；禁止以前端估算代替。"),
        "peer_coverage": ("同业样本", "检查同业数量、行业和快照日期", "补充同一行业且时点兼容的版本化快照。"),
    }
    checks = [{
        "code": "ledger", "label": labels["ledger"][0],
        "status": "pass" if ledger_validation.valid else "blocked",
        "detail": labels["ledger"][1] if ledger_validation.valid else ", ".join(ledger_validation.errors),
        "remediation": labels["ledger"][2],
    }]
    for code, check in readiness["checks"].items():
        label, _, remediation = labels[code]
        checks.append({"code": code, "label": label, **check, "remediation": remediation})
    blocked = [check["code"] for check in checks if check["status"] == "blocked"]
    warnings = [check["code"] for check in checks if check["status"] == "warning"]
    return {
        "snapshot_id": snapshot_id,
        "research_as_of": payload["research_as_of"],
        "status": "blocked" if blocked else "warning" if warnings else "pass",
        "valid": not blocked,
        "errors": ledger_validation.errors,
        "blocked": blocked,
        "warnings": warnings,
        "checks": checks,
        "conclusion_allowed": not blocked,
    }


def research_evidence(snapshot_id: str) -> dict[str, Any]:
    payload = load_snapshot(snapshot_id)
    records = []
    summary = _summary(payload)
    symbol_key = payload["symbol"].replace(".", "_")
    raw_bars = [
        bar for bar in payload["data"].get("bars", [])
        if bar.get("adjustment") == "RAW" and bar["trade_date"] <= payload["research_as_of"][:10]
    ]
    latest_bar = max(raw_bars, key=lambda item: item["trade_date"], default=None)
    for bar in raw_bars:
        records.append({
            "evidence_id": f"fact_{symbol_key}_close_{bar['trade_date']}_RAW", "kind": "fact", "metric": "close",
            "value": bar["close"], "period": bar["trade_date"],
            "published_at": f"{bar['trade_date']}T15:00:00+08:00", "unit": "CNY/share",
            "provider": payload.get("provider", "snapshot"), "status": "verified",
            "field_path": f"bars.{bar['trade_date']}.close", "input_ids": [], "operation": None,
            "price_basis": "RAW",
        })
    eligible_statements = [
        statement for statement in payload["data"].get("statements", [])
        if not statement.get("published_at") or statement["published_at"] <= payload["research_as_of"]
    ]
    for statement in eligible_statements:
        for metric, value in statement.get("values", {}).items():
            if value is not None:
                records.append({
                    "evidence_id": f"fact_{symbol_key}_{metric}_{statement['fiscal_period']}",
                    "kind": "fact", "metric": metric, "value": value, "period": statement["fiscal_period"],
                    "published_at": statement.get("published_at"), "unit": statement.get("unit", "CNY"),
                    "provider": payload.get("provider", "snapshot"), "status": "verified",
                    "field_path": f"statements.{statement['statement_type']}.{statement['fiscal_period']}.{metric}",
                    "input_ids": [], "operation": None,
                })
        values = statement.get("values", {})
        if values.get("revenue") not in (None, 0) and values.get("net_profit") is not None:
            period = statement["fiscal_period"]
            records.append({
                "evidence_id": f"calc_net_margin_{period}", "kind": "calculation",
                "metric": "net_margin", "value": values["net_profit"] / values["revenue"] * 100,
                "period": period, "published_at": statement.get("published_at"), "unit": "percent",
                "provider": "fintrace_calculator", "status": "verified", "field_path": None,
                "input_ids": [f"fact_{symbol_key}_net_profit_{period}", f"fact_{symbol_key}_revenue_{period}"],
                "operation": "divide_percent",
            })
    statement_ids = {record["evidence_id"] for record in records}
    ttm_statements = FinancialPeriodEngine.derive_ttm(
        [FinancialStatement(**item) for item in eligible_statements], "income"
    )
    latest_ttm = max(ttm_statements, key=lambda item: item.fiscal_period, default=None)
    ttm_id = summary["evidence_ids"]["ttm_net_profit"]
    ttm_period = latest_ttm.fiscal_period if latest_ttm else None
    ttm_sources = [
        f"fact_{symbol_key}_net_profit_{period}" for period in (latest_ttm.source_periods if latest_ttm else [])
        if f"fact_{symbol_key}_net_profit_{period}" in statement_ids
    ]
    if ttm_id and ttm_id.startswith("calc_") and summary["key_metrics"]["ttm_net_profit"] is not None:
        records.append({
            "evidence_id": ttm_id, "kind": "calculation", "metric": "net_profit_ttm",
            "value": summary["key_metrics"]["ttm_net_profit"], "period": ttm_period,
            "published_at": None, "unit": "CNY", "provider": "fintrace_calculator",
            "status": "verified", "field_path": None, "input_ids": sorted(ttm_sources),
            "operation": "period_engine",
        })
    shares_records = [record for record in records if record["metric"] == "total_shares"]
    if summary["evidence_ids"]["market_cap"] and latest_bar is not None and shares_records:
        share_record = min(shares_records, key=lambda record: abs(record["value"] - summary["key_metrics"]["total_shares"]))
        records.append({
            "evidence_id": "calc_market_cap", "kind": "calculation", "metric": "market_cap",
            "value": summary["key_metrics"]["market_cap"], "period": None, "published_at": None,
            "unit": "CNY", "provider": "fintrace_calculator", "status": "verified",
            "field_path": None, "input_ids": [summary["evidence_ids"]["price"], share_record["evidence_id"]],
            "operation": "multiply",
        })
    if summary["evidence_ids"]["pe_ttm"] and ttm_id:
        records.append({
            "evidence_id": "calc_pe_ttm", "kind": "calculation", "metric": "pe_ttm",
            "value": summary["key_metrics"]["pe_ttm"],
            "period": ttm_period, "published_at": None, "unit": "multiple",
            "provider": "fintrace_calculator", "status": "verified", "field_path": None,
            "input_ids": ["calc_market_cap", ttm_id], "operation": "divide",
        })
    existing_ids = {record["evidence_id"] for record in records}
    for point in research_financial_trends(snapshot_id, "TTM")["points"]:
        for metric in ("revenue", "net_profit"):
            calc_id = point["evidence_ids"].get(metric)
            if not calc_id or calc_id in existing_ids or not calc_id.startswith("calc_"):
                continue
            records.append({
                "evidence_id": calc_id, "kind": "calculation", "metric": f"{metric}_ttm",
                "value": point[metric], "period": point["fiscal_period"],
                "published_at": point["published_at"], "unit": "CNY",
                "provider": "fintrace_calculator", "status": "verified", "field_path": None,
                "input_ids": point["source_evidence_ids"][metric], "operation": "period_engine",
            })
            existing_ids.add(calc_id)
        margin_id = point["evidence_ids"].get("net_margin")
        if margin_id and margin_id not in existing_ids:
            records.append({
                "evidence_id": margin_id, "kind": "calculation", "metric": "net_margin_ttm",
                "value": point["net_margin"], "period": point["fiscal_period"],
                "published_at": point["published_at"], "unit": "percent",
                "provider": "fintrace_calculator", "status": "verified", "field_path": None,
                "input_ids": [point["evidence_ids"]["net_profit"], point["evidence_ids"]["revenue"]],
                "operation": "divide_percent",
            })
            existing_ids.add(margin_id)
    return {
        "snapshot_id": snapshot_id, "research_as_of": payload["research_as_of"],
        "provider": payload.get("provider", "snapshot"), "records": records,
        "dependency_graph": {
            "nodes": [{
                "id": record["evidence_id"], "kind": record["kind"],
                "metric": record["metric"], "status": record["status"],
            } for record in records],
            "edges": [{"source": input_id, "target": record["evidence_id"]}
                      for record in records for input_id in record.get("input_ids", [])],
        },
    }


def research_trace(snapshot_id: str) -> dict[str, Any]:
    """Expose only persisted execution events; never synthesize a success trace."""
    payload = load_snapshot(snapshot_id)
    tasks = [task for task in list_tasks() if task.get("snapshot_id") == snapshot_id]
    task = tasks[0] if tasks else None
    events = (task or {}).get("trace", (task or {}).get("events", []))
    return {
        "snapshot_id": snapshot_id, "research_as_of": payload["research_as_of"],
        "provider": payload.get("provider", "snapshot"), "available": bool(events),
        "trace_id": (task or {}).get("trace_id"), "task_id": (task or {}).get("id"),
        "model": (task or {}).get("model"), "prompt_version": (task or {}).get("prompt_version"),
        "git_commit": (task or {}).get("git_commit"), "events": events,
        "unavailable_reason": None if events else "trace_not_recorded_for_legacy_task",
    }


def research_report(snapshot_id: str) -> dict[str, Any]:
    payload = load_snapshot(snapshot_id)
    validation = research_validation(snapshot_id)
    report_path = OUTPUT_DIR / f"{payload['symbol']}_research_report.md"
    available = report_path.exists() and validation["conclusion_allowed"]
    return {
        "snapshot_id": snapshot_id, "research_as_of": payload["research_as_of"],
        "provider": payload.get("provider", "snapshot"), "currency": payload["data"].get("profile", {}).get("currency", "CNY"),
        "validation_status": validation["status"], "conclusion_allowed": validation["conclusion_allowed"],
        "available": available, "format": "markdown",
        "filename": report_path.name if report_path.exists() else None,
        "content": report_path.read_text(encoding="utf-8") if available else None,
        "unavailable_reason": (
            "validator_blocked" if not validation["conclusion_allowed"]
            else "report_not_generated" if not report_path.exists() else None
        ),
    }


def research_artifacts(snapshot_id: str) -> dict[str, Any]:
    payload = load_snapshot(snapshot_id)
    symbol = payload["symbol"]
    candidates = [
        ("report", OUTPUT_DIR / f"{symbol}_research_report.md", "text/markdown"),
        ("excel", OUTPUT_DIR / f"{symbol}_cn_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("metadata", OUTPUT_DIR / f"{symbol}_cn_report.metadata.json", "application/json"),
    ]
    artifacts = [{
        "kind": kind, "filename": path.name, "media_type": media_type, "size_bytes": path.stat().st_size,
    } for kind, path, media_type in candidates if path.exists()]
    validation = research_validation(snapshot_id)
    return {
        "snapshot_id": snapshot_id, "research_as_of": payload["research_as_of"],
        "provider": payload.get("provider", "snapshot"), "validation_status": validation["status"],
        "artifacts": artifacts,
    }
