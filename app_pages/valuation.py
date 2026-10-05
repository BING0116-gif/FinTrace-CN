import pandas as pd
import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from ui.status import callout


item, summary, validation = context_or_empty("估值分析", "三层查看 Bear/Base/Bull 可用范围、倍数分布和假设注册表；阻断时隐藏隐含价格。")
if item and summary:
    sid = item["id"]
    result = loader.valuation(sid)
    if result.get("available") is False:
        st.warning("同业覆盖不足或关键输入缺失；页面只展示缺口，不生成目标价。", icon=":material/block:")
    else:
        allowed = bool(result.get("conclusion_allowed"))
        if not allowed:
            callout("blocked", f"Validator 已阻断估值输出：{result.get('gated_reason') or '关键证据缺失'}。")
        st.subheader("估值摘要")
        summary_cols = st.columns(5)
        target_price = result.get("target_price") if allowed else None
        values = [("Bear", None, ""), ("Base", target_price, " CNY"), ("Bull", None, ""), ("当前 RAW 价格", (summary.get("key_metrics") or {}).get("price"), " CNY"), ("同行数量", result.get("peer_count"), " 家")]
        for col, (label, value, suffix) in zip(summary_cols, values):
            with col:
                with st.container(border=True):
                    st.metric(label, "未覆盖" if value is None else f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}")
        st.caption(f"价格口径：{result.get('price_basis')} · 期间口径：{result.get('period_basis')} · Validator：{result.get('validation_status')}")
        st.subheader("倍数与敏感性")
        multiples = result.get("multiples", {})
        rows = [{"方法": name, "目标公司倍数": value.get("target_multiple"), "同行中位数": value.get("median"), "隐含价格": value.get("implied_price") if allowed else None} for name, value in multiples.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        for name, distribution_rows in (result.get("distributions") or {}).items():
            with st.expander(f"{name} 可比公司分布", expanded=False):
                st.dataframe(pd.DataFrame(distribution_rows), hide_index=True, width="stretch")
                interval = (result.get("valuation_ranges") or {}).get(name, {})
                st.write({"P25": interval.get("p25"), "中位数": interval.get("median"), "P75": interval.get("p75"), "价格区间": {key: interval.get(key) if allowed else None for key in ("implied_price_low", "implied_price_median", "implied_price_high")}})
        st.subheader("假设注册表")
        assumptions = [{"假设/方法": name, "基准值": formula.get("target_multiple"), "目标输入 Evidence": ", ".join(formula.get("target_input_evidence_ids", [])), "同行输入 Evidence": ", ".join(formula.get("peer_input_evidence_ids", [])), "状态": result.get("validation_status")} for name, formula in (result.get("formulas") or {}).items()]
        if assumptions:
            st.dataframe(pd.DataFrame(assumptions), hide_index=True, width="stretch")
        else:
            st.info("暂无可注册的估值假设。")
