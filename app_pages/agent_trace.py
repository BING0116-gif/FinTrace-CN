"""高级分组：Agent 执行轨迹（仅呈现已持久化的事件，不补造成功步骤）。"""

import streamlit as st

from app_pages._shared import context_or_empty


item, summary, validation = context_or_empty(
    "Agent 执行轨迹",
    "仅呈现已记录的研究流程事件；外部工具内容始终按数据处理。",
)
if item and summary:
    import workbench

    workbench.trace(workbench.load_research(item["id"])[0])
