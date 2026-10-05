import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from ui.charts import cash_flow_trends, financial_trends, price_bars
from ui.layout import section
from ui.status import callout


item, summary, validation = context_or_empty("财务分析", "展示服务层已计算的收入、利润、现金流和期间口径；每个结果可以回到 Evidence。")
if item and summary:
    sid = item["id"]
    basis = st.segmented_control("期间口径", ["FY", "Q1", "H1", "9M", "TTM"], default="FY", key="financial_period_basis") or "FY"
    trends = loader.trends(sid, basis)
    financials = loader.financials(sid)
    market = loader.market(sid, "RAW")
    if trends.get("issues"):
        st.warning(f"存在 {len(trends['issues'])} 个数据质量提示；缺失值保持为未覆盖。", icon=":material/warning:")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            section("收入与利润趋势")
            financial_trends(trends.get("points", []), key=f"financial_trends_{sid}_{basis}")
            st.caption(f"来源：{trends.get('provider')} · 币种：{trends.get('currency')} · 期间：{trends.get('period_basis')}")
    with right:
        with st.container(border=True):
            section("RAW 价格纪律")
            price_bars(market.get("bars", []), key=f"price_{sid}")
            st.caption(f"价格口径：{market.get('adjustment')} · 单位：{market.get('unit')} · 研究截至：{market.get('research_as_of')}")
    with st.container(border=True):
        section("现金流与现金转换")
        cash_flow_trends(financials.get("statements", []))
        st.caption("现金流点直接来自已披露财务报表；页面不在前端推导现金转换率。")
    section("计算展开")
    points = trends.get("points", [])
    if points:
        selected_period = st.selectbox("选择期间", [point.get("fiscal_period") for point in points], key="financial_point_choice")
        selected = next(point for point in points if point.get("fiscal_period") == selected_period)
        st.write({"指标结果": {key: selected.get(key) for key in ("revenue", "net_profit", "net_margin")}, "期间": selected.get("fiscal_period"), "Evidence IDs": selected.get("evidence_ids"), "源 Evidence IDs": selected.get("source_evidence_ids"), "Provider": selected.get("provider")})
    else:
        st.info("该期间没有可展开的财务点。")
    section("盈利质量与口径提示")
    if financials.get("issues"):
        st.dataframe(financials["issues"], hide_index=True, width="stretch")
    else:
        callout("verified", "财务披露期间、单位和研究时点通过当前快照检查。")
