"""Native Streamlit chart helpers; all points come from service responses."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

# conclusion_health_donut 的图例为 HTML 外置渲染。


def financial_trends(points: list[dict[str, Any]], *, key: str) -> None:
    rows = [{"期间": item.get("fiscal_period"), "营业收入": item.get("revenue"), "归母净利润": item.get("net_profit")} for item in points if item.get("revenue") is not None or item.get("net_profit") is not None]
    if not rows:
        st.info("该期间没有可绘制的财务数据。")
        return
    frame = pd.DataFrame(rows).set_index("期间")
    st.line_chart(frame, width="stretch", height=300)


def price_bars(bars: list[dict[str, Any]], *, key: str) -> None:
    rows = [{"交易日": item.get("trade_date"), "RAW 收盘价": item.get("close"), "成交量": item.get("volume")} for item in bars if item.get("close") is not None]
    if not rows:
        st.info("RAW 价格未覆盖。")
        return
    st.line_chart(pd.DataFrame(rows).set_index("交易日")[["RAW 收盘价"]], width="stretch", height=280)


def cash_flow_trends(statements: list[dict[str, Any]]) -> None:
    rows = [{"期间": item.get("fiscal_period"), "经营活动现金流": (item.get("values") or {}).get("operating_cash_flow"), "自由现金流": (item.get("values") or {}).get("free_cash_flow")} for item in statements if item.get("available_as_of") and ((item.get("values") or {}).get("operating_cash_flow") is not None or (item.get("values") or {}).get("free_cash_flow") is not None)]
    if not rows:
        st.info("经营活动现金流未覆盖。")
        return
    st.line_chart(pd.DataFrame(rows).set_index("期间"), width="stretch", height=280)


def conclusion_health_donut(verified: int, warning: int, blocked: int, *, key: str, total_label: str = "条结论") -> None:
    """结论健康度三扇区 donut + 右侧图例（对齐设计稿图1：图例含计数与百分比）。"""
    import plotly.graph_objects as go

    from ui.theme import TOKENS

    total = verified + warning + blocked
    if total == 0:
        st.info("暂无可聚合的验证状态。")
        return
    legend_rows = "".join(
        f"<div style='display:flex;align-items:center;gap:.4rem;font-size:.8rem;margin:.3rem 0'>"
        f"<span style='width:9px;height:9px;border-radius:9999px;background:{color};flex:none'></span>"
        f"<span style='color:#172B4D'>{label}</span>"
        f"<span style='margin-left:auto;font-weight:700;color:#172B4D'>&nbsp;{value}</span>"
        f"<span style='color:#627D98;width:38px;text-align:right'>{value * 100 // total}%</span></div>"
        for label, value, color in (
            ("可验证", verified, TOKENS["green"]),
            ("需进一步核查", warning, TOKENS["amber"]),
            ("存在冲突/受限", blocked, TOKENS["coral"]),
        )
    )
    fig = go.Figure(go.Pie(
        values=[verified, warning, blocked],
        labels=["可验证", "需进一步核查", "存在冲突受限"],
        hole=0.66, marker=dict(colors=[TOKENS["green"], TOKENS["amber"], TOKENS["coral"]]),
        textinfo="none", hovertemplate="%{label}：%{value}<extra></extra>",
        sort=False, direction="clockwise",
    ))
    fig.update_layout(
        height=190, margin=dict(l=4, r=4, t=4, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
        annotations=[dict(
            text=f"<b style='color:#D99400'>{total}</b><br><span style='font-size:10px;color:#627D98'>{total_label}</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(size=19),
        )],
    )
    chart_col, legend_col = st.columns([1.15, 1])
    with chart_col:
        st.plotly_chart(fig, width="stretch", key=key, config={"displayModeBar": False})
    with legend_col:
        st.markdown(
            f"<div style='padding-top:1.2rem'>{legend_rows}</div>",
            unsafe_allow_html=True,
        )


def mini_bar(series: dict[str, float | None], *, key: str, color: str | None = None) -> None:
    """近 5 期迷你柱状图：卡片内嵌，弱化坐标轴。"""
    import plotly.graph_objects as go

    from ui.theme import TOKENS

    items = [(period, value) for period, value in series.items() if value is not None]
    if not items:
        st.caption("近 5 期数据未覆盖。")
        return
    periods = [item[0] for item in items]
    values = [item[1] for item in items]
    fig = go.Figure(go.Bar(
        x=periods, y=values,
        marker_color=color or TOKENS["blue"],
        hovertemplate="期间: %{x}<br>数值: %{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        height=110, margin=dict(l=4, r=4, t=4, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, tickfont=dict(size=9), showline=False),
        yaxis=dict(visible=False, showgrid=False),
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch", key=key, config={"displayModeBar": False})
