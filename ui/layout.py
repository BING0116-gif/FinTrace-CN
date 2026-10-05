"""Shared frame, card grid and empty/error states.

顶部上下文条已迁移到 ui/context_bar.py（全站共用）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from services import research_loader as loader
from services.session_state import set_snapshot


def page_title(title: str, description: str, *, eyebrow: str = "FinTrace-CN") -> None:
    st.markdown(f"<div class='ft-eyebrow'>{eyebrow}</div>", unsafe_allow_html=True)
    st.title(title)
    st.caption(description)


def section(title: str, *, hint: str | None = None, action: str | None = None, action_path: str | None = None) -> None:
    """蓝条区块标题（对齐设计稿「| 相对估值」样式）。

    hint 为标题后的灰色说明；action + action_path 渲染右侧「查看详情 →」跳转。
    """
    hint_html = f"<span class='ft-section-hint'>{hint}</span>" if hint else ""
    if action and action_path:
        left, right = st.columns([4, 1])
        with left:
            st.markdown(
                f"<div class='ft-section'><span class='ft-section-bar'></span>"
                f"<span class='ft-section-title'>{title}</span>{hint_html}</div>",
                unsafe_allow_html=True,
            )
        with right:
            st.page_link(action_path, label=action, icon=":material/arrow_forward:")
    else:
        st.markdown(
            f"<div class='ft-section'><span class='ft-section-bar'></span>"
            f"<span class='ft-section-title'>{title}</span>{hint_html}</div>",
            unsafe_allow_html=True,
        )


def card_grid(cols: int, cards: list[Callable[[], None]], *, gap: int = 12) -> None:
    """统一卡片网格：12px 间距、卡片内边距 16px（由主题层控制）。

    cards 是零参渲染函数列表，按行填充 cols 列网格。
    """
    if not cards:
        return
    for start in range(0, len(cards), cols):
        row = cards[start:start + cols]
        columns = st.columns(cols, gap="small")
        for index, card in enumerate(row):
            with columns[index]:
                with st.container(border=True):
                    card()


def sidebar_context(catalog: list[dict[str, Any]]) -> None:
    with st.sidebar:
        st.markdown(
            "<div class='ft-brand'><div class='ft-brand-name'>◈ FinTrace-CN</div>"
            "<div class='ft-brand-sub'>A 股研究验证平台</div></div>",
            unsafe_allow_html=True,
        )
        if catalog:
            options = {f"{item.get('name') or item.get('symbol')} · {item.get('symbol')}": item["id"] for item in catalog}
            ids = list(options.values())
            current = st.session_state.get("selected_snapshot_id")
            index = ids.index(current) if current in ids else 0
            selected = st.selectbox("研究快照", list(options), index=index, key="global_snapshot_choice")
            if options[selected] != current:
                set_snapshot(options[selected])
                st.rerun()
        else:
            st.warning("暂无本地研究快照。", icon=":material/database:")
        st.caption("离线快照与在线数据会明确区分。")


def empty_state(title: str, detail: str, *, icon: str = ":material/inbox:") -> None:
    with st.container(border=True):
        st.subheader(title)
        st.caption(detail)
        st.info("当前没有可展示的结果；系统不会用猜测值填充。", icon=icon)


def unavailable(result: dict[str, Any], title: str = "数据未覆盖") -> None:
    reason = result.get("reason") or result.get("unavailable_reason") or "服务没有返回可展示结果。"
    with st.container(border=True):
        st.subheader(title)
        st.warning(reason, icon=":material/warning:")


def current_context() -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    catalog = loader.catalog()
    item, summary = loader.current(catalog, st.session_state.get("selected_snapshot_id"))
    validation = loader.validation(item["id"]) if item else None
    return item, summary, validation
