"""研究总览（UI_REDESIGN_PLAN_V2 §5.1，对齐设计稿图1）。

一屏卡片化布局：进度 stepper → 右列健康度 donut + 证据完整度 →
中列财务指标卡 ×3 → 最近研究任务 → 底部三卡（关键结论 / 主要证据来源 / 风险与关注点）。
所有数值来自服务层；证据 ID 收进芯片悬浮与展开区，不在明面直出。
"""

import streamlit as st

from app_pages._shared import context_or_empty
from services import research_loader as loader
from src.cn import workbench_service as service
from ui.cards import conclusion
from ui.charts import conclusion_health_donut, mini_bar
from ui.chips import chip_row, evidence_chip
from ui.stepper import stepper
from ui.status import callout


def _yoy_fragment(change: float | None) -> str:
    if change is None:
        return "<span style='color:#627D98;font-size:.8rem'>同比未覆盖</span>"
    color = "#D9534F" if change >= 0 else "#159570"
    arrow = "▲" if change >= 0 else "▼"
    return f"<span style='color:{color};font-weight:700;font-variant-numeric:tabular-nums'>{arrow} {abs(change):.1f}%</span>"


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
        st.subheader("关键财务指标")
        points = trends.get("points", [])
        statements = financials.get("statements", [])
        latest_period = insights.get("latest_period")
        evidence_ids_by_period = {p.get("fiscal_period"): p.get("evidence_ids") or {} for p in points}
        latest_ids = evidence_ids_by_period.get(latest_period) or {}
        cf_series = _cash_flow_series(statements)
        cf_latest_period = next(reversed(cf_series), None) if cf_series else None
        cf_evidence = ""
        for row in statements:
            if row.get("fiscal_period") == cf_latest_period and (row.get("evidence_ids") or {}).get("operating_cash_flow"):
                cf_evidence = row["evidence_ids"]["operating_cash_flow"]
        cash_latest = cf_series.get(cf_latest_period) if cf_latest_period else None
        cards = [
            ("营业收入", latest_period, insights.get("revenue_change_percent"), _financial_series(points, "revenue"), latest_ids.get("revenue"), "#1F6FEB"),
            ("归母净利润", latest_period, insights.get("net_profit_change_percent"), _financial_series(points, "net_profit"), latest_ids.get("net_profit"), "#159570"),
            ("经营活动现金流", cf_latest_period, _cash_flow_yoy(statements), cf_series, cf_evidence, "#D99400"),
        ]
        card_cols = st.columns(3)
        for col, (label, period, change, series, evidence_id, color) in zip(card_cols, cards):
            with col:
                with st.container(border=True):
                    st.markdown(f"<div style='color:#627D98;font-size:.78rem;font-weight:600'>{label}</div>", unsafe_allow_html=True)
                    latest_value = list(series.values())[-1] if series else None
                    if latest_value is None:
                        st.markdown("<div style='font-size:1.3rem;color:#627D98'>未覆盖</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(
                            f"<div style='font-size:1.45rem;font-weight:700;font-variant-numeric:tabular-nums'>{latest_value:,.2f} <span style='font-size:.8rem;color:#627D98'>亿元</span></div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(_yoy_fragment(change) + f" <span style='color:#627D98;font-size:.75rem'>同比 · {period or '期间未覆盖'}</span>", unsafe_allow_html=True)
                    mini_bar(series, key=f"overview_mini_{label}_{sid}", color=color)
                    evidence_chip(evidence_id, "年报证据" if evidence_id else "", detail={"证据编号": evidence_id} if evidence_id else None)
    with top_right:
        with st.container(border=True):
            st.markdown("#### 结论健康度")
            conclusion_health_donut(verified_count, warning_count, blocked_count, key=f"overview_donut_{sid}")
        with st.container(border=True):
            st.markdown("#### 证据完整度")
            total_records = len(records)
            if total_records:
                st.progress(verified_count / total_records, text=f"已匹配 {verified_count} / {total_records} 条证据")
            else:
                st.caption("暂无证据记录。")
            chip_row([f"事实 ×{sum(1 for x in records if x.get('kind') == 'fact')}", f"计算 ×{sum(1 for x in records if x.get('kind') == 'calculation')}"])

    # 6. 最近的研究任务卡
    with st.container(border=True):
        st.markdown("#### 最近的研究任务")
        try:
            evaluations = service.list_evaluations()
        except Exception:
            evaluations = []
        uploaded = st.session_state.get("task_uploaded_documents", [])
        if evaluations:
            recent = evaluations[0]
            meta_cols = st.columns(5)
            meta_cols[0].metric("类型", recent.get("kind") or "未记录")
            meta_cols[1].metric("运行时间", str(recent.get("run_at") or "未记录")[:16])
            meta_cols[2].metric("登记文档", len(uploaded))
            meta_cols[3].metric("提取证据", len(records))
            meta_cols[4].metric("产物版本", str(recent.get("benchmark_version") or "未记录")[:18])
        else:
            st.caption("尚无已落盘的评测/任务产物；系统不会用占位数字代替。")

    # 7. 底部三卡
    bottom_left, bottom_center, bottom_right = st.columns(3)
    with bottom_left:
        with st.container(border=True):
            st.markdown("#### 关键结论")
            if not allowed:
                callout("blocked", "Validator 已阻断确定性结论；页面隐藏推测性估值与报告结论。")
            else:
                status = insights.get("performance_status", "insufficient_data")
                conclusion(
                    "业绩状态",
                    f"服务层判定为 `{status}`，同比变化来自版本化财务期间数据。",
                    kind="inference", status=(validation or {}).get("status", "warning"),
                    evidence_count=len(records),
                )
    with bottom_center:
        with st.container(border=True):
            st.markdown("#### 主要证据来源")
            providers: dict[str, int] = {}
            for record in records:
                provider = str(record.get("provider") or "未记录")
                providers[provider] = providers.get(provider, 0) + 1
            if providers:
                chip_row([f"{name} ×{count}" for name, count in sorted(providers.items(), key=lambda kv: -kv[1])])
            else:
                st.caption("暂无证据来源记录。")
            st.caption("来源与快照口径见文档与证据页。")
    with bottom_right:
        with st.container(border=True):
            st.markdown(f"#### 风险与关注点 <span style='background:#D99400;color:#fff;border-radius:9999px;padding:.05rem .5rem;font-size:.72rem'>{len(warnings)}</span>", unsafe_allow_html=True)
            if warnings:
                for check in warnings:
                    st.markdown(
                        f"<div style='background:rgba(217,148,0,.10);border-radius:8px;padding:.45rem .7rem;margin-bottom:.4rem;font-size:.82rem'>"
                        f"<b>{check.get('label', check.get('code'))}</b> · {check.get('detail')}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("当前没有需要关注的风险项。")
