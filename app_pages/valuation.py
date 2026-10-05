"""估值页（UI_REDESIGN_PLAN_V2 §5.3，对齐设计稿图3）。

顶部行情条（RAW 口径）+ 六个 Tab；相对估值为主视图：
情景切换 → 敏感性热力矩阵 → 估值区间条 → 假设注册表 → 投资逻辑脆弱性（P2-2 交互拖拽版）→ 跟踪计划。
矩阵与区间仅为服务层倍数的确定性换算可视化；Validator 阻断时隐藏隐含价格。
"""

import json

import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from ui.charts import financial_trends
from ui.chips import chip_row, evidence_chip
from ui.layout import section
from ui.status import callout
from ui.theme import TOKENS


SCENARIOS = {"Bear（悲观）": "bear", "Base（基准）": "base", "Bull（乐观）": "bull"}


def _fmt_multiple(value) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}×"
    return str(value) if value not in (None, "") else "未覆盖"


def _fmt_price(value) -> str:
    if isinstance(value, (int, float)):
        return f"¥{value:.2f}"
    return str(value) if value not in (None, "") else "未覆盖"


def _up_down(change: float | None) -> tuple[str, str]:
    if change is None:
        return "—", "#627D98"
    color = TOKENS["red_up"] if change >= 0 else TOKENS["green_down"]
    arrow = "▲" if change >= 0 else "▼"
    return f"{arrow} {abs(change):.2f}%", color


def _quote_bar(item: dict, summary: dict) -> tuple[str, float | None]:
    """顶部行情条：公司/代码、最新价（涨红跌绿）、总市值、PE、PB、ROE。"""
    profile = summary.get("profile") or {}
    metrics = summary.get("key_metrics") or {}
    market = loader.market(item["id"], "RAW")
    bars = sorted(
        (row for row in market.get("bars", []) if row.get("close") is not None),
        key=lambda row: row.get("trade_date") or "",
    )
    price = metrics.get("price")
    change = None
    if len(bars) >= 2 and bars[-2].get("close"):
        change = (bars[-1]["close"] / bars[-2]["close"] - 1) * 100
    pct, color = _up_down(change)
    name = profile.get("name") or item.get("name") or "未命名公司"
    symbol = summary.get("symbol") or item.get("symbol") or "—"

    def _cell(label: str, value: str, extra: str = "", color: str = "#172B4D") -> str:
        return (
            f"<div style='min-width:96px'><div style='font-size:.72rem;color:#627D98'>{label}</div>"
            f"<div style='font-size:1.05rem;font-weight:700;color:{color};"
            f"font-variant-numeric:tabular-nums'>{value}</div>"
            f"{f'<div style=\"font-size:.72rem;color:{color}\">{extra}</div>' if extra else ''}</div>"
        )

    market_cap = metrics.get("market_cap")
    book_equity = metrics.get("book_equity")
    ttm_profit = metrics.get("ttm_net_profit")
    pe = metrics.get("pe_ttm")
    pb = (market_cap / book_equity) if market_cap and book_equity else None
    roe = (ttm_profit / book_equity * 100) if ttm_profit and book_equity and book_equity > 0 else None

    cells = "".join([
        _cell(f"{name} {symbol}", "RAW 口径", "离线快照 · 非实时行情", "#172B4D"),
        _cell("最新价", f"¥ {price:,.2f}" if price is not None else "未覆盖", pct, color),
        _cell("总市值", f"{market_cap / 1e8:,.0f} 亿元" if market_cap else "未覆盖"),
        _cell("PE (TTM)", f"{pe:.2f}×" if pe else "未覆盖"),
        _cell("PB (LF)", f"{pb:.2f}×" if pb else "未覆盖"),
        _cell("ROE (TTM)", f"{roe:.1f}%" if roe else "未覆盖"),
    ])
    st.markdown(
        f"<div style='display:flex;gap:1.6rem;flex-wrap:wrap;align-items:center;"
        f"background:#FFFFFF;border:1px solid {TOKENS['border']};border-radius:12px;"
        f"padding:.7rem 1rem'>{cells}</div>",
        unsafe_allow_html=True,
    )
    st.caption("最新价与涨跌来自快照 RAW bars；总市值 / PE 为服务层确定性计算；PB、ROE 为快照字段的确定性换算。")
    return symbol, price


