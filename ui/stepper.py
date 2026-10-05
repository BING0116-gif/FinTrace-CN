"""横向研究进度 stepper（UI_REDESIGN_PLAN_V2 §5.1 / P1-1）。

纯 HTML/CSS 通过 st.markdown 注入；状态三态映射：
verified → ✅（green）、warning/degraded → ⏳（amber）、blocked → ❌（coral）、
unknown/其它 → 未开始（灰）。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.theme import TOKENS


def _dot_state(status: Any) -> tuple[str, str]:
    """返回 (图标, 颜色)。"""
    key = str(status or "unknown").lower()
    if key in {"verified", "pass"}:
        return "✓", TOKENS["green"]
    if key in {"warning", "degraded", "stale", "limited"}:
        return "…", TOKENS["amber"]
    if key in {"blocked", "conflicted"}:
        return "×", TOKENS["coral"]
    return "○", "#B8C4D0"


def stepper(steps: list[dict[str, Any]], *, key: str = "ft_stepper") -> None:
    """渲染横向圆点连线组件；每步下方放计数与说明。"""
    if not steps:
        return
    items = []
    total = len(steps)
    for index, step in enumerate(steps):
        icon, color = _dot_state(step.get("status"))
        is_last = index == total - 1
        connector = (
            ""
            if is_last
            else f"<div style='flex:1;height:2px;background:{'#D5DEE8' if str(step.get('status')).lower() in {'verified','pass'} else '#E5EAF0'};"
                 f"margin:14px 6px 0;min-width:24px'></div>"
        )
        count = step.get("count")
        count_text = f"{count}" if count is not None else ""
        detail = step.get("detail") or ""
        label = step.get("label") or ""
        items.append(
            f"<div style='display:flex;flex-direction:column;align-items:center;min-width:76px'>"
            f"<div style='width:30px;height:30px;border-radius:9999px;background:{color};color:#fff;"
            f"display:flex;align-items:center;justify-content:center;font-size:.9rem;font-weight:700'>{icon}</div>"
            f"<div style='font-size:.78rem;font-weight:600;margin-top:.3rem;color:#172B4D;white-space:nowrap'>{label}</div>"
            f"<div style='font-size:.7rem;color:#627D98;white-space:nowrap'>{detail}"
            f"{f' · {count_text}' if count_text else ''}</div></div>"
        )
        if connector:
            items.append(connector)
    html = (
        f"<div class='{key}' style='display:flex;align-items:flex-start;"
        f"background:#FFFFFF;border:1px solid {TOKENS['border']};border-radius:12px;padding:16px'>"
        + "".join(items)
        + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)
