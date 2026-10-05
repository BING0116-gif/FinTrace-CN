"""Navigation registry for the modular FinTrace-CN front end.

信息架构（UI_REDESIGN_PLAN_V2 §3）：业务导航 8 项 + 「高级」折叠分组。
演示/工程向页面全部降级到「高级」，默认不展开。
"""

from __future__ import annotations

import streamlit as st


# 业务导航 8 项（导航注册表快照测试依赖此顺序）
BUSINESS_PAGES: list[tuple[str, str, str]] = [
    ("app_pages/overview.py", "总览", ":material/space_dashboard:"),
    ("app_pages/research_tasks.py", "研究任务", ":material/task_alt:"),
    ("app_pages/documents.py", "文档与证据", ":material/folder_open:"),
    ("app_pages/financial_analysis.py", "财务分析", ":material/analytics:"),
    ("app_pages/research_review.py", "研判核查", ":material/fact_check:"),
    ("app_pages/valuation.py", "估值", ":material/query_stats:"),
    ("app_pages/memo.py", "投资备忘录", ":material/description:"),
    ("app_pages/audit_replay.py", "审计回放", ":material/history:"),
]

# 「高级」分组：演示 / 工程向页面，默认收起
ADVANCED_PAGES: list[tuple[str, str, str]] = [
    ("app_pages/demo.py", "案例演示", ":material/slideshow:"),
    ("app_pages/card15_demo.py", "CARD-15 Demo", ":material/science:"),
    ("app_pages/agent_research.py", "AI Agent 研究", ":material/smart_toy:"),
    ("app_pages/agent_trace.py", "Agent 执行轨迹", ":material/route:"),
    ("app_pages/evaluations.py", "评测与消融", ":material/leaderboard:"),
    ("app_pages/daily_review.py", "每日复盘", ":material/today:"),
    ("app_pages/legacy_compat.py", "旧版页面入口", ":material/arrow_back:"),
]


def _register(entries: list[tuple[str, str, str]]) -> list[st.Page]:
    return [st.Page(path, title=title, icon=icon) for path, title, icon in entries]


def pages() -> dict[str, list[st.Page]]:
    """业务 8 项置顶；「高级」分组默认收起（workbench.py 传 expanded=False）。"""
    return {
        "": _register(BUSINESS_PAGES),
        "高级": _register(ADVANCED_PAGES),
    }
