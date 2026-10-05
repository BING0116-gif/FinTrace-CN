"""Native Streamlit chart helpers; all points come from service responses."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


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
