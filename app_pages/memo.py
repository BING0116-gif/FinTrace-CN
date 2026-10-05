import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from ui.status import callout


item, summary, validation = context_or_empty("投资备忘录", "阅读型交付：每段带 FACT / INFERENCE / OPINION 标记，并能沿 Claim → Calculation → Evidence 回溯。")
if item and summary:
    report = loader.report(item["id"])
    if not report.get("available"):
        callout("blocked" if report.get("unavailable_reason") == "validator_blocked" else "warning", f"备忘录不可用：{report.get('unavailable_reason') or '尚未生成'}。关键证据失效时系统会阻断该段落。")
    else:
        st.caption(f"来源：{report.get('provider')} · 研究截至：{report.get('research_as_of')} · Validator：{report.get('validation_status')}")
        content = report.get("content") or ""
        for index, paragraph in enumerate([part.strip() for part in content.split("\n\n") if part.strip()]):
            kind = "FACT" if paragraph.startswith("事实") or "Evidence" in paragraph else "INFERENCE" if paragraph.startswith(("推断", "分析")) else "OPINION"
            with st.container(border=True):
                st.caption(kind)
                st.markdown(paragraph)
                st.caption(f"段落 {index + 1} · 点击审计回放查看事件、版本和 Evidence Pack")
        st.download_button("下载投资备忘录", content, report.get("filename") or "memo.md", "text/markdown", icon=":material/download:")
