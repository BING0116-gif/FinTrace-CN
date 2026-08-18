"""Read-only FinTrace-CN research workbench for local versioned snapshots.

Run: .venv\\Scripts\\streamlit run workbench.py
"""

from __future__ import annotations

import json
import importlib
from pathlib import Path
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.cn import workbench_service as service

# Streamlit can keep imported modules alive across script reruns.  Reload the
# local service module so a changed UI cannot call a stale service contract.
service = importlib.reload(service)
REQUIRED_SERVICE_FUNCTIONS = (
    "research_summary", "research_peer_valuation", "research_readiness",
    "research_evidence", "research_validation", "research_market",
    "research_financials", "research_financial_trends", "research_display_guardrails",
    "research_overview_insights", "research_valuation", "list_evaluations", "evaluation_detail",
    "list_daily_reviews", "daily_review_summary", "daily_review_detail",
    "start_daily_review", "acquire_live_daily_review",
)


def service_contract_ready() -> bool:
    """Prevent a stale process from exposing a traceback to the user."""
    missing = [name for name in REQUIRED_SERVICE_FUNCTIONS if not callable(getattr(service, name, None))]
    if missing:
        st.error("工作台组件版本不一致。请重启本地工作台后重试。")
        st.caption(f"Missing service functions: {', '.join(missing)}")
        return False
    return True


ROOT = Path(__file__).resolve().parent

NAVIGATION = ["案例演示", "研究总览", "市场与行情", "财务表现", "同行估值", "证据与校验", "Agent 执行轨迹", "研究报告", "研究任务", "评测与消融", "每日复盘"]

DEMO_CASES = {
    "成功研究：贵州茅台": {
        "snapshot_id": "600519.SH_20260810_tushare_v1",
        "status": "pass",
        "summary": "固定快照、完整证据链和同业估值输入均通过校验，可打开研究报告。",
        "next_page": "研究报告",
    },
    "Validator 阻断：缺少关键估值输入": {
        "snapshot_id": "600519.SH_demo_missing_evidence_v1",
        "status": "blocked",
        "summary": "同一套确定性规则发现总股本证据缺失，因此隐藏估值结论和报告。",
        "next_page": "证据与校验",
    },
}


@st.cache_data(ttl=300, max_entries=32)
def load_research(snapshot_id: str) -> tuple[dict, dict]:
    """Load only versioned local data; the UI remains a presentation layer."""
    snapshot = service.load_snapshot(snapshot_id)
    summary = service.research_summary(snapshot_id)
    return snapshot, summary


def cn_money(value: float, unit: str = "亿元") -> str:
    divisor = 1e8 if unit == "亿元" else 1e4
    return f"{value / divisor:,.2f} {unit}"


def evidence_id(symbol: str, metric: str, period: str) -> str:
    return f"fact_{symbol.replace('.', '_')}_{metric}_{period}"


def dependency_graph_dot(graph: dict) -> str:
    """Render only dependency-bearing evidence records from the service graph."""
    edges = graph.get("edges", [])
    connected = {item[key] for item in edges for key in ("source", "target")}
    nodes = {item["id"]: item for item in graph.get("nodes", []) if item["id"] in connected}
    lines = ['digraph {', 'rankdir=LR;', 'node [shape=box, style=rounded, color="#7c9bc7", fontname="Arial"];']
    for node_id, node in nodes.items():
        safe_id = node_id.replace('"', '\\"')
        label = f"{node['metric']}\\n{node_id}".replace('"', '\\"')
        lines.append(f'"{safe_id}" [label="{label}"];')
    for edge in edges:
        source = edge["source"].replace('"', '\\"')
        target = edge["target"].replace('"', '\\"')
        lines.append(f'"{source}" -> "{target}";')
    lines.append('}')
    return "\n".join(lines)


def open_evidence(evidence_id_value: str) -> None:
    """Route a KPI evidence action to the read-only evidence detail."""
    st.session_state["selected_evidence_id"] = evidence_id_value
    st.session_state["workbench_page"] = "证据与校验"


def open_demo_case(snapshot_id: str, page: str) -> None:
    """Switch the read-only workbench to one reproducible demonstration case."""
    st.session_state["snapshot_picker"] = snapshot_id
    st.session_state["workbench_page"] = page


def demo_cases(catalog: list[dict[str, str]]) -> None:
    """Give an interviewer a short, truthful walkthrough before the full workbench."""
    available = {item["id"] for item in catalog}
    st.title("30 秒看懂 FinTrace-CN")
    st.caption("所有内容来自本地版本化快照；页面不抓取实时行情，也不在前端计算或补全数据。")
    st.markdown("**快照** → **证据** → **Validator** → **报告 / 阻断**")
    for name, case in DEMO_CASES.items():
        with st.container(border=True):
            st.subheader(name)
            status_label = "通过" if case["status"] == "pass" else "已阻断"
            st.badge(status_label, icon=":material/check_circle:" if case["status"] == "pass" else ":material/block:", color="green" if case["status"] == "pass" else "red")
            st.write(case["summary"])
            st.caption(f"Snapshot ID: {case['snapshot_id']}")
            if case["snapshot_id"] not in available:
                st.warning("演示快照尚未生成。请先运行 scripts\\create_golden_baseline.py。")
            else:
                st.button(
                    "打开并查看证据链" if case["status"] == "pass" else "查看阻断原因",
                    key=f"demo_{case['snapshot_id']}",
                    on_click=open_demo_case,
                    args=(case["snapshot_id"], case["next_page"]),
                )
    st.info("成功案例用于说明可复现研究如何交付；阻断案例用于说明系统宁可不给结论，也不以缺失数据凑出答案。", icon=":material/shield:")


