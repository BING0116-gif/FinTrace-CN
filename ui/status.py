"""Consistent validation and data-state presentation."""

from __future__ import annotations

from typing import Any

import streamlit as st


LABELS = {"pass": "可验证", "verified": "可验证", "warning": "警告", "limited": "降级", "degraded": "降级", "blocked": "阻断", "conflicted": "冲突", "stale": "过期", "unknown": "未覆盖"}
COLORS = {"pass": "green", "verified": "green", "warning": "orange", "limited": "orange", "degraded": "orange", "blocked": "red", "conflicted": "red", "stale": "orange", "unknown": "gray"}


def normalize(status: Any) -> str:
    return str(status or "unknown").lower().replace(" ", "_")


def badge(status: Any, *, label: str | None = None) -> None:
    key = normalize(status)
    st.badge(label or LABELS.get(key, str(status or "未覆盖")), color=COLORS.get(key, "gray"))


def summary_card(validation: dict[str, Any], *, affected: str = "") -> None:
    status = normalize(validation.get("status"))
    with st.container(border=True):
        left, right = st.columns([1, 3])
        with left:
            badge(status)
        with right:
            checks = validation.get("checks") or []
            failed = [item for item in checks if item.get("status") in {"blocked", "warning"}]
            reason = "；".join(item.get("detail", "") for item in failed[:2]) or "关键证据和口径检查通过。"
            st.write(reason)
            st.caption(f"受影响结果：{affected or '当前研究输出'} · 下一步：{failed[0].get('remediation') if failed else '可继续研究'}")


def callout(status: Any, message: str) -> None:
    key = normalize(status)
    fn = st.error if key in {"blocked", "conflicted"} else st.warning if key in {"warning", "limited", "degraded", "stale"} else st.success if key in {"pass", "verified"} else st.info
    fn(message, icon=":material/" + ("block" if key == "blocked" else "warning" if key in {"warning", "limited", "degraded", "stale"} else "check_circle" if key in {"pass", "verified"} else "info") + ":")
