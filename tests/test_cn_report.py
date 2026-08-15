from pathlib import Path

from src.cn.providers.snapshot import SnapshotProvider
from src.cn.report import CnResearchReportBuilder
from src.cn.symbols import normalize_cn_symbol
from src.cn.evidence import EvidenceLedger


FIXTURE = Path(__file__).parents[1] / "data" / "snapshots" / "cn" / "600519.SH_20260810_tushare_v1.json"


def test_cn_report_is_chinese_traceable_and_offline():
    report = CnResearchReportBuilder(SnapshotProvider(FIXTURE)).build(normalize_cn_symbol("600519.SH"))

    assert "# 贵州茅台（600519.SH）研究报告" in report.markdown
    assert "## 市场价格" in report.markdown
    assert "## TTM 财务表现" in report.markdown
    assert "## 基础估值" in report.markdown
    assert "## Validator 结果" in report.markdown
    assert "calc_market_cap" in report.markdown
    assert "| P/E（TTM）" in report.markdown and "`calc_pe_ttm`" in report.markdown
    assert "fact_600519_SH_close_2026-08-10_RAW" in report.markdown
    assert report.validation.valid


def test_bank_boundary_report_declares_inapplicable_generic_valuation_methods():
    fixture = Path(__file__).parents[1] / "tests" / "fixtures" / "cn" / "600036.SH_bank_boundary_v1.json"
    report = CnResearchReportBuilder(SnapshotProvider(fixture)).build(normalize_cn_symbol("600036.SH"))

    assert "金融机构估值边界" in report.markdown
    assert "不将 PS、EV/EBITDA 或通用 DCF 作为银行估值结论" in report.markdown
    assert report.validation.valid


def test_report_uses_latest_half_year_balance_fact_consistently_for_market_cap():
    snapshot = Path(__file__).parents[1] / "data" / "snapshots" / "cn" / "300750.SZ_20260812_tushare_v1.json"
    report = CnResearchReportBuilder(SnapshotProvider(snapshot)).build(
        normalize_cn_symbol("300750.SZ"), research_as_of="2026-08-12T10:45:00+08:00"
    )

    assert report.validation.valid


def test_evidence_ledger_accepts_machine_precision_for_large_market_cap():
    ledger = EvidenceLedger(snapshot_id="test")
    ledger.add_fact(evidence_id="price", symbol="TEST", metric="close", value=390.4,
                    currency="CNY", unit="CNY/share", fiscal_period=None, period_basis="RAW",
                    published_at=None, available_at=None, provider="test", field_path="price")
    ledger.add_fact(evidence_id="shares", symbol="TEST", metric="total_shares", value=4_626_650_861,
                    currency="CNY", unit="shares", fiscal_period="2026H1", period_basis="2026H1_END",
                    published_at=None, available_at=None, provider="test", field_path="shares")
    ledger.add_calculation(evidence_id="market_cap", symbol="TEST", metric="market_cap",
                           value=390.4 * 4_626_650_861, currency="CNY", unit="CNY",
                           operation="multiply", input_ids=["price", "shares"])

    assert ledger.validate(research_as_of="2026-08-12T10:45:00+08:00").valid
