from src.cn.research import ResearchState


def test_research_state_keeps_plan_evidence_trace_and_bounded_recovery():
    state = ResearchState.create(query="生成贵州茅台研究报告", symbol="600519.SH", research_as_of="2026-08-10T23:00:00+08:00")
    state.record_tool(tool_name="get_cn_financials", arguments={"ticker": "600519.SH"}, started_at="2026-08-10T10:00:00+08:00", result_status="ok", provider="snapshot", evidence_ids=["fact_revenue", "calc_ttm_profit"])
    state.register_evidence(state.tool_trace[0].evidence_ids)
    state.finalize_validation({"valid": True, "missing_evidence": []})

    assert state.plan.required_evidence == ["price", "shares", "net_profit_ttm", "peer_multiples"]
    assert state.facts == ["fact_revenue"]
    assert state.calculations == ["calc_ttm_profit"]
    assert state.request_recovery("missing_peer")
    assert state.request_recovery("missing_peer")
    assert not state.request_recovery("missing_peer")
    assert state.conflicts == ["recovery_limit_reached:missing_peer"]
    assert state.to_dict()["validation_result"]["valid"]
