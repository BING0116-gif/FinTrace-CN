"""Offline, deterministic benchmark primitives for FinTrace-CN agent traces."""

from __future__ import annotations

import json
import csv
import inspect
import time
import hashlib
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from src.cn.research import ResearchState


METRIC_KEYS = ("tool_f1", "parameter_accuracy", "evidence_coverage", "e2e_success_rate")
ABLATION_VARIANTS = (
    "direct_llm",
    "agent_tools",
    "agent_tools_evidence",
    "agent_tools_evidence_validator",
)

# CARD-11: the v2 scorecard is deliberately explicit.  A missing denominator
# is reported as N/A, never converted to a flattering zero or target number.
V2_METRICS = (
    "extraction_precision", "extraction_recall", "extraction_f1",
    "numeric_exact_match", "unit_accuracy", "period_accuracy", "scope_accuracy", "page_attribution_accuracy",
    "citation_precision", "citation_recall", "calculation_accuracy",
    "checker_precision", "checker_recall", "checker_f1", "false_positive_rate",
    "tool_selection_accuracy", "parameter_accuracy", "task_completion_rate", "evidence_coverage",
    "unsafe_conclusion_leakage", "replay_success_rate", "multi_run_consistency",
    "latency", "token_cost",
)


def precision_recall_f1(true_positive: int, false_positive: int, false_negative: int) -> dict[str, float | None]:
    """Return deterministic P/R/F1; undefined denominators stay ``None``."""
    tp, fp, fn = float(true_positive), float(false_positive), float(false_negative)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"precision": None if precision is None else round(precision, 12), "recall": None if recall is None else round(recall, 12), "f1": None if f1 is None else round(f1, 12)}


def _rate(correct: int, total: int) -> float | None:
    return float(correct) / float(total) if total else None


def compute_v2_metrics(observations: Mapping[str, object]) -> dict[str, float | None]:
    """Compute the 24-card scorecard from captured counts, not model prose.

    ``observations`` accepts either direct metric values or count objects.  The
    count form is useful for fixtures and makes the denominator auditable.
    """
    out: dict[str, float | None] = {key: None for key in V2_METRICS}
    for key in V2_METRICS:
        value = observations.get(key)
        if isinstance(value, (int, float)):
            out[key] = float(value)
        elif isinstance(value, Mapping) and "correct" in value:
            out[key] = _rate(int(value.get("correct", 0)), int(value.get("total", 0)))
    extraction = observations.get("extraction")
    if isinstance(extraction, Mapping):
        prf = precision_recall_f1(int(extraction.get("tp", 0)), int(extraction.get("fp", 0)), int(extraction.get("fn", 0)))
        out.update({"extraction_precision": prf["precision"], "extraction_recall": prf["recall"], "extraction_f1": prf["f1"]})
    checker = observations.get("checker")
    if isinstance(checker, Mapping):
        prf = precision_recall_f1(int(checker.get("tp", 0)), int(checker.get("fp", 0)), int(checker.get("fn", 0)))
        out.update({"checker_precision": prf["precision"], "checker_recall": prf["recall"], "checker_f1": prf["f1"]})
        negatives = int(checker.get("negative_total", 0))
        out["false_positive_rate"] = _rate(int(checker.get("fp", 0)), negatives)
    return out


