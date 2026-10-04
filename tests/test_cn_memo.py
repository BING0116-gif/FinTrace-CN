import pytest

from src.cn.memo import (
    MEMO_SECTION_IDS, MemoValidationError, _build_memo_prompt,
    _validate_memo_segment_output, build_memo, render_memo_json,
    render_memo_markdown,
)
from src.cn.graph import Claim, ClaimGraph


def test_memo_has_all_sections_and_two_renderings():
    memo = build_memo(symbol="600519.SH", run_id="r1")
    assert [s.section_id for s in memo.sections] == list(MEMO_SECTION_IDS)
    assert memo.validation["valid"]
    assert "不构成投资建议" in render_memo_markdown(memo)
    assert len(render_memo_json(memo)["sections"]) == 11


def test_llm_segment_is_fail_closed_and_whitelisted():
    _validate_memo_segment_output([{"sentence_span": "逻辑成立。", "claim_id": "c1", "claim_type": "inference", "derived_from": ["c1"]}], {"c1"})
    with pytest.raises(MemoValidationError):
        _validate_memo_segment_output([{"sentence_span": "利润为 10。", "claim_id": None, "claim_type": "opinion"}], set())


def test_prompt_injects_claim_whitelist():
    prompt = _build_memo_prompt("risks", {}, {}, {"c2", "c1"})
    assert "c1" in prompt and "不得编造" in prompt

def test_blocked_claim_is_removed_from_conclusion_section():
    graph = ClaimGraph("memo-run", claims=[Claim("c1", "fact", "historical", "收入已验证", ["e1"], validation_status="blocked")], evidence_index={"e1": {"status": "inactive"}})
    memo = build_memo(hits=[{"text": "公司概览"}], graph=graph, symbol="600000.SH", run_id="memo-run")
    overview = next(section for section in memo.sections if section.section_id == "company_overview")
    assert overview.status == "blocked"
    assert all(mark.get("claim_id") is None for mark in overview.tier_marking)
