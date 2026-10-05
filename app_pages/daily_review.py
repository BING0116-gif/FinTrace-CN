import streamlit as st

from ui.layout import page_title
from ui.status import callout


page_title("每日复盘", "离线可复现与实时采集明确区分；缺失模块保持未覆盖，不输出预测性结论。", eyebrow="可信与复盘")
service = __import__("src.cn.workbench_service", fromlist=["workbench_service"])
reviews = service.list_daily_reviews()
if not reviews:
    st.info("暂无市场复盘快照；可在下方按需采集。")
else:
    labels = {f"{row.get('review_as_of')} · {row.get('id')}": row["id"] for row in reviews}
    selected = st.selectbox("复盘快照", list(labels), key="daily_review_snapshot")
    sid = labels[selected]
    summary = service.daily_review_summary(sid)
    validation = summary.get("validation", {})
    status = validation.get("status", "unknown")
    callout("warning" if summary.get("is_synthetic_demo") else status, "离线演示快照（synthetic_demo），不代表真实行情。" if summary.get("is_synthetic_demo") else f"数据源：{summary.get('provider')} · 校验：{status}")
    cols = st.columns(4)
    for col, (label, value) in zip(cols, [("指数", summary.get("index_count", 0)), ("板块", summary.get("sector_count", 0)), ("涨停", summary.get("limit_up_count", 0)), ("结论", "允许" if validation.get("conclusion_allowed") else "阻断")]):
        with col:
            st.metric(label, value)
    panorama = service.daily_review_detail(sid, "panorama")
    st.json({"研究截至": summary.get("review_as_of"), "provider": summary.get("provider"), "validation": validation, "panorama_sections": list((panorama or {}).get("sections", {}))})

with st.form("daily_review_acquisition", border=True):
    review_date = st.text_input("实时采集日期（YYYYMMDD）", placeholder="例如 20260814")
    submitted = st.form_submit_button("按需获取实时数据", type="primary", icon=":material/cloud_download:")
if submitted:
    try:
        result = service.acquire_live_daily_review(review_date)
        callout("verified" if result.get("status") == "ok" else "warning", result.get("message", "采集已返回"))
    except Exception as exc:
        callout("blocked", f"采集失败：{type(exc).__name__}: {exc}")
