#!/usr/bin/env python3
"""Run the FinTrace-CN benchmark against a real offline agent trajectory.

The ``--model`` option is deliberately required: without it this command only
lists cases, which prevents an accidental bill.  All data tools read one pinned
local snapshot and never call Tushare or another network provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
# The application-level LLM package is imported as ``llms`` by the offline
# runner, while other project modules use the ``src.*`` namespace.
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

from src.cn.benchmark import BenchmarkCase, BenchmarkRunner, load_cases
from src.cn.offline_agent import OfflineCnAgent, SYSTEM_PROMPT


DEFAULT_CASES = PROJECT_ROOT / "data" / "benchmarks" / "cn_agent_v1.json"
DEFAULT_SNAPSHOTS = PROJECT_ROOT / "data" / "snapshots" / "cn"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "benchmark"


def _git_commit() -> str:
    """Return the checked-out commit without making benchmark execution depend on Git."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real offline A-share Agent benchmark")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="Benchmark JSON file")
    parser.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOTS), help="Directory containing pinned snapshots")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output directory")
    parser.add_argument("--category", default=None, help="Run only a benchmark category")
    parser.add_argument("--model", default=None, help="Registered LLM model to invoke (required for a run)")
    parser.add_argument("--temperature", type=float, default=0.0, help="Fixed LLM temperature")
    parser.add_argument("--max-steps", type=int, default=6, help="Fixed maximum tool-calling steps")
    parser.add_argument("--all-snapshots", action="store_true", help="Build one price-routing case for every local snapshot")
    parser.add_argument("--list", action="store_true", dest="list_cases", help="List cases and exit")
    return parser.parse_args(argv)


def _snapshot_for(case, snapshot_dir: Path) -> Path:
    if case.snapshot_path:
        path = Path(case.snapshot_path)
        return path if path.is_absolute() else PROJECT_ROOT / path
    ticker = "600519.SH"
    for requirements in case.required_arguments.values():
        if requirements.get("ticker"):
            ticker = str(requirements["ticker"])
            break
    matches = sorted(snapshot_dir.glob(f"{ticker}_*.json"))
    if not matches:
        raise FileNotFoundError(f"No local snapshot available for {case.case_id} ({ticker}).")
    return matches[-1]


def _all_snapshot_cases(snapshot_dir: Path) -> list[BenchmarkCase]:
    """Create one evidence-backed routing case per pinned local snapshot."""
    cases = []
    for path in sorted(snapshot_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        ticker = str(payload["symbol"])
        bars = [bar for bar in payload.get("data", {}).get("bars", []) if bar.get("adjustment") == "RAW"]
        if not bars:
            continue
        latest = max(bars, key=lambda item: item["trade_date"])
        cases.append(BenchmarkCase(
            case_id=f"snapshot-price-{ticker.replace('.', '-').lower()}", category="snapshot_routing",
            query=f"Use the offline snapshot to fetch the closing price for {ticker} and return its evidence ID.",
            expected_tools=["resolve_cn_symbol", "get_cn_prices"],
            required_arguments={"resolve_cn_symbol": {"query": ticker}, "get_cn_prices": {"ticker": ticker}},
            required_evidence=[f"fact_{ticker.replace('.', '_')}_close_{latest['trade_date']}_RAW"],
            snapshot_path=str(path.relative_to(PROJECT_ROOT)), research_as_of=payload["research_as_of"],
        ))
    return cases


async def _run(args: argparse.Namespace, cases) -> dict:
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_paths = [_snapshot_for(case, snapshot_dir) for case in cases]
    snapshot_ids = sorted({json.loads(path.read_text(encoding="utf-8"))["snapshot_id"] for path in snapshot_paths})

    async def execute(case):
        agent = OfflineCnAgent(snapshot_path=_snapshot_for(case, snapshot_dir), model_name=args.model,
                               temperature=args.temperature, max_steps=args.max_steps,
            required_metrics=case.required_metrics,
                               requested_valuation_method=case.requested_valuation_method)
        return await agent.run(case.query)

    metadata = {
        "benchmark_version": "cn-snapshot-e2e-v1" if args.all_snapshots else json.loads(Path(args.cases).read_text(encoding="utf-8"))["version"],
        "snapshot_id": snapshot_ids[0] if len(snapshot_ids) == 1 else snapshot_ids,
        "snapshot_ids": snapshot_ids,
        "model": args.model,
        "temperature": args.temperature,
        "max_steps": args.max_steps,
        "network": False,
        "executor": "OfflineCnAgent",
        "prompt_version": f"offline-cn-agent-{hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:12]}",
        "git_commit": _git_commit(),
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }
    return await BenchmarkRunner(cases).run(execute, output_dir=args.output, metadata=metadata)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    cases = _all_snapshot_cases(Path(args.snapshot_dir)) if args.all_snapshots else load_cases(args.cases)
    if args.list_cases:
        for case in cases:
            print(f"{case.case_id:<14} {case.category:<10} {case.query}")
        return 0
    if not args.model:
        print("ERROR: --model is required to run a real Agent benchmark; use --list for the free case inventory.", file=sys.stderr)
        return 2
    if args.category:
        cases = [case for case in cases if case.category == args.category]
        if not cases:
            print(f"ERROR: no cases found for category '{args.category}'", file=sys.stderr)
            return 1
    try:
        payload = asyncio.run(_run(args, cases))
    except Exception as exc:
        print(f"ERROR: benchmark failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"Results written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
