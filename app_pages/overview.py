import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from ui.cards import conclusion, metric, workflow
from ui.status import callout, summary_card


item, summary, validation = context_or_empty("研究总览", "先看研究进行到哪里、哪些结论可用，以及下一步需要补什么证据。")
if item and summary:
    snapshot_id = item["id"]
    readiness = loader.readiness(snapshot_id)
    insights = loader.overview_insights(snapshot_id)
    evidence = loader.evidence(snapshot_id)
    financials = loader.financials(snapshot_id)
    valuation = loader.valuation(snapshot_id)
    steps = [
        {"label": "文档已登记", "status": "verified" if evidence.get("records") else "unknown", "detail": "Evidence Ledger 可读取" if evidence.get("records") else "暂无证据", "count": len(evidence.get("records", []))},
        {"label": "财务分析", "status": "verified" if financials.get("statements") else "unknown", "detail": f"{len(financials.get('statements', []))} 个披露期间", "count": len(financials.get("statements", []))},
        {"label": "研报核查", "status": "warning", "detail": "等待草稿 Claim", "count": 0},
        {"label": "估值", "status": "verified" if valuation.get("available") else "degraded", "detail": f"{valuation.get('peer_count', 0)} 家同行", "count": valuation.get("peer_count", 0)},
        {"label": "备忘录", "status": "unknown", "detail": "等待研究证据", "count": 0},
    ]
    workflow(steps)
    st.subheader("结论健康度")
    summary_card(validation or {}, affected="估值区间、研究备忘录")
    cols = st.columns(4)
    records = evidence.get("records", [])
    with cols[0]:
        st.metric("可验证结论", sum(1 for x in records if x.get("status") == "verified"))
    with cols[1]:
        st.metric("需要核查", len(validation.get("warnings", [])) if validation else 0)
    with cols[2]:
        st.metric("已阻断", len(validation.get("blocked", [])) if validation else 0)
    with cols[3]:
        st.metric("Evidence 数量", len(records))
    st.subheader("关键指标")
    metrics = summary.get("key_metrics", {})
    metric_cols = st.columns(6)
    latest_statements = [row for row in financials.get("statements", []) if row.get("available_as_of")]
    latest_statement = max(latest_statements, key=lambda row: row.get("fiscal_period", ""), default={})
    latest_values = latest_statement.get("values") or {}
    latest_period = latest_statement.get("fiscal_period")
    cashflow_id = (latest_statement.get("evidence_ids") or {}).get("operating_cash_flow")
    entries = [("RAW 收盘价", metrics.get("price"), "CNY/share", summary.get("research_as_of"), summary.get("evidence_ids", {}).get("price")), ("市值", metrics.get("market_cap"), "CNY", None, summary.get("evidence_ids", {}).get("market_cap")), ("TTM P/E", metrics.get("pe_ttm"), "multiple", "TTM", summary.get("evidence_ids", {}).get("pe_ttm")), ("TTM 归母净利润", metrics.get("ttm_net_profit"), "CNY", "TTM", summary.get("evidence_ids", {}).get("ttm_net_profit")), ("营业收入", metrics.get("ttm_revenue"), "CNY", "TTM", None), ("经营活动现金流", latest_values.get("operating_cash_flow"), "CNY", latest_period, cashflow_id)]
    for col, entry in zip(metric_cols, entries):
        with col:
            metric(entry[0], entry[1], unit=entry[2], period=entry[3], evidence_id=entry[4])
    st.subheader("关键结论")
    allowed = bool((validation or {}).get("conclusion_allowed"))
    if not allowed:
        callout("blocked", "Validator 已阻断确定性结论；页面隐藏推测性估值与报告结论。")
    else:
        status = insights.get("performance_status", "insufficient_data")
        conclusion("业绩状态", f"服务层判定为 `{status}`，同比变化来自版本化财务期间数据。", kind="inference", status=validation.get("status", "warning"), evidence_count=len(records))
    st.subheader("风险与关注点")
    for check in (validation or {}).get("checks", []):
        if check.get("status") != "pass":
            with st.container(border=True):
                st.write(f"**{check.get('label', check.get('code'))}**")
                st.caption(f"{check.get('detail')} · 处理：{check.get('remediation')}")
