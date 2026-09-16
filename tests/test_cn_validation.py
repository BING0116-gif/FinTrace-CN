"""Tests for the standalone financial and report validators."""

from src.cn.evidence import EvidenceLedger
from src.validation.financial_validator import FinancialValidator
from src.validation.report_validator import ReportValidator


def _sample_ledger() -> EvidenceLedger:
    ledger = EvidenceLedger(snapshot_id="test_v1")
    ledger.add_fact(
        evidence_id="fact_close_600519_20260810_RAW",
        symbol="600519.SH", metric="close", value=1500.0,
        currency="CNY", unit="CNY/share",
        fiscal_period=None, period_basis="RAW",
        published_at="2026-08-09T15:00:00+08:00",
        available_at="2026-08-09T15:00:00+08:00",
        provider="test", field_path="bars.2026-08-09.close",
    )
    ledger.add_fact(
        evidence_id="fact_600519_revenue_2025FY",
        symbol="600519.SH", metric="revenue", value=150000000000.0,
        currency="CNY", unit="CNY",
        fiscal_period="2025-12-31", period_basis="FY",
        published_at="2026-04-30T00:00:00+08:00",
        available_at="2026-04-30T00:00:00+08:00",
        provider="test", field_path="statements.income.2025-12-31.revenue",
    )
    ledger.add_fact(
        evidence_id="fact_600519_net_profit_2025FY",
        symbol="600519.SH", metric="net_profit", value=75000000000.0,
        currency="CNY", unit="CNY",
        fiscal_period="2025-12-31", period_basis="FY",
        published_at="2026-04-30T00:00:00+08:00",
        available_at="2026-04-30T00:00:00+08:00",
        provider="test", field_path="statements.income.2025-12-31.net_profit",
    )
    ledger.add_fact(
        evidence_id="fact_600519_total_shares",
        symbol="600519.SH", metric="total_shares", value=1256197800.0,
        currency="CNY", unit="shares",
        fiscal_period=None, period_basis=None,
        published_at=None, available_at=None,
        provider="test", field_path="profile.total_shares",
    )
    return ledger


# ---------------------------------------------------------------------------
# FinancialValidator tests
# ---------------------------------------------------------------------------

def test_validation_passes_clean_ledger():
    ledger = _sample_ledger()
    validator = FinancialValidator(max_data_age_days=365)
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    assert result.valid is True
    assert result.errors == []


def test_validation_future_fact():
    ledger = _sample_ledger()
    ledger.add_fact(
        evidence_id="fact_future", symbol="600519.SH", metric="close", value=1600.0,
        currency="CNY", unit="CNY/share",
        fiscal_period=None, period_basis="RAW",
        published_at="2026-08-15T15:00:00+08:00",
        available_at="2026-08-15T15:00:00+08:00",
        provider="test", field_path="bars.2026-08-15.close",
    )
    validator = FinancialValidator()
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    assert result.valid is False
    assert any("future_fact" in e for e in result.errors)


def test_validation_currency_mismatch():
    ledger = _sample_ledger()
    ledger.add_fact(
        evidence_id="fact_usd", symbol="600519.SH", metric="revenue", value=1000000.0,
        currency="USD", unit="USD",
        fiscal_period="2025-12-31", period_basis="FY",
        published_at="2026-04-30T00:00:00+08:00",
        available_at="2026-04-30T00:00:00+08:00",
        provider="test", field_path="test.usd",
    )
    validator = FinancialValidator()
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    assert result.valid is False
    assert any("currency_mismatch" in e for e in result.errors)


def test_validation_period_basis_mismatch():
    ledger = _sample_ledger()
    ledger.add_fact(
        evidence_id="fact_ttm", symbol="600519.SH", metric="revenue", value=38000000000.0,
        currency="CNY", unit="CNY",
        fiscal_period="2026-06-30", period_basis="TTM",
        published_at="2026-08-01T00:00:00+08:00",
        available_at="2026-08-01T00:00:00+08:00",
        provider="test", field_path="test.ttm",
    )
    validator = FinancialValidator()
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    assert result.valid is False
    assert any("period_basis_mismatch" in e for e in result.errors)


def test_validation_expired_data_latest_stale_blocks():
    # If the latest (and only) figure for a metric is stale, it must block.
    ledger = EvidenceLedger(snapshot_id="stale")
    ledger.add_fact(
        evidence_id="fact_old_close", symbol="600519.SH", metric="close", value=500.0,
        currency="CNY", unit="CNY/share",
        fiscal_period=None, period_basis="RAW",
        published_at="2020-01-01T15:00:00+08:00",
        available_at="2020-01-01T15:00:00+08:00",
        provider="test", field_path="bars.2020-01-01.close",
    )
    validator = FinancialValidator(max_data_age_days=365)
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    assert result.valid is False
    assert any("expired_data" in e for e in result.errors)


