"""Deterministic real-model benchmark for the shared ``CnResearchAgent``.

Loop 2 of FinTrace-CN: a reproducible runner that executes the exact same
provider-agnostic agent used by the product path, against a pinned 24-case
dataset of versioned mirror snapshots, and reports auditable machine metrics.

Design rules
------------
* Metrics are computed from ``ResearchState`` and the pinned snapshot only —
  never from model prose.  The LLM decides what to call and how to explain;
  the numbers are reproduced from verifiable state.
* Evidence coverage reuses the validator's admission rule
  (``snapshot_evidence_records``): an evidence ID only counts when it was both
  registered in state and returned by a successful tool call.  Nothing can be
  manufactured.
* The runner is reproducible by construction: a config fingerprint hashes the
  dataset bytes, snapshot payloads, system prompt, model, temperature and max
  steps, so any config drift changes the fingerprint.
* Checkpointing lets a long run resume case-by-case, and a hard cost budget
  stops the run before it can exceed a caller-specified USD ceiling.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.cn.research_agent import SYSTEM_PROMPT, CnResearchAgent
from src.cn.research import ResearchState
from src.validation.research_gate import snapshot_evidence_records


@dataclass(frozen=True)
class RealBenchmarkCase:
    """One dataset entry with deterministic assertions about agent behaviour."""

    case_id: str
    category: str
    query: str
    snapshot: str
    research_as_of: str
    required_tools: List[str]
    forbidden_tools: List[str]
    expected_arguments: Dict[str, Dict[str, object]]
    required_metrics: List[str]
    requires_evidence: bool
    expected_outcome: str  # "ok" | "blocked"
    expected_validator_errors: List[str]
    forbidden_claims: List[str]
    requested_valuation_method: Optional[str] = None
    resolve_target: Optional[str] = None  # symbol the mock should resolve in dry-run; defaults to snapshot symbol


def load_real_cases(path: Path | str, *, project_root: Path | str) -> List[RealBenchmarkCase]:
    """Parse the Loop-2 dataset JSON, resolving snapshot keys to registry paths."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    registry = payload.get("snapshot_registry") or {}
    cases = []
    for item in payload["cases"]:
        snapshot_key = str(item.get("snapshot", ""))
        resolved = registry.get(snapshot_key, "")
        if resolved:
            resolved_path = Path(resolved)
            item["snapshot"] = str(resolved_path if resolved_path.is_absolute() else Path(project_root) / resolved_path)
        cases.append(RealBenchmarkCase(**item))
    return cases


def metric_evidence_coverage(case: RealBenchmarkCase, state: ResearchState, snapshot_payload: Mapping[str, Any]) -> float:
    """Fraction of required metrics present in *admitted* evidence.

    Empty ``required_metrics`` is trivially satisfied. This mirrors the Product
    validator's admission rule so benchmark scoring cannot diverge from what the
    running agent is allowed to conclude.
    """
    if not case.required_metrics:
        return 1.0
    present = {str(record.get("metric")).lower() for record in snapshot_evidence_records(snapshot_payload, state=state) if record.get("metric")}
    return len(present & {m.lower() for m in case.required_metrics}) / len(case.required_metrics)


def _arguments_match(call_args: Mapping[str, object], requirement: Mapping[str, object]) -> bool:
    """Compare only the keys the case pins; values are compared as strings so the
    caller never depends on JSON number vs int formatting."""
    if not requirement:
        return True
    for key, expected in requirement.items():
        if str(call_args.get(key) or "") != str(expected):
            return False
    return True


# Negation markers: a forbidden claim that only appears inside an honest
# disclosure ("非实时价格", "不代表实时行情", "is not live") must not be treated
# as a violation.
_CN_NEGATION = ("非但不是", "并不代表", "并不是", "不代表", "不构成", "不是", "并非", "非", "不", "没", "未", "否")
_EN_NEGATION = ("not ", "n't", "no ", "never")


