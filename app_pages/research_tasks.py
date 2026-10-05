import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from services.session_state import set_snapshot
from ui.status import callout


item, summary, validation = context_or_empty("研究任务", "用三步登记研究对象、上传材料并启动受控研究；每个任务保留事件流和失败状态。")

step = st.segmented_control("任务步骤", ["1 选择研究对象", "2 上传材料", "3 确认并启动"], default="1 选择研究对象", key="task_step_control")
if step == "1 选择研究对象":
    with st.form("research_task_object"):
        symbol = st.text_input("股票代码", value=item.get("symbol", "") if item else "", placeholder="例如 600519.SH")
        purpose = st.text_input("研究目的", placeholder="例如：核查 2025FY 盈利质量")
        cutoff = st.date_input("研究截止日期")
        research_type = st.selectbox("研究类型", ["公司研究", "估值", "研报核查", "每日复盘"])
        submitted = st.form_submit_button("保存研究对象", type="primary", icon=":material/save:")
    if submitted:
        st.session_state["task_object"] = {"symbol": symbol.strip(), "purpose": purpose, "cutoff": str(cutoff), "research_type": research_type}
        st.success("研究对象已记录。下一步上传材料或直接确认启动。")
elif step == "2 上传材料":
    task_object = st.session_state.get("task_object", {})
    st.caption(f"当前对象：{task_object.get('symbol') or (item or {}).get('symbol') or '未填写'}")
    uploads = st.file_uploader("上传年报、研报草稿、公告或其他材料", type=["pdf", "txt", "md"], accept_multiple_files=True, key="research_materials")
    if uploads and st.button("登记并解析材料", type="primary", icon=":material/upload_file:"):
        records = []
        for upload in uploads:
            try:
                result = loader.service.ingest_demo_document(upload.getvalue(), upload.name, symbol=task_object.get("symbol"), fiscal_period=None, published_at=None)
                record = result.get("document", {})
                records.append({"file_name": upload.name, "document_id": result.get("document_id"), "sha256": record.get("sha256"), "status": record.get("status"), "facts": len(result.get("facts", [])), "warnings": result.get("warnings", []), "document": record, "fragments": result.get("fragments", []), "fact_rows": result.get("facts", [])})
            except Exception as exc:
                records.append({"file_name": upload.name, "status": "blocked", "warnings": [f"{type(exc).__name__}: {exc}"]})
        st.session_state.task_uploaded_documents = records
    records = st.session_state.get("task_uploaded_documents", [])
    if records:
        st.dataframe(records, hide_index=True, width="stretch")
    else:
        st.info("尚未上传材料；没有材料时系统不会生成文档证据。")
else:
    task_object = st.session_state.get("task_object", {})
    uploaded = st.session_state.get("task_uploaded_documents", [])
    with st.container(border=True):
        st.subheader("确认研究口径")
        st.write({"研究对象": task_object.get("symbol") or (item or {}).get("symbol"), "研究时点": task_object.get("cutoff") or (summary or {}).get("research_as_of"), "Provider / Snapshot": (summary or {}).get("provider", "未选择") + " / " + ((item or {}).get("id") or "未选择"), "缓存": "仅使用版本化快照", "备忘录": "需通过 Validator 后生成"})
        st.caption(f"已登记材料：{len(uploaded)} 个；上传材料的 SHA256 和解析状态可在文档与证据页查看。")
    if st.button("启动受控研究", type="primary", icon=":material/play_arrow:"):
        symbol = task_object.get("symbol") or (item or {}).get("symbol")
        if not symbol:
            callout("blocked", "缺少股票代码，任务没有启动。")
        else:
            try:
                task = loader.service.start_research(symbol)
                st.session_state.task_last_message = task.get("message")
                callout("verified" if task.get("status") in {"queued", "running", "succeeded", "completed"} else "warning", f"任务状态：{task.get('status')} · {task.get('message') or '—'}")
                if task.get("snapshot_id"):
                    set_snapshot(task["snapshot_id"])
                    loader.clear_caches()
            except Exception as exc:
                callout("blocked", f"任务启动失败：{type(exc).__name__}: {exc}")

st.subheader("任务事件流")
tasks = loader.service.list_tasks()
if not tasks:
    st.info("尚无任务记录。")
else:
    st.dataframe([{key: task.get(key) for key in ("id", "symbol", "kind", "status", "created_at", "updated_at", "message")} for task in tasks], hide_index=True, width="stretch")
    selected = st.selectbox("查看任务详情", [task["id"] for task in tasks], key="task_detail_choice")
    task = loader.service.get_task(selected)
    progress = loader.service.get_task_progress(selected)
    st.progress(int(progress.get("progress_percent") or 0), text=f"{progress.get('status')} · {progress.get('current_step') or 'waiting'}")
    with st.status(f"事件流：{task.get('status')}", state="complete" if task.get("status") in {"succeeded", "completed"} else "error" if task.get("status") in {"failed", "blocked"} else "running", expanded=False):
        for event in task.get("trace", [])[-20:]:
            st.write(f"{event.get('at')} · {event.get('event')} · {event.get('status')} · {event.get('detail')}")
