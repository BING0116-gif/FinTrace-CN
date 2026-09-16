#!/usr/bin/env python3
"""Render a self-contained, offline HTML market-review report from a snapshot.

This is the system-level home of the "daily review" HTML artifact.  It is
imported by both:

* ``api.py``  -> served as ``GET /api/daily-review/{snapshot_id}/report``
  (a shareable, CDN-free URL), and
* ``workbench.py`` -> offered as a "download HTML report" fallback when the
  API server is not running.

Design notes (kept from the original demo generator):
* No external CDN / network dependency -> safe for a live interview demo.
* CN colour convention: 涨=红, 跌=绿.
* Every data row renders its ``evidence_id`` so the verifiable-evidence design
  is visible at a glance.
* Honest flag: ``synthetic_demo`` snapshots are clearly marked as non-realtime;
  live snapshots are marked as 实时混合数据.
"""
from __future__ import annotations

from typing import Any, Dict


def pct_color(v: float) -> str:
    # CN convention: up -> red, down -> green
    return "#d8392b" if v > 0 else ("#1a9850" if v < 0 else "#888")


def bar(value: float, max_abs: float, label: str) -> str:
    v = float(value)
    width = (abs(v) / max_abs * 100) if max_abs else 0
    color = pct_color(v)
    side = "right" if v >= 0 else "left"
    return f"""
    <div class="bar-row">
      <span class="bar-label">{label}</span>
      <div class="bar-track">
        <div class="bar-fill" style="width:{width:.1f}%;background:{color};margin-{side}:auto"></div>
      </div>
      <span class="bar-val" style="color:{color}">{v:+.2f}%</span>
    </div>"""


def evidence_badge(eid: str) -> str:
    return f'<span class="ev" title="evidence_id">🔒 {eid}</span>' if eid else ""