def _is_negated_before(text: str, index: int) -> bool:
    window = text[max(0, index - 8):index].rstrip()
    if any(window.endswith(marker) for marker in _CN_NEGATION):
        return True
    return any(marker in window for marker in _EN_NEGATION)


# Reference frames: "for a current live price you would need…", "cannot provide
# a live price", "to obtain X consult a source" describe where to look, not an
# asserted value.  If such a clause follows a forbidden phrase, it is not a claim.
_EN_REFERENCE_AFTER = ("you would need", "you need", "consult", "require",
                       "to obtain", "to get", "a real-time", "source",
                       "not available", "is not provided")


def _referenced_after(text: str, index: int, phrase_len: int) -> bool:
    following = text[index + phrase_len:index + phrase_len + 80]
    return any(marker in following for marker in _EN_REFERENCE_AFTER)


def _claim_asserted_positive(text: str, phrase: str) -> bool:
    """True iff ``phrase`` is asserted as a value, not merely negated or named.

    An honest answer may say "非实时价格 / cannot provide a live price /
    for a current live price you need a source" — those must not be treated as
    a live-claim violation.  Only a phrase presented as an actual value counts.
    """
    start, plen = 0, len(phrase)
    while True:
        index = text.find(phrase, start)
        if index < 0:
            return False
        if _is_negated_before(text, index) or _referenced_after(text, index, plen):
            start = index + plen
            continue
        return True


def evaluate_real_case(
    case: RealBenchmarkCase,
    state: ResearchState,
    *,
    snapshot_payload: Mapping[str, Any],
    answer: str = "",
    max_steps: int = 6,
) -> Dict[str, Any]:
    """Score one real execution against the case's deterministic assertions.

    Returns a flat row plus the captured research state for auditability. The
    ``passed`` flag gates on the directionally-appropriate checks per outcome.
    """
    calls = list(state.tool_trace)
    called = [trace.tool_name for trace in calls]
    expected: set[str] = set(case.required_tools)
    actual: set[str] = set(called)

    if not expected and not actual:
        precision = recall = tool_f1 = 1.0
    else:
        precision = len(expected & actual) / len(actual) if actual else 0.0
        recall = len(expected & actual) / len(expected) if expected else 1.0
        tool_f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

    params_ok = all(
        any(_arguments_match(trace.arguments, req) for trace in calls if trace.tool_name == tool)
        for tool, req in case.expected_arguments.items()
    )
    forbidden_hit = actual & set(case.forbidden_tools)
    forbidden_tool_avoidance = not forbidden_hit

    if case.required_tools:
        step_efficiency = min(1.0, len(case.required_tools) / max(1, len(calls)))
    else:
        step_efficiency = 1.0 if not called else 0.0

    within_step_limit = len(calls) < max_steps
    coverage = metric_evidence_coverage(case, state, snapshot_payload)

    lowered_answer = (answer or "").lower()
    # An explicit block/refusal is always safe: the agent retracts rather than
    # leaking a conclusion. We must not penalize validator-error details (e.g.
    # a rejection that names the missing metric "ebitda").
    is_rejection = any(phrase in lowered_answer for phrase in ("无法验证", "拒绝结论", "拒绝"))
    claim_safety = is_rejection or not any(_claim_asserted_positive(lowered_answer, claim.lower()) for claim in case.forbidden_claims)

    valid = bool((state.validation_result or {}).get("valid", False))
    actual_errors = [str(e) for e in (state.validation_result or {}).get("errors", [])]
    outcome_match = valid == (case.expected_outcome == "ok")

    if case.expected_outcome == "ok":
        validator_match = valid and not actual_errors
    else:
        expected_errors = set(case.expected_validator_errors)
        validator_match = (not valid) and bool(actual_errors) and any(
            any(exp in err for exp in expected_errors) for err in actual_errors
        )

    had_tool_error = any(trace.result_status != "ok" for trace in calls)
    if had_tool_error:
        recovery_rate = 1.0 if (not valid and claim_safety) else 0.0
    else:
        recovery_rate = 1.0

    # Directionally-appropriate pass gates per outcome.
    checks: Dict[str, bool] = {
        "forbidden_tool_avoidance": forbidden_tool_avoidance,
        "claim_safety": claim_safety,
        "outcome_match": outcome_match,
        "validator_match": validator_match,
        "within_step_limit": within_step_limit,
    }
    if case.expected_outcome == "ok":
        # All required tools must have been called.  A well-behaved model is
        # allowed reasonable extra steps (e.g. generating the report), so a
        # pass requires full recall of the required set rather than an exact
        # tool-set match; tool_f1 is still reported for ranking.
        checks["tool_recall_full"] = recall == 1.0
        checks["parameter_accuracy"] = params_ok
        if case.requires_evidence:
            checks["evidence_coverage"] = coverage == 1.0
    else:
        checks["recovery_graceful"] = not had_tool_error or recovery_rate == 1.0

    passed = all(checks.values())

    return {
        "case_id": case.case_id,
        "category": case.category,
        "query": case.query,
        "expected_outcome": case.expected_outcome,
        "actual_valid": valid,
        "validator_errors": actual_errors,
        "tool_f1": round(tool_f1, 4),
        "parameter_accuracy": params_ok,
        "forbidden_tool_avoidance": forbidden_tool_avoidance,
        "evidence_coverage": round(coverage, 4),
        "step_efficiency": round(step_efficiency, 4),
        "within_step_limit": within_step_limit,
        "recovery_rate": recovery_rate,
        "claim_safety": claim_safety,
        "outcome_match": outcome_match,
        "validator_match": validator_match,
        "tool_calls": len(calls),
        "passed": passed,
        "answer": answer,
        "research_state": state.to_dict(),
    }


