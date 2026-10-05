"""Navigation registry for the modular FinTrace-CN front end."""

from __future__ import annotations

import streamlit as st


def pages() -> dict[str, list[st.Page]]:
    return {
        "": [
            st.Page("app_pages/overview.py", title="总览", icon=":material/space_dashboard:"),
            st.Page("app_pages/research_tasks.py", title="研究任务", icon=":material/task_alt:"),
        ],
        "研究": [
            st.Page("app_pages/documents.py", title="文档与证据", icon=":material/folder_open:"),
            st.Page("app_pages/financial_analysis.py", title="财务分析", icon=":material/analytics:"),
            st.Page("app_pages/report_checker.py", title="研报核查", icon=":material/fact_check:"),
            st.Page("app_pages/valuation.py", title="估值分析", icon=":material/query_stats:"),
            st.Page("app_pages/memo.py", title="投资备忘录", icon=":material/description:"),
        ],
        "可信与复盘": [
            st.Page("app_pages/audit_replay.py", title="审计回放", icon=":material/history:"),
            st.Page("app_pages/daily_review.py", title="每日复盘", icon=":material/today:"),
            st.Page("app_pages/evaluations.py", title="系统评测", icon=":material/leaderboard:"),
        ],
        "演示模式": [
            st.Page("app_pages/demo.py", title="案例演示", icon=":material/slideshow:"),
            st.Page("app_pages/card15_demo.py", title="CARD-15 Demo", icon=":material/science:"),
        ],
        "兼容入口": [
            st.Page("app_pages/legacy_compat.py", title="旧工作台入口", icon=":material/arrow_back:")
        ],
    }
