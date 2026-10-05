"""Small page helpers. Pages stay direct scripts while data access is shared."""

from __future__ import annotations

from typing import Any

import streamlit as st

from services import research_loader as loader
from ui.context_bar import render as render_context_bar
from ui.layout import current_context, page_title, unavailable


def context_or_empty(title: str, description: str):
    item, summary, validation = current_context()
    page_title(title, description)
    # 全站统一的顶部上下文条：公司/代码 + 可验证徽章 + 离线可复现 + 本次研究时间。
    render_context_bar(item, summary, validation)
    if not item or not summary:
        st.info("请选择一个研究快照后继续。", icon=":material/info:")
        return None, None, None
    return item, summary, validation


def safe_section(title: str, result: dict, *, allow_empty: bool = False):
    if not result or result.get("status") == "unavailable":
        unavailable(result or {}, title)
        return False
    if not allow_empty and result.get("available") is False:
        unavailable(result, title)
        return False
    return True