def style() -> None:
    st.set_page_config(page_title="FinTrace-CN | 研究工作台", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
    st.markdown(
        """<style>
        :root { --ink:#10233d; --muted:#667893; --line:#dde5ef; --navy:#0b1d35; --blue:#2c6bed; --teal:#00a7a0; --amber:#c78512; }
        .stApp { background: #f4f7fb; color: var(--ink); }
        section[data-testid="stSidebar"] { background: linear-gradient(180deg,#08182e,#102b4a); }
        section[data-testid="stSidebar"] * { color:#dbe8f6 !important; }
        section[data-testid="stSidebar"] .stRadio label { border-radius:8px; padding:7px 8px; }
        .block-container { padding: 1.35rem 2.25rem 2rem; max-width: 1540px; }
        .brand { font-size:1.15rem; font-weight:750; letter-spacing:.03em; color:#fff; margin:.2rem 0 1.6rem; }
        .eyebrow { color:#5e718d; font-size:.74rem; letter-spacing:.12em; text-transform:uppercase; font-weight:700; margin-bottom:.35rem; }
        h1 { font-size:1.8rem !important; letter-spacing:-.035em; margin-bottom:.1rem !important; }
        h2 { font-size:1.12rem !important; margin-top:1.4rem !important; }
        .subline { color:var(--muted); font-size:.9rem; }
        .statusbar { display:flex; align-items:center; flex-wrap:wrap; gap:.55rem; padding:.65rem .85rem; background:#fff; border:1px solid var(--line); border-radius:10px; margin:1rem 0 1.3rem; box-shadow:0 2px 10px rgba(31,55,88,.035); }
        .badge { display:inline-flex; align-items:center; gap:.35rem; padding:.25rem .55rem; border-radius:999px; font-size:.73rem; font-weight:650; }
        .verified { background:#dff4eb; color:#137555; }.warning { background:#fff1cf; color:#8a5a00; }.blocked { background:#fde4e1; color:#a33b32; }.snapshot { background:#e8effa; color:#315d9d; }.neutral { background:#eef1f5; color:#536171; }
        .card-note { font-size:.77rem; color:var(--muted); padding-top:.5rem; border-top:1px solid #edf0f4; }
        [data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:11px; padding:1.05rem 1.1rem; min-height:124px; box-shadow:0 2px 10px rgba(31,55,88,.035); }
        [data-testid="stMetricLabel"] { color:var(--muted); font-weight:600; font-size:.78rem; }
        [data-testid="stMetricValue"] { color:var(--ink); font-size:1.55rem; }
        .panel { background:#fff; border:1px solid var(--line); border-radius:11px; padding:1rem 1.2rem; margin-bottom:1rem; }
        .evidence { color:#2c6bed; font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:.76rem; font-weight:600; }
        .warn { border-left:3px solid var(--amber); background:#fffaf0; padding:.75rem .9rem; color:#684b14; border-radius:5px; }
        .trace { border-left:2px solid #95b5ea; padding:.45rem 0 .45rem 1rem; margin-left:.5rem; }
        .stButton>button { border-radius:7px; font-weight:600; }
        </style>""",
        unsafe_allow_html=True,
    )


def header(snapshot: dict, metadata: dict) -> None:
    profile = snapshot["data"]["profile"]
    validation = service.research_validation(snapshot["snapshot_id"])
    validation_class = {"pass": "verified", "warning": "warning", "blocked": "blocked"}[validation["status"]]
    validation_label = {"pass": "校验通过", "warning": "校验警告", "blocked": "校验阻断"}[validation["status"]]
    st.markdown('<div class="eyebrow">Versioned research workspace / 只读快照</div>', unsafe_allow_html=True)
    left, right = st.columns([5, 2])
    with left:
        st.title(f"{profile['name']}  ·  {snapshot['symbol']}")
        st.markdown(f'<div class="subline">{profile["industry_name"]} · {profile["currency"]} · 研究截至 {snapshot["research_as_of"].replace("T", " ")}</div>', unsafe_allow_html=True)
    with right:
        st.download_button("导出研究元数据", json.dumps(metadata, ensure_ascii=False, indent=2), f"{snapshot['symbol']}-research-metadata.json", "application/json", width="stretch")
    st.markdown(f'''<div class="statusbar"><span class="badge snapshot">▣ 版本化快照</span><span class="badge {validation_class}">● {validation_label}</span><span class="badge neutral">Provider · {snapshot["provider"]}</span><span class="badge neutral">Snapshot · {snapshot["snapshot_id"]}</span><span class="badge neutral">口径 · RAW / CNY</span></div>''', unsafe_allow_html=True)


def security_status(snapshot_id: str) -> None:
    """Display stored trading/security flags without inferring a trade conclusion."""
    flags = service.research_market(snapshot_id).get("security_flags", {})
    labels = []
    if flags.get("beijing_exchange"):
        labels.append("北交所证券")
    if flags.get("special_treatment_name_flag"):
        labels.append("证券名称含 ST 标识")
    trading_status = flags.get("latest_trading_status")
    if trading_status and str(trading_status).upper() not in {"NORMAL", "TRADING"}:
        labels.append(f"最新交易状态：{trading_status}")
    if labels:
        st.warning(
            " · ".join(labels) + "。状态仅转述固定快照中的证券标识/交易字段，"
            "不推断复牌、价格或交易结论。",
            icon=":material/warning:",
        )


def overview(snapshot: dict, metadata: dict) -> None:
    data, metrics = snapshot["data"], metadata["key_metrics"]
    bars = pd.DataFrame(service.research_market(snapshot["snapshot_id"])["bars"]).sort_values("trade_date")
    financial_result = service.research_financials(snapshot["snapshot_id"])
    statements = pd.DataFrame(financial_result["statements"])
    statements = statements[statements["available_as_of"]].copy()
    fy = _annual_income(statements).tail(5)
    validation = service.research_validation(snapshot["snapshot_id"])
    validation_class = {"pass": "verified", "warning": "warning", "blocked": "blocked"}[validation["status"]]
    st.markdown("### 研究总览")
    security_status(snapshot["snapshot_id"])
    a, b, c, d = st.columns(4)
    price = metrics.get("price")
    market_cap = metrics.get("market_cap")
    ttm_profit = metrics.get("ttm_net_profit")
    pe_ttm = metrics.get("pe_ttm")
    a.metric("RAW 收盘价", f"¥ {price:,.2f}" if price is not None else "未覆盖", help="研究时点收盘价；未采用前复权或后复权")
    b.metric("市值", cn_money(market_cap) if market_cap is not None else "未覆盖", help="总股本 × RAW 收盘价")
    c.metric("TTM P/E", f"{pe_ttm:.2f}×" if pe_ttm is not None and validation["conclusion_allowed"] else "已阻断", help="市值 ÷ TTM 归母净利润；校验阻断时不展示")
    d.metric("TTM 归母净利润", cn_money(ttm_profit) if ttm_profit is not None else "未覆盖", help="后端确定性计算结果")
    evidence_actions = [
        (a, "收盘价证据", metadata["evidence_ids"].get("price")),
        (b, "市值证据", metadata["evidence_ids"].get("market_cap")),
        (c, "P/E 证据", metadata["evidence_ids"].get("pe_ttm")),
        (d, "TTM 净利润证据", metadata["evidence_ids"].get("ttm_net_profit")),
    ]
    for container, label, item_id in evidence_actions:
        with container:
            st.button(
                label, key=f"overview_{label}_{snapshot['snapshot_id']}",
                icon=":material/account_tree:", disabled=item_id is None,
                on_click=open_evidence if item_id else None, args=(item_id,) if item_id else (),
                width="stretch",
            )
    price_id = metadata["evidence_ids"]["price"] or "未覆盖"
    ttm_id = metadata["evidence_ids"]["ttm_net_profit"] or "未覆盖"
    st.caption(f"关键数值可追溯：收盘价 {price_id} · 市值 {metadata['evidence_ids'].get('market_cap') or '未覆盖'} · P/E {metadata['evidence_ids'].get('pe_ttm') or '未覆盖'} · TTM {ttm_id}")
    if validation["status"] == "blocked":
        st.error("校验已阻断：关键输入或证据链不完整，因此不展示确定性估值结论。请前往“证据与校验”查看修复建议。")
    elif validation["status"] == "warning":
        st.warning("校验存在警告：当前内容可供基础阅读，但同业覆盖或数据时效不足，不应据此形成强结论。")
    st.markdown("### 新手研究摘要")
    readiness = service.research_readiness(snapshot["snapshot_id"])
    readiness_label = {"ready": "可用于基础研究", "limited": "可用但存在限制", "blocked": "关键数据不足"}[readiness["status"]]
    st.markdown(f"**研究就绪度：{readiness_label}**")
    with st.expander("查看数据覆盖与限制", expanded=readiness["status"] != "ready"):
        labels = {"snapshot_freshness": "快照时效", "annual_financial_coverage": "年度财报覆盖", "key_metrics": "关键估值输入", "peer_coverage": "同业样本"}
        rows = [{"检查项": labels[name], "状态": check["status"], "说明": check["detail"]} for name, check in readiness["checks"].items()]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("warning 表示可继续阅读但不应据此作强结论；blocked 表示缺少关键数据。")
    insights = service.research_overview_insights(snapshot["snapshot_id"])
    revenue_change = insights["revenue_change_percent"]
    profit_change = insights["net_profit_change_percent"]
    summary_left, summary_middle, summary_right = st.columns(3)
    with summary_left:
        if revenue_change is None or profit_change is None:
            st.info("业绩趋势：可比年度数据不足，暂不作趋势判断。")
        else:
            state = {"improving": "改善", "under_pressure": "承压", "diverging": "分化"}[insights["performance_status"]]
            st.markdown(f"**业绩状态：{state}**\n\n最近可比年度营收变化 **{revenue_change:+.1f}%**，归母净利润变化 **{profit_change:+.1f}%**。这是已披露业绩变化，不是预测。")
    with summary_middle:
        pe = metrics.get("pe_ttm")
        if not validation["conclusion_allowed"]:
            st.error("估值解读已被 Validator 阻断。")
        elif pe is None or pe <= 0:
            st.info("估值解读：盈利或估值输入不足，PE 暂不可用。")
        else:
            st.markdown(f"**估值读法：TTM PE {pe:.1f} 倍**\n\n市场为最近十二个月每 1 元利润支付约 {pe:.1f} 元。没有完整同业和历史分位数据，不能仅凭此判断贵或便宜。")
    with summary_right:
        if insights["latest_period"] is None:
            st.info("下一次关注：缺少完整年度财报，建议先补齐数据。")
        else:
            st.markdown(f"**下一次应验证什么**\n\n关注下一份财报的营收、归母净利润是否延续 {insights['latest_period']} 的趋势；若背离，再查看成本、毛利率和一次性损益。")
    st.caption(f"摘要仅使用截至 {snapshot['research_as_of'][:10]} 的快照和已披露财报自动生成，不构成买卖建议。")
    left, right = st.columns([1.65, 1])
    with left:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bars.trade_date, y=bars.close, mode="lines+markers", customdata=bars[["evidence_id", "price_basis", "provider"]], hovertemplate="日期: %{x}<br>收盘价: %{y}<br>Evidence ID: %{customdata[0]}<br>价格口径: %{customdata[1]}<br>来源: %{customdata[2]}<extra></extra>", line=dict(color="#2c6bed", width=2.5), fill="tozeroy", fillcolor="rgba(44,107,237,.08)", name="RAW 收盘价"))
        fig.add_vline(x=snapshot["research_as_of"][:10], line_dash="dot", line_color="#8b9bb0")
        fig.update_layout(title="价格区间（RAW）", height=310, margin=dict(l=15,r=15,t=45,b=15), paper_bgcolor="#fff", plot_bgcolor="#fff", yaxis_title="CNY / 股", xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#edf1f5"), showlegend=False)
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key=f"overview_market_{snapshot['snapshot_id']}")
        if event.selection.points:
            selected_id = event.selection.points[0].get("customdata", [None])[0]
            if selected_id:
                st.session_state["selected_evidence_id"] = selected_id
    with right:
        validation_text = {"pass": "证据与关键输入通过", "warning": "存在非阻断警告", "blocked": "关键结论已阻断"}[validation["status"]]
        st.markdown(f"<div class='panel'><b>可信度状态</b><br><br><span class='badge {validation_class}'>● {validation_text}</span><p class='subline'>状态来自后端 Evidence Ledger 与研究门控；计算仅在服务层完成。</p><div class='card-note'>只读 · 无前端派生计算</div></div>", unsafe_allow_html=True)
        st.markdown("<div class='warn'><b>非实时行情</b><br>本页仅展示固定版本快照，不构成交易或投资建议。</div>", unsafe_allow_html=True)
    chart_financials = fy.dropna(subset=["revenue_billion", "net_profit_billion"])
    chart_financials = chart_financials.copy()
    chart_financials["revenue_evidence_id"] = chart_financials["evidence_ids"].apply(lambda ids: ids.get("revenue"))
    chart_financials["profit_evidence_id"] = chart_financials["evidence_ids"].apply(lambda ids: ids.get("net_profit"))
    revenue_custom = list(zip(chart_financials["revenue_evidence_id"], chart_financials["published_at"], [financial_result["provider"]] * len(chart_financials)))
    profit_custom = list(zip(chart_financials["profit_evidence_id"], chart_financials["published_at"], [financial_result["provider"]] * len(chart_financials)))
    fig2 = go.Figure()
    fig2.add_bar(x=chart_financials.fiscal_period, y=chart_financials["revenue_billion"], customdata=revenue_custom, hovertemplate="报告期: %{x}<br>营业收入: %{y}<br>Evidence ID: %{customdata[0]}<br>披露时间: %{customdata[1]}<br>来源: %{customdata[2]}<extra></extra>", name="营业收入", marker_color="#6d8fd5")
    fig2.add_scatter(x=chart_financials.fiscal_period, y=chart_financials["net_profit_billion"], customdata=profit_custom, hovertemplate="报告期: %{x}<br>归母净利润: %{y}<br>Evidence ID: %{customdata[0]}<br>披露时间: %{customdata[1]}<br>来源: %{customdata[2]}<extra></extra>", name="归母净利润", yaxis="y2", mode="lines+markers", line=dict(color="#00a7a0", width=2.5))
    fig2.update_layout(title="年度业绩趋势 · 单位：亿元", height=300, margin=dict(l=15,r=15,t=45,b=15), paper_bgcolor="#fff", plot_bgcolor="#fff", legend=dict(orientation="h", y=1.13), yaxis=dict(title="收入", gridcolor="#edf1f5"), yaxis2=dict(title="净利润", overlaying="y", side="right", showgrid=False))
    event2 = st.plotly_chart(fig2, width="stretch", on_select="rerun", selection_mode="points", key=f"overview_financial_{snapshot['snapshot_id']}")
    if event2.selection.points:
        selected_id = event2.selection.points[0].get("customdata", [None])[0]
        if selected_id:
            st.session_state["selected_evidence_id"] = selected_id


