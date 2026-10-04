from src.cn.acme import (
    TolerancePolicy, check_accounting_identities, check_cross_modal,
    check_cross_source, check_period_relations, check_table_structural,
    validate_multimodal_evidence,
)
from src.cn.domain import FinancialStatement
from src.cn.normalization import normalize_statements

def fact(metric, value, period="2024FY", provider="filing", **kw):
    return {"fact_id": f"{provider}-{metric}-{period}", "symbol": "600000.SH", "metric": metric,
            "value": value, "fiscal_period": period, "period_basis": "FY", "statement_type": "balance",
            "currency": "CNY", "unit": "CNY", "scope": "consolidated", "provider": provider, **kw}

def test_accounting_identity_uses_explicit_tolerance_and_blocks_large_residual():
    good = [fact("assets", 100000), fact("liabilities", 40000), fact("equity", 60000)]
    assert check_accounting_identities(good)[0].status == "passed"
    near = [fact("assets", 100000), fact("liabilities", 40000), fact("equity", 60000.5)]
    assert check_accounting_identities(near)[0].status == "warning"
    bad = [fact("assets", 100000), fact("liabilities", 40000), fact("equity", 50000)]
    assert check_accounting_identities(bad)[0].status == "violated"
    profit = [fact("net_profit", 90, period="2024FY"), fact("profit_before_tax", 100, period="2024FY"), fact("income_tax", 10, period="2024FY")]
    assert check_accounting_identities(profit)[0].status == "passed"

def test_table_cross_source_and_modal_are_detection_only():
    result = check_table_structural([{"rows": [{"children": [1000, 2000], "subtotal": 5000}]}])
    assert result[0].constraint_id == "subtotal_reconciliation" and result[0].status == "violated"
    sources = check_cross_source([fact("revenue", 100, provider="filing"), fact("revenue", 100.05, provider="snapshot")])
    assert sources[0].constraint_id == "ROUNDING_MATCH"
    modal = check_cross_modal([{"metric": "gross_margin_change", "values": {"body": -2.1, "table": -2.2}, "computed_value": -2.2}])
    assert modal[0].conflict_type == "value_mismatch" and modal[0].resolution_status == "unresolved"

def test_period_relation_delegates_to_period_engine_for_single_quarter():
    rows = [FinancialStatement("income", "2024Q1", "Q1", None, None, "CNY", "CNY", {"revenue": 40}, scope="consolidated"),
            FinancialStatement("income", "2024H1", "H1", None, None, "CNY", "CNY", {"revenue": 100}, scope="consolidated")]
    facts = normalize_statements(rows, symbol="600000.SH", provider="filing")
    # The engine derives Q2; this check must not implement its own H1-Q1 formula.
    assert check_period_relations(facts)[0].status == "passed"

def test_integrity_report_has_review_queue_and_never_corrects_values():
    report = validate_multimodal_evidence([fact("assets", 10000), fact("liabilities", 1000), fact("equity", 2000)], document_id="doc-1")
    assert report.document_id == "doc-1"
    assert report.review_queue and report.totals["violated"] == 1
    assert not hasattr(report, "corrected_values")
