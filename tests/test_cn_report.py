from pathlib import Path

from src.cn.providers.snapshot import SnapshotProvider
from src.cn.report import CnResearchReportBuilder
from src.cn.symbols import normalize_cn_symbol


FIXTURE = Path(__file__).parents[1] / "data" / "snapshots" / "cn" / "600519.SH_20260810_tushare_v1.json"


def test_cn_report_is_chinese_traceable_and_offline():
    report = CnResearchReportBuilder(SnapshotProvider(FIXTURE)).build(normalize_cn_symbol("600519.SH"))

    assert "# 贵州茅台（600519.SH）研究报告" in report.markdown
    assert "## 市场价格" in report.markdown
    assert "## TTM 财务表现" in report.markdown
    assert "## 基础估值" in report.markdown
    assert "## Validator 结果" in report.markdown
    assert "calc_market_cap" in report.markdown
    assert "fact_600519_SH_close_2026-08-10_RAW" in report.markdown
    assert report.validation.valid


def test_bank_boundary_report_declares_inapplicable_generic_valuation_methods():
    fixture = Path(__file__).parents[1] / "tests" / "fixtures" / "cn" / "600036.SH_bank_boundary_v1.json"
    report = CnResearchReportBuilder(SnapshotProvider(fixture)).build(normalize_cn_symbol("600036.SH"))

    assert "Financial-institution valuation boundary" in report.markdown
    assert "PS, EV/EBITDA, or generic DCF" in report.markdown
    assert report.validation.valid
