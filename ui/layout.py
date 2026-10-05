"""Shared frame, context bar and empty/error states."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from services import research_loader as loader
from services.session_state import set_snapshot
from ui.status import badge, normalize


def page_title(title: str, description: str, *, eyebrow: str = "FinTrace-CN") -> None:
    st.markdown(f"<div class='ft-eyebrow'>{eyebrow}</div>", unsafe_allow_html=True)
    st.title(title)
    st.caption(description)


def context_bar(item: dict[str, Any] | None, summary: dict[str, Any] | None, validation: dict[str, Any] | None) -> None:
    if not item or not summary:
        st.info("尚未选择研究快照。请从左侧选择公司，或前往研究任务创建研究。", icon=":material/info:")
        return
    status = normalize((validation or {}).get("status"))
    profile = summary.get("profile") or {}
    trace = loader.trace(item["id"])
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(
                f"**{profile.get('name') or item.get('name') or '未命名公司'}** "
                f"`{summary.get('symbol', item.get('symbol', '—'))}` · "
                f"研究截至 `{summary.get('research_as_of', item.get('research_as_of', '—'))}` · "
                f"Provider `{summary.get('provider', '—')}` · Run `{trace.get('task_id') or '未记录'}` · 模式 `离线可复现`"
            )
            badge(status)
            st.page_link("app_pages/research_tasks.py", label="新建研究", icon=":material/add:")
            payload = {"snapshot": summary, "validation": validation, "evidence": loader.evidence(item["id"])}
            st.download_button("Evidence Pack", json.dumps(payload, ensure_ascii=False, indent=2), f"{summary.get('symbol', 'research')}_evidence_pack.json", "application/json", icon=":material/download:")


def sidebar_context(catalog: list[dict[str, Any]]) -> None:
    with st.sidebar:
        st.markdown("## FinTrace-CN")
        st.caption("可验证的 A 股研究工作台")
        if catalog:
            options = {f"{item.get('name') or item.get('symbol')} · {item.get('symbol')}": item["id"] for item in catalog}
            ids = list(options.values())
            current = st.session_state.get("selected_snapshot_id")
            index = ids.index(current) if current in ids else 0
            selected = st.selectbox("研究快照", list(options), index=index, key="global_snapshot_choice")
            if options[selected] != current:
                set_snapshot(options[selected])
                st.rerun()
        else:
            st.warning("暂无本地研究快照。", icon=":material/database:")
        st.caption("离线快照与在线数据会明确区分。")


def empty_state(title: str, detail: str, *, icon: str = ":material/inbox:") -> None:
    with st.container(border=True):
        st.subheader(title)
        st.caption(detail)
        st.info("当前没有可展示的结果；系统不会用猜测值填充。", icon=icon)


def unavailable(result: dict[str, Any], title: str = "数据未覆盖") -> None:
    reason = result.get("reason") or result.get("unavailable_reason") or "服务没有返回可展示结果。"
    with st.container(border=True):
        st.subheader(title)
        st.warning(reason, icon=":material/warning:")


def current_context() -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    catalog = loader.catalog()
    item, summary = loader.current(catalog, st.session_state.get("selected_snapshot_id"))
    validation = loader.validation(item["id"]) if item else None
    return item, summary, validation