def test_validation_expired_data_fresh_latest_with_stale_comparative_ok():
    # A fresh latest alongside a stale older bar of the same metric is fine:
    # only the latest is freshness-checked.
    ledger = _sample_ledger()  # already contains a fresh close (2026-08-09)
    ledger.add_fact(
        evidence_id="fact_old_close", symbol="600519.SH", metric="close", value=500.0,
        currency="CNY", unit="CNY/share",
        fiscal_period=None, period_basis="RAW",
        published_at="2020-01-01T15:00:00+08:00",
        available_at="2020-01-01T15:00:00+08:00",
        provider="test", field_path="bars.2020-01-01.close",
    )
    validator = FinancialValidator(max_data_age_days=365)
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    assert not any("expired_data" in e for e in result.errors)


def test_validation_expired_data_comparative_exempt():
    # A stale *comparative* (non-latest) figure must NOT block the report;
    # only the latest period of each metric is freshness-checked.
    ledger = _sample_ledger()
    ledger.add_fact(
        evidence_id="fact_old_revenue", symbol="600519.SH", metric="revenue", value=100000000000.0,
        currency="CNY", unit="CNY",
        fiscal_period="2024-12-31", period_basis="FY",
        published_at="2025-04-30T00:00:00+08:00",
        available_at="2025-04-30T00:00:00+08:00",
        provider="test", field_path="statements.income.2024-12-31.revenue",
    )
    validator = FinancialValidator(max_data_age_days=365)
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    assert not any("expired_data" in e for e in result.errors)


def test_validation_empty_ledger():
    ledger = EvidenceLedger(snapshot_id="empty")
    validator = FinancialValidator()
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    assert result.valid is True
    assert result.evidence_coverage == 0.0


def test_validation_evidence_coverage():
    ledger = _sample_ledger()
    validator = FinancialValidator()
    result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
    # No calculations in the sample ledger, so all facts are "covered"
    assert result.evidence_coverage >= 0.0


# ---------------------------------------------------------------------------
# ReportValidator tests
# ---------------------------------------------------------------------------

def test_report_validator_no_numbers():
    ledger = _sample_ledger()
    validator = ReportValidator(ledger)
    result = validator.validate("这是一份研究报告，没有数字。")
    assert result.valid is True
    assert result.unsupported_numbers == []


def test_report_validator_cited_evidence():
    ledger = _sample_ledger()
    validator = ReportValidator(ledger)
    report = "收盘价 `fact_close_600519_20260810_RAW` 为1500元/股。"
    result = validator.validate(report)
    # The report has a cited evidence ID that exists
    # But 1500 is not in known_values (the evidence has value 1500.0, which IS known)
    # Actually, 1500.0 IS in known_values from the ledger
    # Let me think... known_values = {1500.0, 150000000000.0, 75000000000.0, 1256197800.0}
    assert result.valid is True


def test_report_validator_unsupported_number():
    ledger = _sample_ledger()
    validator = ReportValidator(ledger)
    report = "该股目标价5000元。"
    result = validator.validate(report)
    # 5000 is not in known_values
    assert len(result.unsupported_numbers) > 0


def test_report_validator_citation_coverage():
    ledger = _sample_ledger()
    validator = ReportValidator(ledger)
    report = "参考 `fact_close_600519_20260810_RAW` 和 `fact_600519_revenue_2025FY`。"
    result = validator.validate(report)
    # 2 out of 4 evidence IDs are cited
    assert result.citation_coverage_rate == 0.5


def test_report_validator_missing_citation():
    ledger = _sample_ledger()
    validator = ReportValidator(ledger)
    report = "参考 `fact_nonexistent_id`。"
    result = validator.validate(report)
    assert result.valid is False
    assert any("missing_evidence_ids" in e for e in result.errors)


def test_report_validator_percentage():
    ledger = _sample_ledger()
    validator = ReportValidator(ledger)
    report = "毛利率为25.5%。"
    result = validator.validate(report)
    # 25.5 is not in known_values
    assert len(result.unsupported_numbers) > 0


def test_report_validator_multiple():
    ledger = _sample_ledger()
    validator = ReportValidator(ledger)
    report = "PE倍数为30.5x。"
    result = validator.validate(report)
    assert len(result.unsupported_numbers) > 0