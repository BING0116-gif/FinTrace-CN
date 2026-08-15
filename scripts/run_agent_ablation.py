#!/usr/bin/env python3
"""Real LLM Agent Ablation — compare four configurations on the same fixture cases.

Usage::

    # List available cases
    python scripts/run_agent_ablation.py --list

    # Run all 4 variants against all cases (requires --model)
    python scripts/run_agent_ablation.py --model gpt-4o-mini

    # Run a single variant
    python scripts/run_agent_ablation.py --model gpt-4o-mini --variant agent_tools_evidence_validator

    # Dry-run with mock provider (no actual LLM call)
    python scripts/run_agent_ablation.py --dry-run

The ``--model`` option is deliberately required for a real run to prevent
accidental billing.  Use ``--dry-run`` for offline testing.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.cn.ablation_agent import (
    ABLATION_VARIANTS,
    AblationAgent,
    compute_ablation_metrics,
)
from src.cn.benchmark import (
    METRIC_KEYS,
    BenchmarkCase,
    evaluate_research_state,
    load_cases,
    summarize,
    write_ablation_report,
)

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_CASES = PROJECT_ROOT / "data" / "benchmarks" / "cn_agent_ablation_v3.json"
DEFAULT_SNAPSHOTS = PROJECT_ROOT / "data" / "snapshots" / "cn"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "agent_ablation"

# Relative paths in fixture cases are resolved against PROJECT_ROOT
CASE_SNAPSHOT_DIRS = [
    PROJECT_ROOT / "tests" / "fixtures" / "cn",
    PROJECT_ROOT / "data" / "snapshots" / "cn",
]


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real LLM Agent Ablation — compare 4 configurations"
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="Fixture cases JSON file")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output directory")
    parser.add_argument("--model", default=None, help="Registered LLM model (required for real run)")
    parser.add_argument("--variant", choices=ABLATION_VARIANTS, help="Run only one variant")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature")
    parser.add_argument("--max-steps", type=int, default=6, help="Max ReAct steps")
    parser.add_argument("--dry-run", action="store_true", help="Use mock provider, no LLM cost")
    parser.add_argument("--list", action="store_true", help="List cases and exit")
    return parser.parse_args(argv)


def _resolve_snapshot(case: BenchmarkCase) -> Path:
    """Resolve a case's snapshot_path to an absolute path."""
    if not case.snapshot_path:
        # Fallback: use the default snapshot
        return DEFAULT_SNAPSHOTS / "600519.SH_20260810_tushare_v1.json"
    path = Path(case.snapshot_path)
    if path.is_absolute():
        return path
    # Try relative to PROJECT_ROOT
    absolute = PROJECT_ROOT / path
    if absolute.exists():
        return absolute
    # Try each snapshot dir
    for directory in CASE_SNAPSHOT_DIRS:
        candidate = directory / path.name
        if candidate.exists():
            return candidate
        candidate = directory / path
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Snapshot not found for case {case.case_id}: {case.snapshot_path}. "
        f"Tried: {absolute}, and each of {[str(d) for d in CASE_SNAPSHOT_DIRS]}"
    )


# ---------------------------------------------------------------------------
# Mock provider for dry-run testing
# ---------------------------------------------------------------------------

class _MockProvider:
    """Simulates an LLM that always calls the expected tools correctly."""

    model_name = "mock-model"
    api_style = "openai"

    def __init__(self, case: BenchmarkCase):
        self._case = case
        self._turns = 0

    async def call_with_tools(self, messages, tools, temperature=0.0, **kwargs):
        from types import SimpleNamespace
        from src.llms.async_client import LLMToolResponse, ToolCall

        self._turns += 1
        expected = self._case.expected_tools

        if self._turns <= len(expected):
            tool_name = expected[self._turns - 1]
            args = self._case.required_arguments.get(tool_name, {})
            call = ToolCall(id=f"call-{self._turns}", name=tool_name, arguments=args, parse_error=None)
            return LLMToolResponse(
                text="",
                tool_calls=[call],
                cost=0.001,
                raw={"role": "assistant", "tool_calls": []},
            )
        # No more tools expected
        return LLMToolResponse(
            text=f"已完成对 {self._case.query} 的分析。",
            tool_calls=[],
            cost=0.001,
            raw={"role": "assistant", "content": "已完成。"},
        )

    async def __call__(self, messages, temperature=0.0):
        return f"Mock response for: {self._case.query}", 0.001


