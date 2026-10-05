import pandas as pd
import streamlit as st

from ui.layout import page_title


page_title("系统评测", "只展示本地已落盘、可追溯的 benchmark 和 ablation 产物；未测量指标不会以 0 代替。", eyebrow="可信与复盘")
service = __import__("src.cn.workbench_service", fromlist=["workbench_service"])
items = service.list_evaluations()
if not items:
    st.info("尚无可展示的评测产物。")
else:
    labels = {f"{item.get('kind')} · {item.get('id')}": item["id"] for item in items}
    selected = st.selectbox("评测产物", list(labels), key="evaluation_artifact")
    detail = service.evaluation_detail(labels[selected])
    st.caption(f"版本：{(detail.get('metadata') or {}).get('benchmark_version') or '未记录'} · 运行时间：{(detail.get('metadata') or {}).get('run_at') or '未记录'}")
    if detail.get("variants"):
        st.dataframe(pd.DataFrame(detail["variants"]), hide_index=True, width="stretch")
    if detail.get("missing_variants"):
        st.warning(f"未测量配置：{', '.join(detail['missing_variants'])}")
    if detail.get("summary"):
        st.json(detail["summary"])
    if detail.get("results"):
        st.dataframe(pd.DataFrame(detail["results"]), hide_index=True, width="stretch")
