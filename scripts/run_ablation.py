#!/usr/bin/env python3
"""Ablation comparison runner for A-share benchmark variants.

Usage:
    python scripts/run_ablation.py                          # run all 4 variants
    python scripts/run_ablation.py --list                   # list variants
    python scripts/run_ablation.py --variant direct_llm     # single variant
    python scripts/run_ablation.py --output results/ablation # custom output
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.cn.benchmark import (
    ABLATION_VARIANTS, BenchmarkRunner, evaluate_research_state, load_cases,
    summarize, write_ablation_report,
)
from src.cn.research import ResearchState

_PROJECT_ROOT = Path(__file__).parents[1]
_DEFAULT_CASES = _PROJECT_ROOT / "data" / "benchmarks" / "cn_agent_v1.json"
_DEFAULT_OUTPUT = _PROJECT_ROOT / "output" / "ablation"


# ---------------------------------------------------------------------------
# Ablation variant executors
# ---------------------------------------------------------------------------

def _build_state_direct_llm(case):
    """Variant: direct_llm — no tools, no evidence, just raw LLM output.

    Simulates a "blind" LLM response that gets the symbol right but
    has no financial data support.
    """
    state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2026-08-10T00:00:00+08:00")
    # Only record resolve_cn_symbol (direct LLM can guess the symbol)
    if "resolve_cn_symbol" in case.expected_tools:
        state.record_tool(tool_name="resolve_cn_symbol", arguments={}, started_at="2026-08-10T00:00:00+00:00",
                          ended_at="2026-08-10T00:00:05+00:00", result_status="ok")
    return state


def _build_state_agent_tools(case):
    """Variant: agent_tools — tools called, but no evidence registered."""
    state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2026-08-10T00:00:00+08:00")
    for tool_name in case.expected_tools:
        arguments = case.required_arguments.get(tool_name, {})
        state.record_tool(tool_name=tool_name, arguments=arguments, started_at="2026-08-10T00:00:00+00:00",
                          ended_at="2026-08-10T00:00:30+00:00", result_status=case.expected_status)
    # No evidence registered
    return state


def _build_state_agent_tools_evidence(case):
    """Variant: agent_tools_evidence — tools + evidence, but no validator."""
    state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2026-08-10T00:00:00+08:00")
    for tool_name in case.expected_tools:
        arguments = case.required_arguments.get(tool_name, {})
        state.record_tool(tool_name=tool_name, arguments=arguments, started_at="2026-08-10T00:00:00+00:00",
                          ended_at="2026-08-10T00:00:30+00:00", result_status=case.expected_status)
    state.register_evidence(case.required_evidence)
    return state


def _build_state_agent_tools_evidence_validator(case):
    """Variant: agent_tools_evidence_validator — full pipeline with validator."""
    state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2026-08-10T00:00:00+08:00")
    for tool_name in case.expected_tools:
        arguments = case.required_arguments.get(tool_name, {})
        state.record_tool(tool_name=tool_name, arguments=arguments, started_at="2026-08-10T00:00:00+00:00",
                          ended_at="2026-08-10T00:00:30+00:00", result_status=case.expected_status)
    state.register_evidence(case.required_evidence)
    if case.required_evidence:
        state.finalize_validation({"valid": True, "missing_evidence": []})
    return state


_VARIANT_BUILDERS = {
    "direct_llm": _build_state_direct_llm,
    "agent_tools": _build_state_agent_tools,
    "agent_tools_evidence": _build_state_agent_tools_evidence,
    "agent_tools_evidence_validator": _build_state_agent_tools_evidence_validator,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ablation comparison runner")
    parser.add_argument("--cases", default=str(_DEFAULT_CASES), help="Benchmark JSON file")
    parser.add_argument("--output", default=str(_DEFAULT_OUTPUT), help="Output directory")
    parser.add_argument("--variant", default=None, choices=ABLATION_VARIANTS, help="Run a single variant")
    parser.add_argument("--list", action="store_true", dest="list_variants", help="List variants and exit")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    if args.list_variants:
        print("Available ablation variants:")
        for v in ABLATION_VARIANTS:
            desc = _VARIANT_BUILDERS[v].__doc__.strip() if _VARIANT_BUILDERS[v].__doc__ else ""
            print(f"  {v:<40} {desc}")
        return 0

    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"ERROR: cases file not found: {cases_path}", file=sys.stderr)
        return 1

    cases = load_cases(cases_path)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    variants_to_run = [args.variant] if args.variant else list(ABLATION_VARIANTS)
    variant_runs: Dict[str, Dict[str, Any]] = {}

    print(f"Running ablation: {len(variants_to_run)} variants, {len(cases)} cases each")
    print()

    for variant_name in variants_to_run:
        builder = _VARIANT_BUILDERS[variant_name]
        results = []
        for case in cases:
            state = builder(case)
            results.append(evaluate_research_state(case, state))

        summary = summarize(results)
        variant_runs[variant_name] = {
            "summary": summary,
            "results": results,
            "metadata": {
                "benchmark_version": "cn-agent-v1",
                "snapshot_id": "offline_ablation",
                "network": False,
                "variant": variant_name,
                "run_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            },
        }
        print(f"  {variant_name:<40} "
              f"F1={summary['tool_f1']:.3f}  "
              f"Param={summary['parameter_accuracy']:.3f}  "
              f"Evid={summary['evidence_coverage']:.3f}  "
              f"E2E={summary['e2e_success_rate']:.3f}")

    # Generate ablation report
    report = write_ablation_report(output_dir, variant_runs)
    print(f"\nAblation report written to {output_dir}")
    print()
    print("Comparison table:")
    print("=" * 80)
    print(f"{'Variant':<40} {'Cases':>6} {'F1':>8} {'Param':>8} {'Evid':>8} {'E2E':>8}")
    print("-" * 80)
    for row in report["variants"]:
        print(f"{row['variant']:<40} {row['cases']:>6} {row['tool_f1']:>8.3f} "
              f"{row['parameter_accuracy']:>8.3f} {row['evidence_coverage']:>8.3f} "
              f"{row['e2e_success_rate']:>8.3f}")

    if report["missing_variants"]:
        print(f"\nNot measured: {', '.join(report['missing_variants'])}")

    # Check for regression from full pipeline
    full = variant_runs.get("agent_tools_evidence_validator", {}).get("summary", {})
    for variant_name, run in variant_runs.items():
        if variant_name != "agent_tools_evidence_validator" and full:
            s = run["summary"]
            ratio = s["e2e_success_rate"] / full["e2e_success_rate"] if full["e2e_success_rate"] > 0 else 0
            print(f"  {variant_name} vs full: {ratio:.2%} relative e2e")

    return 0


if __name__ == "__main__":
    sys.exit(main())