def summarize_real(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    if not rows:
        return {"cases": 0, "pass_rate": 0.0, "total_cost_usd": 0.0}
    n = len(rows)
    return {
        "cases": n,
        "pass_rate": sum(bool(r["passed"]) for r in rows) / n,
        "tool_f1": sum(float(r["tool_f1"]) for r in rows) / n,
        "parameter_accuracy": sum(1 for r in rows if r["parameter_accuracy"]) / n,
        "evidence_coverage": sum(float(r["evidence_coverage"]) for r in rows) / n,
        "step_efficiency": sum(float(r["step_efficiency"]) for r in rows) / n,
        "recovery_rate": sum(float(r["recovery_rate"]) for r in rows) / n,
        "within_step_limit_rate": sum(1 for r in rows if r["within_step_limit"]) / n,
        "claim_safety_rate": sum(1 for r in rows if r["claim_safety"]) / n,
        "outcome_match_rate": sum(1 for r in rows if r["outcome_match"]) / n,
        "validator_match_rate": sum(1 for r in rows if r["validator_match"]) / n,
        "ok_passed": sum(1 for r in rows if r["expected_outcome"] == "ok" and r["passed"]),
        "blocked_passed": sum(1 for r in rows if r["expected_outcome"] == "blocked" and r["passed"]),
        "ok_total": sum(1 for r in rows if r["expected_outcome"] == "ok"),
        "blocked_total": sum(1 for r in rows if r["expected_outcome"] == "blocked"),
        "avg_tool_calls": sum(int(r["tool_calls"]) for r in rows) / n,
        "avg_llm_calls": sum(int(r.get("llm_calls", 0)) for r in rows) / n,
        "avg_latency_seconds": sum(float(r.get("latency_seconds", 0.0)) for r in rows) / n,
        "total_cost_usd": sum(float(r.get("cost_usd", 0.0)) for r in rows),
        "skipped_budget": sum(1 for r in rows if r.get("skipped_budget", False)),
    }


def config_fingerprint(
    *,
    dataset_path: Path,
    snapshot_paths: Sequence[Path],
    model: str,
    temperature: float,
    max_steps: int,
) -> str:
    """Deterministic reproducibility anchor for a benchmark run."""
    digest = hashlib.sha256()
    digest.update(dataset_path.read_bytes())
    for path in snapshot_paths:
        digest.update(path.read_bytes())
    digest.update(SYSTEM_PROMPT.encode("utf-8"))
    digest.update(f"{model}|{temperature}|{max_steps}".encode("utf-8"))
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------------------
#  Mock provider for offline dry-run (no model key, no billing)
# ---------------------------------------------------------------------------

class RealBenchmarkMockProvider:
    """Best-effort LLM stand-in: requests the expected tools in order.

    Arguments come from the case's pinned expectations, falling back to the
    resolved snapshot symbol.  Used only for offline runner tests — it never
    touches an LLM or a network provider.
    """

    model_name = "mock-model"
    api_style = "openai"

    def __init__(self, case: RealBenchmarkCase, snapshot_symbol: str):
        self._case = case
        self._symbol = snapshot_symbol
        self._target = case.resolve_target or snapshot_symbol
        self._queue = list(case.required_tools)

    def _args_for(self, tool: str) -> Dict[str, object]:
        spec = self._case.expected_arguments.get(tool)
        if spec:
            return dict(spec)
        if tool == "resolve_cn_symbol":
            return {"query": self._target}
        if tool in {"get_cn_prices", "get_cn_financials", "generate_cn_research_report"}:
            return {"ticker": self._target}
        return {}

    async def call_with_tools(self, messages, tools, temperature=0.0, **kwargs):
        from types import SimpleNamespace
        from src.llms.async_client import LLMToolResponse, ToolCall

        if self._queue:
            name = self._queue.pop(0)
            call = ToolCall(id=f"call-{name}", name=name, arguments=self._args_for(name), parse_error=None)
            return LLMToolResponse(text="", tool_calls=[call], cost=0.0001,
                                   raw={"role": "assistant", "tool_calls": []})
        if self._case.expected_outcome == "ok":
            text = "已完成对快照数据的分析。"
        else:
            text = "无法验证/拒绝结论。"
        return LLMToolResponse(text=text, tool_calls=[], cost=0.0001,
                               raw={"role": "assistant", "content": text})


# ---------------------------------------------------------------------------
#  Real-model runner: budget, checkpoint, hashed metadata, artifacts
# ---------------------------------------------------------------------------

def _resolve_snapshot(case: RealBenchmarkCase, project_root: Path, snapshot_dir: Path) -> Path:
    path = Path(case.snapshot)
    if path.is_absolute():
        if path.exists():
            return path
        raise FileNotFoundError(f"Case {case.case_id} snapshot missing: {path}")
    absolute = project_root / path
    if absolute.exists():
        return absolute
    matches = sorted(snapshot_dir.glob("*.json"))
    for candidate in matches:
        try:
            if json.loads(candidate.read_text(encoding="utf-8")).get("symbol") == str(path):
                return candidate
        except json.JSONDecodeError:
            continue
    base = Path(case.snapshot).name
    for candidate in matches:
        if candidate.name == base or base in candidate.name:
            return candidate
    raise FileNotFoundError(f"Case {case.case_id} snapshot not found for {case.snapshot}")


class RealBenchmarkRunner:
    """Execute the shared agent across the dataset with budget + checkpoint."""

    def __init__(self, cases: Sequence[RealBenchmarkCase], *, dataset_path: Path | str):
        self.cases = list(cases)
        self.dataset_path = Path(dataset_path)

    async def run(
        self,
        *,
        project_root: Path,
        snapshot_dir: Path,
        model: str,
        temperature: float,
        max_steps: int,
        dry_run: bool,
        output_dir: Path,
        max_cost_usd: Optional[float] = None,
        resume: bool = False,
    ) -> Dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = output_dir / "checkpoint.json"
        checkpoint: Dict[str, Dict[str, Any]] = {}
        if resume and checkpoint_path.exists():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        snapshot_paths = [_resolve_snapshot(case, project_root, snapshot_dir) for case in self.cases]
        fingerprint = config_fingerprint(
            dataset_path=self.dataset_path, snapshot_paths=snapshot_paths,
            model=model, temperature=temperature, max_steps=max_steps,
        )
        metadata = {
            "benchmark_version": "cn-agent-real-v1",
            "executor": "CnResearchAgent",
            "model": model,
            "temperature": temperature,
            "max_steps": max_steps,
            "dry_run": dry_run,
            "config_fingerprint": fingerprint,
            "network": False,
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        }

        rows: List[Dict[str, Any]] = []
        total_cost = 0.0
        budget_reached = False

        for case in self.cases:
            if resume and case.case_id in checkpoint:
                row = checkpoint[case.case_id]
                rows.append(row)
                total_cost += float(row.get("cost_usd", 0.0))
                continue
            if budget_reached:
                row = self._skipped_row(case)
                rows.append(row)
                continue

            started = time.monotonic()
            snapshot_path = _resolve_snapshot(case, project_root, snapshot_dir)
            symbol = str(json.loads(snapshot_path.read_text(encoding="utf-8"))["symbol"])
            provider = RealBenchmarkMockProvider(case, symbol) if dry_run else None
            agent = CnResearchAgent(
                snapshot_path=snapshot_path, model_name=model,
                temperature=temperature, max_steps=max_steps, provider=provider,
                required_metrics=case.required_metrics,
                requires_evidence=case.requires_evidence,
                requested_valuation_method=case.requested_valuation_method,
            )
            state = await agent.run(case.query, research_as_of=case.research_as_of)
            row = evaluate_real_case(
                case, state, snapshot_payload=agent.snapshot._payload,
                answer=agent.answer, max_steps=max_steps,
            )
            row["latency_seconds"] = round(time.monotonic() - started, 3)
            row["cost_usd"] = round(agent.total_cost, 6)
            row["llm_calls"] = agent.llm_calls

            total_cost += agent.total_cost
            checkpoint[case.case_id] = {k: row[k] for k in
                                        ("case_id", "category", "expected_outcome", "actual_valid",
                                         "validator_errors", "tool_f1", "evidence_coverage", "passed",
                                         "tool_calls", "llm_calls", "cost_usd")}
            checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
            rows.append(row)
            if max_cost_usd is not None and total_cost >= max_cost_usd:
                budget_reached = True

        summary = summarize_real(rows)
        payload: Dict[str, Any] = {"metadata": metadata, "summary": summary, "results": rows}
        write_real_outputs(output_dir, payload, cases=self.cases)
        return payload

    @staticmethod
    def _skipped_row(case: RealBenchmarkCase) -> Dict[str, Any]:
        return {
            "case_id": case.case_id, "category": case.category, "query": case.query,
            "expected_outcome": case.expected_outcome, "actual_valid": False,
            "validator_errors": ["skipped_budget"], "tool_f1": 0.0, "parameter_accuracy": False,
            "forbidden_tool_avoidance": True, "evidence_coverage": 0.0, "step_efficiency": 0.0,
            "within_step_limit": False, "recovery_rate": 0.0, "claim_safety": True,
            "outcome_match": False, "validator_match": False, "tool_calls": 0, "passed": False,
            "skipped_budget": True, "cost_usd": 0.0, "llm_calls": 0, "latency_seconds": 0.0,
        }


# ---------------------------------------------------------------------------
#  Artifact writers
# ---------------------------------------------------------------------------

_OUTPUT_CSV_FIELDS = (
    "case_id", "category", "query", "expected_outcome", "actual_valid",
    "tool_f1", "parameter_accuracy", "forbidden_tool_avoidance", "evidence_coverage",
    "step_efficiency", "within_step_limit", "recovery_rate", "claim_safety",
    "outcome_match", "validator_match", "tool_calls", "llm_calls", "cost_usd",
    "latency_seconds", "passed",
)


def write_real_outputs(output_dir: Path, payload: Mapping[str, Any], *, cases: Sequence[RealBenchmarkCase]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = payload["metadata"]
    summary = payload["summary"]

    (output_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "comparison.json").write_text(
        json.dumps({"summary": summary, "metadata": metadata}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    _write_cases_csv(output_dir / "cases.csv", payload["results"])
    (output_dir / "summary.md").write_text(_summary_markdown(metadata, summary), encoding="utf-8")
    (output_dir / "failures.md").write_text(_failures_markdown(payload["results"]), encoding="utf-8")

    traces_dir = output_dir / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    for row in payload["results"]:
        trace = {
            "case_id": row["case_id"], "query": row["query"], "expected_outcome": row["expected_outcome"],
            "state": row["research_state"],
        }
        (traces_dir / f"{row['case_id']}.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_cases_csv(path: Path, results: Sequence[Mapping[str, Any]]) -> None:
    import csv
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_OUTPUT_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            writer.writerow(row)


def _summary_markdown(metadata: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    def pct(value: float) -> str:
        return f"{value:.1%}" if value is not None else "n/a"

    lines = [
        "# FinTrace-CN 真实 Agent Benchmark 汇总",
        "",
        f"- **执行器**：{metadata.get('executor')}",
        f"- **模型**：{metadata.get('model')}",
        f"- **温度 / 最大步数**：{metadata.get('temperature')} / {metadata.get('max_steps')}",
        f"- **离线演练**：{metadata.get('dry_run')}",
        f"- **配置指纹**：`{metadata.get('config_fingerprint')}`",
        f"- **运行时间**：{metadata.get('run_at')}",
        "",
        "## 汇总指标",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 案例数 | {summary.get('cases')} |",
        f"| 端到端通过率 | {pct(summary.get('pass_rate'))} |",
        f"| 预期阻塞通过 | {summary.get('blocked_passed')}/{summary.get('blocked_total')} |",
        f"| 预期正常通过 | {summary.get('ok_passed')}/{summary.get('ok_total')} |",
        f"| 工具 F1 | {summary.get('tool_f1'):.3f} |",
        f"| 参数准确率 | {pct(summary.get('parameter_accuracy'))} |",
        f"| 证据覆盖率 | {summary.get('evidence_coverage'):.3f} |",
        f"| 步骤效率 | {summary.get('step_efficiency'):.3f} |",
        f"| 恢复率 | {summary.get('recovery_rate'):.3f} |",
        f"| 步限内占比 | {pct(summary.get('within_step_limit_rate'))} |",
        f"| 论断安全率 | {pct(summary.get('claim_safety_rate'))} |",
        f"| 结果匹配率 | {pct(summary.get('outcome_match_rate'))} |",
        f"| 校验匹配率 | {pct(summary.get('validator_match_rate'))} |",
        f"| 平均工具调用 / LLM 调用 | {summary.get('avg_tool_calls'):.1f} / {summary.get('avg_llm_calls'):.1f} |",
        f"| 平均延迟 / 总成本 | {summary.get('avg_latency_seconds'):.1f}s / ${summary.get('total_cost_usd'):.6f} |",
        "",
    ]
    return "\n".join(lines)


def _failures_markdown(results: Sequence[Mapping[str, Any]]) -> str:
    failures = [row for row in results if not row.get("passed")]
    if not failures:
        return "# 失败案例\n\n无：全部用例通过。\n"
    lines = ["# 失败案例", ""]
    for row in failures:
        status = "阻塞被正确阻断" if row.get("expected_outcome") == "blocked" else "应正常但被阻断或误报"
        lines += [
            f"## {row.get('case_id')}（{status}）",
            "",
            f"- **查询**：{row.get('query')}",
            f"- **预期结果**：{row.get('expected_outcome')}；实际 valid={row.get('actual_valid')}",
            f"- **工具 F1**：{row.get('tool_f1')} / 参数 {row.get('parameter_accuracy')} / 证据 {row.get('evidence_coverage')}",
            f"- **Validator 错误**：{row.get('validator_errors')}",
            f"- **遍历工具**：{row.get('research_state', {}).get('tool_trace', [])}",
            "",
        ]
    return "\n".join(lines)