def _sensitivity_heatmap(result: dict, summary: dict, *, allowed: bool, metric_name: str) -> None:
    """PE × EPS → 隐含价格热力矩阵（确定性换算，仅可视化同行估值输入）。"""
    import pandas as pd
    import plotly.graph_objects as go

    from ui.theme import TOKENS as T

    multiple = (result.get("multiples") or {}).get(metric_name) or {}
    median = multiple.get("median")
    metrics = summary.get("key_metrics") or {}
    shares = metrics.get("total_shares")
    ttm_profit = metrics.get("ttm_net_profit")
    if not allowed or median is None or not shares or not ttm_profit or shares <= 0:
        st.info("敏感性矩阵未覆盖：缺少同行中位数或股本/TTM 利润输入，或 Validator 已阻断。")
        return
    eps = ttm_profit / shares
    if eps <= 0:
        st.info("TTM 每股收益非正，敏感性矩阵不适用（不生成替代数字）。")
        return
    pes = [median * f for f in (0.8, 0.9, 1.0, 1.1, 1.2)]
    epss = [eps * f for f in (0.8, 0.9, 1.0, 1.1, 1.2)]
    matrix = [[pe * eps_value for eps_value in epss] for pe in pes]
    frame = pd.DataFrame(matrix, index=[f"{p:.2f}×" for p in pes], columns=[f"{e:.2f}" for e in epss])
    fig = go.Figure(go.Heatmap(
        z=frame.values, x=list(frame.columns), y=list(frame.index),
        colorscale=[[0, "#E8F1FB"], [0.5, "#7FA8E0"], [1, TOKENS["blue"]]],
        hovertemplate="PE %{y} × EPS %{x} 元<br>隐含价格 %{z:.2f} 元<extra></extra>",
    ))
    fig.update_layout(
        height=300, margin=dict(l=8, r=8, t=36, b=8),
        title=f"{metric_name} × EPS 敏感性（隐含价格，元/股；中心格为基准）",
        xaxis_title="EPS（元）", yaxis_title="倍数",
    )
    fig.add_annotation(x=f"{epss[2]:.2f}", y=f"{pes[2]:.2f}×", text="基准", showarrow=True, arrowhead=2)
    st.plotly_chart(fig, width="stretch", key=f"heatmap_{metric_name}", config={"displayModeBar": False})
    st.caption("矩阵为服务层倍数与 TTM EPS 的确定性换算情景，仅用于展示敏感度，不构成预测或目标价。")


