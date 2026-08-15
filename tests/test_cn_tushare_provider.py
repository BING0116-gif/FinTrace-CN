import pandas as pd

from src.cn.providers.tushare import TushareCallBudget, TushareProvider
from src.cn.symbols import normalize_cn_symbol


class FakeTushareClient:
    def stock_basic(self, **_kwargs):
        return pd.DataFrame([{"name": "贵州茅台", "industry": "白酒"}])

    def daily(self, **_kwargs):
        return pd.DataFrame([
            {"trade_date": "20260810", "open": 1, "high": 2, "low": 0.5,
             "close": 1.5, "vol": 10, "amount": 20}
        ])

    @staticmethod
    def _statement(**values):
        row = {
            "report_type": "1", "comp_type": "1", "end_type": "1",
            "end_date": "20260331", "ann_date": "20260425",
            "f_ann_date": "20260425", "update_flag": "0",
        }
        row.update(values)
        return pd.DataFrame([row])

    def income(self, **_kwargs):
        first = self._statement(revenue=100, n_income_attr_p=20, ebit=30, ebitda=40)
        revised = self._statement(revenue=101, n_income_attr_p=21, ebit=31, ebitda=41)
        revised["f_ann_date"] = "20260426"
        return pd.concat([first, revised], ignore_index=True)

    def balancesheet(self, **_kwargs):
        return self._statement(
            total_assets=1000, total_liab=300, total_hldr_eqy_exc_min_int=700, total_share=1
        )

    def cashflow(self, **_kwargs):
        return self._statement(n_cashflow_act=50, free_cashflow=30)


def test_tushare_provider_maps_approved_calls_to_canonical_schema():
    provider = TushareProvider("test-token", call_budget=TushareCallBudget(max_calls=5))
    provider._client = FakeTushareClient()
    symbol = normalize_cn_symbol("600519.SH")

    profile = provider.get_profile(symbol)
    bars = provider.get_daily_bars(symbol, start_date="2026-08-01", end_date="2026-08-10")
    statements = provider.get_financial_statements(
        symbol, research_as_of="2026-05-01T00:00:00+08:00"
    )

    assert profile and profile.name == "贵州茅台"
    assert bars[0].trade_date == "2026-08-10"
    assert bars[0].adjustment == "RAW"
    assert len(statements) == 3
    assert statements[0].available_at == "2026-04-26T00:00:00+08:00"
    assert statements[0].period_basis == "2026Q1_CUMULATIVE"
    assert statements[0].values["revenue"] == 101.0
    assert provider.call_budget.used_calls == 5


def test_tushare_provider_keeps_bank_statements_instead_of_treating_comp_type_as_scope():
    provider = TushareProvider("test-token", call_budget=TushareCallBudget(max_calls=3))
    client = FakeTushareClient()
    for method in (client.income, client.balancesheet, client.cashflow):
        frame = method()
        frame["comp_type"] = "2"  # Tushare bank issuer category
        setattr(client, method.__name__, lambda _frame=frame, **_kwargs: _frame)
    provider._client = client

    statements = provider.get_financial_statements(normalize_cn_symbol("600036.SH"))

    assert len(statements) == 3
