"""研究总览（UI_REDESIGN_PLAN_V2 §5.1，对齐设计稿图1）。

一屏卡片化布局：进度 stepper → 右列健康度 donut + 证据完整度 →
中列财务指标卡 ×3 → 最近研究任务 → 底部三卡（关键结论 / 主要证据来源 / 风险与关注点）。
所有数值来自服务层；证据 ID 收进芯片悬浮与展开区，不在明面直出。
"""

import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from src.cn import workbench_service as service
from ui.charts import conclusion_health_donut, mini_bar
from ui.chips import evidence_chip
from ui.layout import section
from ui.stepper import stepper
from ui.status import callout
from ui.theme import TOKENS

MUTED = TOKENS["muted"]
TEXT = TOKENS["text"]


def _card_head(title: str, color: str, *, hint: str = "", action: str = "", action_path: str = "") -> None:
    """卡片头：彩色小方标 + 加粗标题 + 右侧说明/跳转箭头（对齐设计稿卡片头）。"""
    hint_html = f"<span style='color:{MUTED};font-weight:500;font-size:.74rem;margin-left:.4rem'>{hint}</span>" if hint else ""
    arrow = "<span style='margin-left:auto;color:#B8C4D0;font-weight:700'>›</span>"
    if action and action_path:
        arrow = f"<span style='margin-left:auto'><a class='ft-section-link' href='#{action_path}'>{action}</a></span>"
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:.45rem;margin-bottom:.5rem'>"
        f"<span style='width:20px;height:20px;border-radius:6px;background:{color}1A;color:{color};"
        f"display:inline-flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:800'>▣</span>"
        f"<span style='font-weight:800;font-size:.92rem;color:{TEXT}'>{title}</span>{hint_html}{arrow}</div>",
        unsafe_allow_html=True,
    )


def _list_row(icon: str, icon_color: str, text: str, count: str = "") -> str:
    count_html = f"<span class='ft-list-count'>{count}</span>" if count else ""
    return (
        f"<div class='ft-list-row'><span style='color:{icon_color};font-weight:800;flex:none'>{icon}</span>"
        f"<span style='color:{TEXT}'>{text}</span>{count_html}</div>"
    )


def _yoy_fragment(change: float | None) -> str:
    if change is None:
        return f"<span style='color:{MUTED};font-size:.8rem'>同比未覆盖</span>"
    color = TOKENS["red_up"] if change >= 0 else TOKENS["green_down"]
    arrow = "▲" if change >= 0 else "▼"
    return f"<span style='color:{color};font-weight:800;font-variant-numeric:tabular-nums'>{arrow} {abs(change):.1f}%</span>"


def _financial_series(points: list[dict], field: str, *, last: int = 5) -> dict[str, float]:
    """近 N 期服务层数值（亿元），按期间升序取尾部。"""
    rows = sorted(
        (point for point in points if point.get(field) is not None),
        key=lambda point: point.get("fiscal_period") or "",
    )[-last:]
    return {row.get("fiscal_period") or "—": float(row[field]) / 1e8 for row in rows}


def _cash_flow_series(statements: list[dict], *, last: int = 5) -> dict[str, float]:
    rows = sorted(
        (
            item for item in statements
            if item.get("available_as_of") and (item.get("values") or {}).get("operating_cash_flow") is not None
        ),
        key=lambda item: item.get("fiscal_period") or "",
    )
    annual = [item for item in rows if str(item.get("fiscal_period", "")).endswith("FY")] or rows
    return {
        item.get("fiscal_period") or "—": float(item["values"]["operating_cash_flow"]) / 1e8
        for item in annual[-last:]
    }


def _cash_flow_yoy(statements: list[dict]) -> float | None:
    rows = list(_cash_flow_series(statements, last=2).items())
    if len(rows) < 2 or not rows[0][1]:
        return None
    return (rows[1][1] / rows[0][1] - 1) * 100


