from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agents.tools.cn_tools import build_cn_snapshot_tools
from src.cn.domain import FinancialStatement
from src.cn.normalization import NormalizationError, derive_normalized_periods, normalize_statements, normalize_unit_value


FIXTURE = Path(__file__).parent / "fixtures" / "cn" / "600519.SH_illustrative_v1.json"


def statement(statement_type="income", fiscal_period="2025FY", period_basis="FY", *, unit="CNY", currency="CNY", values=None):
    return FinancialStatement(
        statement_type=statement_type, fiscal_period=fiscal_period,
        period_basis=period_basis, published_at="2026-04-01T00:00:00+08:00",
        available_at="2026-04-01T00:00:00+08:00", currency=currency, unit=unit,
        values=values or {"revenue": 1.0},
    )


def test_unit_conversion_is_explicit_and_dimension_safe():
    assert normalize_unit_value(3.1, "亿元") == pytest.approx(310_000_000)
    assert normalize_unit_value(31_000, "万元") == pytest.approx(310_000_000)
    with pytest.raises(NormalizationError, match="incompatible"):
        normalize_unit_value(1, "%")


def test_normalization_preserves_raw_period_and_marks_unknown_scope_ambiguous():
    facts = normalize_statements(
        [statement(fiscal_period="2024FY", period_basis="2024FY_CUMULATIVE", unit="万元", values={"revenue": 3.1})],
        symbol="600519.SH", provider="fixture",
    )
    assert facts[0].value == pytest.approx(31_000)
    assert facts[0].period_basis == "FY"
    assert facts[0].flow_stock == "flow"
    assert facts[0].validation_status == "ambiguous"
    assert "scope_unknown" in facts[0].warnings


def test_explicit_scope_and_balance_stock_semantics():
    facts = normalize_statements(
        [statement(statement_type="balance", fiscal_period="2025FY", period_basis="FY", values={"book_equity": 10})],
        symbol="600036.SH", provider="fixture", scope="consolidated",
    )
    assert facts[0].flow_stock == "stock"
    assert facts[0].period_basis == "POINT_IN_TIME"
    assert facts[0].validation_status == "normalized"


def test_mixed_currency_and_invalid_scope_are_rejected():
    with pytest.raises(NormalizationError, match="Mixed statement currencies"):
        normalize_statements(
            [statement(currency="CNY"), statement(fiscal_period="2024FY", currency="USD")],
            symbol="600519.SH", provider="fixture",
        )
    with pytest.raises(NormalizationError, match="Unsupported accounting scope"):
        normalize_statements([statement()], symbol="600519.SH", provider="fixture", scope="group")


def test_unsupported_period_and_stock_derivation_are_blocked():
    with pytest.raises(NormalizationError, match="Unsupported fiscal period"):
        normalize_statements([statement(fiscal_period="2025UNKNOWN")], symbol="600519.SH", provider="fixture")
    with pytest.raises(NormalizationError, match="cannot be differenced"):
        derive_normalized_periods(
            [statement(statement_type="balance")], symbol="600036.SH",
            provider="fixture", statement_type="balance",
        )


def test_period_engine_is_reused_for_single_quarter_and_ttm():
    rows = [
        statement(fiscal_period="2024FY", values={"revenue": 100}),
        statement(fiscal_period="2024Q1", period_basis="Q1", values={"revenue": 20}),
        statement(fiscal_period="2025FY", values={"revenue": 130}),
        statement(fiscal_period="2025Q1", period_basis="Q1", values={"revenue": 30}),
    ]
    derived = derive_normalized_periods(rows, symbol="600519.SH", provider="fixture", statement_type="income", scope="consolidated")
    by_key = {(fact.fiscal_period, fact.period_basis): fact.value for fact in derived if fact.metric == "revenue"}
    assert by_key[("2025Q1", "TTM")] == pytest.approx(110)
    assert by_key[("2025Q1", "SINGLE_QUARTER")] == pytest.approx(30)
    assert by_key[("2025FY", "TTM")] == pytest.approx(130)


def test_normalization_tool_reads_snapshot_and_returns_provenance():
    tools = {tool.name: tool for tool in build_cn_snapshot_tools(FIXTURE)}
    result = json.loads(asyncio.run(tools["normalize_cn_financials"].execute(
        ticker="600519.SH", research_as_of="2025-04-01T00:00:00+08:00", scope="consolidated"
    )))
    assert result["status"] == "ok"
    assert result["provider"] == "snapshot"
    assert result["normalized_facts"]
    assert result["validation"]["status"] == "pass"


def test_analysis_tool_returns_deterministic_analysis_envelope():
    tools = {tool.name: tool for tool in build_cn_snapshot_tools(FIXTURE)}
    result = json.loads(asyncio.run(tools["analyze_cn_financials"].execute(
        ticker="600519.SH", research_as_of="2025-04-01T00:00:00+08:00", scope="consolidated"
    )))
    assert result["status"] == "ok"
    assert result["analysis"]["data_complete"] is False
    assert result["analysis"]["missing"]
