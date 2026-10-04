"""Small, read-only demo surface for the document-to-memo evidence chain.

The existing workbench remains the primary snapshot UI.  This module adds a
single navigation entry with tabs for the CARD-15 pages and deliberately shows
missing artifacts as unavailable instead of inventing demo data.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

DEMO_TABS = (
    "Upload Task", "Document Viewer", "Execution Trace", "Financial Analysis",
    "Report Corrections", "Valuation", "Claim-Evidence Graph", "Investment Memo",
    "Validator", "Audit Replay", "Export Evidence Pack",
)


def _unavailable(message: str) -> None:
    st.info(f"data_unavailable：{message}")


def _json_block(value: Any) -> None:
    st.json(value if value is not None else {})


def _artifact_block(artifacts: dict[str, Any] | None, key: str, label: str) -> None:
    artifact = (artifacts or {}).get(key)
    if not artifact:
        _unavailable(f"当前运行没有 {label} 产物。")
    elif artifact.get("status") != "available":
        st.error(f"{label} 产物不可读：{artifact.get('error', 'unknown_error')}")
    elif artifact.get("data") is None:
        st.info(f"{label} 产物已存在：{artifact.get('filename', 'unknown')}")
    elif isinstance(artifact.get("data"), str):
        st.markdown(artifact["data"])
    else:
        _json_block(artifact.get("data"))


def _render_status_summary(service_data: dict[str, Any], selected_run: dict[str, Any]) -> None:
    provenance = service_data.get("provenance") or {}
    validation = (service_data.get("pages") or {}).get("validator") or {}
    artifacts = selected_run.get("artifacts") or {}
    available = sum(1 for key in ("acme", "claim_passport", "fragility", "temporal", "finfuzz")
                    if artifacts.get(key) and artifacts[key].get("status") == "available")
    source_label = "synthetic_demo" if provenance.get("synthetic_demo") else provenance.get("provider") or "unknown"
    validation_label = validation.get("status") or "unknown"
    run_label = selected_run.get("run_id") or "未选择"
    readiness = service_data.get("readiness") or {"status": "missing_assets", "reason": "未执行 readiness 检查"}
    readiness_status = readiness.get("status", "unknown")
    if readiness_status == "ready":
        st.success(f"Demo readiness：{readiness_status} · {readiness.get('reason', '')}")
    elif readiness_status in {"partial", "missing_assets"}:
        st.warning(f"Demo readiness：{readiness_status} · {readiness.get('reason', '')}")
    else:
        st.error(f"Demo readiness：{readiness_status} · {readiness.get('reason', '')}")
    with st.expander("查看真实材料验收检查", expanded=readiness_status != "ready"):
        st.json(readiness.get("checks", {}))
    with st.container(horizontal=True):
        st.metric("Source", source_label, border=True)
        st.metric("Validation", validation_label, border=True)
        st.metric("Selected run", run_label, border=True)
        st.metric("Innovation artifacts", f"{available}/5", border=True)
    with st.expander("查看 provenance", expanded=False):
        st.json({
            "snapshot_id": provenance.get("snapshot_id"),
            "research_as_of": provenance.get("research_as_of"),
            "fetched_at": provenance.get("fetched_at"),
            "provider": provenance.get("provider"),
            "data_quality": provenance.get("data_quality"),
            "source": provenance.get("source"),
            "synthetic_demo": provenance.get("synthetic_demo"),
        })


def render_demo_pages(*, service_data: dict[str, Any] | None = None,
                      export_pack: Any | None = None,
                      ingest_document: Any | None = None) -> None:
    """Render CARD-15 from the workbench service contract only."""
    service_data = service_data or {}
    snapshot = service_data.get("snapshot") or {}
    pages = service_data.get("pages") or {}
    selected_run = service_data.get("selected_run") or {}
    artifacts = selected_run.get("artifacts")
    st.title("Demo chain")
    provenance = service_data.get("provenance") or {}
    st.caption(
        f"Document → Evidence → Calculation → Claim → Memo；Snapshot {provenance.get('snapshot_id', 'unknown')}，"
        "所有缺失或 blocked 状态原样展示。"
    )
    _render_status_summary(service_data, selected_run)
    tabs = st.tabs(DEMO_TABS)

    with tabs[0]:
        st.subheader("Upload Task")
        if not callable(ingest_document):
            _unavailable("当前工作台未注册文档服务。")
        else:
            with st.form("card15_document_upload", clear_on_submit=False):
                uploaded = st.file_uploader("上传 PDF、TXT 或 Markdown", type=["pdf", "txt", "md"])
                upload_symbol = st.text_input("A 股代码（可选）", placeholder="例如：600519.SH")
                upload_period = st.text_input("财务期间（可选）", placeholder="例如：2025FY")
                upload_published = st.text_input("披露时间（可选）", placeholder="ISO-8601 时间")
                submitted = st.form_submit_button("注册并解析", type="primary")
            if submitted:
                if uploaded is None:
                    st.warning("请先选择一个文档。")
                else:
                    try:
                        result = ingest_document(
                            uploaded.getvalue(), uploaded.name, symbol=upload_symbol,
                            fiscal_period=upload_period, published_at=upload_published,
                        )
                        st.session_state["card15_document_result"] = result
                        st.success(f"解析完成：{result['document']['document_id']}")
                    except (OSError, ValueError) as exc:
                        st.error(f"文档注册/解析失败：{exc}")
            document_result = st.session_state.get("card15_document_result")
            if document_result:
                st.caption(f"Document ID: {document_result['document']['document_id']} · 候选 Evidence：{document_result.get('candidate_evidence_count', 0)}")
    with tabs[1]:
        st.subheader("Document Viewer")
        document_result = st.session_state.get("card15_document_result") or {}
        fragments = document_result.get("fragments") or snapshot.get("source_fragments", [])
        if fragments:
            st.dataframe(fragments, width="stretch", hide_index=True)
            facts = document_result.get("facts") or []
            if facts:
                st.subheader("Extracted candidates")
                st.caption("以下是解析候选，不等同于已验证的金融 Evidence。")
                st.dataframe(facts, width="stretch", hide_index=True)
        else:
            _unavailable("当前快照没有页级 SourceFragment。")
    with tabs[2]:
        st.subheader("Execution Trace")
        _json_block(pages.get("trace", {}).get("events", []))
    with tabs[3]:
        st.subheader("Financial Analysis")
        _json_block(pages.get("financial_analysis", {}))
    with tabs[4]:
        st.subheader("Report Corrections")
        _artifact_block(artifacts, "corrections", "Report Corrections")
    with tabs[5]:
        st.subheader("Valuation")
        _json_block(pages.get("valuation", {}))
    with tabs[6]:
        st.subheader("Claim-Evidence Graph")
        _json_block(pages.get("evidence", {}).get("dependency_graph", {}))
        _artifact_block(artifacts, "claim_passport", "Claim Passport")
        _artifact_block(artifacts, "fragility", "Fragility")
    with tabs[7]:
        st.subheader("Investment Memo")
        _artifact_block(artifacts, "memo", "Investment Memo")
    with tabs[8]:
        st.subheader("Validator")
        _json_block(pages.get("validator", {}))
        document_result = st.session_state.get("card15_document_result") or {}
        if document_result.get("acme_report"):
            st.subheader("ACME on uploaded document")
            st.caption("ACME 只检测并定位约束异常，不自动修正候选数字。")
            _json_block(document_result["acme_report"])
        st.divider()
        _artifact_block(artifacts, "acme", "ACME")
        _artifact_block(artifacts, "finfuzz", "FinFuzz")
    with tabs[9]:
        st.subheader("Audit Replay")
        runs = service_data.get("runs", [])
        if not runs:
            _unavailable("runs 目录为空，无法重放。")
        else:
            st.write(selected_run.get("validation", {}))
            st.dataframe((selected_run.get("timeline") or {}).get("events", []), width="stretch", hide_index=True)
        _artifact_block(artifacts, "temporal", "Temporal Revalidation")
    with tabs[10]:
        st.subheader("Export Evidence Pack")
        run_id = selected_run.get("run_id")
        if not run_id:
            st.warning("blocked：没有持久化 run，不能导出 Evidence Pack；不能用 snapshot 页面内容伪造 Evidence Pack。")
        elif not callable(export_pack):
            _unavailable("当前工作台未注册 Evidence Pack 导出服务。")
        elif st.button("导出当前 Evidence Pack", key="card15_export_pack"):
            try:
                result = export_pack(run_id)
                st.download_button(
                    "下载 Evidence Pack ZIP",
                    data=result["content"],
                    file_name=result["filename"],
                    mime=result.get("media_type", "application/zip"),
                    key="card15_download_pack",
                )
                st.success(f"已通过服务层生成 {result['filename']}。")
            except (FileNotFoundError, ValueError, OSError) as exc:
                st.error(f"Evidence Pack 导出失败：{exc}")

