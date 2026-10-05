"""Small reusable cards for workflow, metrics and evidence links."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from services.session_state import go_to_evidence
from ui.chips import evidence_chip
from ui.status import badge, normalize


def metric(label: str, value: Any, *, period: str | None = None, unit: str | None = None, evidence_id: str | None = None, delta: Any = None) -> None:
    with st.container(border=True):
        st.metric(label, "未覆盖" if value is None else value, delta=delta)
        st.caption(" · ".join(item for item in (period, unit) if item) or "期间和单位未记录")
        if evidence_id:
            # 证据编号收进芯片悬浮与展开区；明面不再直出裸 ID（§4.2）。
            evidence_chip(evidence_id, "证据来源", detail={"证据编号": evidence_id})
            st.button("查看证据链", key=f"evidence_link_{evidence_id}", on_click=go_to_evidence, args=(evidence_id,), icon=":material/arrow_forward:")


def workflow(steps: list[dict[str, Any]]) -> None:
    with st.container(border=True):
        st.subheader("研究进度")
        cols = st.columns(min(4, len(steps)) or 1)
        for index, step in enumerate(steps):
            with cols[index % len(cols)]:
                badge(step.get("status"), label=step.get("label"))
                st.caption(f"{step.get('detail', '未覆盖')} · {step.get('count', 0)} 个产物")


def conclusion(title: str, text: str, *, kind: str = "inference", status: str = "verified", evidence_count: int = 0, calculation: str | None = None) -> None:
    with st.container(border=True):
        left, right = st.columns([4, 1])
        with left:
            st.markdown(f"**{title}**")
            st.write(text)
            st.caption(f"{kind.upper()} · Evidence {evidence_count} · Calculation {calculation or '未关联'}")
        with right:
            badge(status)
