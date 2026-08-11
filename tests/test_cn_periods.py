import pytest

from src.cn.domain import FinancialStatement
from src.cn.periods import FinancialPeriodEngine, PeriodEngineError


def statement(period, revenue, cashflow=None):
    values = {"revenue": revenue}
    if cashflow is not None:
        values["operating_cash_flow"] = cashflow
    return FinancialStatement(
        statement_type="income",
        fiscal_period=period,
        period_basis="CUMULATIVE",
        published_at=None,
        available_at=None,
        currency="CNY",
        unit="CNY",
        values=values,
    )


def test_cumulative_reports_convert_to_single_quarters():
    records = [
        statement("2025Q1", 10), statement("2025H1", 30),
        statement("20259M", 60), statement("2025FY", 100),
    ]
    quarters = FinancialPeriodEngine.derive_single_quarters(records, "income")

    assert [(item.fiscal_period, item.values["revenue"]) for item in quarters] == [
        ("2025Q1", 10), ("2025Q2", 20), ("2025Q3", 30), ("2025Q4", 40),
    ]


def test_ttm_uses_current_cumulative_plus_prior_fy_minus_prior_comparable_period():
    records = [
        statement("2024Q1", 25), statement("2024FY", 100),
        statement("2025Q1", 30), statement("2025H1", 65),
        statement("2024H1", 55),
    ]
    ttm = FinancialPeriodEngine.derive_ttm(records, "income")
    values = {item.fiscal_period: item.values["revenue"] for item in ttm}

    assert values["2024FY"] == 100
    assert values["2025Q1"] == 105
    assert values["2025H1"] == 110


def test_balance_sheet_records_cannot_be_differenced():
    record = FinancialStatement(
        statement_type="balance", fiscal_period="2025Q1", period_basis="END",
        published_at=None, available_at=None, currency="CNY", unit="CNY", values={"total_assets": 100},
    )
    with pytest.raises(PeriodEngineError, match="Balance-sheet"):
        FinancialPeriodEngine.derive_single_quarters([record], "balance")
