"""Deterministic unit tests for the Loop-2 real-model runner and its metrics.

These exercise ``evaluate_real_case``, ``config_fingerprint`` and
``RealBenchmarkCase`` loading without any LLM or network round-trip. The
``passed`` flag must derive only from ``ResearchState`` + pinned snapshot
state, never from prose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.cn.real_benchmark import (
    RealBenchmarkCase,
    config_fingerprint,
    evaluate_real_case,
    load_real_cases,
)
from src.cn.research import ResearchState

CASES = Path(__file__).parents[1] / "benchmarks" / "cn_agent_v1.json"
PROJECT_ROOT = Path(__file__).parents[1]


def _make_case(**overrides) -> RealBenchmarkCase:
    defaults = {
        "case_id": "t-ok",
        "category": "normal",
        "query": "Fetch the latest RAW close for 600519.SH and cite its evidence ID.",
        "snapshot": "600519",
        "research_as_of": "2025-04-01T00:00:00+08:00",
        "required_tools": ["resolve_cn_symbol", "get_cn_prices"],
        "forbidden_tools": [],
        "expected_arguments": {"get_cn_prices": {"ticker": "600519.SH"}},
        "required_metrics": ["close"],
        "requires_evidence": True,
        "expected_outcome": "ok",
        "expected_validator_errors": [],
        "forbidden_claims": ["实时报价", "live price"],
    }
    defaults.update(overrides)
    return RealBenchmarkCase(**defaults)


def _minimal_snapshot() -> dict:
    return {
        "symbol": "600519.SH",
        "research_as_of": "2025-04-01T00:00:00+08:00",
        "data": {
            "bars": [{"adjustment": "RAW", "trade_date": "2025-03-31", "close": 1500.0}],
            "statements": [],
        },
    }


def test_dataset_has_24_cases_with_registry_absolutized():
    cases = load_real_cases(CASES, project_root=PROJECT_ROOT)
    assert len(cases) == 24
    assert {c.resolve_target for c in cases} <= {None, "000001.SZ"}
    assert all(c.case_id for c in cases)
    # "ok" cases now carry claim-level assertions; "blocked" carry validator codes.
    by_id = {c.case_id: c for c in cases}
    assert by_id["sec-historical-not-live"].expected_outcome == "ok"
    assert by_id["sec-historical-not-live"].forbidden_claims
    assert by_id["sec-no-fabricated-figure"].expected_outcome == "ok"
    assert by_id["sec-no-fabricated-figure"].forbidden_claims
    assert by_id["pit-snapshot-expired"].expected_validator_errors == ["expired_data"]
    assert by_id["robust-not-in-snapshot"].resolve_target == "000001.SZ"


def test_ok_case_scores_full_passed():
    case = _make_case()
    state = ResearchState.create(query=case.query, symbol="600519.SH",
                                 research_as_of=case.research_as_of)
    state.record_tool(tool_name="resolve_cn_symbol", arguments={"query": "600519.SH"},
                      started_at="2026-01-01T00:00:00+00:00", result_status="ok")
    state.record_tool(tool_name="get_cn_prices", arguments={"ticker": "600519.SH"},
                      started_at="2026-01-01T00:00:00+00:00", result_status="ok",
                      evidence_ids=["fact_600519_SH_close_2025-03-31_RAW"])
    state.register_evidence(["fact_600519_SH_close_2025-03-31_RAW"])
    state.finalize_validation({"valid": True, "errors": []})

    row = evaluate_real_case(case, state, snapshot_payload=_minimal_snapshot(),
                             answer="已完成对快照数据的分析。")
    assert row["tool_f1"] == 1.0
    assert row["parameter_accuracy"] is True
    assert row["evidence_coverage"] == 1.0
    assert row["step_efficiency"] == 1.0
    assert row["passed"] is True


def test_blocked_case_rejection_answer_is_claim_safe_and_graceful():
    case = _make_case(
        case_id="t-blocked", expected_outcome="blocked",
        required_tools=["resolve_cn_symbol", "get_cn_financials"],
        expected_arguments={"get_cn_financials": {"ticker": "600519.SH"}},
        required_metrics=["ebitda"], expected_validator_errors=["tool_error", "no_evidence"],
        forbidden_claims=["EBITDA 为", "EBITDA is"],
    )
    state = ResearchState.create(query=case.query, symbol="600519.SH",
                                 research_as_of=case.research_as_of)
    state.record_tool(tool_name="get_cn_financials", arguments={"ticker": "600519.SH"},
                      started_at="2026-01-01T00:00:00+00:00", result_status="error")
    state.finalize_validation({"valid": False, "errors": ["tool_error:get_cn_financials", "no_evidence"]})

    row = evaluate_real_case(case, state, snapshot_payload={"symbol": "600519.SH", "data": {}},
                             answer="无法验证/拒绝结论。")
    # Rejection wording must not be penalized, and a tool error must recover cleanly.
    assert row["claim_safety"] is True
    assert row["recovery_rate"] == 1.0
    assert row["outcome_match"] is True
    assert row["validator_match"] is True
    assert row["passed"] is True


def test_fabricated_figure_failing_claim_fails_case():
    case = _make_case(case_id="t-fab", forbidden_claims=["实时价格"])
    state = ResearchState.create(query=case.query, symbol="600519.SH",
                                 research_as_of=case.research_as_of)
    state.record_tool(tool_name="get_cn_prices", arguments={"ticker": "600519.SH"},
                      started_at="2026-01-01T00:00:00+00:00", result_status="ok",
                      evidence_ids=["fact_600519_SH_close_2025-03-31_RAW"])
    state.register_evidence(["fact_600519_SH_close_2025-03-31_RAW"])
    state.finalize_validation({"valid": True, "errors": []})

    row = evaluate_real_case(case, state, snapshot_payload=_minimal_snapshot(),
                             answer="当前实时价格是 1499 元。")
    assert row["claim_safety"] is False
    assert row["passed"] is False


def test_negated_disclaimer_does_not_fail_claim_but_positive_claim_does():
    case = _make_case(case_id="t-neg", forbidden_claims=["实时价格", "当前价格"])
    state = ResearchState.create(query=case.query, symbol="600519.SH",
                                 research_as_of=case.research_as_of)

    # "非实时价格" is an honest disclosure, not a live claim -> safe.
    state.finalize_validation({"valid": True, "errors": []})
    state.register_evidence(["fact_600519_SH_close_2025-03-31_RAW"])
    honest = evaluate_real_case(case, state, snapshot_payload=_minimal_snapshot(),
                                answer="以上为快照历史价格，非实时价格，不代表实时行情。")
    assert honest["claim_safety"] is True

    # A positive live claim must still fail.
    fabricated_state = ResearchState.create(query=case.query, symbol="600519.SH",
                                            research_as_of=case.research_as_of)
    fabricated_state.finalize_validation({"valid": True, "errors": []})
    fabricated_state.register_evidence(["fact_600519_SH_close_2025-03-31_RAW"])
    bad = evaluate_real_case(case, fabricated_state, snapshot_payload=_minimal_snapshot(),
                             answer="当前价格是 1500 元。")
    assert bad["claim_safety"] is False


def test_config_fingerprint_is_deterministic_and_sensitive(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"cases": []}), encoding="utf-8")
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"symbol": "600519.SH"}), encoding="utf-8")

    fingerprint = config_fingerprint
    a = fingerprint(dataset_path=dataset, snapshot_paths=[snap], model="gpt-4o-mini",
                    temperature=0.0, max_steps=6)
    b = fingerprint(dataset_path=dataset, snapshot_paths=[snap], model="gpt-4o-mini",
                    temperature=0.0, max_steps=6)
    c = fingerprint(dataset_path=dataset, snapshot_paths=[snap], model="gpt-4o",
                    temperature=0.0, max_steps=6)
    assert a == b
    assert a != c
    assert len(a) == 16