def market(snapshot: dict) -> None:
    market_result = service.research_market(snapshot["snapshot_id"])
    st.markdown("### 市场与行情")
    coverage = market_result["adjustment_coverage"]
    mode = st.segmented_control("复权口径", ["RAW", "QFQ", "HFQ"], default="RAW")
    if not coverage.get(mode, False):
        st.info(f"当前固定快照未覆盖 {mode} 口径；未以任何方式补值。")
        mode = "RAW"
    market_result = service.research_market(snapshot["snapshot_id"], mode)
    bars = pd.DataFrame(market_result["bars"]).sort_values("trade_date")
    st.caption(" · ".join(f"{basis}：{'已覆盖' if covered else '未覆盖'}" for basis, covered in coverage.items()))
    hover = [
        f"日期: {row.trade_date}<br>开盘: {row.open:.2f}<br>最高: {row.high:.2f}"
        f"<br>最低: {row.low:.2f}<br>收盘: {row.close:.2f}"
        f"<br>Evidence ID: {row.evidence_id}<br>价格口径: {row.price_basis}<br>来源: {row.provider}"
        for row in bars.itertuples()
    ]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.72, 0.28])
    fig.add_trace(go.Candlestick(
        x=bars.trade_date, open=bars.open, high=bars.high, low=bars.low, close=bars.close,
        customdata=bars[["evidence_id", "price_basis", "provider"]],
        hovertext=hover, hoverinfo="text",
        increasing_line_color="#1c9a82", decreasing_line_color="#6c7b91", name="RAW",
    ), row=1, col=1)
    fig.add_trace(go.Bar(x=bars.trade_date, y=bars.volume, marker_color="#9fb2cc", name="成交量（手）", hovertemplate="日期: %{x}<br>成交量: %{y:,.0f} 手<extra></extra>"), row=2, col=1)
    fig.add_vline(x=snapshot["research_as_of"][:10], line_dash="dot", line_color="#8b9bb0", annotation_text="研究时点", row=1, col=1)
    fig.update_layout(height=560, title=f"日线与成交量 / {mode}", xaxis_rangeslider_visible=False, paper_bgcolor="#fff", plot_bgcolor="#fff", margin=dict(l=15,r=15,t=45,b=15), showlegend=False)
    fig.update_yaxes(title_text="CNY / 股", row=1, col=1)
    fig.update_yaxes(title_text="手", row=2, col=1)
    event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key=f"market_chart_{snapshot['snapshot_id']}")
    if event.selection.points:
        point = event.selection.points[0]
        selected_id = point.get("customdata", [None])[0]
        if selected_id:
            st.session_state["selected_evidence_id"] = selected_id
    st.dataframe(bars.tail(12).sort_values("trade_date", ascending=False)[["trade_date","open","high","low","close","volume"]], width="stretch", hide_index=True, column_config={"trade_date":"交易日","close":st.column_config.NumberColumn("收盘价", format="¥ %.2f"), "volume":"成交量（手）"})
    latest = bars.iloc[-1]
    st.caption(f"悬浮数据与表格均来自快照 bars[]；最近收盘价证据：{latest.evidence_id}。点击数据点后，Evidence ID 会在跨页面会话中保留。")


