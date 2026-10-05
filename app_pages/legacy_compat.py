"""Compatibility bridge for the pre-redesign workbench pages."""

import streamlit as st

from app_pages._shared import context_or_empty


item, summary, validation = context_or_empty("旧工作台入口", "保留原有只读页面作为兼容回退；新研究流程请使用左侧模块化导航。")
if item and summary:
    import workbench

    options = {
        "AI Agent 研究": workbench.agent_research,
        "市场与行情": lambda: workbench.market(workbench.load_research(item["id"])[0]),
        "财务表现": lambda: workbench.financials(workbench.load_research(item["id"])[0]),
        "证据与校验": lambda: workbench.evidence(workbench.load_research(item["id"])[0], summary),
        "研究报告": lambda: workbench.report(workbench.load_research(item["id"])[0]),
    }
    choice = st.selectbox("兼容页面", list(options), key="legacy_compat_page")
    options[choice]()
