"""研判核查（Claim Passport 为主视图）。

对应 UI_REDESIGN_PLAN_V2 §5.2：左栏研报草稿（Claim 高亮 + 问题标签），
右栏声明核查护照（状态表格 + 核查按钮 + 证据与原文）。
"""

import json

import pandas as pd
import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from src.cn.checker import DraftClaim, check_report
from ui.chips import evidence_chip
from ui.claim_passport import render
from ui.status import badge, callout

FINDING_LABELS = {
    "numeric_mismatch": "错误数字",
    "repeat_error": "重复错误",
    "calculation_basis": "计算口径",
    "missing_evidence": "缺少证据",
}

SEVERITY_BG = {"error": "rgba(217,83,79,.10)", "warning": "rgba(217,148,0,.10)", "info": "rgba(31,111,235,.08)"}
STATUS_BG = {"verified": "rgba(21,149,112,.10)", "blocked": "rgba(217,83,79,.10)", "warning": "rgba(217,148,0,.10)"}


def _finding_label(check_type: str) -> str:
    for key, label in FINDING_LABELS.items():
        if key in check_type:
            return label
    return "需核查"


item, summary, validation = context_or_empty(
    "研判核查",
    "研报草稿中的 Claim 与确定性 Checker、Evidence、Calculation 和 Validator 分层；"
    "声明核查护照展示每个 Claim 的证据与原文。",
)
if item and summary:
    sid = item["id"]
    left, right = st.columns([1.05, 1])
    evidence = loader.evidence(sid)
    facts = [
        {
            "fact_id": row.get("evidence_id"), "metric": row.get("metric"),
            "value": row.get("value"), "unit": row.get("unit"),
            "fiscal_period": row.get("period"), "available_at": row.get("published_at"),
            "scope": None, "version": "AS_REPORTED",
        }
        for row in evidence.get("records", []) if row.get("kind") == "fact"
    ]

    with left:
        st.subheader("研报草稿")
        report_available = loader.report(sid)
        prefill = st.session_state.get("report_draft", "") or (
            report_available.get("content") or "" if report_available.get("available") else ""
        )
        draft = st.text_area(
            "草稿文本", value=prefill, height=280, key="review_draft",
            placeholder="粘贴研报草稿或报告文本；未核查的文本不会进入结论。",
            label_visibility="collapsed",
        )
        st.session_state.report_draft = draft
        view_mode = st.segmented_control(
            "视图", ["全文视图", "问题视图"], default="全文视图", key="review_view_mode"
        )

        claims = st.session_state.get("checker_claims", [])
        findings_all = st.session_state.get("checker_findings", [])
        if view_mode == "问题视图":
            problem_sentences = {
                (row.get("original") or ""): row for row in findings_all
            }
            shown = 0
            for original, row in problem_sentences.items():
                if not original:
                    continue
                shown += 1
                label = _finding_label(row.get("check_type", ""))
                bg = SEVERITY_BG.get(row.get("severity", "warning"), SEVERITY_BG["warning"])
                st.markdown(
                    f"<div style='background:{bg};border-radius:8px;padding:.7rem .9rem;margin-bottom:.5rem'>"
                    f"<span style='background:{'#D9534F' if row.get('severity') == 'error' else '#D99400'};color:#fff;"
                    f"border-radius:9999px;padding:.1rem .55rem;font-size:.72rem;font-weight:700'>{label}</span> "
                    f"{original}</div>",
                    unsafe_allow_html=True,
                )
                if row.get("suggestion"):
                    st.caption(f"建议：{row['suggestion']}")
            if not shown:
                st.info("当前草稿没有已发现的问题；运行核查后此处会列出含问题的段落。")
        else:
            sentences = [line.strip() for line in draft.splitlines() if line.strip()]
            status_by_sentence = {c.get("statement") or c.get("title"): c.get("status") for c in claims}
            for index, sentence in enumerate(sentences):
                status = status_by_sentence.get(sentence)
                bg = STATUS_BG.get(status or "", "transparent")
                tag = ""
                claim_finding = next((row for row in findings_all if row.get("claim_id") and sentence in {c.get("statement") for c in claims if c.get("claim_id") == row.get("claim_id")}), None)
                if claim_finding:
                    tag = (f"<span style='background:#D9534F;color:#fff;border-radius:9999px;"
                           f"padding:.05rem .5rem;font-size:.7rem;margin-left:.4rem'>"
                           f"{_finding_label(claim_finding.get('check_type', ''))}</span>")
                st.markdown(
                    f"<div style='background:{bg};border-radius:8px;padding:.5rem .7rem;"
                    f"margin-bottom:.4rem;line-height:1.55'>{sentence}{tag}</div>",
                    unsafe_allow_html=True,
                )
            if not sentences:
                st.info("草稿为空；粘贴文本后可对单个句子运行确定性核查。")

        st.caption("草稿原文与结构化 Claim 分开保存；只有确定性 Checker 结果才能升级 Claim 状态。")
        with st.form("review_claim_check", border=True):
            sentence = st.text_input("待核查句子", value=draft.splitlines()[0][:300] if draft.strip() else "")
            metric_name = st.selectbox("指标", ["revenue", "net_profit", "net_profit_parent", "pe", "pb", "ps"])
            period = st.text_input("期间", value="2025FY", help="使用 YYYYFY、YYYYQ1、YYYYH1、YYYY9M 或 TTM。")
            value = st.number_input("句中数值", value=0.0, format="%.4f")
            unit = st.selectbox("单位", ["CNY", "亿元", "万元", "CNY/share", "multiple"])
            evidence_options = [row.get("evidence_id") for row in facts if row.get("metric") == metric_name and row.get("evidence_id")]
            evidence_id = st.selectbox("引用证据来源", ["（未引用）", *evidence_options])
            claim_type = st.selectbox("认识论类型", ["factual", "causal", "valuation", "opinion"])
            check = st.form_submit_button("核查此声明", type="primary", icon=":material/fact_check:")
        if check:
            claim = DraftClaim(
                "draft_claim_1", sentence or draft[:300] or "（空句子）",
                metric=metric_name, period=period, value=value, unit=unit,
                claim_type=claim_type,
                evidence_ids=() if evidence_id == "（未引用）" else (evidence_id,),
            )
            findings = check_report([claim], facts, research_as_of=summary.get("research_as_of"))
            status = "verified" if not findings else "blocked" if any(row.severity == "error" for row in findings) else "warning"
            st.session_state["checker_claims"] = [{
                "claim_id": claim.claim_id, "title": claim.sentence, "statement": claim.sentence,
                "kind": claim.mapped_claim_type, "status": status, "source": evidence_id,
                "accounting_context": {"metric": metric_name, "period": period, "unit": unit},
                "calculation": {"checker": "src.cn.checker.check_report"},
                "dependency": list(claim.evidence_ids),
                "validation": {"status": status, "findings": [row.to_dict() for row in findings]},
                "integrity": "确定性 Checker 输出；未经 Checker 的文本不会进入结论。",
            }]
            st.session_state["checker_findings"] = [row.to_dict() for row in findings]
            st.rerun()

    with right:
        st.subheader("声明核查护照")
        st.caption("Claim Passport · 每个声明的证据与验证状态")
        claims = st.session_state.get("checker_claims", [])
        if not claims:
            st.info("尚未核查任何声明。在左侧填写声明句子后点击「核查此声明」。")
        else:
            claim = claims[-1]
            render(claim)
            findings = st.session_state.get("checker_findings", [])
            if findings:
                st.subheader("核查发现")
                st.dataframe(pd.DataFrame(findings), hide_index=True, width="stretch")
            else:
                callout(claim.get("status", "degraded"), "声明已通过当前确定性检查；仍需结合全局 Validator 和证据依赖决定是否可用于报告。")
            st.download_button(
                "导出核查报告",
                json.dumps({"snapshot_id": sid, "claims": claims, "validation": validation}, ensure_ascii=False, indent=2),
                f"{item['symbol']}_claim_check.json", "application/json", icon=":material/download:",
            )

    with right:
        st.subheader("证据与原文")
        records = evidence.get("records", [])
        if not records:
            st.info("当前快照没有可展示的证据来源。")
        else:
            for record in records[:12]:
                detail = {
                    "指标": record.get("metric"), "数值": record.get("value"), "单位": record.get("unit"),
                    "期间": record.get("period") or "—", "来源": record.get("provider"),
                    "状态": record.get("status"),
                }
                evidence_chip(
                    record.get("evidence_id", ""), str(record.get("provider") or "快照"),
                    detail=detail,
                )
            st.caption("点击证据来源芯片展开完整字段；证据 ID 收纳在芯片悬浮提示与展开区内，审计回放页保留全量 ID。")
