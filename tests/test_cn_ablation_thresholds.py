"""Tests for the deterministic ablation CI regression gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_ablation_thresholds.py"
SPEC = importlib.util.spec_from_file_location("check_ablation_thresholds", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _payload(**overrides):
    metrics = {
        "tool_f1": 1.0,
        "parameter_accuracy": 1.0,
        "evidence_coverage": 1.0,
        "e2e_success_rate": 1.0,
        "error_conclusion_leakage": 0.0,
    }
    metrics.update(overrides)
    return {"metrics": {MODULE.VARIANT: metrics}}


def test_thresholds_accept_complete_deterministic_variant():
    assert MODULE.check_thresholds(_payload()) == []


def test_thresholds_report_missing_or_regressed_metrics():
    failures = MODULE.check_thresholds(_payload(tool_f1=0.9, evidence_coverage=None))
    assert "tool_f1: expected 1.0, got 0.9" in failures
    assert "evidence_coverage: missing or non-numeric" in failures
