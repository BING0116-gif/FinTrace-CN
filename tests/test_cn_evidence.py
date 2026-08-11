from src.cn.evidence import EvidenceLedger


def _ledger():
    ledger = EvidenceLedger(snapshot_id="600519.SH_test")
    ledger.add_fact(
        evidence_id="fact_price", symbol="600519.SH", metric="close", value=100,
        currency="CNY", unit="CNY/share", fiscal_period=None, period_basis="RAW",
        published_at="2026-08-10T15:00:00+08:00", available_at="2026-08-10T15:00:00+08:00",
        provider="snapshot", field_path="bars.2026-08-10.close",
    )
    ledger.add_fact(
        evidence_id="fact_shares", symbol="600519.SH", metric="total_shares", value=10,
        currency="CNY", unit="share", fiscal_period="2026Q1", period_basis="END",
        published_at="2026-04-25T00:00:00+08:00", available_at="2026-04-25T00:00:00+08:00",
        provider="snapshot", field_path="balance.2026Q1.total_shares",
    )
    return ledger


def test_ledger_recalculates_market_cap_and_keeps_inputs_traceable():
    ledger = _ledger()
    ledger.add_calculation(
        evidence_id="calc_market_cap", symbol="600519.SH", metric="market_cap", value=1000,
        currency="CNY", unit="CNY", operation="multiply", input_ids=["fact_price", "fact_shares"],
    )
    validation = ledger.validate(research_as_of="2026-08-11T00:00:00+08:00")
    assert validation.valid
    assert ledger.get("calc_market_cap").input_ids == ("fact_price", "fact_shares")


def test_ledger_blocks_future_facts_and_detects_bad_calculations():
    ledger = _ledger()
    ledger.add_calculation(
        evidence_id="calc_wrong", symbol="600519.SH", metric="market_cap", value=999,
        currency="CNY", unit="CNY", operation="multiply", input_ids=["fact_price", "fact_shares"],
    )
    validation = ledger.validate(research_as_of="2026-08-01T00:00:00+08:00")
    assert not validation.valid
    assert "future_fact:fact_price" in validation.errors
    assert "calculation_mismatch:calc_wrong" in validation.errors
