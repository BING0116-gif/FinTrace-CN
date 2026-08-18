"""Deterministic daily review analysis.

Two MVP analysis paths are implemented (per the implementation plan):

* ``panorama_review`` — 路径四「八大板块全景复盘」: 指数收盘 / 市场特征 /
  标的动态 / 核心驱动 / 领涨领跌 / 偏差复核 / 次日推演 / 宏观快照.
* ``hotspot_review`` — 路径五「热点速览」: 大盘概览 / 板块排名 / 热点板块 /
  成交额TOP / 主力净流入TOP / 涨幅TOP.

Every numeric datum is registered as an evidence record with a stable
``evidence_id`` derived from the snapshot, so each number is auditable.  Missing
sections are reported as ``未覆盖`` rather than being invented, and the
next-day inference section is explicitly marked unsupported by an offline
snapshot (the gate blocks any deterministic forecast).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .gate import review_gate
from .schema import MarketReviewSnapshot


def _record(
    *,
    evidence_id: str,
    metric: str,
    value: float,
    unit: str,
    source: str,
    as_of: str,
    field_path: str,
    period: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "kind": "fact",
        "metric": metric,
        "value": value,
        "unit": unit,
        "period": period or "—",
        "source": source,
        "provider": source,
        "status": "verified",
        "field_path": field_path,
        "input_ids": [],
        "operation": None,
        "published_at": as_of,
        "as_of": as_of,
    }


def _build_evidence(snapshot: MarketReviewSnapshot) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    as_of = snapshot.research_as_of
    source = snapshot.provider
    for index in snapshot.indices:
        records.append(_record(
            evidence_id=index.evidence_id, metric="index_close", value=index.close,
            unit="point", source=source, as_of=as_of,
            field_path=f"data.indices.{index.index_code}.close", period=index.index_code,
        ))
        records.append(_record(
            evidence_id=f"{index.evidence_id}__pct", metric="index_pct_change",
            value=index.pct_change, unit="percent", source=source, as_of=as_of,
            field_path=f"data.indices.{index.index_code}.pct_change", period=index.index_code,
        ))
    if snapshot.breadth is not None:
        b = snapshot.breadth
        for metric, value, unit, path in (
            ("breadth_up_count", b.up_count, "家", "data.breadth.up_count"),
            ("breadth_down_count", b.down_count, "家", "data.breadth.down_count"),
            ("breadth_flat_count", b.flat_count, "家", "data.breadth.flat_count"),
            ("breadth_limit_up", b.limit_up_count, "家", "data.breadth.limit_up_count"),
            ("breadth_limit_down", b.limit_down_count, "家", "data.breadth.limit_down_count"),
            ("breadth_total_amount", b.total_amount_yi, "亿元", "data.breadth.total_amount_yi"),
        ):
            records.append(_record(
                evidence_id=f"{b.evidence_id}__{metric}", metric=metric, value=float(value),
                unit=unit, source=source, as_of=as_of, field_path=path,
            ))
    for sector in snapshot.sectors:
        records.append(_record(
            evidence_id=sector.evidence_id, metric="sector_pct_change", value=sector.pct_change,
            unit="percent", source=source, as_of=as_of,
            field_path=f"data.sectors.{sector.sector_name}.pct_change", period=sector.sector_name,
        ))
    for flow in snapshot.money_flow:
        records.append(_record(
            evidence_id=flow.evidence_id, metric="main_net_inflow", value=flow.net_inflow_yi,
            unit="亿元", source=source, as_of=as_of,
            field_path=f"data.money_flow.{flow.name}.net_inflow_yi", period=flow.name,
        ))
    for row in snapshot.limit_up:
        records.append(_record(
            evidence_id=row.evidence_id, metric="limit_up_close", value=row.close,
            unit="CNY", source=source, as_of=as_of,
            field_path=f"data.limit_up.{row.code}.close", period=row.code,
        ))
    return records


def panorama_review(snapshot: MarketReviewSnapshot) -> Dict[str, Any]:
    """路径四：八大板块全景复盘（确定性、可溯源）。"""
    gate = review_gate(snapshot)
    allowed = gate.conclusion_allowed
    evidence = _build_evidence(snapshot)
    evidence_ids = [record["evidence_id"] for record in evidence]

    # 1) 指数收盘
    indices = [
        {
            "index_code": i.index_code, "index_name": i.index_name, "close": i.close,
            "pct_change": i.pct_change, "change": i.change, "amount_yi": i.amount_yi,
            "turnover": i.turnover, "evidence_id": i.evidence_id,
        }
        for i in snapshot.indices
    ]
    top_index = max(snapshot.indices, key=lambda i: i.pct_change) if snapshot.indices else None
    index_summary = (
        f"{top_index.index_name} 领涨（+{top_index.pct_change:.2f}%），"
        f"上证指数收 {indices[0]['close']:.2f}" if (allowed and indices) else "无法验证"
    )

    # 2) 市场特征（广度）
    breadth = snapshot.breadth
    breadth_block = breadth is None
    up_ratio = None
    if breadth is not None and (breadth.up_count + breadth.down_count + breadth.flat_count) > 0:
        up_ratio = breadth.up_count / (breadth.up_count + breadth.down_count + breadth.flat_count) * 100
    characteristics = {
        "up_count": breadth.up_count if breadth else None,
        "down_count": breadth.down_count if breadth else None,
        "flat_count": breadth.flat_count if breadth else None,
        "limit_up_count": breadth.limit_up_count if breadth else None,
        "limit_down_count": breadth.limit_down_count if breadth else None,
        "total_amount_yi": breadth.total_amount_yi if breadth else None,
        "turnover": breadth.turnover if breadth else None,
        "up_ratio_percent": round(up_ratio, 2) if up_ratio is not None else None,
        "evidence_id": breadth.evidence_id if breadth else None,
        "note": "未覆盖" if breadth_block else ("红盘占比 %.1f%%" % up_ratio if up_ratio is not None else "广度已覆盖"),
    }

    # 3) 标的动态（连板天梯）
    ladder = [
        {
            "code": r.code, "name": r.name, "board_days": r.board_days, "close": r.close,
            "pct_change": r.pct_change, "limit_order_yi": r.limit_order_yi, "logic": r.logic,
            "evidence_id": r.evidence_id,
        }
        for r in snapshot.limit_up
    ]
    max_board = max((r.board_days for r in snapshot.limit_up), default=0)
    stock_dynamics = {
        "limit_up_count": len(snapshot.limit_up),
        "max_board_days": max_board,
        "ladder": ladder,
        "evidence_ids": [r.evidence_id for r in snapshot.limit_up],
    }

    # 4) 核心驱动（热点题材）
    core_drivers = [
        {"theme_name": h.theme_name, "driver": h.driver, "related_stocks": h.related_stocks,
         "ai_summary": h.ai_summary, "ai_generated": h.ai_generated,
         "news_links": getattr(h, "news_links", None), "evidence_id": h.evidence_id}
        for h in snapshot.hotspots
    ]

    # 5) 领涨领跌（板块）
    ranked = sorted(snapshot.sectors, key=lambda s: s.pct_change, reverse=True)
    leaders = [
        {"sector_name": s.sector_name, "sector_type": s.sector_type, "pct_change": s.pct_change,
         "leading_stock": s.leading_stock, "evidence_id": s.evidence_id}
        for s in ranked[:5]
    ]
    laggards = [
        {"sector_name": s.sector_name, "sector_type": s.sector_type, "pct_change": s.pct_change,
         "leading_stock": s.leading_stock, "evidence_id": s.evidence_id}
        for s in ranked[-5:][::-1] if s.pct_change < 0
    ]

    # 6) 偏差复核（确定性观察，非结论）
    deviation = _deviation_review(snapshot, top_index, up_ratio)

    # 7) 次日推演 —— 离线快照不支持确定性预测，明确标注未覆盖
    next_day = {
        "supported": False,
        "status": "未覆盖",
        "note": "离线快照不含 order-book / 实时资金博弈，无法给出确定性次日推演；如需请接入实时数据并重跑。",
        "evidence_ids": [],
    }

    # 8) 宏观快照 —— 本项目不采集宏观，明确标注未覆盖
    macro = {
        "supported": False,
        "status": "未覆盖",
        "note": "宏观快照（利率 / 汇率 / PMI 等）不在本模块采集范围；缺数据不补值。",
        "evidence_ids": [],
    }

    return {
        "snapshot_id": snapshot.snapshot_id,
        "research_as_of": snapshot.research_as_of,
        "provider": snapshot.provider,
        "data_quality": snapshot.data_quality,
        "is_synthetic_demo": gate.is_synthetic,
        "conclusion_allowed": allowed,
        "validation": {
            "status": gate.status, "conclusion_allowed": gate.conclusion_allowed,
            "errors": gate.errors, "warnings": gate.warnings, "checks": gate.checks,
        },
        "evidence_records": evidence,
        "evidence_ids": evidence_ids,
        "sections": {
            "index_closing": {"summary": index_summary, "indices": indices,
                              "evidence_ids": [i.evidence_id for i in snapshot.indices]},
            "market_characteristics": characteristics,
            "stock_dynamics": stock_dynamics,
            "core_drivers": {"themes": core_drivers,
                             "evidence_ids": [h.evidence_id for h in snapshot.hotspots]},
            "leaders_laggards": {"leaders": leaders, "laggards": laggards,
                                "evidence_ids": [s.evidence_id for s in ranked]},
            "deviation_review": deviation,
            "next_day_inference": next_day,
            "macro_snapshot": macro,
        },
    }


def _deviation_review(
    snapshot: MarketReviewSnapshot,
    top_index: Optional[Any],
    up_ratio: Optional[float],
) -> Dict[str, Any]:
    """确定性偏差观察：指数涨跌与红盘占比是否一致。"""
    if top_index is None or up_ratio is None:
        return {"supported": False, "status": "未覆盖",
                "note": "指数或广度缺失，无法做偏差复核。", "evidence_ids": []}
    index_sign = "涨" if top_index.pct_change >= 0 else "跌"
    breadth_sign = "红盘占优" if up_ratio >= 50 else "绿盘占优"
    consistent = (top_index.pct_change >= 0 and up_ratio >= 50) or (top_index.pct_change < 0 and up_ratio < 50)
    return {
        "supported": True,
        "consistent": consistent,
        "index_leader_sign": index_sign,
        "breadth_sign": breadth_sign,
        "observation": (
            f"领涨指数 {top_index.index_name} {index_sign}（{top_index.pct_change:+.2f}%），"
            f"全市场{up_ratio:.1f}% 红盘，二者{'一致' if consistent else '出现背离'}。"
        ),
        "note": "仅为盘面一致性观察，不构成方向结论。",
        "evidence_ids": [top_index.evidence_id, snapshot.breadth.evidence_id] if snapshot.breadth else [top_index.evidence_id],
    }


def hotspot_review(snapshot: MarketReviewSnapshot) -> Dict[str, Any]:
    """路径五：热点速览（确定性、可溯源）。"""
    gate = review_gate(snapshot)
    evidence = _build_evidence(snapshot)

    breadth = snapshot.breadth
    market_overview = {
        "up_count": breadth.up_count if breadth else None,
        "down_count": breadth.down_count if breadth else None,
        "limit_up_count": breadth.limit_up_count if breadth else None,
        "limit_down_count": breadth.limit_down_count if breadth else None,
        "total_amount_yi": breadth.total_amount_yi if breadth else None,
        "evidence_id": breadth.evidence_id if breadth else None,
        "status": "未覆盖" if breadth is None else "已覆盖",
    }

    # 板块排名（当前快照；5 日序列离线不可得）
    sector_ranking = [
        {"sector_name": s.sector_name, "sector_type": s.sector_type, "pct_change": s.pct_change,
         "leading_stock": s.leading_stock, "net_inflow_yi": s.net_inflow_yi, "evidence_id": s.evidence_id}
        for s in sorted(snapshot.sectors, key=lambda s: s.pct_change, reverse=True)
    ]
    sector_5d = {"supported": False, "status": "未覆盖",
                 "note": "5 日板块序列需多日快照，离线单日快照不包含；未补值。", "evidence_ids": []}

    top_sectors = [s for s in sector_ranking if s["pct_change"] > 0][:5]
    top_amount = sorted(snapshot.indices, key=lambda i: i.amount_yi, reverse=True)[:5]
    top_amount_section = [
        {"index_name": i.index_name, "amount_yi": i.amount_yi, "pct_change": i.pct_change,
         "evidence_id": i.evidence_id}
        for i in top_amount
    ]
    top_inflow = sorted(snapshot.money_flow, key=lambda f: f.net_inflow_yi, reverse=True)[:5]
    top_inflow_section = [
        {"name": f.name, "net_inflow_yi": f.net_inflow_yi, "main_inflow_yi": f.main_inflow_yi,
         "evidence_id": f.evidence_id}
        for f in top_inflow
    ]
    top_10d = {"supported": False, "status": "未覆盖",
               "note": "10 日涨幅 TOP 需历史序列，离线单日快照不包含；未补值。", "evidence_ids": []}

    return {
        "snapshot_id": snapshot.snapshot_id,
        "research_as_of": snapshot.research_as_of,
        "provider": snapshot.provider,
        "data_quality": snapshot.data_quality,
        "is_synthetic_demo": gate.is_synthetic,
        "conclusion_allowed": gate.conclusion_allowed,
        "validation": {
            "status": gate.status, "conclusion_allowed": gate.conclusion_allowed,
            "errors": gate.errors, "warnings": gate.warnings, "checks": gate.checks,
        },
        "evidence_records": evidence,
        "evidence_ids": [r["evidence_id"] for r in evidence],
        "sections": {
            "market_overview": market_overview,
            "sector_5d": sector_5d,
            "hot_sectors": {"items": top_sectors,
                            "evidence_ids": [s["evidence_id"] for s in top_sectors]},
            "top_amount": {"items": top_amount_section,
                           "evidence_ids": [s["evidence_id"] for s in top_amount_section]},
            "top_net_inflow": {"items": top_inflow_section,
                               "evidence_ids": [s["evidence_id"] for s in top_inflow_section]},
            "top_10d_gainers": top_10d,
        },
    }