item, summary, validation = context_or_empty(
    "研究总览", "基于公开信息的多源证据验证；一屏查看研究进度、结论健康度与下一步需要核查的内容。"
)
if item and summary:
    sid = item["id"]
    records = loader.evidence(sid).get("records", [])
    financials = loader.financials(sid)
    trends = loader.trends(sid, "FY")
    valuation = loader.valuation(sid)
    insights = loader.overview_insights(sid)
    allowed = bool((validation or {}).get("conclusion_allowed"))
    warnings = [check for check in (validation or {}).get("checks", []) if check.get("status") != "pass"]

    # 2. 研究进度卡（横向 stepper）
    claims = st.session_state.get("checker_claims", [])
    report_state = loader.report(sid)
    steps = [
        {"label": "文档已登记", "status": "verified" if records else "unknown", "detail": "快照就绪" if records else "等待快照", "count": 1 if records else 0},
        {"label": "解析完成", "status": "verified" if financials.get("statements") else "unknown", "detail": "披露期间", "count": len(financials.get("statements", []))},
        {"label": "证据提取", "status": "verified" if records else "unknown", "detail": "条证据", "count": len(records)},
        {"label": "财务分析", "status": "verified" if trends.get("points") else "unknown", "detail": "可比期间", "count": len([p for p in trends.get("points", []) if p.get("revenue") is not None])},
        {"label": "研判核查", "status": "verified" if claims else ("warning" if allowed else "blocked"), "detail": "已核查声明", "count": len(claims)},
        {"label": "估值", "status": "verified" if valuation.get("available") and allowed else ("warning" if valuation.get("available") else "unknown"), "detail": "家同行", "count": valuation.get("peer_count", 0)},
        {"label": "备忘录", "status": "verified" if report_state.get("available") else "unknown", "detail": "报告" if report_state.get("available") else "等待结论", "count": 1 if report_state.get("available") else 0},
    ]
    stepper(steps, key=f"overview_stepper_{sid}")

    # 3/4. 右列：结论健康度卡 + 证据完整度卡；中列：财务指标卡 ×3
    verified_count = sum(1 for x in records if x.get("status") == "verified")
    warning_count = len((validation or {}).get("warnings", []))
    blocked_count = len((validation or {}).get("blocked", []))

    top_left, top_right = st.columns([1.7, 1])
    with top_left:
        section("关键财务指标", hint="已披露数据 · 单位：亿元")
        points = trends.get("points", [])
        statements = financials.get("statements", [])
        latest_period = insights.get("latest_period")
        evidence_ids_by_period = {p.get("fiscal_period"): p.get("evidence_ids") or {} for p in points}
        latest_ids = evidence_ids_by_period.get(latest_period) or {}
        cf_series = _cash_flow_series(statements)
        cf_latest_period = next(iter(reversed(cf_series)), None) if cf_series else None
        cf_evidence = ""
        for row in statements:
            if row.get("fiscal_period") == cf_latest_period and (row.get("evidence_ids") or {}).get("operating_cash_flow"):
                cf_evidence = row["evidence_ids"]["operating_cash_flow"]
        cards = [
            ("营业收入（亿元）", latest_period, insights.get("revenue_change_percent"), _financial_series(points, "revenue"), latest_ids.get("revenue"), TOKENS["blue"]),
            ("归母净利润（亿元）", latest_period, insights.get("net_profit_change_percent"), _financial_series(points, "net_profit"), latest_ids.get("net_profit"), TOKENS["green"]),
            ("经营活动现金流（亿元）", cf_latest_period, _cash_flow_yoy(statements), cf_series, cf_evidence, TOKENS["amber"]),
        ]
        card_cols = st.columns(3)
        for col, (label, period, change, series, evidence_id, color) in zip(card_cols, cards):
            with col:
                with st.container(border=True):
                    _card_head(label, color)
                    latest_value = list(series.values())[-1] if series else None
                    if latest_value is None:
                        st.markdown(f"<div style='font-size:1.5rem;font-weight:800;color:{MUTED}'>未覆盖</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(
                            f"<div style='font-size:1.55rem;font-weight:800;font-variant-numeric:tabular-nums;"
                            f"letter-spacing:-.02em;color:{TEXT}'>{latest_value:,.1f}</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        _yoy_fragment(change)
                        + f" <span style='color:{MUTED};font-size:.74rem'>同比增速（{period or '期间未覆盖'}）</span>",
                        unsafe_allow_html=True,
                    )
                    mini_bar(series, key=f"overview_mini_{label}_{sid}", color=color)
                    evidence_chip(evidence_id, "年报证据" if evidence_id else "", detail={"证据编号": evidence_id} if evidence_id else None)
    with top_right:
        with st.container(border=True):
            _card_head("结论健康度", TOKENS["green"], hint="查看核查结果 →")
            conclusion_health_donut(verified_count, warning_count, blocked_count, key=f"overview_donut_{sid}")
        with st.container(border=True):
            _card_head("证据完整度", TOKENS["blue"])
            total_records = len(records)
            if total_records:
                st.progress(verified_count / total_records, text=f"已匹配 {verified_count} / {total_records} 条证据")
                st.caption(f"已匹配 {verified_count:,} 条证据（来自 {len(set(str(x.get('provider')) for x in records))} 个来源）")
            else:
                st.caption("暂无证据记录。")

    # 6. 最近的研究任务卡
    with st.container(border=True):
        try:
            evaluations = service.list_evaluations()
        except Exception:
            evaluations = []
        uploaded = st.session_state.get("task_uploaded_documents", [])
        head_l, head_r = st.columns([3, 1])
        with head_l:
            _card_head("最近的研究任务", TOKENS["blue"])
        with head_r:
            st.markdown(
                f"<div style='text-align:right;padding-top:.2rem'>"
                f"<a class='ft-section-link' href='#research_tasks'>查看任务详情 →</a></div>",
                unsafe_allow_html=True,
            )
        if evaluations:
            recent = evaluations[0]
            name = (summary.get("profile") or {}).get("name") or item.get("name") or "未命名公司"
            symbol = summary.get("symbol") or item.get("symbol") or "—"
            st.markdown(
                f"<div class='ft-list-row'><b style='color:{TEXT}'>{name}</b>"
                f"<span style='color:{MUTED}'>{symbol}</span>"
                f"<span style='margin-left:auto;background:rgba(21,149,112,.12);color:{TOKENS['green']};"
                f"border-radius:9999px;padding:.1rem .6rem;font-size:.74rem;font-weight:700'>● 可验证</span></div>",
                unsafe_allow_html=True,
            )
            meta = st.columns(5)
            meta[0].metric("类型", recent.get("kind") or "未记录")
            meta[1].metric("运行时间", str(recent.get("run_at") or "未记录")[:16])
            meta[2].metric("登记文档", len(uploaded))
            meta[3].metric("提取证据", len(records))
            meta[4].metric("产物版本", str(recent.get("benchmark_version") or "未记录")[:18])
        else:
            st.caption("尚无已落盘的评测/任务产物；系统不会用占位数字代替。")

    # 7. 底部三卡
    bottom_left, bottom_center, bottom_right = st.columns(3)
    with bottom_left:
        with st.container(border=True):
            _card_head("关键结论", TOKENS["green"], hint="（选）")
            if not allowed:
                callout("blocked", "Validator 已阻断确定性结论；页面隐藏推测性估值与报告结论。")
            else:
                status_label = {"improving": "改善", "under_pressure": "承压", "diverging": "分化"}.get(
                    insights.get("performance_status"), "数据不足"
                )
                rev = insights.get("revenue_change_percent")
                profit = insights.get("net_profit_change_percent")
                rows = [
                    _list_row("✓", TOKENS["green"], f"业绩状态：<b>{status_label}</b>（服务层判定，来自版本化财务数据）"),
                    _list_row("▲" if (rev or 0) >= 0 else "▼", TOKENS["red_up"] if (rev or 0) >= 0 else TOKENS["green_down"],
                              f"营业收入同比 {rev:+.1f}%" if rev is not None else "营业收入同比未覆盖", latest_period or ""),
                    _list_row("▲" if (profit or 0) >= 0 else "▼", TOKENS["red_up"] if (profit or 0) >= 0 else TOKENS["green_down"],
                              f"归母净利润同比 {profit:+.1f}%" if profit is not None else "归母净利润同比未覆盖", latest_period or ""),
                    _list_row("✓", TOKENS["green"], f"已验证证据 {verified_count:,} 条可追溯至原文"),
                ]
                st.markdown("".join(rows), unsafe_allow_html=True)
    with bottom_center:
        with st.container(border=True):
            _card_head("主要证据来源", TOKENS["blue"], hint=f"{len(records):,} 份")
            providers: dict[str, int] = {}
            for record in records:
                provider = str(record.get("provider") or "未记录")
                providers[provider] = providers.get(provider, 0) + 1
            if providers:
                colors = [TOKENS["blue"], TOKENS["green"], TOKENS["amber"], TOKENS["coral"], MUTED]
                rows = "".join(
                    _list_row("▤", colors[index % len(colors)], name, f"{count:,}")
                    for index, (name, count) in enumerate(sorted(providers.items(), key=lambda kv: -kv[1])[:6])
                )
                st.markdown(rows, unsafe_allow_html=True)
            else:
                st.caption("暂无证据来源记录。")
            st.caption("来源与快照口径见文档与证据页。")
    with bottom_right:
        with st.container(border=True):
            badge_color = TOKENS["amber"] if warnings else TOKENS["green"]
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:.45rem;margin-bottom:.5rem'>"
                f"<span style='width:20px;height:20px;border-radius:6px;background:rgba(217,148,0,.1);"
                f"color:{TOKENS['amber']};display:inline-flex;align-items:center;justify-content:center;"
                f"font-size:.72rem;font-weight:800'>!</span>"
                f"<span style='font-weight:800;font-size:.92rem;color:{TEXT}'>风险与关注点</span>"
                f"<span style='margin-left:auto;background:rgba(217,148,0,.12);color:{badge_color};"
                f"border-radius:9999px;padding:.08rem .55rem;font-size:.72rem;font-weight:700'>{len(warnings)} 项</span></div>",
                unsafe_allow_html=True,
            )
            if warnings:
                rows = "".join(
                    _list_row(
                        "●" if check.get("status") == "warning" else "✕",
                        TOKENS["amber"] if check.get("status") == "warning" else TOKENS["coral"],
                        f"<b>{check.get('label', check.get('code'))}</b> · {check.get('detail')}",
                    )
                    for check in warnings[:6]
                )
                st.markdown(rows, unsafe_allow_html=True)
            else:
                st.markdown(_list_row("✓", TOKENS["green"], "当前没有需要关注的风险项"), unsafe_allow_html=True)
