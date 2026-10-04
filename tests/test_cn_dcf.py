import pytest

from src.cn.valuation_dcf import build_dcf, dcf_sensitivity, valuation_applicability


def inputs():
    return {
        "industry": "manufacturing", "forecast_method": "explicit_fcff",
        "forecast_fcff": [100, 110, 121], "wacc": 0.10, "terminal_growth": 0.03,
        "wacc_range": [0.09, 0.10, 0.11], "growth_range": [0.02, 0.03, 0.04],
        "bridge": {key: {"value": value, "evidence_id": f"e_{key}"} for key, value in {
            "net_debt": 50, "minority_interest": 10, "non_operating_assets": 5,
            "other_adjustments": 0, "diluted_shares": 20,
        }.items()},
    }


def test_dcf_ev_to_equity_bridge_and_sensitivity_are_traceable():
    result = build_dcf(inputs())
    assert result.bridge.equity_value == result.bridge.enterprise_value - 50 - 10 + 5
    assert result.bridge.implied_price == result.bridge.equity_value / 20
    assert len(result.sensitivity["matrix"]) == 3
    assert result.assumptions


def test_dcf_monotonicity_and_gate():
    matrix = dcf_sensitivity([100, 110], [0.09, 0.10], [0.02, 0.03])
    assert matrix["matrix"][0][1] > matrix["matrix"][0][0]
    assert matrix["matrix"][0][0] > matrix["matrix"][1][0]
    assert valuation_applicability("bank")["allowed"] is False


def test_dcf_fails_closed_on_missing_bridge_or_divergent_terminal_value():
    data = inputs(); del data["bridge"]["net_debt"]
    with pytest.raises(ValueError, match="missing_bridge_evidence:net_debt"):
        build_dcf(data)
    data = inputs(); data["wacc"] = data["terminal_growth"]
    with pytest.raises(ValueError, match="wacc_must_exceed_terminal_growth"):
        build_dcf(data)
