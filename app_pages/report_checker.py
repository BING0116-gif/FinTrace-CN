import json
import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from src.cn.checker import DraftClaim, check_report
from ui.claim_passport import render
from ui.status import callout


item, summary, validation = context_or_empty("研报核查", "将研报草稿中的 Claim 与确定性 Checker、Evidence、Calculation 和 Validator 明确分层。")
if item and summary:
    sid = item["id"]
    evidence = loader.evidence(sid)
    facts = [{"fact_id": row.get("evidence_id"), "metric": row.get("metric"), "value": row.get("value"), "unit": row.get("unit"), "fiscal_period": row.get("period"), "available_at": row.get("published_at"), "scope": None, "version": "AS_REPORTED"} for row in evidence.get("records", []) if row.get("kind") == "fact"]
    draft = st.text_area("研报草稿", value=st.session_state.get("report_draft", ""), height=220, placeholder="粘贴需要核查的数字、单位和因果判断；未提交的文本不进入结论。", key="checker_draft")
    st.session_state.report_draft = draft
    st.caption("草稿原文与结构化 Claim 分开保存；只有确定性 Checker 结果才能升级 Claim 状态。")
    with st.form("structured_claim_check", border=True):
        sentence = st.text_input("待核查句子", value=draft.splitlines()[0][:300] if draft.strip() else "")
        metric_name = st.selectbox("指标", ["revenue", "net_profit", "net_profit_parent", "pe", "pb", "ps"])
        period = st.text_input("期间", value="2025FY", help="使用 YYYYFY、YYYYQ1、YYYYH1、YYYY9M 或 TTM。")
        value = st.number_input("句中数值", value=0.0, format="%.4f")
        unit = st.selectbox("单位", ["CNY", "亿元", "万元", "CNY/share", "multiple"])
        evidence_options = [row.get("evidence_id") for row in facts if row.get("metric") == metric_name and row.get("evidence_id")]
        evidence_id = st.selectbox("引用 Evidence ID", ["（未引用）", *evidence_options])
        claim_type = st.selectbox("认识论类型", ["factual", "causal", "valuation", "opinion"])
        check = st.form_submit_button("运行确定性 Checker", type="primary", icon=":material/fact_check:")
    if check:
        claim = DraftClaim("draft_claim_1", sentence or draft[:300] or "（空句子）", metric=metric_name, period=period, value=value, unit=unit, claim_type=claim_type, evidence_ids=() if evidence_id == "（未引用）" else (evidence_id,))
        findings = check_report([claim], facts, research_as_of=summary.get("research_as_of"))
        status = "verified" if not findings else "blocked" if any(row.severity == "error" for row in findings) else "warning"
        st.session_state["checker_claims"] = [{"claim_id": claim.claim_id, "title": claim.sentence, "statement": claim.sentence, "kind": claim.mapped_claim_type, "status": status, "source": evidence_id, "accounting_context": {"metric": metric_name, "period": period, "unit": unit}, "calculation": {"checker": "src.cn.checker.check_report"}, "dependency": list(claim.evidence_ids), "validation": {"status": status, "findings": [row.to_dict() for row in findings]}, "integrity": "确定性 Checker 输出；未经 Checker 的文本不会进入结论。"}]
        st.session_state["checker_findings"] = [row.to_dict() for row in findings]
    st.caption("Financial Claim Passport 的八个 proof 区块：Statement、Source、Accounting Context、Calculation、Assumption、Dependency、Validation、Integrity。")
    claims = st.session_state.get("checker_claims", [])
    if not claims:
        st.info("尚未提取 Claim。")
    else:
        selected = st.selectbox("Claim", [claim["claim_id"] for claim in claims], key="claim_choice")
        claim = next(claim for claim in claims if claim["claim_id"] == selected)
        render(claim)
        findings = st.session_state.get("checker_findings", [])
        if findings:
            st.subheader("确定性 Checker Finding")
            st.dataframe(findings, hide_index=True, width="stretch")
        else:
            callout(claim.get("status", "degraded"), "Claim 已通过当前确定性检查；仍需结合全局 Validator 和 Evidence 依赖决定是否可用于报告。")
        st.download_button("导出核查报告", json.dumps({"snapshot_id": item["id"], "claims": claims, "validation": validation}, ensure_ascii=False, indent=2), f"{item['symbol']}_claim_check.json", "application/json", icon=":material/download:")
