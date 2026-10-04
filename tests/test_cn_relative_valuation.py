from __future__ import annotations

import pytest

from src.cn.valuation import (
    AssumptionRegistry,
    build_scenarios,
    build_valuation_result,
    method_dispersion,
    sensitivity_pb_roe,
    sensitivity_pe_eps,
)


def inputs():
    return {
        "shares": 100,
        "scenarios": {
            name: {
                "eps": {"low": 2, "mid": 3, "high": 4},
                "target_pe": {"low": 8, "mid": 10, "high": 12},
                "bps": 20,
                "target_pb": {"low": 1, "mid": 1.5, "high": 2},
                "revenue_per_share": 30,
                "target_ps": {"low": 1, "mid": 1.2, "high": 1.5},
            }
            for name in ("bear", "base", "bull")
        },
        "eps_range": [2, 3, 4], "target_pe_range": [8, 10, 12],
        "roe_range": [0.1, 0.2, 0.3], "target_pb_range": [1, 1.5, 2], "bps": 20,
    }


def test_pe_eps_matrix_is_hand_calculable_and_monotonic():
    matrix = sensitivity_pe_eps([2, 3, 4], [8, 10, 12], 100)
    assert matrix.matrix == [[16, 20, 24], [24, 30, 36], [32, 40, 48]]
    assert matrix.y_name == "EPS (TTM)"


def test_pb_matrix_uses_bps_times_pb_and_is_monotonic():
    matrix = sensitivity_pb_roe([0.1, 0.2, 0.3], [1, 1.5, 2], 20, 100)
    assert matrix.matrix == [[20, 30, 40]] * 3
    assert matrix.x_values == [1, 1.5, 2]


def test_scenarios_register_all_inputs_and_methods_stay_separate():
    registry = AssumptionRegistry()
    scenarios = build_scenarios(inputs(), registry)
    assert len(scenarios) == 9
    assert all(item.assumption_ids for item in scenarios)
    assert set(item.method for item in scenarios) == {"pe", "pb", "ps"}
    assert set(method_dispersion(scenarios)) == {"pe", "pb", "ps"}


def test_negative_eps_marks_only_pe_not_applicable():
    data = inputs()
    data["scenarios"]["base"]["eps"] = -1
    registry = AssumptionRegistry()
    rows = build_scenarios(data, registry)
    base_pe = next(item for item in rows if item.method == "pe" and item.scenario == "base")
    assert base_pe.status == "not_applicable_negative_eps"
    assert next(item for item in rows if item.method == "pb" and item.scenario == "base").status == "ok"


def test_result_has_dispersion_assumptions_and_validation():
    registry = AssumptionRegistry()
    result = build_valuation_result(inputs(), registry)
    assert result.validation["valid"]
    assert result.method_dispersion
    assert result.assumptions
    assert all(matrix.assumption_ids for matrix in result.sensitivity)


def test_empty_scenario_inputs_fail_closed():
    with pytest.raises(ValueError, match="scenarios_input_required"):
        build_scenarios({}, AssumptionRegistry())