def _financial_value(values: object, field: str, divisor: float = 1e8) -> float | None:
    """Return a display-ready financial value without inventing missing data."""
    if not isinstance(values, dict):
        return None
    value = values.get(field)
    if value is None or pd.isna(value):
        return None
    return float(value) / divisor


def _annual_income(statements: pd.DataFrame) -> pd.DataFrame:
    annual = statements[
        (statements.statement_type == "income")
        & statements.fiscal_period.astype(str).str.endswith("FY")
    ].copy()
    annual["revenue_billion"] = annual["values"].apply(lambda values: _financial_value(values, "revenue"))
    annual["net_profit_billion"] = annual["values"].apply(lambda values: _financial_value(values, "net_profit"))
    return annual.sort_values("fiscal_period")


def financials(snapshot: dict) -> None:
    guardrails = service.research_display_guardrails(snapshot["snapshot_id"])
    st.markdown("### 财务表现")
    period_basis = st.segmented_control("期间口径", ["FY", "Q1", "H1", "9M", "TTM"], default="FY")
    metric = st.segmented_control("展示指标", ["收入", "归母净利润", "净利率"], default="收入")
    field = {"收入": "revenue", "归母净利润": "net_profit", "净利率": "net_margin"}[metric]
    financial_result = service.research_financial_trends(snapshot["snapshot_id"], period_basis)
    frame = pd.DataFrame(financial_result["points"])
    if frame.empty:
        st.info(f"当前快照没有可用的 {period_basis} 财务数据；未进行补零或跨期间推断。")
        if guardrails["missing_data"]["visible"]:
            st.warning(f"存在 {guardrails['missing_data']['count']} 个缺失财务字段；界面显示为未覆盖。")
        if guardrails["future_data"]["visible"]:
            st.error(f"存在 {guardrails['future_data']['count']} 份晚于研究截止日披露的数据；已排除。")
        if guardrails["validation_block"]["visible"]:
            st.error("校验已阻断：不展示确定性结论。")
        return
    frame["value"] = frame[field]
    if field != "net_margin":
        frame["value"] = frame["value"].apply(lambda value: value / 1e8 if pd.notna(value) else None)
    frame["evidence_id"] = frame["evidence_ids"].apply(lambda ids: ids.get(field))
    chart_data = frame.dropna(subset=["value"])
    title = f"{period_basis} · {metric}"
    y_title = "%" if field == "net_margin" else f"亿元 {financial_result['currency']}"
    if chart_data.empty:
        st.info(f"当前快照的 {period_basis} {metric}未覆盖；未进行补零。")
    else:
        chart_data = chart_data.copy()
        fig = px.bar(
            chart_data, x="fiscal_period", y="value", text_auto=".1f",
            custom_data=["evidence_id", "published_at", "provider", "period_basis"],
            color_discrete_sequence=["#2c6bed"],
        )
        fig.update_traces(hovertemplate="报告期: %{x}<br>数值: %{y}<br>Evidence ID: %{customdata[0]}<br>披露时间: %{customdata[1]}<br>来源: %{customdata[2]}<br>期间口径: %{customdata[3]}<extra></extra>")
        fig.update_layout(title=title, height=380, paper_bgcolor="#fff", plot_bgcolor="#fff", margin=dict(l=15,r=15,t=45,b=15), yaxis_title=y_title, xaxis_title="报告期")
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key=f"financial_chart_{snapshot['snapshot_id']}_{period_basis}_{metric}")
        if event.selection.points:
            selected_id = event.selection.points[0].get("customdata", [None])[0]
            if selected_id:
                st.session_state["selected_evidence_id"] = selected_id
    table = frame[["fiscal_period", "published_at", "revenue", "net_profit", "net_margin", "evidence_id"]].copy()
    table["revenue"] = table["revenue"].apply(lambda value: value / 1e8 if pd.notna(value) else None)
    table["net_profit"] = table["net_profit"].apply(lambda value: value / 1e8 if pd.notna(value) else None)
    table = table.sort_values("fiscal_period", ascending=False)
    table_event = st.dataframe(
        table, width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row",
        key=f"financial_table_{snapshot['snapshot_id']}_{period_basis}_{metric}",
        column_config={
            "fiscal_period": "报告期", "published_at": "披露时间",
            "revenue": st.column_config.NumberColumn("营业收入（亿元）", format="%.2f"),
            "net_profit": st.column_config.NumberColumn("归母净利润（亿元）", format="%.2f"),
            "net_margin": st.column_config.NumberColumn("净利率", format="%.2f%%"),
            "evidence_id": "当前指标 Evidence ID",
        },
    )
    if table_event.selection.rows:
        selected_id = table.iloc[table_event.selection.rows[0]]["evidence_id"]
        if selected_id:
            st.session_state["selected_evidence_id"] = selected_id
    selected_id = st.session_state.get("selected_evidence_id")
    if selected_id and selected_id in set(table["evidence_id"].dropna()):
        selected = next(item for item in service.research_evidence(snapshot["snapshot_id"])["records"] if item["evidence_id"] == selected_id)
        with st.container(border=True):
            st.markdown(f"#### 证据详情 · `{selected_id}`")
            st.write({"报告期": selected.get("period"), "披露时间": selected.get("published_at"), "来源": selected["provider"], "字段路径": selected.get("field_path")})
    if guardrails["missing_data"]["visible"]:
        st.warning(f"存在 {guardrails['missing_data']['count']} 个缺失财务字段；界面显示为暂无数据，未进行补值。")
    if guardrails["future_data"]["visible"]:
        st.error(f"存在 {guardrails['future_data']['count']} 份晚于研究截止日披露的数据；已从图表和证据详情中排除。")
    if guardrails["validation_block"]["visible"]:
        st.error("校验已阻断：不展示确定性结论，请在证据与校验页修复关键输入或依赖。")


def valuation(snapshot: dict, metadata: dict) -> None:
    m = metadata["key_metrics"]
    st.markdown("### 同行估值")
    st.info("当前多标的工作台尚未为每个快照生成同行估值产物，因此不展示或推导同业中位数。")
    rows = [{"指标": "PE", "目标公司": m["market_cap"] / m["ttm_net_profit"] if m["market_cap"] and m["ttm_net_profit"] else None}, {"指标": "PB", "目标公司": m["market_cap"] / m["book_equity"] if m["market_cap"] and m["book_equity"] else None}, {"指标": "PS", "目标公司": m["market_cap"] / m["ttm_revenue"] if m["market_cap"] and m["ttm_revenue"] else None}]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    peer = service.research_peer_valuation(snapshot["snapshot_id"])
    if not peer.get("available"):
        st.warning("当前本地快照没有可用同业参照，不能判断估值高低。请补充同一行业、相近日期且财务口径完整的快照。")
        return
    st.markdown("#### 同业参照（仅限兼容本地快照）")
    reference_rows = []
    for name, value in peer["multiples"].items():
        median = value.get("median")
        if median is None:
            continue
        target_value = next((item["鐩爣鍏徃"] for item in rows if item["鎸囨爣"] == name), None)
        comparison = "数据不足" if target_value is None else "高于同业中位数" if target_value > median else "低于同业中位数" if target_value < median else "接近同业中位数"
        reference_rows.append({"指标": name, "目标公司": target_value, "同业中位数": median, "对比": comparison, "中位数对应价格": value.get("implied_price"), "样本置信度": value.get("confidence")})
    st.dataframe(pd.DataFrame(reference_rows), width="stretch", hide_index=True)
    peers = "、".join(peer["peer_names"].values())
    low_confidence = "peer_count_below_4_low_confidence" in peer["validation"].get("warnings", [])
    note = "样本少于 4 家，仅作低置信度参考。" if low_confidence else "样本数达到基础可比要求，但不构成投资建议。"
    st.caption(f"已纳入 {peer['peer_count']} 家可比公司：{peers}。{note} 同业仅按同一行业、相近快照日期和 TTM 口径筛选。")