def render_report_html(snap: Dict[str, Any]) -> str:
    """Build the standalone HTML report string for a market-review snapshot.

    ``snap`` is the full snapshot payload as produced by
    ``collect_daily_review(...)`` / ``workbench_service.load_market_review(...)``
    (i.e. it contains a ``data`` block plus top-level meta fields).
    """
    d = snap.get("data") or {}
    meta = snap.get("source_metadata") or {}
    # live 快照中 breadth / 其他二级字段可能为 None（设计内 partial 行为），
    # 必须 or {} 兜底，否则 breadth.get(...) 会对 None 调用 .get 抛
    # 'NoneType' object has no attribute 'get'。
    breadth = d.get("breadth") or {}
    up = breadth.get("up_count", 0)
    down = breadth.get("down_count", 0)
    flat = breadth.get("flat_count", 0)
    lu = breadth.get("limit_up_count", 0)
    ld = breadth.get("limit_down_count", 0)
    total_amt = breadth.get("total_amount_yi", 0)
    total = up + down + flat
    up_pct = (up / total * 100) if total else 0

    # indices
    idx = d.get("indices", [])
    idx_max = max((abs(x.get("pct_change", 0)) for x in idx), default=1) or 1
    idx_html = "".join(
        bar(x.get("pct_change", 0), idx_max, f'{x.get("index_name")} {x.get("close")}')
        for x in idx
    )
    idx_table = "".join(
        f"<tr><td>{x.get('index_name')}</td><td>{x.get('close')}</td>"
        f"<td style='color:{pct_color(x.get('pct_change',0))}'>{x.get('pct_change'):+.2f}%</td>"
        f"<td>{x.get('amount_yi')}亿</td><td>{x.get('turnover')}%</td>"
        f"<td>{evidence_badge(x.get('evidence_id'))}</td></tr>"
        for x in idx
    )

    # sectors
    sec = d.get("sectors", [])
    sec_max = max((abs(x.get("pct_change", 0)) for x in sec), default=1) or 1
    sec_html = "".join(
        bar(x.get("pct_change", 0), sec_max,
            f'{x.get("sector_name")} · 龙头 {x.get("leading_stock")} · {x.get("net_inflow_yi")}亿')
        for x in sec
    )
    sec_table = "".join(
        f"<tr><td>{x.get('sector_name')}</td><td>{x.get('sector_type')}</td>"
        f"<td style='color:{pct_color(x.get('pct_change',0))}'>{x.get('pct_change'):+.2f}%</td>"
        f"<td>{x.get('leading_stock')}</td><td>{x.get('net_inflow_yi')}亿</td>"
        f"<td>{evidence_badge(x.get('evidence_id'))}</td></tr>"
        for x in sec
    )

    # limit-up ladder
    lu_rows = "".join(
        f"<tr><td>{x.get('name')} <small>{x.get('code')}</small></td>"
        f"<td>{x.get('board_days')}板</td>"
        f"<td>{x.get('close')}</td>"
        f"<td style='color:{pct_color(x.get('pct_change',0))}'>{x.get('pct_change'):+.2f}%</td>"
        f"<td>{x.get('limit_order_yi')}亿</td>"
        f"<td class='logic'>{x.get('logic')}</td>"
        f"<td>{evidence_badge(x.get('evidence_id'))}</td></tr>"
        for x in d.get("limit_up", [])
    )

    # money flow
    mf_rows = "".join(
        f"<tr><td>{x.get('name')}</td>"
        f"<td style='color:{pct_color(x.get('net_inflow_yi',0))}'>{x.get('net_inflow_yi')}亿</td>"
        f"<td>{x.get('main_inflow_yi')}亿</td>"
        f"<td>{evidence_badge(x.get('evidence_id'))}</td></tr>"
        for x in d.get("money_flow", [])
    )

    # hotspots
    hs_html = "".join(
        f"<div class='hotspot'><div class='hs-head'>{h.get('theme_name')} {evidence_badge(h.get('evidence_id'))}</div>"
        f"<div class='hs-driver'>🧭 {h.get('driver')}</div>"
        f"<div class='hs-stocks'>📌 {', '.join(h.get('related_stocks', []))}</div></div>"
        for h in d.get("hotspots", [])
    )

    synthetic = meta.get("synthetic_demo")
    flag = ('<span class="flag synthetic">示例数据 · synthetic_demo=true · 非实时行情</span>'
            if synthetic else '<span class="flag live">实时混合数据</span>')

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FinTrace-CN · A股每日复盘报告</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  background:#0f1420; color:#e6e9ef; margin:0; padding:24px; }}
.wrap {{ max-width: 980px; margin: 0 auto; }}
header {{ border-bottom:1px solid #2a3242; padding-bottom:16px; margin-bottom:20px; }}
h1 {{ margin:0 0 6px; font-size:22px; }}
.sub {{ color:#9aa4b2; font-size:13px; line-height:1.7; }}
.flag {{ display:inline-block; padding:3px 10px; border-radius:12px; font-size:12px; margin-left:8px; }}
.flag.synthetic {{ background:#3a2a12; color:#f0b14a; border:1px solid #6b4a1c; }}
.flag.live {{ background:#10301c; color:#5fd38a; }}
.cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:16px 0; }}
.card {{ background:#171d2b; border:1px solid #2a3242; border-radius:10px; padding:14px 16px; flex:1; min-width:130px; }}
.card .n {{ font-size:24px; font-weight:700; }}
.card .l {{ font-size:12px; color:#9aa4b2; margin-top:4px; }}
.card.up .n {{ color:#d8392b; }} .card.down .n {{ color:#1a9850; }}
.card.lu .n {{ color:#f0b14a; }}
section {{ background:#131926; border:1px solid #2a3242; border-radius:12px; padding:18px; margin:16px 0; }}
h2 {{ font-size:16px; margin:0 0 14px; border-left:3px solid #4d7cff; padding-left:10px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:7px 8px; border-bottom:1px solid #222a38; }}
th {{ color:#9aa4b2; font-weight:600; }}
.bar-row {{ display:flex; align-items:center; gap:10px; margin:6px 0; font-size:13px; }}
.bar-label {{ width:280px; color:#c7cfdc; }}
.bar-track {{ flex:1; background:#1c2333; border-radius:6px; height:14px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:6px; }}
.bar-val {{ width:64px; text-align:right; font-variant-numeric:tabular-nums; }}
.ev {{ font-size:10px; color:#7d8aa0; background:#1c2333; padding:1px 6px; border-radius:8px; white-space:nowrap; }}
.logic {{ color:#c7cfdc; max-width:300px; }}
.hotspot {{ background:#171d2b; border:1px solid #2a3242; border-radius:10px; padding:12px 14px; margin:10px 0; }}
.hs-head {{ font-weight:700; font-size:14px; }}
.hs-driver {{ color:#c7cfdc; margin:6px 0; font-size:13px; }}
.hs-stocks {{ color:#9aa4b2; font-size:12px; }}
.foot {{ color:#7d8aa0; font-size:12px; line-height:1.8; margin-top:24px; border-top:1px solid #2a3242; padding-top:14px; }}
code {{ background:#1c2333; padding:1px 5px; border-radius:4px; color:#8fb0ff; }}
</style></head>
<body><div class="wrap">
<header>
  <h1>FinTrace-CN · A股每日复盘 {flag}</h1>
  <div class="sub">
    snapshot_id: <code>{snap.get('snapshot_id')}</code><br>
    schema: {snap.get('schema_version')} · provider: {snap.get('provider')} ·
    as_of: {snap.get('research_as_of')} · 生成: {snap.get('fetched_at')}
  </div>
</header>

<div class="cards">
  <div class="card up"><div class="n">{up}</div><div class="l">上涨 ({(up_pct):.0f}%)</div></div>
  <div class="card down"><div class="n">{down}</div><div class="l">下跌</div></div>
  <div class="card"><div class="n">{flat}</div><div class="l">平盘</div></div>
  <div class="card lu"><div class="n">{lu}</div><div class="l">涨停</div></div>
  <div class="card"><div class="n">{ld}</div><div class="l">跌停</div></div>
  <div class="card"><div class="n">{total_amt}亿</div><div class="l">两市成交额</div></div>
</div>

<section><h2>指数涨跌</h2>
  {idx_html}
  <table style="margin-top:14px"><tr><th>指数</th><th>收盘</th><th>涨跌幅</th><th>成交额</th><th>换手</th><th>证据</th></tr>{idx_table}</table>
</section>

<section><h2>行业板块 (top)</h2>
  {sec_html}
  <table style="margin-top:14px"><tr><th>板块</th><th>类型</th><th>涨跌幅</th><th>龙头</th><th>净流入</th><th>证据</th></tr>{sec_table}</table>
</section>

<section><h2>涨停梯队</h2>
  <table><tr><th>个股</th><th>连板</th><th>收盘</th><th>涨跌幅</th><th>封单</th><th>逻辑</th><th>证据</th></tr>{lu_rows}</table>
</section>

<section><h2>主力资金净流入 (top)</h2>
  <table><tr><th>个股</th><th>净流入</th><th>主力净流入</th><th>证据</th></tr>{mf_rows}</table>
</section>

<section><h2>题材热点</h2>
  {hs_html}
</section>

<div class="foot">
  <b>可验证设计 (verifiable-by-design)：</b> 每条数据都携带 <code>evidence_id</code>（证据链ID），
  对应底层快照与来源；缺失字段保持 <code>未覆盖</code> 而非编造。本示例为
  <code>synthetic_demo</code> 固定快照，<b>明确标注为非实时行情</b>，绝不伪称实时。
  切换 <code>collect_daily_review(live=True, token=...)</code> 即走真实 Tushare 拉取（失败自动回退并保留示例标记）。
</div>
</div></body></html>"""