def environment_fingerprint(*, suite: str, dataset: str, config: Mapping[str, object] | None = None, code_version: str = "") -> dict[str, str]:
    """Create a stable, auditable fingerprint for a benchmark invocation."""
    payload = {"suite": suite, "dataset": dataset, "config": dict(config or {}), "code_version": code_version}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return {"fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(), "suite": suite, "dataset": dataset, "code_version": code_version, "python": platform.python_version()}


def build_v2_report(*, suite: str = "cn_agent_v2", dataset: str = "synthetic", metrics: Mapping[str, object] | None = None, metadata: Mapping[str, object] | None = None, ablation: Mapping[str, object] | None = None, finfuzz: Mapping[str, object] | None = None) -> dict[str, object]:
    """Build a report with every scorecard row, including honest N/A values."""
    measured = compute_v2_metrics(metrics or {})
    rows = [{"metric": key, "value": measured[key], "status": "measured" if measured[key] is not None else "N/A", "reason": None if measured[key] is not None else "no denominator or captured observation"} for key in V2_METRICS]
    report: dict[str, object] = {"schema_version": "cn-agent-v2-benchmark-1.0.0", "suite": suite, "dataset": dataset, "metrics": rows, "metadata": dict(metadata or {}), "environment": environment_fingerprint(suite=suite, dataset=dataset, config=metadata or {})}
    if ablation is not None: report["ablation"] = dict(ablation)
    if finfuzz is not None:
        report["finfuzz"] = dict(finfuzz)
    return report


def write_v2_report(output_dir: Path | str, report: Mapping[str, object]) -> dict[str, object]:
    directory = Path(output_dir); directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# {report.get('suite', 'cn_agent_v2')} benchmark", "", f"数据集：{report.get('dataset')}", f"环境指纹：{report.get('environment', {}).get('fingerprint')}", "", "| 指标 | 值 | 状态 |", "|---|---:|---|"]
    for row in report.get("metrics", []):
        value = "N/A" if row.get("value") is None else f"{float(row['value']):.6f}"
        lines.append(f"| {row['metric']} | {value} | {row['status']} |")
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dict(report)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    query: str
    expected_tools: List[str]
    required_arguments: Dict[str, Dict[str, object]]
    required_evidence: List[str]
    expected_status: str = "ok"
    snapshot_path: Optional[str] = None
    research_as_of: Optional[str] = None
    validator_expected: Optional[bool] = None
    required_metrics: List[str] = field(default_factory=list)
    requires_evidence: bool = False
    requested_valuation_method: Optional[str] = None


def load_cases(path: Path | str) -> List[BenchmarkCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [BenchmarkCase(**item) for item in payload["cases"]]


def evaluate_case(case: BenchmarkCase, trace: Iterable[Dict[str, object]], *, evidence_ids: Iterable[str] = ()) -> Dict[str, object]:
    """Score a captured trace without invoking an LLM or a data provider."""
    calls = list(trace)
    called_tools = [str(call.get("tool_name", "")) for call in calls]
    expected = set(case.expected_tools)
    actual = set(called_tools)
    if not expected and not actual:
        tool_precision = tool_recall = tool_f1 = 1.0
    else:
        tool_precision = len(expected & actual) / len(actual) if actual else 0.0
        tool_recall = len(expected & actual) / len(expected) if expected else 1.0
        tool_f1 = 0.0 if tool_precision + tool_recall == 0 else 2 * tool_precision * tool_recall / (tool_precision + tool_recall)
    arguments_ok = True
    for tool_name, requirements in case.required_arguments.items():
        matching = [call for call in calls if call.get("tool_name") == tool_name]
        arguments_ok = arguments_ok and bool(matching) and any(
            all((call.get("arguments") or {}).get(key) == value for key, value in requirements.items())
            for call in matching
        )
    evidence = set(evidence_ids)
    coverage = len(evidence & set(case.required_evidence)) / len(case.required_evidence) if case.required_evidence else 1.0
    status_ok = not calls if not expected else bool(calls) and str(calls[-1].get("result_status")) == case.expected_status
    return {"case_id": case.case_id, "tool_f1": tool_f1, "parameters_ok": arguments_ok,
            "evidence_coverage": coverage, "status_ok": status_ok,
            "passed": tool_f1 == 1.0 and arguments_ok and coverage == 1.0 and status_ok}


def summarize(results: Iterable[Dict[str, object]]) -> Dict[str, object]:
    rows = list(results)
    if not rows:
        return {"cases": 0, "tool_f1": 0.0, "parameter_accuracy": 0.0, "evidence_coverage": 0.0, "e2e_success_rate": 0.0}
    size = len(rows)
    return {
        "cases": size,
        "tool_f1": sum(float(row["tool_f1"]) for row in rows) / size,
        "parameter_accuracy": sum(bool(row["parameters_ok"]) for row in rows) / size,
        "evidence_coverage": sum(float(row["evidence_coverage"]) for row in rows) / size,
        "e2e_success_rate": sum(bool(row["passed"]) for row in rows) / size,
        "avg_latency_seconds": sum(float(row.get("latency_seconds", 0.0)) for row in rows) / size,
        "avg_tool_calls": sum(int(row.get("tool_calls", 0)) for row in rows) / size,
        "avg_llm_calls": sum(int(row.get("llm_calls", 0)) for row in rows) / size,
        "total_cost_usd": sum(float(row.get("cost_usd", 0.0)) for row in rows),
    }


def evaluate_research_state(case: BenchmarkCase, state: ResearchState) -> Dict[str, object]:
    """Evaluate the trace and evidence produced by one real research execution."""
    trace_evidence = [evidence_id for trace in state.tool_trace for evidence_id in trace.evidence_ids]
    result = evaluate_case(
        case,
        (trace.__dict__ for trace in state.tool_trace),
        evidence_ids=[*state.facts, *state.calculations, *trace_evidence],
    )
    # Keep the captured state in JSON results so a measured score remains
    # auditable: callers can inspect actual arguments, tool errors, evidence,
    # validator output, and cost rather than trusting an aggregate metric.
    validator_ok = True
    if case.validator_expected is not None:
        validator_ok = bool(state.validation_result) and bool(state.validation_result.get("valid")) == case.validator_expected
    result["validator_ok"] = validator_ok
    result["passed"] = bool(result["passed"]) and validator_ok
    result.update({"trace_id": state.trace_id, "query": state.query, "tool_calls": len(state.tool_trace),
                   "research_state": state.to_dict()})
    cost_trace = state.cost_trace
    result["cost_usd"] = sum(float(item.get("cost_usd", 0.0)) for item in cost_trace)
    result["llm_calls"] = sum(int(item.get("llm_calls", 0)) for item in cost_trace)
    return result


class BenchmarkRegressionError(AssertionError):
    """Raised when a benchmark summary falls below its accepted baseline."""


def build_ablation_report(variant_runs: Mapping[str, Mapping[str, object]]) -> Dict[str, object]:
    """Build a like-for-like comparison from captured benchmark result JSON.

    Values are copied from completed runs only; this function deliberately does
    not invent a missing variant or turn an unavailable LLM run into a score.
    """
    unknown = set(variant_runs) - set(ABLATION_VARIANTS)
    if unknown:
        raise ValueError(f"Unknown ablation variants: {', '.join(sorted(unknown))}")
    if not variant_runs:
        raise ValueError("At least one captured benchmark run is required.")

    compatibility = {}
    rows = []
    for name, payload in variant_runs.items():
        summary = payload.get("summary")
        if not isinstance(summary, Mapping):
            raise ValueError(f"Variant {name} has no benchmark summary.")
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError(f"Variant {name} metadata must be an object.")
        for key in ("benchmark_version", "snapshot_id"):
            value = metadata.get(key)
            if value is not None:
                compatibility.setdefault(key, value)
                if compatibility[key] != value:
                    raise ValueError(f"Ablation runs use different {key} values.")
        rows.append({"variant": name, **{metric: summary.get(metric) for metric in METRIC_KEYS},
                     "cases": summary.get("cases")})
    return {"variants": rows, "metadata": compatibility, "missing_variants": [name for name in ABLATION_VARIANTS if name not in variant_runs]}


def write_ablation_report(output_dir: Path | str, variant_runs: Mapping[str, Mapping[str, object]]) -> Dict[str, object]:
    """Write machine-readable and Markdown ablation tables from captured runs."""
    report = build_ablation_report(variant_runs)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ablation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ("variant", "cases", *METRIC_KEYS)
    with (directory / "ablation.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["variants"])
    table = ["| 配置 | 案例数 | 工具 F1 | 参数准确率 | 证据覆盖率 | 端到端成功率 |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in report["variants"]:
        table.append("| {variant} | {cases} | {tool_f1:.3f} | {parameter_accuracy:.3f} | {evidence_coverage:.3f} | {e2e_success_rate:.3f} |".format(**row))
    if report["missing_variants"]:
        table.extend(["", "未测量的配置：" + "、".join(report["missing_variants"]) + "。"])
    (directory / "ablation.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    return report


def check_regression(
    summary: Mapping[str, object], baseline: Mapping[str, object], *, max_regression: Optional[Mapping[str, float]] = None,
) -> Dict[str, object]:
    """Compare summary metrics to a baseline using absolute tolerated decreases."""
    limits = dict(max_regression or {})
    regressions = []
    for metric in METRIC_KEYS:
        if metric not in baseline:
            continue
        current, previous = float(summary[metric]), float(baseline[metric])
        allowed = float(limits.get(metric, 0.0))
        if current < previous - allowed:
            regressions.append({"metric": metric, "baseline": previous, "current": current, "allowed_drop": allowed})
    return {"passed": not regressions, "regressions": regressions}


class BenchmarkRunner:
    """Run fixture cases against real ``ResearchState`` objects and persist reports."""

    def __init__(self, cases: Sequence[BenchmarkCase]):
        self.cases = list(cases)

    async def run(
        self,
        execute_case: Callable[[BenchmarkCase], ResearchState | Awaitable[ResearchState]],
        *,
        output_dir: Path | str,
        baseline_path: Path | str | None = None,
        max_regression: Optional[Mapping[str, float]] = None,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        """Execute every case, write ``results.json``/``results.csv``, then gate regressions."""
        rows = []
        for case in self.cases:
            started_at = time.monotonic()
            state = execute_case(case)
            if inspect.isawaitable(state):
                state = await state
            if not isinstance(state, ResearchState):
                raise TypeError(f"Benchmark executor for {case.case_id} must return ResearchState.")
            row = evaluate_research_state(case, state)
            row["latency_seconds"] = time.monotonic() - started_at
            rows.append(row)

        payload: Dict[str, object] = {"summary": summarize(rows), "results": rows, "metadata": dict(metadata or {})}
        if baseline_path is not None:
            baseline_payload = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
            baseline = baseline_payload.get("summary", baseline_payload)
            payload["regression"] = check_regression(payload["summary"], baseline, max_regression=max_regression)

        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_csv(directory / "results.csv", rows)
        if payload.get("regression", {}).get("passed") is False:
            details = payload["regression"]["regressions"]
            raise BenchmarkRegressionError(f"Benchmark regression detected: {details}")
        return payload

    @staticmethod
    def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
        fields = ("case_id", "trace_id", "query", "tool_calls", "llm_calls", "latency_seconds", "cost_usd", "tool_f1", "parameters_ok", "evidence_coverage", "status_ok", "validator_ok", "passed")
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


@dataclass(frozen=True)
class BenchmarkV2Case:
    case_id: str
    split: str
    input_type: str
    expected: dict[str, object] = field(default_factory=dict)
    truth: list[dict[str, object]] = field(default_factory=list)


def load_v2_cases(root: Path | str, split: str = "synthetic") -> list[BenchmarkV2Case]:
    """Load one split and reject accidental real/holdout mixing."""
    if split not in {"synthetic", "real", "holdout"}:
        raise ValueError("split must be synthetic, real, or holdout")
    path = Path(root) / f"{split}.json" if Path(root).is_dir() else Path(root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    declared = payload.get("split", split)
    if declared != split:
        raise ValueError(f"dataset split mismatch: requested {split}, file declares {declared}")
    if split != "synthetic" and payload.get("offline_fixture", False):
        raise ValueError("real/holdout data cannot be marked as an offline fixture")
    return [BenchmarkV2Case(item["case_id"], split, str(item.get("input_type", "document")), dict(item.get("expected", {})), list(item.get("truth", []))) for item in payload.get("cases", [])]


def run_v2_cli(argv: Sequence[str] | None = None) -> int:
    """Small offline CLI used by ``python -m src.cn.benchmark``."""
    import argparse
    parser = argparse.ArgumentParser(description="FinTrace-CN v2 benchmark")
    parser.add_argument("--suite", default="cn_agent_v2")
    parser.add_argument("--set", dest="split", default="synthetic", choices=("synthetic", "real", "holdout"))
    parser.add_argument("--out", default="output/benchmark")
    parser.add_argument("--dataset-root", default="tests/fixtures/cn/benchmark_v2")
    args = parser.parse_args(argv)
    cases = load_v2_cases(args.dataset_root, args.split)
    report = build_v2_report(suite=args.suite, dataset=args.split, metrics={}, metadata={"case_count": len(cases), "network": False, "status": "fixture inventory only"})
    write_v2_report(Path(args.out) / args.suite / args.split, report)
    print(json.dumps({"suite": args.suite, "set": args.split, "cases": len(cases), "report": str(Path(args.out) / args.suite / args.split)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_v2_cli())