def valuation_safe(snapshot: dict, metadata: dict) -> None:
    """展示服务层生成的同行估值，前端不派生任何倍数。"""
    st.markdown("### 同行估值")
    peer = service.research_valuation(snapshot["snapshot_id"])
    if peer.get("method_boundary") == "financial_institution_pe_pb_only":
        st.warning("金融机构不适用通用企业估值框架；当前仅展示 PE/PB，隐藏 PS、EV/EBITDA 和通用企业 DCF。")
    if not peer.get("available"):
        st.warning("当前没有兼容的本地同行快照，因此不判断估值高低，也不生成替代数字。")
        return
    metric = st.segmented_control("估值指标", list(peer["multiples"]), default=next(iter(peer["multiples"])))
    multiple = peer["multiples"][metric]
    interval = peer["valuation_ranges"][metric]
    target = peer["target_multiples"].get(metric)
    confidence_label = {"high": "高", "medium": "中", "low": "低", "unavailable": "不可用"}.get(multiple.get("confidence"), "未测量")
    with st.container(horizontal=True):
        st.metric("目标公司", f"{target:.2f}×" if target is not None else "未覆盖", border=True)
        st.metric("同行中位数", f"{interval['median']:.2f}×" if interval["median"] is not None else "未覆盖", border=True)
        st.metric("同行区间 P25–P75", f"{interval['p25']:.2f}–{interval['p75']:.2f}×" if interval["p25"] is not None and interval["p75"] is not None else "未覆盖", border=True)
        st.metric("样本置信度", confidence_label, border=True)
    if peer["conclusion_allowed"]:
        st.caption(
            f"隐含价格区间：¥{interval['implied_price_low']:.2f}–¥{interval['implied_price_high']:.2f}；"
            f"中位数对应 ¥{interval['implied_price_median']:.2f}。仅为确定性同行倍数换算，不构成投资建议。"
            if interval["implied_price_low"] is not None and interval["implied_price_high"] is not None
            else "当前输入不足，未生成隐含价格区间。"
        )
    else:
        st.error("Validator 已阻断：隐含价格和确定性估值区间已隐藏。")
    distribution = pd.DataFrame(peer["distributions"][metric])
    chart_rows = distribution.dropna(subset=["value"])
    if not chart_rows.empty:
        colors = chart_rows["included"].map({True: "#2c6bed", False: "#c78512"})
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_rows["value"], y=chart_rows["name"], mode="markers", marker=dict(size=12, color=colors),
            customdata=chart_rows[["symbol", "included", "exclusion_reason", "snapshot_id", "research_as_of"]],
            hovertemplate="公司: %{y} (%{customdata[0]})<br>倍数: %{x:.2f}<br>纳入: %{customdata[1]}<br>原因: %{customdata[2]}<br>Snapshot: %{customdata[3]}<br>研究时点: %{customdata[4]}<extra></extra>",
            name="同行",
        ))
        if target is not None:
            fig.add_vline(x=target, line_color="#00a7a0", line_width=2, annotation_text="目标公司")
        if interval["p25"] is not None and interval["p75"] is not None:
            fig.add_vrect(x0=interval["p25"], x1=interval["p75"], fillcolor="rgba(44,107,237,.10)", line_width=0, annotation_text="P25–P75")
        fig.update_layout(height=max(330, 52 * len(chart_rows)), xaxis_title=f"{metric}（倍）", yaxis_title=None, margin=dict(l=15, r=15, t=30, b=15), paper_bgcolor="#fff", plot_bgcolor="#fff", showlegend=False)
        st.plotly_chart(fig, width="stretch", key=f"peer_distribution_{snapshot['snapshot_id']}_{metric}")
    st.markdown("#### 同行纳入与剔除")
    reason_labels = {
        "same_industry_same_period": "同一行业且期间兼容", "industry_mismatch": "行业不一致",
        "period_basis_mismatch": "期间口径不一致", "missing_evidence_ids": "证据缺失",
        "invalid_price_or_shares": "价格或股本无效", "iqr_outlier": "IQR 异常值",
    }
    decisions = []
    metric_rows = {row["symbol"]: row for row in peer["distributions"][metric]}
    for decision in peer["decisions"]:
        row = metric_rows.get(decision["symbol"])
        reason = row.get("exclusion_reason") if row and row.get("exclusion_reason") else decision["reason"]
        decisions.append({"代码": decision["symbol"], "公司": peer["peer_names"].get(decision["symbol"], decision["symbol"]), "纳入": bool(row and row["included"]), "原因": reason_labels.get(reason, reason)})
    for symbol in peer["date_excluded_symbols"]:
        decisions.append({"代码": symbol, "公司": symbol, "纳入": False, "原因": "快照日期差超过 7 天"})
    st.dataframe(pd.DataFrame(decisions), width="stretch", hide_index=True)
    with st.expander("查看公式与证据输入"):
        formula = peer["formulas"][metric]
        st.code(f"目标倍数 = {formula['target_multiple']}\n隐含价格 = {formula['implied_price']}", language=None)
        st.write({"目标公司 Evidence IDs": formula["target_input_evidence_ids"], "同行 Evidence IDs": formula["peer_input_evidence_ids"]})
        with st.container(horizontal=True):
            for item_id in formula["target_input_evidence_ids"]:
                st.button("查看证据", key=f"valuation_evidence_{metric}_{item_id}", on_click=open_evidence, args=(item_id,), icon=":material/account_tree:")
    names = "、".join(peer["peer_names"].values())
    low_confidence = "peer_count_below_4_low_confidence" in peer["validation"].get("warnings", [])
    confidence = "样本少于 4 家，仅作低置信度参考。" if low_confidence else "样本数达到基础比较门槛。"
    st.caption(f"同行（{peer['peer_count']} 家）：{names}。{confidence} 价格口径 {peer['price_basis']}，期间口径 {peer['period_basis']}；仅纳入同一行业和相近快照日期，不构成投资建议。")


def evidence(snapshot: dict, metadata: dict) -> None:
    st.markdown("### 证据与校验中心")
    evidence_result = service.research_evidence(snapshot["snapshot_id"])
    validation = service.research_validation(snapshot["snapshot_id"])
    records = evidence_result["records"]
    rows = [{
        "Evidence ID": item["evidence_id"], "类型": "计算" if item["kind"] == "calculation" else "事实",
        "指标": item["metric"], "数值": item["value"], "单位": item["unit"],
        "期间": item.get("period") or "—", "来源": item["provider"], "状态": item["status"],
    } for item in records]
    frame = pd.DataFrame(rows)
    event = st.dataframe(
        frame, width="stretch", hide_index=True, height=360, on_select="rerun",
        selection_mode="single-row", key=f"evidence_table_{snapshot['snapshot_id']}",
    )
    selected_id = st.session_state.get("selected_evidence_id")
    if event.selection.rows:
        selected_id = frame.iloc[event.selection.rows[0]]["Evidence ID"]
        st.session_state["selected_evidence_id"] = selected_id
    selected = next((item for item in records if item["evidence_id"] == selected_id), None)
    if selected is not None:
        with st.container(border=True):
            st.markdown(f"#### 证据详情 · `{selected['evidence_id']}`")
            detail_left, detail_right = st.columns(2)
            detail_left.write({
                "类型": selected["kind"], "指标": selected["metric"], "数值": selected["value"],
                "单位": selected["unit"], "期间": selected.get("period"), "来源": selected["provider"],
            })
            detail_right.write({
                "字段路径": selected.get("field_path"), "运算": selected.get("operation"),
                "依赖 Evidence IDs": selected.get("input_ids", []), "披露时间": selected.get("published_at"),
            })
    else:
        st.info("选择任一证据行查看字段路径或计算依赖；也可从研究总览点击关键指标证据。")
    validation_export = {
        "snapshot_id": snapshot["snapshot_id"],
        "research_as_of": validation["research_as_of"],
        "provider": snapshot.get("provider", "snapshot"),
        "validation": validation,
        "evidence_records": records,
        "dependency_graph": evidence_result["dependency_graph"],
    }
    st.download_button(
        "下载全部证据与校验材料（JSON）",
        json.dumps(validation_export, ensure_ascii=False, indent=2),
        f"{snapshot['symbol']}_evidence_validation.json",
        "application/json",
        icon=":material/download:",
    )
    if validation["status"] == "blocked":
        st.error("当前存在关键缺口，系统不会输出确定性结论或研究报告。请按下方阻断项补齐数据后重跑。")
    elif validation["status"] == "warning":
        st.warning("基础证据和关键输入已通过；当前可阅读全部已验证材料与生成基础研究报告。黄色项表示研究范围受限，例如不能据此给出同行估值结论，并不等于已展示的事实数据不可信。")
    else:
        st.success("该快照的证据、关键输入和研究范围均满足当前研究要求，可生成完整研究交付。")

    left, right = st.columns(2)
    with left:
        st.markdown("#### 计算依赖")
        graph = evidence_result["dependency_graph"]
        if graph["edges"]:
            st.graphviz_chart(dependency_graph_dot(graph))
        else:
            st.info("当前证据集中没有计算依赖关系。")
    with right:
        st.markdown("#### Validator 清单")
        for check in validation["checks"]:
            if check["status"] == "pass":
                message = f"**{check['label']}** — 已通过：{check['detail']}"
            elif check["status"] == "warning":
                message = (
                    f"**{check['label']}** — 研究范围限制：{check['detail']}\n\n"
                    f"当前影响：不阻断已验证事实和基础报告；涉及该项的扩展结论会降级或不展示。\n\n"
                    f"如需扩展范围：{check['remediation']}"
                )
            else:
                message = (
                    f"**{check['label']}** — 关键阻断：{check['detail']}\n\n"
                    f"需要处理：{check['remediation']}"
                )
            if check["status"] == "pass":
                st.success(message)
            elif check["status"] == "warning":
                st.warning(message)
            else:
                st.error(message)
        st.caption(f"综合状态：{validation['status']} · 允许确定性结论：{validation['conclusion_allowed']} · 研究截至：{validation['research_as_of']}")


