from pathlib import Path

from src.cn.providers.snapshot import SnapshotProvider
from src.cn.symbols import normalize_cn_symbol


FIXTURE = Path(__file__).parent / "fixtures" / "cn" / "600519.SH_illustrative_v1.json"


def test_snapshot_provider_reads_profile_and_raw_bars_offline():
    provider = SnapshotProvider(FIXTURE)
    symbol = normalize_cn_symbol("600519.SH")

    profile = provider.get_profile(symbol)
    bars = provider.get_daily_bars(symbol, adjustment="RAW")

    assert profile is not None
    assert profile.name == "贵州茅台（测试样例）"
    assert len(bars) == 1
    assert bars[0].adjustment == "RAW"


def test_snapshot_provider_excludes_future_disclosures():
    provider = SnapshotProvider(FIXTURE)
    symbol = normalize_cn_symbol("600519")

    as_of_april_1 = provider.get_financial_statements(
        symbol, research_as_of="2025-04-01T00:00:00+08:00"
    )
    as_of_may_1 = provider.get_financial_statements(
        symbol, research_as_of="2025-05-01T00:00:00+08:00"
    )

    assert [item.fiscal_period for item in as_of_april_1] == ["2024FY"]
    assert [item.fiscal_period for item in as_of_may_1] == ["2024FY", "2025Q1"]