def _range_bar(result: dict, price: float | None, scenario_key: str, metric_name: str, *, allowed: bool) -> None:
    """估值区间条：三档隐含价格 + 当前 RAW 价格标记，情景高亮。"""
    import plotly.graph_objects as go

    from ui.theme import TOKENS as T

    interval = (result.get("valuation_ranges") or {}).get(metric_name) or {}
    low = interval.get("implied_price_low") if allowed else None
    median = interval.get("implied_price_median") if allowed else None
    high = interval.get("implied_price_high") if allowed else None
    marks = [
        ("Bear 区间下限", low, T["muted"]),
        ("Base 中位数", median, T["blue"]),
        ("Bull 区间上限", high, T["green"]),
    ]
    highlights = {"bear": ("Bear 区间下限", T["coral"]), "base": ("Base 中位数", T["blue"]), "bull": ("Bull 区间上限", T["green"])}
    highlight_name, highlight_color = highlights.get(scenario_key, ("Base 中位数", T["blue"]))
    values = [value for _, value, _ in marks if value is not None]
    axis_values = values + ([price] if price is not None else [])
    if not axis_values:
        st.info("隐含价格区间未覆盖：Validator 已阻断或输入不足。")
        return
    x_min, x_max = min(axis_values), max(axis_values)
    pad = max((x_max - x_min) * 0.15, x_max * 0.02, 0.01)
    fig = go.Figure()
    if low is not None and high is not None:
        fig.add_shape(type="line", x0=low, x1=high, y0=0, y1=0, line=dict(color="#D5DEE8", width=8))
    for label, value, color in marks:
        if value is None:
            continue
        is_highlight = label == highlight_name
        fig.add_trace(go.Scatter(
            x=[value], y=[0], mode="markers+text",
            marker=dict(size=16 if is_highlight else 12, color=highlight_color if is_highlight else color),
            text=[f"{label}<br>{_fmt_price(value)}"], textposition="top center", textfont=dict(size=11),
            hovertemplate=f"{label}: ¥%{{x:.2f}}<extra></extra>",
        ))
    if price is not None:
        fig.add_vline(x=price, line=dict(color=T["coral"], dash="dot", width=2),
                      annotation_text=f"当前 RAW 价格 ¥{price:.2f}")
    fig.update_layout(
        height=190, margin=dict(l=10, r=10, t=14, b=30),
        xaxis=dict(range=[x_min - pad, x_max + pad], visible=False),
        yaxis=dict(visible=False), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch", key=f"range_bar_{metric_name}", config={"displayModeBar": False})


def _fragility_svg(rows: list[dict], conclusion_risk: str) -> None:
    """投资逻辑脆弱性（P2-2 交互版）：假设卡片可拖拽，箭头自动跟随。"""
    payload = json.dumps({"rows": rows, "conclusion_risk": conclusion_risk}, ensure_ascii=False)
    html = f"""
<div id="ft-frag" style="border:1px solid #E5EAF0;border-radius:12px;background:#FFFFFF;padding:6px">
  <svg id="ft-frag-svg" width="100%" height="250" xmlns="http://www.w3.org/2000/svg"></svg>
  <div style="font-size:.74rem;color:#627D98;padding:2px 8px 6px">
    拖拽假设卡片或结论节点调整布局；箭头连线自动跟随。风险徽章：<span style="color:#D9534F">■ 高</span>
    <span style="color:#D99400">■ 中</span> <span style="color:#159570">■ 低</span></div>
</div>
<script>
(function () {{
  const DATA = {payload};
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const svg = document.getElementById('ft-frag-svg');
  const CARD_W = 150, CARD_H = 46;
  const width = svg.clientWidth || 800, height = 250;
  const RISK_COLOR = {{ '高': '#D9534F', '中': '#D99400' }};
  const nodes = [];

  function el(name, attrs, parent) {{
    const node = document.createElementNS(SVG_NS, name);
    for (const key in attrs) node.setAttribute(key, attrs[key]);
    (parent || svg).appendChild(node);
    return node;
  }}
  function riskColor(level) {{ return RISK_COLOR[level] || '#159570'; }}

  const n = DATA.rows.length;
  const startY = (height - n * (CARD_H + 16)) / 2 + 8;
  DATA.rows.forEach(function (row, index) {{
    nodes.push({{
      id: 'a' + index, label: row.label, value: row.value, risk: row.risk,
      x: 16, y: startY + index * (CARD_H + 16), kind: 'assumption',
    }});
  }});
  nodes.push({{
    id: 'conclusion', label: '估值结论', value: '投资结论节点', risk: DATA.conclusion_risk,
    x: Math.max(width - CARD_W - 24, CARD_W + 160), y: height / 2 - CARD_H / 2, kind: 'conclusion',
  }});

  const edgesGroup = el('g', {{}});
  const nodesGroup = el('g', {{}});

  function anchorRight(node) {{ return {{ x: node.x + CARD_W, y: node.y + CARD_H / 2 }}; }}
  function anchorLeft(node) {{ return {{ x: node.x, y: node.y + CARD_H / 2 }}; }}

  function drawEdges() {{
    edgesGroup.innerHTML = '';
    nodes.forEach(function (node) {{
      if (node.kind !== 'assumption') return;
      const from = anchorRight(node);
      const to = anchorLeft(nodes.find(item => item.id === 'conclusion'));
      const path = el('path', {{
        d: 'M ' + from.x + ' ' + from.y +
           ' C ' + (from.x + 60) + ' ' + from.y + ', ' + (to.x - 60) + ' ' + to.y + ', ' + (to.x - 8) + ' ' + to.y,
        fill: 'none', stroke: '#B8C4D0', 'stroke-width': 1.6,
      }}, edgesGroup);
      const arrow = el('path', {{
        d: 'M ' + (to.x - 6) + ' ' + to.y + ' l -9 -4.5 v 9 z', fill: '#B8C4D0',
      }}, edgesGroup);
      path.dataset.to = '1'; arrow.dataset.to = '1';
    }});
  }}

  function drawNodes() {{
    nodesGroup.innerHTML = '';
    nodes.forEach(function (node) {{
      const g = el('g', {{ 'data-node': node.id, style: 'cursor:move' }}, nodesGroup);
      const color = riskColor(node.risk);
      el('rect', {{
        x: node.x, y: node.y, width: CARD_W, height: CARD_H, rx: 10,
        fill: node.kind === 'conclusion' ? 'rgba(31,111,235,.08)' : '#FFFFFF',
        stroke: node.kind === 'conclusion' ? color : '#E5EAF0', 'stroke-width': 1.4,
      }}, g);
      const label = el('text', {{
        x: node.kind === 'conclusion' ? node.x + CARD_W / 2 : node.x + 12,
        y: node.y + 19, 'font-size': 11, 'font-weight': 700, fill: '#172B4D',
        'text-anchor': node.kind === 'conclusion' ? 'middle' : 'start',
      }}, g);
      label.textContent = node.label;
      const value = el('text', {{
        x: node.kind === 'conclusion' ? node.x + CARD_W / 2 : node.x + 12,
        y: node.y + 36, 'font-size': 11, fill: '#627D98',
        'text-anchor': node.kind === 'conclusion' ? 'middle' : 'start',
      }}, g);
      value.textContent = node.value;
      el('circle', {{ cx: node.x + CARD_W - 14, cy: node.y + CARD_H / 2, r: 8, fill: color }}, g);
      const badge = el('text', {{
        x: node.x + CARD_W - 14, y: node.y + CARD_H / 2 + 3.5, 'font-size': 9,
        fill: '#fff', 'text-anchor': 'middle',
      }}, g);
      badge.textContent = node.risk;
      g.addEventListener('pointerdown', function (event) {{
        event.preventDefault();
        const startX = event.clientX, startY = event.clientY;
        const originX = node.x, originY = node.y;
        function onMove(moveEvent) {{
          node.x = Math.max(4, Math.min(width - CARD_W - 4, originX + moveEvent.clientX - startX));
          node.y = Math.max(4, Math.min(height - CARD_H - 4, originY + moveEvent.clientY - startY));
          drawEdges(); drawNodes();
        }}
        function onUp() {{
          window.removeEventListener('pointermove', onMove);
          window.removeEventListener('pointerup', onUp);
        }}
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
      }});
    }});
  }}

  function render() {{
    drawEdges(); drawNodes();
  }}
  render();
  window.addEventListener('resize', render);
}})();
</script>
"""
    st.html(html)


item, summary, validation = context_or_empty(
    "估值分析", "相对估值为主视图：情景、敏感性、假设注册表与跟踪计划；阻断时隐藏隐含价格。"
)
if item and summary:
    sid = item["id"]
    result = loader.valuation(sid)
    allowed = bool(result.get("conclusion_allowed"))
    price = (summary.get("key_metrics") or {}).get("price")

    _quote_bar(item, summary)

    tabs = st.tabs(["投资要点", "相对估值", "绝对估值", "财务分析", "风险提示", "研报与数据"])
    with tabs[0]:
        insights = loader.overview_insights(sid)
        if insights.get("revenue_change_percent") is None:
            st.info("可比年度数据不足，暂不作业绩趋势判断。")
        else:
            status_label = {"improving": "改善", "under_pressure": "承压", "diverging": "分化"}.get(
                insights.get("performance_status"), "数据不足"
            )
            st.markdown(
                f"**业绩状态：{status_label}** — 最近可比年度营收变化 "
                f"**{insights['revenue_change_percent']:+.1f}%**，归母净利润变化 "
                f"**{insights['net_profit_change_percent']:+.1f}%**。这是已披露业绩变化，不是预测。"
            )
        if not allowed:
            callout("blocked", "Validator 已阻断估值输出；隐含价格与目标价已隐藏。")

    with tabs[1]:
        if result.get("available") is False:
            st.warning("同业覆盖不足或关键输入缺失；页面只展示缺口，不生成目标价。", icon=":material/block:")
        else:
            if not allowed:
                callout("blocked", f"Validator 已阻断估值输出：{result.get('gated_reason') or '关键证据缺失'}。")
            multiples = result.get("multiples", {})
            default_metric = next(iter(multiples), None)
            scenario_label = st.segmented_control(
                "情景切换", list(SCENARIOS), default="Base（基准）", key="valuation_scenario"
            )
            scenario_key = SCENARIOS.get(scenario_label or "Base（基准）", "base")
            metric_name = st.selectbox(
                "估值倍数", list(multiples), index=0 if default_metric else None,
                key="valuation_metric", disabled=not multiples,
            )
            if multiples and metric_name:
                metric_data = multiples[metric_name]
                cols = st.columns(4)
                target = metric_data.get("target_multiple")
                cols[0].metric("目标公司", f"{target:.2f}×" if target is not None else "未覆盖")
                cols[1].metric("同行中位数", f"{metric_data.get('median'):.2f}×" if metric_data.get("median") is not None else "未覆盖")
                interval = (result.get("valuation_ranges") or {}).get(metric_name, {})
                p25, p75 = interval.get("p25"), interval.get("p75")
                cols[2].metric("同行区间 P25–P75", f"{p25:.2f}–{p75:.2f}×" if p25 is not None and p75 is not None else "未覆盖")
                confidence_label = {"high": "高", "medium": "中", "low": "低", "unavailable": "不可用"}.get(metric_data.get("confidence"), "未测量")
                cols[3].metric("样本置信度", confidence_label)
                section("敏感性热力矩阵")
                _sensitivity_heatmap(result, summary, allowed=allowed, metric_name=metric_name)
                section("估值区间条")
                _range_bar(result, price, scenario_key, metric_name, allowed=allowed)
                if allowed:
                    st.caption("情景仅切换高亮档位：Bear=区间下限、Base=中位数、Bull=区间上限；当前价格为快照 RAW 收盘价。")
                section("假设注册表")
                formulas = result.get("formulas") or {}
                if formulas:
                    registry = []
                    interval_data = (result.get("valuation_ranges") or {}).get(metric_name, {})
                    metric_multiple = multiples.get(metric_name) or {}
                    for name, formula in formulas.items():
                        # formulas 中的 target_multiple 是公式表达式；基准值用服务层算得的数值倍数。
                        base_value = metric_multiple.get("target_multiple") if name == metric_name else formula.get("target_multiple")
                        registry.append({
                            "关键假设": f"{name} 同业中位数口径",
                            "基准值": _fmt_multiple(base_value),
                            "区间范围": (
                                f"{interval_data.get('p25'):.2f}–{interval_data.get('p75'):.2f}×"
                                if isinstance(interval_data.get("p25"), (int, float)) and isinstance(interval_data.get("p75"), (int, float)) else "未覆盖"
                            ),
                            "数据来源": "同行快照 · " + ", ".join(formula.get("peer_input_evidence_ids", [])[:2]),
                            "验证状态": result.get("validation_status") or "未覆盖",
                        })
                    st.dataframe(registry, hide_index=True, width="stretch", key="assumption_registry")
                    st.caption("数据来源列的完整证据编号可在文档与证据页或审计回放查看。")
                else:
                    st.info("暂无可注册的估值假设。")
                section("投资逻辑脆弱性", hint="可拖拽调整布局")
                metrics = summary.get("key_metrics") or {}
                freshness = next((check for check in (validation or {}).get("checks", []) if check.get("code") == "snapshot_freshness"), {})
                fragility_rows = [
                    {"label": "同业中位数", "value": _fmt_multiple(multiples.get(metric_name, {}).get("median")), "risk": "高" if not allowed else "中"},
                    {"label": "TTM 净利润", "value": f"{(metrics.get('ttm_net_profit') or 0) / 1e8:,.0f} 亿" if metrics.get("ttm_net_profit") else "未覆盖", "risk": "中" if metrics.get("ttm_net_profit") else "高"},
                    {"label": "总股本", "value": "已披露" if metrics.get("total_shares") else "未覆盖", "risk": "低" if metrics.get("total_shares") else "高"},
                    {"label": "快照时效", "value": str(freshness.get("detail") or "未覆盖"), "risk": "中" if freshness.get("status") == "warning" else "低"},
                ]
                conclusion_risk = "高" if not allowed else ("中" if (validation or {}).get("warnings") else "低")
                _fragility_svg(fragility_rows, conclusion_risk)
                section("跟踪计划")
                with st.container(border=True):
                    plan = st.columns(4)
                    plan[0].markdown("**可跟踪指标**\n\n季度营收、归母净利润、同业中位数变化")
                    plan[1].markdown("**触发条件**\n\n最新财报同比变化超过 ±10%，或验证状态变为阻断")
                    plan[2].markdown("**影响的论断**\n\n" + "、".join(formulas.keys() or ["当前估值倍数"]))
                    plan[3].markdown("**重新验证**\n\n重新运行受控研究并在研判核查页复核声明")
            else:
                st.info("当前快照没有可用的估值倍数输入。")

    with tabs[2]:
        st.caption("绝对估值（DCF 等）在当前版本不提供；系统不会用推测输入生成目标价。")
        peer = result
        if peer.get("method_boundary") == "financial_institution_pe_pb_only":
            callout("warning", "金融机构不适用通用企业估值框架；当前仅展示 PE/PB。")

    with tabs[3]:
        trends = loader.trends(sid, "FY")
        financial_trends(trends.get("points", []), key=f"valuation_financial_{sid}")
        st.page_link("app_pages/financial_analysis.py", label="前往财务分析页查看完整口径 →", icon=":material/analytics:")

    with tabs[4]:
        warnings = [check for check in (validation or {}).get("checks", []) if check.get("status") != "pass"]
        if not warnings:
            callout("verified", "当前没有需要关注的风险项。")
        for check in warnings:
            callout(check.get("status"), f"{check.get('label')}：{check.get('detail')} · 处理：{check.get('remediation')}")

    with tabs[5]:
        report_state = loader.report(sid)
        if report_state.get("available"):
            st.markdown(f"研究报告《{report_state.get('filename') or '投资备忘录'}》已生成，可在投资备忘录页查看。")
            st.page_link("app_pages/memo.py", label="打开投资备忘录 →", icon=":material/description:")
        else:
            st.caption("该快照尚未生成研究备忘录。")
        chip_row([f"价格口径 {result.get('price_basis') or 'RAW'}", f"期间口径 {result.get('period_basis') or 'TTM'}", f"验证状态 {result.get('validation_status') or '未覆盖'}"])