def _trace_legacy(snapshot: dict) -> None:
    st.markdown("### Agent 执行轨迹")
    st.caption("仅呈现已记录的研究流程摘要；外部工具内容始终按数据处理。")
    events = [("01", "解析研究对象", f"{snapshot['symbol']} · A 股实体解析", "成功", "—"), ("02", "加载版本化快照", f"{snapshot.get('provider', 'snapshot')} / {snapshot['snapshot_id']}", "成功", "—"), ("03", "确定性计算", "TTM 与市场价值", "成功", "—"), ("04", "Evidence Ledger", "生成事实与计算依赖", "成功", "—")]
    for n, title, detail, status, duration in events:
        st.markdown(f"<div class='trace'><span class='badge verified'>{n} · {status}</span> <b>{title}</b> <span class='subline'>— {detail} · {duration}</span></div>", unsafe_allow_html=True)


def trace(snapshot: dict) -> None:
    """Render only persisted task events; legacy snapshots remain explicitly empty."""
    result = service.research_trace(snapshot["snapshot_id"])
    st.markdown("### Agent 执行轨迹")
    if not result["available"]:
        st.info("该快照没有已持久化的执行轨迹；不会补造成功步骤。")
        return
    st.caption(
        f"任务 {result['task_id']} · Trace {result['trace_id']} · "
        f"模型 {result.get('model') or '未记录'} · Prompt {result.get('prompt_version') or '未记录'}"
    )
    for event in result["events"]:
        with st.container(border=True):
            st.write(f"**{event['event']}** · {event['status']}")
            st.caption(f"{event['at']} · {event['detail']}")
            if event.get("evidence_ids"):
                st.code(", ".join(event["evidence_ids"]), language=None)


def report(snapshot: dict) -> None:
    st.markdown("### 中文研究报告")
    report_path = ROOT / "output" / f"{snapshot['symbol']}_research_report.md"
    if not report_path.exists():
        st.info("该快照尚未生成独立研究报告。请使用受控离线研究流程生成后再查看。")
        return
    report = report_path.read_text(encoding="utf-8")
    st.download_button("下载 Markdown 报告", report, report_path.name, "text/markdown")
    st.text_area("只读报告预览", report[:12000], height=560, disabled=True)


def evaluations() -> None:
    st.markdown("### 评测与消融")
    st.caption("仅展示本地已落盘的评测产物；未测量指标不会以 0 代替。")
    items = service.list_evaluations()
    if not items:
        st.info("尚无可展示的 benchmark 或 ablation 产物。")
        return
    labels = {f"{item['kind']} · {item['id']}": item["id"] for item in items}
    evaluation_id = labels[st.selectbox("评测产物", list(labels), key="evaluation_picker")]
    detail = service.evaluation_detail(evaluation_id)
    st.caption(f"版本：{detail.get('metadata', {}).get('benchmark_version') or '未记录'} · 运行时间：{detail.get('metadata', {}).get('run_at') or '未记录'}")
    if detail["kind"] == "ablation":
        rows = detail.get("variants", [])
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        missing = detail.get("missing_variants", [])
        if missing:
            st.warning(f"未测量配置：{', '.join(missing)}")
        detailed_results = detail.get("detailed_results", {})
        if detailed_results:
            variant = st.selectbox("查看消融案例", list(detailed_results), key="ablation_variant_picker")
            cases = detailed_results[variant]
            st.dataframe(pd.DataFrame([{key: row.get(key) for key in (
                "case_id", "passed", "tool_f1", "parameters_ok", "evidence_coverage",
                "validator_intercepted", "error_conclusion_leakage", "latency_seconds", "cost_usd",
            )} for row in cases]), width="stretch", hide_index=True)
            case_ids = [row.get("case_id", "unknown") for row in cases]
            selected_case = st.selectbox("案例详情", case_ids, key="ablation_case_picker")
            selected = next(row for row in cases if row.get("case_id") == selected_case)
            st.json({key: value for key, value in selected.items() if key not in {"report"}})
        return
    summary = detail.get("summary", {})
    metric_labels = {
        "tool_f1": "工具路由准确率", "parameter_accuracy": "参数准确率",
        "evidence_coverage": "Evidence 覆盖率", "e2e_success_rate": "任务成功率",
        "avg_latency_seconds": "平均延迟（秒）", "total_cost_usd": "总成本（USD）",
        "numeric_accuracy": "数字正确率", "conclusion_leakage_rate": "结论泄漏率",
        "failure_recovery_rate": "失败恢复率",
    }
    rows = [{"指标": label, "值": summary.get(key) if summary.get(key) is not None else "未测量"}
            for key, label in metric_labels.items()]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    regression = detail.get("regression")
    if regression:
        (st.success if regression.get("passed") else st.error)(
            "CI 回归检查通过" if regression.get("passed") else f"CI 回归失败：{regression.get('regressions', [])}"
        )
    results = detail.get("results", [])
    if results:
        st.dataframe(pd.DataFrame([{key: row.get(key) for key in ("case_id", "passed", "tool_f1", "parameters_ok", "evidence_coverage", "latency_seconds", "cost_usd")} for row in results]), width="stretch", hide_index=True)
        case_ids = [row.get("case_id", "unknown") for row in results]
        selected_case = st.selectbox("查看案例轨迹", case_ids, key="evaluation_case_picker")
        selected = next(row for row in results if row.get("case_id") == selected_case)
        if selected.get("research_state"):
            st.json(selected["research_state"])


