"""Financial Claim Passport presentation without upgrading LLM text to facts."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.status import badge


PASSPORT_BLOCKS = ("Statement", "Source", "Accounting Context", "Calculation", "Assumption", "Dependency", "Validation", "Integrity")


def render(claim: dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown(f"### {claim.get('title') or claim.get('statement') or 'Claim'}")
        st.caption(f"Claim ID: `{claim.get('claim_id', '未记录')}` · 类型：{str(claim.get('kind', 'inference')).upper()}")
        badge(claim.get("status", "unknown"))
        for name in PASSPORT_BLOCKS:
            value = claim.get(name.lower().replace(" ", "_")) or claim.get(name)
            with st.expander(name, expanded=name in {"Statement", "Validation"}, icon=":material/verified:"):
                st.write(value if value not in (None, "") else "未记录；系统不会补造该证明区块。")
