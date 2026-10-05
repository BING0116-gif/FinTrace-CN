"""Evidence table, provenance drawer and dependency display."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from services.session_state import go_to_evidence


def evidence_table(result: dict[str, Any], *, key: str = "evidence_table") -> list[dict[str, Any]]:
    records = result.get("records") or []
    if not records:
        st.info("当前快照没有可展示的 Evidence。")
        return []
    rows = [{"Evidence ID": item.get("evidence_id"), "类型": item.get("kind"), "指标": item.get("metric"), "数值": item.get("value"), "单位": item.get("unit"), "期间": item.get("period") or "—", "来源": item.get("provider"), "状态": item.get("status"), "关联 Claim": item.get("claim_id") or "未关联"} for item in records]
    frame = pd.DataFrame(rows)
    event = st.dataframe(frame, hide_index=True, width="stretch", height=360, on_select="rerun", selection_mode="single-row", key=key)
    if event.selection.rows:
        go_to_evidence(str(frame.iloc[event.selection.rows[0]]["Evidence ID"]))
    selected_id = st.session_state.get("selected_evidence_id")
    selected = next((item for item in records if item.get("evidence_id") == selected_id), None)
    if selected:
        detail(selected)
    return records


def detail(record: dict[str, Any]) -> None:
    with st.container(border=True):
        st.subheader(f"Evidence 详情 · {record.get('evidence_id')}")
        left, right = st.columns(2)
        with left:
            st.write({key: record.get(key) for key in ("kind", "metric", "value", "unit", "period", "status", "provider")})
        with right:
            st.write({key: record.get(key) for key in ("field_path", "operation", "input_ids", "published_at", "price_basis")})


def export_payload(payload: dict[str, Any], filename: str) -> None:
    st.download_button("导出 Evidence Pack（JSON）", json.dumps(payload, ensure_ascii=False, indent=2), filename, "application/json", icon=":material/download:")


def dependency_graph(graph: dict[str, Any]) -> None:
    edges = graph.get("edges") or []
    if not edges:
        st.info("当前没有计算依赖边。")
        return
    rows = [{"输入 Evidence": edge.get("source"), "输出 Calculation": edge.get("target")} for edge in edges]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
