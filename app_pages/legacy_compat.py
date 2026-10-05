"""Compatibility bridge for the pre-redesign workbench pages.

旧页面名保留 1 个版本的跳转别名（防止书签/口口相传失效）；
选择旧名称后跳转到新导航对应页面。
"""

import streamlit as st

from app_pages._shared import context_or_empty


# 旧页面名 → 新页面路径（仅保留一个版本的别名，随后移除）
LEGACY_ALIASES: dict[str, str] = {
    "研究总览": "app_pages/overview.py",
    "研究任务": "app_pages/research_tasks.py",
    "证据与校验": "app_pages/documents.py",
    "研究报告": "app_pages/documents.py",
    "市场与行情": "app_pages/financial_analysis.py",
    "财务表现": "app_pages/financial_analysis.py",
    "研报核查": "app_pages/research_review.py",
    "同行估值": "app_pages/valuation.py",
    "研究备忘录": "app_pages/memo.py",
    "审计回放": "app_pages/audit_replay.py",
    "案例演示": "app_pages/demo.py",
    "CARD-15 Demo": "app_pages/card15_demo.py",
    "AI Agent 研究": "app_pages/agent_research.py",
    "Agent 执行轨迹": "app_pages/agent_trace.py",
    "评测与消融": "app_pages/evaluations.py",
    "每日复盘": "app_pages/daily_review.py",
}

item, summary, validation = context_or_empty(
    "旧版页面入口", "旧页面名已映射到新导航；此入口保留一个版本后移除。"
)

st.caption("以下别名用于旧书签跳转；新研究流程请使用左侧业务导航（8 项）。")
choice = st.selectbox("旧页面名", list(LEGACY_ALIASES), key="legacy_page_alias")
if st.button("跳转到新页面", type="primary", icon=":material/arrow_forward:"):
    st.switch_page(LEGACY_ALIASES[choice])

with st.expander("旧版页面（保留原只读视图）"):
    if item and summary:
        import workbench

        options = {
            "AI Agent 研究": workbench.agent_research,
            "市场与行情": lambda: workbench.market(workbench.load_research(item["id"])[0]),
            "财务表现": lambda: workbench.financials(workbench.load_research(item["id"])[0]),
            "证据与校验": lambda: workbench.evidence(workbench.load_research(item["id"])[0], summary),
            "研究报告": lambda: workbench.report(workbench.load_research(item["id"])[0]),
        }
        legacy_choice = st.selectbox("兼容页面", list(options), key="legacy_compat_page")
        options[legacy_choice]()
    else:
        st.info("请选择一个研究快照后继续。")
