"""「开始新研究」全流程向导（UI_REDESIGN_PLAN_V2 P2-4）。

贯穿业务导航 ①→⑨ 的进度引导：每步状态由服务层数据派生（不补造），
点击任一步跳转对应页面；「开始新研究」上下文条入口落在研究任务页。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.theme import TOKENS


def _state_color(done: bool, current: bool) -> tuple[str, str]:
    if done:
        return "✓", TOKENS["green"]
    if current:
        return "●", TOKENS["blue"]
    return "○", "#B8C4D0"


def render_wizard(
    item: dict[str, Any] | None,
    summary: dict[str, Any] | None,
    signals: dict[str, bool],
    *,
    current_step: str = "研究任务",
) -> None:
    """渲染横向向导条。

    signals: 每步完成信号（证据就绪 / 财务就绪 / 声明已核查 / 估值可用 /
    备忘录可用 / 审计轨迹存在 / 复盘可用），全部来自服务层数据。
    """
    if not item or not summary:
        return
    steps: list[tuple[str, str, bool]] = [
        ("总览", "app_pages/overview.py", True),
        ("研究任务", "app_pages/research_tasks.py", bool(signals.get("evidence"))),
        ("文档与证据", "app_pages/documents.py", bool(signals.get("evidence"))),
        ("财务分析", "app_pages/financial_analysis.py", bool(signals.get("financials"))),
        ("研判核查", "app_pages/research_review.py", bool(signals.get("claims"))),
        ("估值", "app_pages/valuation.py", bool(signals.get("valuation"))),
        ("投资备忘录", "app_pages/memo.py", bool(signals.get("memo"))),
        ("审计回放", "app_pages/audit_replay.py", bool(signals.get("trace"))),
        ("每日复盘", "app_pages/daily_review.py", bool(signals.get("daily_review"))),
    ]
    chips = []
    for index, (label, path, done) in enumerate(steps, start=1):
        icon, color = _state_color(done, label == current_step)
        weight = "700" if label == current_step else "600"
        chips.append(
            f"<span style='display:inline-flex;align-items:center;gap:.35rem;"
            f"background:{'#FFFFFF' if label != current_step else 'rgba(31,111,235,.08)'};"
            f"border:1px solid {TOKENS['border']};border-radius:9999px;padding:.22rem .7rem;"
            f"font-size:.78rem;font-weight:{weight};color:{TOKENS['text']};white-space:nowrap'>"
            f"<span style='color:{color};font-weight:700'>{index}</span>"
            f"<span style='color:{color}'>{icon}</span> {label}</span>"
        )
    st.markdown(
        "<div style='display:flex;flex-wrap:wrap;gap:.4rem;align-items:center'>"
        + "".join(chips)
        + "</div>",
        unsafe_allow_html=True,
    )
    next_steps = [s for s in steps if not s[2]]
    if next_steps:
        label, path, _ = next_steps[0]
        st.caption(f"下一步建议：{label}。点击下方按钮继续。")
        st.page_link(path, label=f"前往 {label} →", icon=":material/arrow_forward:")
    else:
        st.caption("全部研究步骤均有产出；可在审计回放页复核全流程。")
