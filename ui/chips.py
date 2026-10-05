"""Chip components: evidence / status / technical identifiers.

设计原则（UI_REDESIGN_PLAN_V2 §4.2）：真实 ID 只出现在悬浮 title 与点击后的
展开区，不在页面明面直出；芯片文案全部使用中文 + 来源标签。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.theme import TOKENS


def _esc(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _chip_html(label: str, title: str, *, bg: str, fg: str, border: str | None = None) -> str:
    border_css = f"border:1px solid {border};" if border else ""
    return (
        f"<span class='ft-chip' title='{_esc(title)}' style='display:inline-flex;align-items:center;"
        f"gap:.3rem;background:{bg};color:{fg};{border_css}border-radius:9999px;"
        f"padding:.14rem .6rem;font-size:.74rem;font-weight:600;margin:0 .35rem .35rem 0;"
        f"white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis'>"
        f"{label}</span>"
    )


def evidence_chip(evidence_id: str | None, source_label: str, *, page: str | None = None, detail: dict[str, Any] | None = None) -> None:
    """渲染 `来源标签` 证据芯片；完整 evidence ID 收进悬浮 title。

    detail 提供时，芯片下方以展开区承载完整字段（一期「点击 → 展开原文/字段」）。
    """
    if not evidence_id:
        return
    short = _short_evidence_id(evidence_id)
    label = f"{_esc(source_label)} <span style='opacity:.75'>· {short}</span>"
    st.markdown(
        _chip_html(label, f"证据编号 {evidence_id} · 来源 {source_label}", bg=TOKENS["chip_bg"], fg=TOKENS["chip_text"]),
        unsafe_allow_html=True,
    )
    if detail:
        with st.expander(f"查看证据详情 · {source_label}", expanded=False):
            st.write(detail)
            st.caption(f"证据编号：{evidence_id}")


def _short_evidence_id(evidence_id: str) -> str:
    """E-XXX 样式短编号：对 fact_/calc_ 前缀 ID 做确定性短化，悬浮保留全量。"""
    compact = evidence_id.replace("fact_", "F-").replace("calc_", "C-")
    return compact if len(compact) <= 34 else compact[:31] + "…"


def status_chip(status: Any, *, label: str | None = None) -> None:
    """状态芯片：绿=可验证 / 琥珀=需核查 / 红=冲突阻断 / 灰=未覆盖。"""
    key = str(status or "unknown").lower()
    palette = {
        "pass": (TOKENS["green"], "rgba(21,149,112,.12)"),
        "verified": (TOKENS["green"], "rgba(21,149,112,.12)"),
        "warning": (TOKENS["amber"], "rgba(217,148,0,.12)"),
        "limited": (TOKENS["amber"], "rgba(217,148,0,.12)"),
        "degraded": (TOKENS["amber"], "rgba(217,148,0,.12)"),
        "stale": (TOKENS["amber"], "rgba(217,148,0,.12)"),
        "blocked": (TOKENS["coral"], "rgba(217,83,79,.12)"),
        "conflicted": (TOKENS["coral"], "rgba(217,83,79,.12)"),
    }
    names = {"pass": "可验证", "verified": "可验证", "warning": "需核查", "limited": "降级", "degraded": "降级", "stale": "已过期", "blocked": "已阻断", "conflicted": "存在冲突"}
    fg, bg = palette.get(key, (TOKENS["muted"], TOKENS["chip_bg"]))
    text = label or names.get(key, "未覆盖")
    st.markdown(
        _chip_html(f"● {text}", f"状态：{text}", bg=bg, fg=fg),
        unsafe_allow_html=True,
    )


def tech_chip(snapshot_id: str | None, *, label: str = "快照版本") -> None:
    """灰色技术芯片：明面只显示「快照版本」，悬浮展开完整 ID。"""
    if not snapshot_id:
        return
    st.markdown(
        _chip_html(
            f"⚙ {label}", f"{label}：{snapshot_id}",
            bg=TOKENS["chip_bg"], fg=TOKENS["muted"],
        ),
        unsafe_allow_html=True,
    )


def chip_row(chips: list[str]) -> None:
    """一行渲染多个只读文本芯片（如来源类型计数）。"""
    if not chips:
        return
    html = "".join(
        _chip_html(_esc(text), _esc(text), bg=TOKENS["chip_bg"], fg=TOKENS["chip_text"])
        for text in chips
    )
    st.markdown(html, unsafe_allow_html=True)
