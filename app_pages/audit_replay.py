import streamlit as st

from app_pages._shared import context_or_empty
from ui.layout import section
from ui.status import callout


item, summary, validation = context_or_empty("审计回放", "按时间线回放 Run、文档解析、ACME、财务计算、研报核查、估值、Memo 和导出事件。")
if item and summary:
    sid = item["id"]
    service = __import__("src.cn.workbench_service", fromlist=["workbench_service"])
    trace = service.research_trace(sid)
    section("研究事件时间线")
    events = trace.get("events", [])
    if not events:
        st.info("该快照没有已持久化的执行轨迹；不会补造成功步骤。")
    else:
        for index, event in enumerate(events, start=1):
            state = "complete" if event.get("status") in {"succeeded", "completed", "success"} else "error" if event.get("status") in {"failed", "blocked"} else "running"
            with st.status(f"{index:02d} · {event.get('event')} · {event.get('status')}", state=state, expanded=False):
                st.write({"时间": event.get("at"), "详情": event.get("detail"), "Evidence IDs": event.get("evidence_ids", []), "版本": trace.get("prompt_version"), "Provider": trace.get("provider"), "Snapshot ID": sid})
    section("Replay Run 与 Failure Injection")
    runs = service.list_demo_runs()
    if not runs:
        st.info("暂无落盘的 Demo Run；系统不会把当前页面临时事件伪装成 Replay Run。")
    else:
        selected = st.selectbox("Replay Run", [row["run_id"] for row in runs], key="replay_run_choice")
        detail = service.demo_run_detail(selected)
        st.write(detail.get("validation", {}))
        st.json(detail.get("timeline", {}))
        if st.button("导出 Evidence Pack", type="primary", icon=":material/archive:"):
            try:
                pack = service.export_demo_evidence_pack(selected)
                st.download_button("下载 ZIP", pack["content"], pack["filename"], pack.get("media_type", "application/zip"), icon=":material/download:")
            except Exception as exc:
                callout("blocked", f"Evidence Pack 导出失败：{type(exc).__name__}: {exc}")
