#!/usr/bin/env python3
"""Run the Loop-2 real-model benchmark for the shared CnResearchAgent.

Reproducible, cost-budgeted, checkpointing runner over the 24-case dataset.

Usage::

    # Free offline inventory
    python scripts/run_real_agent_benchmark.py --list

    # Offline dry-run with the mock provider (no model key, zero cost)
    python scripts/run_real_agent_benchmark.py --dry-run

    # Real-model run (--model required so a paid call is never accidental)
    python scripts/run_real_agent_benchmark.py --model gpt-4o-mini

    # Real run with a hard cost ceiling, resuming any interrupted cases
    python scripts/run_real_agent_benchmark.py --model gpt-4o-mini \
        --max-cost-usd 5.0 --resume

Artifacts under the output directory: metadata.json, results.json, cases.csv,
summary.md, failures.md, traces/<case>.json, comparison.json, checkpoint.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parents[1]))

# Load the project .env so a real run can resolve the model API key/base URL
# from the repository root (no-op if python-dotenv or the file is absent).
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parents[1] / ".env", override=False)
except Exception:  # pragma: no cover - dotenv is optional
    pass

from src.cn.real_benchmark import RealBenchmarkRunner, load_real_cases

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_CASES = PROJECT_ROOT / "benchmarks" / "cn_agent_v1.json"
DEFAULT_SNAPSHOTS = PROJECT_ROOT / "tests" / "fixtures" / "cn"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "real_benchmark"


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Loop-2 real-model Agent benchmark")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="24-case dataset JSON")
    parser.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOTS), help="Directory of pinned snapshots")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output directory")
    parser.add_argument("--category", default=None, help="Run only a benchmark category")
    parser.add_argument("--model", default=None, help="Registered LLM model (required for a real run)")
    parser.add_argument("--temperature", type=float, default=0.0, help="Fixed LLM temperature")
    parser.add_argument("--max-steps", type=int, default=6, help="Maximum ReAct tool-calling steps")
    parser.add_argument("--max-cost-usd", type=float, default=None, help="Hard USD ceiling; stop before exceeding")
    parser.add_argument("--dry-run", action="store_true", help="Use the mock provider, zero cost")
    parser.add_argument("--resume", action="store_true", help="Resume from the existing checkpoint if present")
    parser.add_argument("--list", action="store_true", help="List cases and exit")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    cases = load_real_cases(args.cases, project_root=PROJECT_ROOT)

    if args.list:
        for case in cases:
            print(f"{case.case_id:<32} {case.category:<18} {case.expected_outcome:<8} {case.query}")
        print(f"\n{len(cases)} cases")
        return 0

    if args.category:
        cases = [case for case in cases if case.category == args.category]
        if not cases:
            print(f"ERROR: no cases in category '{args.category}'", file=sys.stderr)
            return 1

    if not args.model and not args.dry_run:
        print("ERROR: --model is required for a real run; use --dry-run for offline testing, "
              "or --list for the free inventory.", file=sys.stderr)
        return 2

    output_dir = Path(args.output)
    runner = RealBenchmarkRunner(cases, dataset_path=args.cases)
    try:
        payload = asyncio.run(runner.run(
            project_root=PROJECT_ROOT,
            snapshot_dir=Path(args.snapshot_dir),
            model=args.model or "mock",
            temperature=args.temperature,
            max_steps=args.max_steps,
            dry_run=args.dry_run,
            output_dir=output_dir,
            max_cost_usd=args.max_cost_usd,
            resume=args.resume,
        ))
    except Exception as exc:
        print(f"ERROR: benchmark failed: {exc}", file=sys.stderr)
        return 1

    summary = payload["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nResults written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())