async def _run_single(
    case: BenchmarkCase,
    variant: str,
    model_name: str,
    temperature: float,
    max_steps: int,
    output_dir: Path,
    dry_run: bool,
) -> Dict[str, Any]:
    """Run one case in one variant, return the evaluated result."""
    snapshot_path = _resolve_snapshot(case)
    print(f"  [{variant}] {case.case_id} ...", end="", flush=True)

    start = time.monotonic()
    if dry_run:
        provider = _MockProvider(case)
        agent = AblationAgent(
            variant=variant,
            snapshot_path=snapshot_path,
            model_name=model_name,
            temperature=temperature,
            max_steps=max_steps,
            provider=provider,
            research_as_of=case.research_as_of,
            required_metrics=case.required_metrics,
            requires_evidence=case.requires_evidence,
            requested_valuation_method=case.requested_valuation_method,
        )
    else:
        agent = AblationAgent(
            variant=variant,
            snapshot_path=snapshot_path,
            model_name=model_name,
            temperature=temperature,
            max_steps=max_steps,
            research_as_of=case.research_as_of,
            required_metrics=case.required_metrics,
            requires_evidence=case.requires_evidence,
            requested_valuation_method=case.requested_valuation_method,
        )

    state = await agent.run(case.query)
    latency = time.monotonic() - start

    # Evaluate the result
    result = evaluate_research_state(case, state)

    # Add ablation-specific metrics
    result["latency_seconds"] = round(latency, 2)
    result["cost_usd"] = round(agent.total_cost, 6)
    result["step_times"] = [round(t, 3) for t in agent.step_times]
    result["variant"] = variant
    result["validator_intercepted"] = agent.validator_intercepted
    result["validator_errors"] = agent.validator_errors

    # Leakage must include gate misses, not only successful interceptions.  A
    # known-negative case or a tool-error trajectory is safe only when the
    # final state is explicitly invalid and the answer is a rejection.
    rejection_phrases = ["无法验证", "拒绝结论", "拒绝"]
    has_rejection = any(phrase in (agent.answer or "") for phrase in rejection_phrases)
    validation_rejected = bool(state.validation_result) and not bool(
        state.validation_result.get("valid", True)
    )
    negative_case = case.validator_expected is False
    has_tool_error = any(trace.result_status != "ok" for trace in state.tool_trace)
    result["error_conclusion_leakage"] = bool(
        (negative_case or has_tool_error) and not (has_rejection and validation_rejected)
    )

    print(f"  done ({latency:.1f}s, ${agent.total_cost:.6f})")
    return result


async def _run_ablation(args: argparse.Namespace, cases: List[BenchmarkCase]) -> None:
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    variants = [args.variant] if args.variant else list(ABLATION_VARIANTS)
    model_name = args.model if args.model else ("mock" if args.dry_run else "unknown")

    all_results: Dict[str, List[Dict[str, Any]]] = {}
    case_list_text = []

    for variant in variants:
        print(f"\n{'=' * 60}")
        print(f"Variant: {variant}")
        print(f"{'=' * 60}")
        variant_results = []
        for case in cases:
            try:
                result = await _run_single(
                    case, variant, model_name, args.temperature,
                    args.max_steps, output_dir, args.dry_run,
                )
                variant_results.append(result)
            except Exception as exc:
                print(f"  ERROR: {exc}")
                variant_results.append({
                    "case_id": case.case_id,
                    "variant": variant,
                    "passed": False,
                    "tool_f1": 0.0,
                    "parameters_ok": False,
                    "evidence_coverage": 0.0,
                    "status_ok": False,
                    "validator_ok": False,
                    "latency_seconds": 0.0,
                    "cost_usd": 0.0,
                    "error_conclusion_leakage": True,
                    "validator_intercepted": False,
                    "validator_errors": [str(exc)],
                    "step_times": [],
                    "error": str(exc),
                })
        all_results[variant] = variant_results
        summary = summarize(variant_results)
        print(f"\n  Summary: {summary}")

    # Compute aggregate metrics
    metrics = compute_ablation_metrics(all_results)

    # Write results
    _write_ablation_outputs(output_dir, all_results, metrics, model_name, args.dry_run)

    # Print comparison table
    _print_comparison_table(metrics)

    print(f"\nResults written to {output_dir}")


