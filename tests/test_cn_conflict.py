from src.cn.conflict import DATA_CONFLICT, NEW_INFORMATION, VERSION_SUPERSESSION, resolve_conflicts, unresolved_report
from src.cn.normalization import NormalizedFact


def fact(fid, value, *, provider="third_party", version="AS_REPORTED", period="2025FY", scope="consolidated", published="2026-01-01"):
    return NormalizedFact(fid, "600519.SH", "revenue", value, "CNY", "元", period, "FY", "income", "flow", scope, (period,), ("e_" + fid,), provider, published, published, "valid", version)


def test_corrected_filing_supersedes_original_and_keeps_record():
    selected, records = resolve_conflicts([fact("old", 10, provider="official_filing"), fact("new", 12, provider="exchange", version="CORRECTED", published="2026-02-01")])
    assert [item.fact_id for item in selected] == ["new"]
    assert records[0].change_kind == VERSION_SUPERSESSION
    assert records[0].selected_source == "new"


def test_same_priority_disagreement_is_unresolved_and_blocked():
    selected, records = resolve_conflicts([fact("a", 10), fact("b", 12)])
    assert selected == []
    assert unresolved_report(records)[0]["change_kind"] == DATA_CONFLICT


def test_priority_and_rounding_and_new_period():
    selected, records = resolve_conflicts([fact("official", 10, provider="exchange"), fact("third", 12), fact("next", 20, period="2026FY")])
    assert {item.fact_id for item in selected} == {"official", "next"}
    assert any(item.change_kind == DATA_CONFLICT and not item.unresolved for item in records)
    assert any(item.change_kind == NEW_INFORMATION for item in records)
    selected, records = resolve_conflicts([fact("a", 10.0), fact("b", 10.0000000001)])
    assert not records and len(selected) == 1
