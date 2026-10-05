"""高级分组：AI Agent 研究入口（原旧版工作台功能降级保留）。"""

import streamlit as st

from app_pages._shared import context_or_empty


item, summary, validation = context_or_empty(
    "AI Agent 研究",
    "自然语言问题 → 真实模型工具调用 → 工具轨迹、Evidence 与 Validator 结果。"
    "未配置所选模型的 API Key 时会明确报错，不会自动降级为 mock。",
)
if item and summary:
    import workbench

    workbench.agent_research()