def _write_ablation_outputs(
    output_dir: Path,
    all_results: Dict[str, List[Dict[str, Any]]],
    metrics: Dict[str, Dict[str, Any]],
    model_name: str,
    dry_run: bool,
) -> None:
    """Write ablation results to JSON, CSV, and Markdown files."""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    # Full results JSON
    payload = {
        "benchmark_version": "cn-agent-ablation-v3",
        "model": model_name,
        "dry_run": dry_run,
        "run_at": timestamp,
        "variants": list(metrics.keys()),
        "metrics": metrics,
        "detailed_results": all_results,
    }
    (output_dir / "ablation_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Per-variant summary CSV
    fields = ["variant", "cases", *METRIC_KEYS,
              "validator_intercept_rate", "error_conclusion_leakage",
              "avg_latency_seconds", "total_cost_usd"]
    with (output_dir / "ablation_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for variant, m in metrics.items():
            row = {"variant": variant, **m}
            writer.writerow(row)

    # Per-case detail CSV
    detail_fields = ["variant", "case_id", "tool_f1", "parameters_ok",
                     "evidence_coverage", "passed", "validator_intercepted",
                     "error_conclusion_leakage", "latency_seconds", "cost_usd"]
    with (output_dir / "ablation_details.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=detail_fields, extrasaction="ignore")
        writer.writeheader()
        for variant, rows in all_results.items():
            for row in rows:
                row["variant"] = variant
                writer.writerow({k: row.get(k) for k in detail_fields})

    # Markdown comparison table
    lines = [
        f"# Agent 消融实验报告",
        f"",
        f"- **模型**：{model_name}",
        f"- **离线演练**：{dry_run}",
        f"- **运行时间**：{timestamp}",
        f"",
        f"## 汇总指标",
        f"",
        f"| 配置 | 案例数 | 工具 F1 | 参数准确率 | 证据覆盖率 | 端到端成功率 | Validator 拦截率 | 错误结论泄漏率 | 平均延迟 | 总成本 |",
        f"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in ABLATION_VARIANTS:
        m = metrics.get(variant, {})
        lines.append(
            f"| {variant} | {m.get('cases', 0)} | "
            f"{m.get('tool_f1', 0):.4f} | {m.get('parameter_accuracy', 0):.4f} | "
            f"{m.get('evidence_coverage', 0):.4f} | {m.get('e2e_success_rate', 0):.4f} | "
            f"{m.get('validator_intercept_rate', 0):.4f} | {m.get('error_conclusion_leakage', 0):.4f} | "
            f"{m.get('avg_latency_seconds', 0):.1f}s | ${m.get('total_cost_usd', 0):.4f} |"
        )

    lines.extend([
        "",
        "## 单案例结果",
        "",
        "| 配置 | 案例 | 工具 F1 | 参数 | 证据 | 通过 | 已拦截 | 泄漏 | 延迟 | 成本 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for variant in ABLATION_VARIANTS:
        rows = all_results.get(variant, [])
        for row in rows:
            lines.append(
                f"| {variant} | {row.get('case_id', '')} | "
                f"{row.get('tool_f1', 0):.2f} | {'Y' if row.get('parameters_ok') else 'N'} | "
                f"{row.get('evidence_coverage', 0):.2f} | {'Y' if row.get('passed') else 'N'} | "
                f"{'Y' if row.get('validator_intercepted') else 'N'} | "
                f"{'Y' if row.get('error_conclusion_leakage') else 'N'} | "
                f"{row.get('latency_seconds', 0):.1f}s | ${row.get('cost_usd', 0):.4f} |"
            )

    (output_dir / "ablation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_comparison_table(metrics: Dict[str, Dict[str, Any]]) -> None:
    """Print a human-readable comparison table to stdout."""
    print(f"\n{'=' * 90}")
    print("Ablation Comparison")
    print(f"{'=' * 90}")
    header = f"{'Variant':<30} {'Cases':>6} {'F1':>8} {'Param':>8} {'Evid':>8} {'E2E':>8} {'Intercept':>10} {'Leakage':>10} {'Lat':>8} {'Cost':>10}"
    print(header)
    print("-" * 90)
    for variant in ABLATION_VARIANTS:
        m = metrics.get(variant, {})
        print(
            f"{variant:<30} {m.get('cases', 0):>6} "
            f"{m.get('tool_f1', 0):>8.4f} {m.get('parameter_accuracy', 0):>8.4f} "
            f"{m.get('evidence_coverage', 0):>8.4f} {m.get('e2e_success_rate', 0):>8.4f} "
            f"{m.get('validator_intercept_rate', 0):>10.4f} {m.get('error_conclusion_leakage', 0):>10.4f} "
            f"{m.get('avg_latency_seconds', 0):>6.1f}s ${m.get('total_cost_usd', 0):>8.4f}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    cases = load_cases(args.cases)

    if args.list:
        print(f"{'Case ID':<20} {'Category':<12} {'Query'}")
        print("-" * 80)
        for case in cases:
            print(f"{case.case_id:<20} {case.category:<12} {case.query}")
        return 0

    if not args.model and not args.dry_run:
        print(
            "ERROR: --model is required for a real run; use --dry-run for offline testing, "
            "or --list for the free case inventory.",
            file=sys.stderr,
        )
        return 2

    asyncio.run(_run_ablation(args, cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
