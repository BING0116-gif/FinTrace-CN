#!/usr/bin/env python3
"""Gate the deterministic agent-ablation artifact used by CI.

This checks only the offline mock fixture.  It is a regression guard for the
research pipeline, not a claim about production-model performance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


VARIANT = "agent_tools_evidence_validator"
REQUIRED_METRICS = {
    "tool_f1": 1.0,
    "parameter_accuracy": 1.0,
    "evidence_coverage": 1.0,
    "e2e_success_rate": 1.0,
    "error_conclusion_leakage": 0.0,
}


def check_thresholds(payload: dict[str, Any]) -> list[str]:
    """Return every violated deterministic regression threshold."""
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return ["missing metrics object"]
    variant_metrics = metrics.get(VARIANT)
    if not isinstance(variant_metrics, dict):
        return [f"missing {VARIANT} metrics"]

    failures: list[str] = []
    for metric, expected in REQUIRED_METRICS.items():
        actual = variant_metrics.get(metric)
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            failures.append(f"{metric}: missing or non-numeric")
        elif actual != expected:
            failures.append(f"{metric}: expected {expected}, got {actual}")
    return failures


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("usage: check_ablation_thresholds.py PATH/ablation_results.json", file=sys.stderr)
        return 2

    artifact = Path(argv[0])
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read ablation artifact: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("Ablation artifact must be a JSON object.", file=sys.stderr)
        return 2

    failures = check_thresholds(payload)
    if failures:
        print("Offline ablation regression gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Offline ablation regression gate passed for {VARIANT}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
