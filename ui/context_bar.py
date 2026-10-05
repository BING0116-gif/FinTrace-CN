"""全站顶部上下文条（UI_REDESIGN_PLAN_V2 §4.1，对齐设计稿图1 顶栏）。

[公司名 代码] [● 可验证] [⧉ 离线可复现] …… [本次研究: 时间] [开始新研究 →]
数据语义只降级到悬浮，不删除：snapshot ID 等收进悬浮提示。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.status import normalize


def render(item: dict[str, Any] | None, summary: dict[str, Any] | None, validation: dict[str, Any] | None) -> None:
    if not item or not summary:
        st.info("尚未选择研究快照。请从左侧选择公司，或前往研究任务创建研究。", icon=":material/info:")
        return
    profile = summary.get("profile") or {}
    name = profile.get("name") or item.get("name") or "未命名公司"
    symbol = summary.get("symbol") or item.get("symbol") or "—"
    snapshot_id = item.get("id") or summary.get("snapshot_id") or ""
    research_as_of = str(summary.get("research_as_of") or item.get("research_as_of") or "—").replace("T", " ")
    allowed = bool((validation or {}).get("conclusion_allowed"))
    status = normalize((validation or {}).get("status"))
    verify_fg, verify_bg = (
        ("#159570", "rgba(21,149,112,.12)") if allowed else ("#D9534F", "rgba(217,83,79,.12)")
    )
    verify_text = "可验证" if allowed else {"blocked": "已阻断", "conflicted": "存在冲突"}.get(status, "需核查")

    def _chip(label: str, title: str, fg: str, bg: str, *, border: bool = False) -> str:
        border_css = "border:1px solid #E5EAF0;" if border else ""
        return (
            f"<span title='{title}' style='display:inline-flex;align-items:center;gap:.3rem;"
            f"background:{bg};color:{fg};border-radius:9px;padding:.3rem .8rem;"
            f"font-size:.82rem;font-weight:700;white-space:nowrap;{border_css}'>{label}</span>"
        )

    chips = "".join([
        _chip(f"{name} {symbol}", f"{name} · {symbol}", "#172B4D", "#FFFFFF", border=True),
        _chip(f"● {verify_text}", "结论门禁状态来自 Validator：允许输出确定性结论时为绿色。", verify_fg, verify_bg),
        _chip("⧉ 离线可复现", f"离线可复现 · 快照版本 {snapshot_id}", "#1F6FEB", "rgba(31,111,235,.10)"),
    ])
    left, mid, right = st.columns([3, 1.15, 1])
    with left:
        st.markdown(
            f"<div style='display:flex;align-items:center;flex-wrap:wrap;gap:.5rem'>{chips}</div>",
            unsafe_allow_html=True,
        )
    with mid:
        st.markdown(
            f"<div style='text-align:right;font-size:.76rem;color:#627D98;padding-top:.45rem'>"
            f"本次研究：<b style='color:#172B4D'>{research_as_of}</b></div>",
            unsafe_allow_html=True,
        )
    with right:
        if st.button("开始新研究", type="primary", icon=":material/rocket_launch:", key="context_bar_new_research", width="stretch"):
            st.switch_page("app_pages/research_tasks.py")
