"""Financial Claim Passport presentation without upgrading LLM text to facts.

UI_REDESIGN_PLAN_V2 §5.2：
- 顶部：声明内容卡（amber 底纹高亮数字）+ 状态徽章；
- 中部：八区块状态表格（名称 | 中文说明 | 值 | 状态图标），点击行展开详情；
- 主按钮：「核查此声明」（复用页面既有核查链路，不新增后端逻辑）；
- 底部：证据与原文 tabs —— 证据来源 chip + 定位到的原文片段。
Claim ID 不在明面直出，收进悬浮提示与展开区。
"""

from __future__ import annotations

import re
from typing import Any, Callable

import streamlit as st

from ui.chips import evidence_chip
from ui.status import badge

# 八个 proof 区块：内部键 → 中文名称
PASSPORT_BLOCKS: tuple[tuple[str, str], ...] = (
    ("statement", "声明内容"),
    ("source", "来源"),
    ("accounting_context", "会计口径"),
    ("calculation", "计算"),
    ("assumption", "假设"),
    ("dependency", "依赖"),
    ("validation", "验证"),
    ("integrity", "完整性"),
)

_NUMBER_PATTERN = re.compile(r"([0-9]+(?:[.,][0-9]+)*(?:\s*%|倍|元|亿|万)?)")


def _highlight_numbers(text: str) -> str:
    """amber 底纹高亮声明中的数字（纯展示，不改文本）。"""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _NUMBER_PATTERN.sub(
        r"<span style='background:rgba(217,148,0,.18);border-radius:4px;padding:0 .18rem'>\1</span>",
        escaped,
    )


def _status_icon(value: Any) -> str:
    if value in (None, "", "未记录"):
        return "⚠️"
    return "✅"


def render(claim: dict[str, Any], *, on_check: Callable[[], None] | None = None, evidence_records: list[dict[str, Any]] | None = None) -> None:
    with st.container(border=True):
        # 顶部：声明内容卡 + 状态徽章
        statement = str(claim.get("statement") or claim.get("title") or "未提供声明内容")
        top = st.columns([4, 1])
        with top[0]:
            st.markdown(_highlight_numbers(statement), unsafe_allow_html=True)
        with top[1]:
            badge(claim.get("status", "unknown"))
        st.markdown(
            f"<span title='Claim ID：{claim.get('claim_id', '未记录')}'>"
            f"<span style='color:#627D98;font-size:.76rem'>类型：{str(claim.get('kind', 'inference')).upper()}"
            f" · 声明编号悬浮可见</span></span>",
            unsafe_allow_html=True,
        )

        # 中部：八区块状态表格
        rows = []
        for key, cn_name in PASSPORT_BLOCKS:
            value = claim.get(key)
            if isinstance(value, dict):
                value_text = "；".join(f"{k}={v}" for k, v in value.items()) or "未记录"
            elif isinstance(value, (list, tuple)):
                value_text = "、".join(str(item) for item in value) if value else "未记录"
            else:
                value_text = str(value) if value not in (None, "") else "未记录"
            rows.append({
                "区块": cn_name,
                "值": value_text if len(value_text) <= 60 else value_text[:57] + "…",
                "状态": _status_icon(value),
            })
        st.dataframe(rows, hide_index=True, width="stretch", key="passport_status_table")
        with st.expander("展开各区块完整详情"):
            for key, cn_name in PASSPORT_BLOCKS:
                value = claim.get(key)
                with st.expander(f"{cn_name}", expanded=False):
                    st.write(value if value not in (None, "") else "未记录；系统不会补造该证明区块。")
                    if key == "validation" and isinstance(value, dict) and value.get("findings"):
                        st.dataframe(value["findings"], hide_index=True, width="stretch")

        # 主按钮：核查此声明
        if on_check is not None:
            st.button("核查此声明", type="primary", icon=":material/fact_check:", on_click=on_check, key="passport_check_button")

        # 底部：证据与原文
        tabs = st.tabs(["证据来源", "原文与定位"])
        with tabs[0]:
            records = evidence_records or []
            dependency_ids = set(claim.get("dependency") or [])
            dependency_ids.update(claim.get("evidence_ids") or [])
            if claim.get("source") and claim.get("source") != "（未引用）":
                dependency_ids.add(claim["source"])
            if not records and not dependency_ids:
                st.caption("该声明尚未关联证据来源。")
            for record in records:
                record_id = record.get("evidence_id", "")
                if record_id not in dependency_ids:
                    continue
                evidence_chip(
                    record_id, str(record.get("provider") or "快照"),
                    detail={
                        "指标": record.get("metric"), "数值": record.get("value"),
                        "单位": record.get("unit"), "期间": record.get("period") or "—",
                        "来源": record.get("provider"), "状态": record.get("status"),
                        "字段路径": record.get("field_path"),
                    },
                )
            if records and not any(record.get("evidence_id") in dependency_ids for record in records):
                st.caption("声明引用的证据不在当前快照证据账本中；系统不会补造证据。")
        with tabs[1]:
            fragment = claim.get("statement") or claim.get("title") or ""
            if fragment:
                st.text_area("声明原文", fragment, height=110, disabled=True, key="passport_source_text")
            else:
                st.caption("暂无可定位的原文片段；文档页码仅在解析结果提供时展示。")
