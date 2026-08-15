"""Small, paid Tushare smoke test for the provider-router normalization chain."""

from __future__ import annotations

import os

import pytest

from src.cn.evidence import EvidenceLedger
from src.cn.providers.router import build_default_router
from src.cn.providers.tushare import TushareCallBudget, TushareProvider
from src.cn.symbols import normalize_cn_symbol


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.getenv("TUSHARE_TOKEN"), reason="TUSHARE_TOKEN not set")
def test_tushare_router_normalizes_and_validates_one_pinned_symbol():
    """Uses exactly five Tushare calls: profile, daily, and three statements."""
    budget = TushareCallBudget(max_calls=5)
    router = build_default_router(tushare_provider=TushareProvider(os.environ["TUSHARE_TOKEN"], call_budget=budget))
    symbol = normalize_cn_symbol("600519.SH")

    profile = router.get_profile(symbol)
    bars = router.get_daily_bars(symbol, start_date="2026-08-01", end_date="2026-08-12")
    statements = router.get_financial_statements(symbol, research_as_of="2026-08-12T23:59:59+08:00")

    assert profile and profile.name
    assert bars and all(bar.adjustment == "RAW" for bar in bars)
    assert statements and all(item.currency == "CNY" and item.available_at for item in statements)
    assert budget.used_calls == 5

    ledger = EvidenceLedger(snapshot_id="integration_tushare_600519_SH")
    ledger.add_market_bar_facts(symbol=str(symbol), bar=max(bars, key=lambda bar: bar.trade_date), provider="tushare")
    for statement in statements:
        ledger.add_statement_facts(symbol=str(symbol), statement=statement, provider="tushare")
    validation = ledger.validate(research_as_of="2026-08-12T23:59:59+08:00")
    assert validation.valid, validation.errors
