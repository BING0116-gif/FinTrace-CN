from __future__ import annotations

import pytest

from src.cn.analysis import ScopeSignalType, comparability_decision, detect_scope_signals
from src.cn.documents.schema import DocumentRecord, ExtractedFact, ParseResult, SourceFragment
from src.cn.evidence import EvidenceError, EvidenceLedger


def _doc(text: str, *, corrected: bool = False) -> ParseResult:
    document = DocumentRecord(
        document_id="doc_scope", file_name="scope.txt", document_type="annual_report",
        sha256="hash", ingested_at="2026-01-01T00:00:00+08:00", source="fixture",
        symbol="600519.SH", fiscal_period="2025FY", published_at="2026-01-01T00:00:00+08:00",
    )
    fragment = SourceFragment("frag_scope", "doc_scope", 3, text, "hash", "text_layer", "exact")
    fact = ExtractedFact(
        "fact_scope", "net_profit", 10, "亿元", "CNY", "2024FY", "consolidated",
        "frag_scope", version="CORRECTED" if corrected else "AS_REPORTED",
    )
    return ParseResult(document, (fragment,), (fact,))


def test_restatement_signal_requires_adjusted_comparison_and_binds_evidence():
    signal = detect_scope_signals(documents=[_doc("前期差错更正：2024年比较数据调整后。", corrected=True)])[0]
    assert signal.signal_type is ScopeSignalType.PRIOR_PERIOD_ERROR_CORRECTION
    assert signal.evidence_ids == ("frag_scope",)
    assert comparability_decision(signal) == "use_adjusted"


def test_material_unknown_disclosure_blocks_yoy():
    signal = detect_scope_signals(documents=[_doc("更正公告披露对本期有重大影响，但未说明调整类型。")])[0]
    assert signal.signal_type is ScopeSignalType.UNKNOWN
    assert comparability_decision(signal) == "block_yoy"


@pytest.mark.parametrize(
    ("text", "kind", "decision"),
    [
        ("会计政策变更影响本期", ScopeSignalType.ACCOUNTING_POLICY_CHANGE, "warning"),
        ("合并范围发生变化，新增子公司", ScopeSignalType.CONSOLIDATION_SCOPE_CHANGE, "warning"),
        ("比较期间已调整", ScopeSignalType.COMPARABLE_PERIOD_ADJUSTED, "block_yoy"),
        ("财务报表重列", ScopeSignalType.RESTATED, "block_yoy"),
    ],
)
def test_all_named_scope_signal_types_are_detected(text, kind, decision):
    signal = detect_scope_signals(documents=[_doc(text)])[0]
    assert signal.signal_type is kind
    assert signal.evidence_ids
    assert comparability_decision(signal) == decision


def test_evidence_calculation_blocks_mixed_accounting_scope():
    ledger = EvidenceLedger(snapshot_id="scope")
    for evidence_id, scope in (("parent", "parent"), ("group", "consolidated")):
        ledger.add_fact(
            evidence_id=evidence_id, symbol="600519.SH", metric="equity", value=1,
            currency="CNY", unit="CNY", fiscal_period="2025FY", period_basis="FY",
            published_at=None, available_at=None, provider="fixture", field_path="x",
            scope=scope,
        )
    with pytest.raises(EvidenceError, match="scope_mismatch"):
        ledger.add_calculation(
            evidence_id="bad_scope", symbol="600519.SH", metric="equity_sum", value=2,
            currency="CNY", unit="CNY", operation="add", input_ids=["parent", "group"],
        )
