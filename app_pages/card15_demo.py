import streamlit as st

from ui.layout import page_title
from ui.status import callout


page_title("CARD-15 Demo", "演示 ACME、Claim Passport、Thesis Fragility、Temporal Revalidation、FinFuzz 与 Evidence Pack。", eyebrow="演示模式")
service = __import__("src.cn.workbench_service", fromlist=["workbench_service"])
catalog = service.list_research()
if not catalog:
    st.info("暂无研究快照。")
else:
    labels = {f"{row.get('symbol')} · {row.get('name')}": row["id"] for row in catalog}
    sid = labels[st.selectbox("演示快照", list(labels), key="card15_snapshot")]
    runs = service.list_demo_runs()
    run_ids = [row["run_id"] for row in runs]
    selected = st.selectbox("Audit Replay Run", ["（未选择）", *run_ids], key="card15_run")
    data = service.card15_demo_data(sid, run_id=None if selected == "（未选择）" else selected)
    st.write(data.get("provenance", {}))
    readiness = data.get("readiness", {})
    callout("verified" if readiness.get("status") == "ready" else "warning", f"素材就绪状态：{readiness.get('status', 'unknown')}")
    selected_run = data.get("selected_run") or {}
    for key, artifact in (selected_run.get("artifacts", {}) or {}).items():
        with st.expander(key):
            st.json(artifact or {"status": "unavailable"})
