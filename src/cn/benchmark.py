"""Offline, deterministic benchmark primitives for FinTrace-CN agent traces."""

from __future__ import annotations

import json
import csv
import inspect
from dataclasses import dataclass
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


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    query: str
    expected_tools: List[str]
    required_arguments: Dict[str, Dict[str, object]]
    required_evidence: List[str]
    expected_status: str = "ok"


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
    }


def evaluate_research_state(case: BenchmarkCase, state: ResearchState) -> Dict[str, object]:
    """Evaluate the trace and evidence produced by one real research execution."""
    trace_evidence = [evidence_id for trace in state.tool_trace for evidence_id in trace.evidence_ids]
    result = evaluate_case(
        case,
        (trace.__dict__ for trace in state.tool_trace),
        evidence_ids=[*state.facts, *state.calculations, *trace_evidence],
    )
    result.update({"trace_id": state.trace_id, "query": state.query, "tool_calls": len(state.tool_trace)})
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
    table = ["| Variant | Cases | Tool F1 | Parameter accuracy | Evidence coverage | E2E success |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in report["variants"]:
        table.append("| {variant} | {cases} | {tool_f1:.3f} | {parameter_accuracy:.3f} | {evidence_coverage:.3f} | {e2e_success_rate:.3f} |".format(**row))
    if report["missing_variants"]:
        table.extend(["", "Missing (not measured): " + ", ".join(report["missing_variants"]) + "."])
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
            state = execute_case(case)
            if inspect.isawaitable(state):
                state = await state
            if not isinstance(state, ResearchState):
                raise TypeError(f"Benchmark executor for {case.case_id} must return ResearchState.")
            rows.append(evaluate_research_state(case, state))

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
        fields = ("case_id", "trace_id", "query", "tool_calls", "tool_f1", "parameters_ok", "evidence_coverage", "status_ok", "passed")
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