@st.fragment(run_every="10s")
def tasks() -> None:
    st.markdown("### 受控研究任务")
    st.caption("仅对已有版本化快照生成研究；没有快照时，只记录采集需求，不生成任何数值或结论。")
    with st.form("new_research_task", border=True):
        symbol = st.text_input("A 股代码", placeholder="例如：600519.SH")
        submitted = st.form_submit_button("启动受控研究", icon=":material/play_arrow:", width="content")
    if submitted:
        try:
            task = service.start_research(symbol)
        except ValueError as exc:
            st.error(f"代码格式无效：{exc}")
        else:
            if task["status"] in {"queued", "running"}:
                st.info(f"任务已进入 {task['status']} 状态：{task['message']}")
            elif task["status"] in {"completed", "succeeded"}:
                st.success(f"{task['symbol']} 的研究已生成；可从侧边栏切换到对应快照查看。")
                load_research.clear()
            elif task["status"] == "needs_snapshot":
                st.warning(task["message"])
                st.code(task["next_step"], language=None)
            else:
                st.error(f"任务状态：{task['status']} · {task['message']}")
    st.markdown("#### 新公司数据采集")
    st.caption("采集仅在服务端执行。Tushare Token 只从服务器 `.env` 读取；每次采集固定最多 6 次调用，且第一次失败即停止。")
    with st.form("snapshot_acquisition", border=True):
        acquisition_symbol = st.text_input("待采集 A 股代码", placeholder="例如：601318.SH", key="acquisition_symbol")
        start_date, end_date = st.columns(2)
        with start_date:
            start = st.date_input("起始日期", value=date.today() - timedelta(days=35), key="acquisition_start")
        with end_date:
            end = st.date_input("截止日期", value=date.today(), key="acquisition_end")
        acquire = st.form_submit_button("采集并固化快照", icon=":material/cloud_download:", width="content")
    if acquire:
        try:
            task = service.collect_snapshot(acquisition_symbol, start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"))
        except ValueError as exc:
            st.error(f"无法启动采集：{exc}")
        else:
            if task["status"] in {"queued", "running"}:
                st.info(f"采集任务已进入 {task['status']} 状态：{task['message']}")
            elif task["status"] in {"completed", "succeeded"}:
                st.success("快照已创建。现在可输入该代码启动受控研究。")
                load_research.clear()
            elif task["status"] == "blocked":
                st.warning(task["message"])
            else:
                st.error(f"采集未完成：{task['message']}")
    history = service.list_tasks()
    status_options = sorted({item.get("status", "unknown") for item in history})
    selected_statuses = st.multiselect(
        "按状态筛选任务", status_options, default=status_options,
        key="task_status_filter", persist_state="session",
    )
    if selected_statuses:
        history = [item for item in history if item.get("status") in selected_statuses]
    if not history:
        st.info("尚无任务记录。")
        return
    rows = []
    for task in history:
        rows.append({"任务 ID": task["id"], "标的": task["symbol"], "状态": task["status"], "创建时间": task["created_at"], "说明": task["message"]})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with st.expander("任务详情、诊断与操作"):
        task_ids = [item["id"] for item in history]
        selected_task_id = st.selectbox("任务 ID", task_ids, key="task_history_picker")
        progress = service.get_task_progress(selected_task_id)
        diagnostics = service.task_diagnostics(selected_task_id)
        st.progress(int(progress.get("progress_percent") or 0), text=f"{progress['status']} · {progress.get('current_step') or 'waiting'}")
        st.json(diagnostics)
        if diagnostics["status"] in {"queued", "running"}:
            if st.button("取消任务", icon=":material/cancel:", key=f"cancel_{selected_task_id}"):
                st.info(service.cancel_task(selected_task_id)["message"])
                st.rerun()
        if diagnostics["kind"] in {"offline_research", "snapshot_acquisition"} and diagnostics["status"] in {"failed", "blocked"}:
            if st.button("安全重跑此任务", icon=":material/replay:", key=f"rerun_{selected_task_id}"):
                st.success(f"已创建重跑任务 {service.rerun_task(selected_task_id)['id']}。")
                st.rerun()


def daily_review() -> None:
    """Read-only market breadth review built from versioned local snapshots,
    with an optional on-demand live acquisition button."""
    st.markdown("### 每日复盘 · 市场广度")
    st.caption("默认离线演示；点击下方按钮可按需拉取 Tushare 实时数据。缺数据标注「未覆盖」，离线演示快照明确标记 synthetic_demo。")

    # ---- On-demand live acquisition bar ----
    acq_col1, acq_col2, acq_col3 = st.columns([3, 1.5, 1.5])
    with acq_col1:
        # Default: today in YYYYMMDD format; user can override.
        today_str = date.today().strftime("%Y%m%d")
        live_date = st.text_input(
            "采集日期（YYYYMMDD）",
            value=today_str,
            key="dr_live_date",
            help="仅支持已过去的交易日。周末/节假日/盘中时段会拦截并提示；建议填最近完整交易日（如上周五）。",
        )
    with acq_col2:
        if st.button("📡 获取实时数据", key="dr_acquire_btn", type="primary",
                     help="混合实时采集：指数 Tushare + 涨停/板块/广度/资金流 AkShare（免费源）。\n需要 .env 中已配置 TUSHARE_TOKEN；任一源不可用对应模块留空，绝不编数据。"):
            # --- Date validation: block future / same-day during market hours ---
            _date_err = None
            try:
                ld = datetime.strptime(live_date, "%Y%m%d").date()
                now = datetime.now()
                today_val = now.date()
                if ld > today_val:
                    _date_err = f"日期 {live_date} 是未来日期，无法采集。请填已过去的交易日。"
                elif ld == today_val:
                    # Chinese A-share market: 9:30-11:30, 13:00-15:00 Mon-Fri
                    _hour = now.hour
                    _wd = now.weekday()  # 0=Mon ... 6=Sun
                    if _wd >= 5:
                        _date_err = f"今天 {live_date} 是周末，休市。请填最近交易日（如上周五）。"
                    elif _hour < 16:
                        _date_err = (
                            f"今天 {live_date} 尚在交易时段内（当前 {_hour}:{now.minute:02d}），"
                            f"Tushare 盘后数据尚未更新。建议填最近完整交易日（如上周五），"
                            f"或等到 16:00 后再试。"
                        )
            except ValueError:
                _date_err = f"日期格式错误：'{live_date}' 不是有效的 YYYYMMDD 格式。"

            if _date_err:
                st.warning(_date_err, icon=":material/event_busy:")
            else:
                with st.spinner(f"正在混合采集（Tushare + AkShare + LLM润色）{live_date} 的实时数据…"):
                    try:
                        result = service.acquire_live_daily_review(live_date)
                        if result["status"] == "ok":
                            st.success(result["message"], icon=":material/cloud_done:")
                            st.session_state["dr_auto_select_snapshot"] = result.get("snapshot_id")
                            st.rerun()
                        elif result["status"] in ("partial_error", "partial"):
                            st.warning(result["message"], icon=":material/warning:")
                            st.session_state["dr_auto_select_snapshot"] = result.get("snapshot_id")
                            st.rerun()
                        else:
                            st.error(result["message"], icon=":material/error:")
                    except Exception as exc:
                        st.error(f"采集过程出错：{type(exc).__name__}: {str(exc)[:200]}", icon=":material/error:")
    with acq_col3:
        st.markdown("")
        st.markdown("")
        st.caption("💡 默认离线，按需实时；热点由 DeepSeek 润色")

    st.divider()

    reviews = service.list_daily_reviews()
    if not reviews:
        st.info("尚未发现本地市场复盘快照。可运行 `scripts\\collect_daily_review.py` 生成离线演示快照，"
                "或通过上方「获取实时数据」按钮触发。")
        return

    labels = {f"{item['review_as_of']} · {item['id']}": item["id"] for item in reviews}
    label_list = list(labels)

    # Determine default index: auto-select newly acquired snapshot if available.
    auto_id = st.session_state.pop("dr_auto_select_snapshot", None)
    default_index = 0
    if auto_id:
        for idx, lbl in enumerate(label_list):
            if labels[lbl] == auto_id:
                default_index = idx
                break

    selected = st.selectbox("复盘快照", label_list, index=default_index, key="daily_review_picker")
    snapshot_id = labels[selected]
    summary = service.daily_review_summary(snapshot_id)
    panorama = service.daily_review_detail(snapshot_id, "panorama")
    hotspots = service.daily_review_detail(snapshot_id, "hotspots")

    synth = summary["is_synthetic_demo"]
    gate_status = summary["validation"]["status"]
    st.markdown(
        f'<div class="statusbar">'
        f'<span class="badge snapshot">复盘时点 {summary["review_as_of"]}</span>'
        f'<span class="badge {"warning" if synth else "verified"}">'
        f'{"离线演示 synthetic_demo" if synth else "来源 " + str(summary["provider"])}</span>'
        f'<span class="badge {"blocked" if gate_status == "blocked" else "verified"}">校验 {gate_status}</span>'
        f'<span class="badge neutral">确定性结论 {"允许" if summary["validation"]["conclusion_allowed"] else "阻断"}</span>'
        f'<span class="badge neutral">指数 {summary["index_count"]} · 板块 {summary["sector_count"]} · 涨停 {summary["limit_up_count"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if synth:
        st.warning("当前为离线演示快照（synthetic_demo），数值仅供架构演示，不代表真实行情，绝不用于实盘决策。", icon=":material/shield:")

    st.markdown("#### 指数收盘")
    indices = panorama["sections"]["index_closing"]["indices"]
    cols = st.columns(min(len(indices), 3) or 1)
    for idx, item in enumerate(indices):
        with cols[idx % len(cols)]:
            with st.container(border=True):
                st.markdown(f"**{item['index_name']}**")
                st.markdown(f"<div style='font-size:1.4rem'>{item['close']:.2f}</div>", unsafe_allow_html=True)
                color = "#c0392b" if item["pct_change"] >= 0 else "#1c9a82"
                sign = "+" if item["pct_change"] >= 0 else ""
                st.markdown(
                    f"<span style='color:{color};font-weight:650'>{sign}{item['pct_change']:.2f}% "
                    f"({sign}{item['change']:.2f})</span> · 额 {item['amount_yi']:.0f}亿",
                    unsafe_allow_html=True,
                )
                st.caption(f"Evidence: {item['evidence_id']}")

    st.markdown("#### 板块涨幅")
    sectors = hotspots["sections"]["hot_sectors"]["items"]
    if sectors:
        sdf = pd.DataFrame(sectors)
        fig = px.bar(
            sdf, x="sector_name", y="pct_change", color="pct_change",
            color_continuous_scale=["#1c9a82", "#c9d3e0", "#c0392b"],
            custom_data=["sector_type", "leading_stock", "net_inflow_yi", "evidence_id"],
        )
        fig.update_traces(hovertemplate=(
            "板块: %{x}<br>涨幅: %{y:.2f}%<br>类型: %{customdata[0]}<br>领涨: %{customdata[1]}"
            "<br>净流入: %{customdata[2]:.1f}亿<br>Evidence: %{customdata[3]}<extra></extra>"))
        fig.update_layout(height=360, paper_bgcolor="#fff", plot_bgcolor="#fff",
                          margin=dict(l=15, r=15, t=30, b=80), yaxis_title="%", xaxis_title="")
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, width="stretch", key=f"dr_sector_{snapshot_id}")
    else:
        st.info("板块数据未覆盖。")

    left, right = st.columns(2)
    with left:
        st.markdown("#### 连板天梯")
        ladder = panorama["sections"]["stock_dynamics"]["ladder"]
        if ladder:
            ldf = pd.DataFrame(ladder)[["name", "board_days", "close", "pct_change", "limit_order_yi", "logic"]]
            st.dataframe(ldf, width="stretch", hide_index=True,
                         column_config={"name": "名称", "board_days": "连板", "close": st.column_config.NumberColumn("价", format="%.2f"),
                                        "pct_change": "涨%", "limit_order_yi": "封单(亿)", "logic": "逻辑"})
        else:
            st.info("涨停天梯未覆盖。")
        st.markdown("#### 主力净流入 TOP")
        inflow = hotspots["sections"]["top_net_inflow"]["items"]
        if inflow:
            idf = pd.DataFrame(inflow)
            st.dataframe(idf, width="stretch", hide_index=True,
                         column_config={"name": "名称", "net_inflow_yi": st.column_config.NumberColumn("净流入(亿)", format="%.1f"),
                                        "main_inflow_yi": "主买(亿)", "evidence_id": "Evidence"})
        else:
            st.info("主力净流入未覆盖。")
    with right:
        st.markdown("#### 全景复盘结论")
        st.write(panorama["sections"]["index_closing"]["summary"])
        chars = panorama["sections"]["market_characteristics"]
        if chars.get("up_ratio_percent") is not None:
            st.write(
                f"红盘占比 **{chars['up_ratio_percent']}%**，涨跌家数 {chars['up_count']}/{chars['down_count']}，"
                f"涨停 {chars['limit_up_count']} / 跌停 {chars['limit_down_count']}，成交额 {chars['total_amount_yi']:.0f} 亿。"
            )
        dev = panorama["sections"]["deviation_review"]
        if dev.get("supported"):
            st.write(dev["observation"])
        st.caption("次日推演 / 宏观快照：离线快照未覆盖，不输出确定性预测。")
        st.markdown("#### 热点题材")
        for theme in panorama["sections"]["core_drivers"]["themes"]:
            with st.container(border=True):
                st.markdown(f"**{theme['theme_name']}**")
                if theme.get("ai_generated") and theme.get("ai_summary"):
                    st.markdown(f"{theme['ai_summary']}  `AI 润色`")
                    with st.popover("查看原始新闻"):
                        st.write(theme["driver"])
                        links = theme.get("news_links") or []
                        if links:
                            st.markdown("来源：" + "  ".join(f"[链接]({u})" for u in links if u))
                else:
                    st.write(theme["driver"])
                st.caption("相关：" + "、".join(theme["related_stocks"]) + f" · {theme['evidence_id']}")

    with st.expander("证据抽屉 · Evidence", expanded=False):
        recs = panorama.get("evidence_records", [])
        if recs:
            rdf = pd.DataFrame([
                {"Evidence ID": r["evidence_id"], "指标": r["metric"], "数值": r["value"],
                 "单位": r["unit"], "期间": r.get("period"), "来源": r["source"]}
                for r in recs
            ])
            st.dataframe(rdf, width="stretch", hide_index=True, height=360,
                         column_config={"Evidence ID": "Evidence ID",
                                        "数值": st.column_config.NumberColumn("数值", format="%.4f")})
            export = {"snapshot_id": snapshot_id, "research_as_of": panorama["research_as_of"],
                      "validation": panorama["validation"], "evidence_records": recs}
            st.download_button("下载全部证据（JSON）", json.dumps(export, ensure_ascii=False, indent=2),
                               f"{snapshot_id}_evidence.json", "application/json", icon=":material/download:")
        else:
            st.info("该快照暂无可导出数值证据。")


def main() -> None:
    style()
    if not service_contract_ready():
        return
    catalog = service.list_research()
    with st.sidebar:
        st.markdown('<div class="brand">◈ FINTRACE / CN</div>', unsafe_allow_html=True)
        choices = {f"{item['name']} · {item['symbol']}": item["id"] for item in catalog}
        selected_label = st.selectbox("研究快照", list(choices), key="snapshot_picker")
        page = st.radio("工作台", NAVIGATION, label_visibility="collapsed", key="workbench_page")
        st.divider()
        st.caption("RESEARCH TERMINAL v0.2\n\n多快照 · 只读工作台")
    if page == "案例演示":
        demo_cases(catalog)
        return
    if page == "每日复盘":
        daily_review()
        return
    snapshot, metadata = load_research(choices[selected_label])
    header(snapshot, metadata)
    {"研究总览": lambda: overview(snapshot, metadata), "市场与行情": lambda: market(snapshot), "财务表现": lambda: financials(snapshot), "同行估值": lambda: valuation_safe(snapshot, metadata), "证据与校验": lambda: evidence(snapshot, metadata), "Agent 执行轨迹": lambda: trace(snapshot), "研究报告": lambda: report(snapshot), "研究任务": tasks, "评测与消融": evaluations}[page]()


if __name__ == "__main__":
    main()
