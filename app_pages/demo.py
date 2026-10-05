import streamlit as st

from ui.layout import page_title
from ui.status import badge


page_title("案例演示", "保留原有成功与阻断案例作为演示模式入口；所有数值来自本地版本化快照。", eyebrow="演示模式")
service = __import__("src.cn.workbench_service", fromlist=["workbench_service"])
catalog = service.list_research()
cases = [("成功研究", "600519.SH_illustrative_demo_v1", True), ("Validator 阻断", "600519.SH_illustrative_missing_shares_v1", False)]
for title, sid, expected in cases:
    with st.container(border=True):
        st.subheader(title)
        if any(row.get("id") == sid for row in catalog):
            validation = service.research_validation(sid)
            badge(validation.get("status"))
            st.write({"snapshot_id": sid, "conclusion_allowed": validation.get("conclusion_allowed"), "expected": expected})
            with st.expander("查看验证清单"):
                st.json(validation)
        else:
            st.warning("演示快照不存在；请运行 bootstrap_demo.py。")
