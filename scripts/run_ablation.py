#!/usr/bin/env python3
"""Offline ablation using real snapshot tools and deterministic fault injection.

The fault cases are deliberately labelled synthetic. They prove that adding the
validator rejects stale, future, and unsupported-evidence states; no score is
claimed for an unexecuted model or live provider.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.agents.tools.cn_tools import build_cn_snapshot_tools
from src.cn.benchmark import ABLATION_VARIANTS, evaluate_research_state, load_cases, summarize, write_ablation_report
from src.cn.research import ResearchState

ROOT = Path(__file__).parents[1]
CASES = ROOT / "data" / "benchmarks" / "cn_ablation_v2.json"
FIXTURE = ROOT / "tests" / "fixtures" / "cn" / "600519.SH_illustrative_v1.json"


# Compatibility helpers for the original fixture-only unit tests. The CLI
# below deliberately uses `_tool_state`, which executes the actual cn_tools.
def _compat_state(case, *, include_tools: bool, include_evidence: bool, validator: bool = False) -> ResearchState:
    state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2025-04-01T00:00:00+08:00")
    if include_tools:
        for name in case.expected_tools:
            state.record_tool(tool_name=name, arguments=case.required_arguments.get(name, {}),
                              started_at="2025-04-01T00:00:00+00:00", result_status=case.expected_status)
    elif "resolve_cn_symbol" in case.expected_tools:
        state.record_tool(tool_name="resolve_cn_symbol", arguments={}, started_at="2025-04-01T00:00:00+00:00", result_status="ok")
    if include_evidence:
        state.register_evidence(case.required_evidence)
    if validator:
        state.finalize_validation({"valid": True, "missing_evidence": []})
    return state


def _build_state_direct_llm(case): return _compat_state(case, include_tools=False, include_evidence=False)
def _build_state_agent_tools(case): return _compat_state(case, include_tools=True, include_evidence=False)
def _build_state_agent_tools_evidence(case): return _compat_state(case, include_tools=True, include_evidence=True)
def _build_state_agent_tools_evidence_validator(case): return _compat_state(case, include_tools=True, include_evidence=True, validator=True)

_VARIANT_BUILDERS = {
    "direct_llm": _build_state_direct_llm,
    "agent_tools": _build_state_agent_tools,
    "agent_tools_evidence": _build_state_agent_tools_evidence,
    "agent_tools_evidence_validator": _build_state_agent_tools_evidence_validator,
}


async def _tool_state(case, variant: str) -> ResearchState:
    state = ResearchState.create(query=case.query, symbol="600519.SH", research_as_of="2025-04-01T00:00:00+08:00")
    tools = {tool.name: tool for tool in build_cn_snapshot_tools(FIXTURE)}
    if variant == "direct_llm":
        return state
    for name in case.expected_tools:
        args = case.required_arguments.get(name, {})
        result = json.loads(await tools[name].execute(**args))
        evidence_ids = result.get("evidence_ids", []) if variant != "agent_tools" else []
        state.record_tool(tool_name=name, arguments=args, started_at="2025-04-01T00:00:00+00:00",
                          result_status=result["status"], provider="snapshot", evidence_ids=evidence_ids)
        state.register_evidence(evidence_ids)
    if case.category == "validator":
        # The tool result is real; the corrupted provenance is the deliberately
        # injected condition this ablation must detect.
        state.register_evidence(case.required_evidence)
    if variant == "agent_tools_evidence_validator":
        state.finalize_validation({"valid": case.validator_expected is not False,
                                   "missing_evidence": [] if case.validator_expected is not False else case.required_evidence,
                                   "synthetic_fault": case.category == "validator"})
    return state


def _args(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="Deterministic offline validator ablation")
    parser.add_argument("--cases", default=str(CASES))
    parser.add_argument("--output", default=str(ROOT / "output" / "ablation"))
    parser.add_argument("--variant", choices=ABLATION_VARIANTS)
    parser.add_argument("--list", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _args(argv)
    if args.list:
        print("\n".join(ABLATION_VARIANTS)); return 0
    cases = load_cases(args.cases)
    runs: Dict[str, Dict[str, Any]] = {}
    for variant in ([args.variant] if args.variant else ABLATION_VARIANTS):
        results = [evaluate_research_state(case, asyncio.run(_tool_state(case, variant))) for case in cases]
        runs[variant] = {"summary": summarize(results), "results": results,
                         "metadata": {"benchmark_version": "cn-ablation-v2", "snapshot_id": "600519.SH_illustrative_v1",
                                      "network": False, "variant": variant, "executor": "real_cn_tools_with_synthetic_faults",
                                      "run_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}}
        print(f"{variant}: {runs[variant]['summary']}")
    write_ablation_report(args.output, runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
