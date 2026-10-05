import pandas as pd
import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from ui.evidence import dependency_graph, evidence_table, export_payload
from ui.layout import section


item, summary, validation = context_or_empty("文档与证据", "文档登记、解析状态、Evidence Ledger 和原文定位集中在一个可回溯界面。")

if item and summary:
    snapshot_id = item["id"]
    left, center, right = st.columns([1, 2, 1.2])
    with left:
        section("研究快照")
        catalog = loader.catalog()
        st.dataframe([{key: row.get(key) for key in ("symbol", "name", "research_as_of", "id")} for row in catalog], hide_index=True, width="stretch")
    with center:
        section("Evidence 表")
        result = loader.evidence(snapshot_id)
        evidence_table(result, key=f"evidence_{snapshot_id}")
    with right:
        section("快照详情")
        st.write({"document_id": snapshot_id, "symbol": summary.get("symbol"), "provider": summary.get("provider"), "research_as_of": summary.get("research_as_of"), "currency": (summary.get("profile") or {}).get("currency")})
        st.caption("原始文档页码仅在文档解析结果提供时展示；没有页码不会被 UI 补造。")
    section("证据依赖")
    dependency_graph(result.get("dependency_graph", {}))
    export_payload({"snapshot": summary, "validation": validation, "evidence": result}, f"{summary.get('symbol', 'research')}_evidence_pack.json")

section("已解析的上传文档")
uploaded = st.session_state.get("task_uploaded_documents", [])
if uploaded:
    st.dataframe(pd.DataFrame(uploaded), hide_index=True, width="stretch")
    selected_document = st.selectbox("查看原文与解析片段", [row.get("document_id") or row.get("file_name") for row in uploaded], key="uploaded_document_choice")
    selected_row = next(row for row in uploaded if (row.get("document_id") or row.get("file_name")) == selected_document)
    document = selected_row.get("document") or {}
    with st.container(border=True):
        st.subheader(f"文档详情 · {document.get('file_name') or selected_row.get('file_name')}")
        st.write({key: document.get(key) for key in ("document_id", "file_name", "sha256", "document_type", "parser_name", "parser_version", "page_count", "status", "symbol", "fiscal_period", "published_at", "warnings")})
        fragments = selected_row.get("fragments") or []
        if fragments:
            fragment = st.selectbox("原文片段", range(len(fragments)), format_func=lambda index: f"第 {fragments[index].get('page_number', '—')} 页 · {fragments[index].get('fragment_id', 'fragment')}", key="document_fragment_choice")
            st.text_area("原文预览", fragments[fragment].get("text", ""), height=180, disabled=True)
            st.caption("原文预览来自解析器返回的片段；没有可定位页码时不展示猜测位置。")
        else:
            st.info("该文档没有可展示的解析片段。")
        facts = selected_row.get("fact_rows") or []
        if facts:
            st.caption("以下是解析候选事实，不等同于已进入研究 Evidence Ledger。")
            st.dataframe(pd.DataFrame(facts), hide_index=True, width="stretch")
else:
    st.info("暂无本次会话上传的文档。前往研究任务上传年报、研报草稿或公告。")
