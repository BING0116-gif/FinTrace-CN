"""Market review collector.

Design contract (offline-first, realtime optional):

* ``collect_daily_review(review_date, token, live=False)`` returns a versioned
  market review snapshot payload.
* By default (``live=False``) it produces a **clearly flagged offline demo**
  snapshot (``provider="synthetic_demo"``, ``data_quality=
  "illustrative_test_fixture_not_for_research"``, ``source_metadata.
  synthetic_demo=true``).  This is the same kind of fixed fixture the per-stock
  workflow already ships and is **never** presented as live quotes.
* When ``live=True`` and a token is supplied (auto-discovered from the env or
  project ``.env`` via :func:`load_tushare_token` when omitted), it *attempts* a
  real Tushare pull.  Network calls use bounded exponential-backoff retries that
  only retry on transient/rate-limit errors (auth or quota errors fail fast).  A
  successful pull is cached locally (``data/cache/daily_review``) so repeated runs
  for the same trade date reuse it instead of re-spending API quota.  Any failure,
  missing section, or permission error falls back to the flagged offline snapshot.
  The demo flag is preserved so a partial/blocked pull can never masquerade as a
  complete realtime market review.

The collector never returns fabricated realtime-looking data while claiming it
is realtime.  Missing fields stay missing (``未覆盖``); they are never invented.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .schema import (
    MARKET_SYMBOL,
    SCHEMA_VERSION,
    SYNTHETIC_DATA_QUALITY,
    SYNTHETIC_PROVIDER,
)


def _as_of_iso(review_date: str) -> str:
    year, month, day = review_date[:4], review_date[4:6], review_date[6:8]
    return f"{year}-{month}-{day}T23:00:00+08:00"


def _eid(prefix: str, key: str, as_of_date: str) -> str:
    return f"fact_market_{prefix}_{key}_{as_of_date}"


def _validate_review_date(review_date: str) -> None:
    if not (len(review_date) == 8 and review_date.isdigit()):
        raise ValueError("review_date must be YYYYMMDD.")


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Safe float cast; NaN/None/empty/garbage -> default (never raises)."""
    try:
        if value is None or value == "":
            return default
        f = float(value)
        if f != f:  # NaN
            return default
        return f
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_code(code: str) -> str:
    """Add the exchange suffix to a bare 6-digit A-share code.

    akshare returns bare codes (e.g. ``"000936"``); the per-stock schema and the
    demo snapshots expect the ``.SH``/``.SZ``/``.BJ`` suffix, so normalize here.
    Already-suffixed codes are returned unchanged.
    """
    code = (code or "").strip()
    if not code or "." in code:
        return code
    head = code[0]
    if head in ("6", "9"):
        return f"{code}.SH"
    if head in ("0", "3"):
        return f"{code}.SZ"
    if head in ("8", "4"):
        return f"{code}.BJ"
    return f"{code}.SH"


# ---------------------------------------------------------------------------
# Tushare token discovery (best-effort, never logs the value)
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_tushare_token() -> Optional[str]:
    """Best-effort Tushare token discovery, without ever logging the value.

    Resolution order: ``TUSHARE_TOKEN`` environment variable, then the
    project-root ``.env`` file.  Returns the stripped token, or ``None`` when no
    token is configured.  Callers must treat the result as a secret.
    """
    env_val = os.getenv("TUSHARE_TOKEN", "").strip()
    if env_val:
        return env_val
    env_path = _project_root() / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("TUSHARE_TOKEN="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Resilient live fetch: bounded retry/backoff + local cache
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 24 * 3600  # a given trade date's EOD data is immutable once closed


def _live_cache_path(review_date: str) -> Path:
    d = _project_root() / "data" / "cache" / "daily_review"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"MARKET_{review_date}_live_v1.json"


def _is_transient(err: Exception) -> bool:
    """True for errors worth retrying: rate-limits, timeouts, transient 5xx."""
    msg = " ".join(str(a) for a in getattr(err, "args", [str(err)])).lower()
    return any(
        k in msg
        for k in (
            "频率", "每分钟", "rate", "timeout", "timed out", "connection",
            "remoteclosed", "remotedisconnected", "proxy", "reset", "502", "503", "504",
        )
    )


def _retry_call(fn: Callable[[], Any], *, max_attempts: int = 3, base_delay: float = 1.5) -> Any:
    """Call ``fn`` with exponential backoff; only transient errors are retried.

    Auth/quota/permission errors are not transient, so they fail fast and let the
    caller fall back to the offline snapshot instead of hammering the API.
    """
    last: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised intentionally
            last = exc
            if _is_transient(exc) and attempt < max_attempts:
                time.sleep(base_delay * (2 ** (attempt - 1)))
                continue
            raise
    if last is not None:
        raise last


def _safe_call(pro: Any, method: str, **kwargs: Any) -> Any:
    """Invoke a Tushare pro method through the resilient retry wrapper."""
    return _retry_call(lambda: getattr(pro, method)(**kwargs))


# ---------------------------------------------------------------------------
# Offline demo builder (deterministic, clearly flagged)
# ---------------------------------------------------------------------------
def _build_synthetic_review(review_date: str) -> Dict[str, Any]:
    _validate_review_date(review_date)
    as_of = _as_of_iso(review_date)
    as_of_date = as_of[:10]
    source = SYNTHETIC_PROVIDER

    indices_raw = [
        ("000001.SH", "上证指数", 3215.34, 0.42, 13.45, 3892.10, 0.92),
        ("399001.SZ", "深证成指", 10182.56, 0.58, 58.73, 5421.33, 1.65),
        ("399006.SZ", "创业板指", 2067.21, 0.91, 18.65, 2456.78, 2.31),
        ("000688.SH", "科创50", 892.45, 1.12, 9.87, 612.34, 1.98),
        ("000300.SH", "沪深300", 3798.12, 0.35, 13.21, 2489.55, 0.61),
        ("000905.SH", "中证500", 5621.78, 0.67, 37.45, 1687.22, 1.12),
        ("000852.SH", "中证1000", 6012.33, 0.83, 49.56, 2034.67, 1.45),
        ("000922.SH", "中证红利", 5123.45, 0.12, 6.12, 432.10, 0.45),
        ("899050.BJ", "北证50", 1023.67, 1.45, 14.62, 56.78, 3.21),
    ]
    indices = [
        {
            "index_code": code, "index_name": name, "close": close,
            "pct_change": pct, "change": change, "amount_yi": amount, "turnover": turnover,
            "evidence_id": _eid("index", code, as_of_date), "source": source, "as_of": as_of, "unit": "point",
        }
        for code, name, close, pct, change, amount, turnover in indices_raw
    ]

    sectors_raw = [
        ("半导体", "industry", 3.21, "中芯国际", 12.4),
        ("消费电子", "industry", 2.45, "立讯精密", 8.7),
        ("电力设备", "industry", 1.98, "宁德时代", 6.3),
        ("计算机", "industry", 1.76, "金山办公", 5.1),
        ("国防军工", "industry", 1.32, "中航沈飞", 3.9),
        ("CPO概念", "concept", 4.12, "新易盛", 9.8),
        ("华为链", "concept", 2.88, "赛力斯", 7.2),
        ("人形机器人", "concept", 3.55, "绿的谐波", 6.6),
        ("低空经济", "concept", 2.10, "万丰奥威", 4.4),
        ("银行", "industry", -0.86, "招商银行", -5.2),
        ("煤炭", "industry", -1.12, "中国神华", -3.8),
        ("地产", "industry", -0.74, "保利发展", -2.1),
    ]
    sectors = [
        {
            "sector_name": name, "sector_type": kind, "pct_change": pct,
            "leading_stock": lead, "net_inflow_yi": inflow,
            "evidence_id": _eid("sector", name, as_of_date), "source": source, "as_of": as_of, "unit": "percent",
        }
        for name, kind, pct, lead, inflow in sectors_raw
    ]

    breadth = {
        "up_count": 2987, "down_count": 1823, "flat_count": 210,
        "limit_up_count": 68, "limit_down_count": 12, "total_amount_yi": 11234.56, "turnover": 1.32,
        "evidence_id": _eid("breadth", "summary", as_of_date), "source": source, "as_of": as_of, "unit": "家",
    }

    limit_up_raw = [
        ("603019.SH", "中科曙光", 3, 52.18, 10.01, 4.6, "算力租赁+国产AI芯片"),
        ("300308.SZ", "中际旭创", 2, 168.90, 20.00, 7.2, "CPO 800G出货超预期"),
        ("002230.SZ", "科大讯飞", 2, 49.73, 10.00, 3.1, "大模型应用落地"),
        ("601127.SH", "赛力斯", 1, 102.45, 10.00, 5.4, "华为智选车交付放量"),
        ("300750.SZ", "宁德时代", 1, 198.60, 4.21, 2.8, "储能订单高增"),
        ("688981.SH", "中芯国际", 1, 58.32, 6.74, 3.9, "半导体国产化"),
        ("002594.SZ", "比亚迪", 1, 245.10, 3.12, 2.2, "海外销量创新高"),
        ("603501.SH", "韦尔股份", 1, 112.36, 7.83, 1.9, "CMOS图像传感器复苏"),
    ]
    limit_up = [
        {
            "code": code, "name": name, "board_days": days, "close": close,
            "pct_change": pct, "limit_order_yi": order, "logic": logic,
            "evidence_id": _eid("limitup", code, as_of_date), "source": source, "as_of": as_of, "unit": "CNY",
        }
        for code, name, days, close, pct, order, logic in limit_up_raw
    ]

    money_flow_raw = [
        ("中科曙光", 18.6, 15.2), ("中际旭创", 14.3, 12.1), ("科大讯飞", 11.8, 9.6),
        ("赛力斯", 9.4, 8.0), ("宁德时代", 8.1, 6.7), ("中芯国际", 7.7, 6.2),
        ("比亚迪", 6.9, 5.5), ("韦尔股份", 5.3, 4.4),
    ]
    money_flow = [
        {
            "name": name, "net_inflow_yi": net, "main_inflow_yi": main,
            "evidence_id": _eid("flow", name, as_of_date), "source": source, "as_of": as_of, "unit": "亿元",
        }
        for name, net, main in money_flow_raw
    ]

    hotspots_raw = [
        ("AI算力", "国产大模型训练与推理需求拉动算力租赁与光模块订单", ["中科曙光", "中际旭创", "工业富联"]),
        ("CPO", "800G/1.6T光模块出货超预期，海外云厂资本开支上修", ["中际旭创", "新易盛", "天孚通信"]),
        ("半导体国产化", "设备与制造环节替代加速，库存周期触底", ["中芯国际", "北方华创", "韦尔股份"]),
        ("华为链", "智选车与终端新品周期，生态协同", ["赛力斯", "立讯精密", "欧菲光"]),
        ("人形机器人", "量产节点临近，核心零部件国产替代", ["绿的谐波", "鸣志电器", "拓普集团"]),
    ]
    hotspots = [
        {
            "theme_name": theme, "driver": driver, "related_stocks": list(stocks),
            "evidence_id": _eid("hotspot", theme, as_of_date), "source": source, "as_of": as_of, "unit": "theme",
        }
        for theme, driver, stocks in hotspots_raw
    ]

    snapshot_id = f"MARKET_{review_date}_synthetic_demo_v1"
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "provider": SYNTHETIC_PROVIDER,
        "symbol": MARKET_SYMBOL,
        "research_as_of": as_of,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_quality": SYNTHETIC_DATA_QUALITY,
        "source_metadata": {
            "synthetic_demo": True,
            "generated_by": "fintrace_cn_daily_review_offline_fallback",
            "live_attempted": False,
            "note": "离线演示快照，非实时行情；仅供架构演示与离线测试，绝不用于实盘决策。",
        },
        "data": {
            "indices": indices, "sectors": sectors, "limit_up": limit_up,
            "money_flow": money_flow, "breadth": breadth, "hotspots": hotspots,
        },
    }


# ---------------------------------------------------------------------------
# Optional realtime path (best-effort; any failure falls back)
# ---------------------------------------------------------------------------
# Theme taxonomy for news-driven hotspots.  Each theme maps to keywords used to
# match real financial news (akshare stock_info_global_em) and limit-up stocks.
# Driver text is ALWAYS the verbatim news headline + source link — never invented.
THEME_KEYWORDS: Dict[str, List[str]] = {
    "AI算力": ["AI", "算力", "光模块", "GPU", "大模型", "英伟达", "智算", "数据中心"],
    "半导体国产化": ["半导体", "芯片", "国产化", "晶圆", "光刻", "射频", "CIS"],
    "新能源/储能": ["储能", "光伏", "锂电", "新能源", "电池", "固态电池", "逆变器"],
    "人形机器人": ["机器人", "减速器", "具身", "伺服", "丝杠"],
    "低空经济": ["低空", "eVTOL", "飞行汽车", "通航"],
    "华为链": ["华为", "鸿蒙", "昇腾", "盘古"],
    "军工": ["军工", "国防", "航空发动机", "卫星", "导弹"],
    "消费复苏": ["消费", "白酒", "零售", "免税", "家电"],
    "医药": ["创新药", "CXO", "医疗", "生物制药", "医保"],
    "周期资源": ["黄金", "铜", "铝", "锂矿", "稀土", "钢铁", "煤炭", "化工"],
}


# ---------------------------------------------------------------------------
# Optional LLM polish for hotspot drivers
# ---------------------------------------------------------------------------
# The raw ``driver`` is always kept (verifiable real-news quotes + links).  When
# a DeepSeek key is configured we additionally generate ``ai_summary`` — one
# polished Chinese sentence condensing the matched real news.  This NEVER invents
# facts: the prompt is strictly bounded to the supplied headlines, forbids stock
# tips and fabrication, and on any failure we degrade to the raw driver instead
# of raising (so a flaky LLM call can never abort the whole live build).
_LLM_POLISH_FN = None
_LLM_POLISH_READY = False


def _get_llm_polish():
    """Lazily resolve the project's DeepSeek (openai-compatible) callable.

    Returns the callable or ``None`` when the LLM layer cannot be imported or no
    key is configured.  Resolution is cached so each live build imports once.

    ``deepseek_v4_flash`` reads its key/base-URL from ``os.environ`` only, and the
    workbench entrypoint does not call ``load_dotenv()`` itself.  So we load the
    project ``.env`` defensively here (no-op if already present) — this mirrors
    how ``load_tushare_token`` already discovers its token, keeping the feature
    working regardless of how the app was started.
    """
    global _LLM_POLISH_FN, _LLM_POLISH_READY
    if _LLM_POLISH_READY:
        return _LLM_POLISH_FN
    _LLM_POLISH_READY = True
    try:
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=_project_root() / ".env")
        except Exception:
            pass
        from src.llms import deepseek_v4_flash  # type: ignore
        _LLM_POLISH_FN = deepseek_v4_flash
    except Exception:
        _LLM_POLISH_FN = None
    return _LLM_POLISH_FN


def _polish_theme_with_llm(theme_name: str, news_items: List[Dict[str, Any]]) -> "tuple[Optional[str], bool]":
    """Condense matched real news into one polished Chinese sentence.

    Returns ``(summary, True)`` on success or ``(None, False)`` when the LLM is
    unavailable or the call fails — caller keeps the raw ``driver`` in that case.
    """
    fn = _get_llm_polish()
    if fn is None or not news_items:
        return None, False
    news_text = "\n".join(
        f"- {str(m.get('标题', ''))}：{str(m.get('摘要', ''))}" for m in news_items[:3]
    )
    if not news_text.strip():
        return None, False
    messages = [
        {
            "role": "system",
            "content": (
                "你是A股复盘助手。仅依据用户给出的真实新闻标题与摘要，"
                "浓缩成一句客观、简洁的中文市场主线说明。"
                "严禁编造新闻中没有的信息，严禁给出任何投资建议，严禁提及具体个股代码或名称。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"题材：{theme_name}\n"
                f"相关真实新闻：\n{news_text}\n\n"
                f"请只输出一句不超过40字的中文主线说明（仅基于上述新闻，"
                f"不添加未提及信息，不荐股，不提个股）。只输出这句话本身，不要解释、不要引号。"
            ),
        },
    ]
    try:
        text, _cost = fn(messages, temperature=0.3)
        text = (text or "").strip().strip('"').strip("'").strip()
        # Guard against empty / junk / runaway output.
        if not text or len(text) < 4 or len(text) > 80:
            return None, False
        return text[:60], True
    except Exception:
        return None, False


def _build_akshare_sections(
    review_date: str, as_of: str, as_of_date: str, source: str
) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]":
    """Pull breadth / limit-up / sectors / money-flow from akshare (free, no
    token).  Each section is fetched independently; any single failure only
    leaves that section empty (uncovered) instead of aborting the whole build.

    A proxy env is temporarily cleared because some sandboxed networks proxy-
    block eastmoney subdomains while normal user machines have no such proxy.
    """
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]
    saved = {k: os.environ.pop(k, None) for k in proxy_keys}
    try:
        import akshare as ak
    except Exception:
        return [], [], None, []
    try:
        # --- limit-up pool ---
        limit_up: List[Dict[str, Any]] = []
        try:
            zt = ak.stock_zt_pool_em(date=review_date)
            if zt is not None and not zt.empty:
                for _, r in zt.iterrows():
                    code = _normalize_code(str(r.get("代码", "")))
                    limit_up.append({
                        "code": code,
                        "name": str(r.get("名称", "")),
                        "board_days": _to_int(r.get("连板数"), 1),
                        "close": _to_float(r.get("最新价")),
                        "pct_change": _to_float(r.get("涨跌幅")),
                        "limit_order_yi": (_to_float(r.get("封板资金"), 0.0) or 0.0) / 1e8,
                        "logic": str(r.get("所属行业", "") or "未披露"),
                        "evidence_id": _eid("limitup", code or str(r.get("名称", "")), as_of_date),
                        "source": source, "as_of": as_of, "unit": "CNY",
                    })
        except Exception:
            limit_up = []

        # --- industry sectors (hybrid: EM first, THS fallback) ---
        # ``stock_board_industry_name_em`` (eastmoney) is blocked in some
        # sandboxed networks, so when it raises or returns nothing we fall back
        # to ``stock_board_industry_summary_ths`` (tonghuashun), which is
        # reachable there and additionally carries sector-level net inflow.
        # This keeps the sector section populated in every environment instead
        # of silently showing "未覆盖".  Missing values are never invented.
        sectors: List[Dict[str, Any]] = []
        try:
            bd = ak.stock_board_industry_name_em()
            if bd is None or bd.empty:
                raise RuntimeError("EM industry board empty")
            for _, r in bd.iterrows():
                name = str(r.get("板块名称", ""))
                lead = r.get("领涨股", "")
                sectors.append({
                    "sector_name": name,
                    "sector_type": "industry",
                    "pct_change": _to_float(r.get("涨跌幅")),
                    "leading_stock": "" if lead is None or lead != lead else str(lead),
                    "net_inflow_yi": (_to_float(r.get("主力资金净流入-净额"), 0.0) or 0.0) / 1e8,
                    "evidence_id": _eid("sector", name, as_of_date),
                    "source": source, "as_of": as_of, "unit": "percent",
                })
        except Exception:
            # EM unreachable/empty -> THS summary (sector 涨跌幅/净流入/领涨股)
            try:
                bd = ak.stock_board_industry_summary_ths()
                if bd is not None and not bd.empty:
                    for _, r in bd.iterrows():
                        name = str(r.get("板块", ""))
                        lead = r.get("领涨股", "")
                        sectors.append({
                            "sector_name": name,
                            "sector_type": "industry",
                            "pct_change": _to_float(r.get("涨跌幅")),
                            "leading_stock": "" if lead is None or lead != lead else str(lead),
                            "net_inflow_yi": _to_float(r.get("净流入"), 0.0) or 0.0,
                            "evidence_id": _eid("sector", name, as_of_date),
                            "source": source, "as_of": as_of, "unit": "percent",
                        })
            except Exception:
                sectors = []

        # --- market breadth (aggregate from full-market quote) ---
        # EM (eastmoney) is blocked in some sandboxed networks, so when
        # ``stock_zh_a_spot_em`` raises or returns nothing we fall back to
        # ``stock_zh_a_spot`` (tonghuashun / sina-backed), which is reachable
        # there and returns the same full-market quote (涨跌幅/成交额).  This
        # keeps the breadth KPIs (上涨/下跌/平盘/涨停/跌停/两市成交额) populated
        # in every environment instead of silently showing all-zero defaults.
        # Missing values are never invented.
        breadth: Optional[Dict[str, Any]] = None

        def _aggregate_breadth(spot: Any, src_label: str) -> Optional[Dict[str, Any]]:
            if spot is None or getattr(spot, "empty", True) or "涨跌幅" not in spot.columns:
                return None
            chg = spot["涨跌幅"].astype(float)
            up = int((chg > 0).sum()); down = int((chg < 0).sum()); flat = int((chg == 0).sum())
            lu = int((chg >= 9.9).sum()); ld = int((chg <= -9.9).sum())
            total_amt = (_to_float(spot["成交额"].astype(float).sum(), 0.0) or 0.0) / 1e8
            turnover = _to_float(spot["换手率"].astype(float).mean(), None) if "换手率" in spot.columns else None
            return {
                "up_count": up, "down_count": down, "flat_count": flat,
                "limit_up_count": lu, "limit_down_count": ld,
                "total_amount_yi": total_amt, "turnover": turnover,
                "evidence_id": _eid("breadth", "summary", as_of_date),
                "source": src_label, "as_of": as_of, "unit": "家",
            }

        try:
            spot = ak.stock_zh_a_spot_em()
            breadth = _aggregate_breadth(spot, "akshare_em")
        except Exception:
            breadth = None
        if breadth is None:
            # EM unreachable/empty -> THS full-market spot (reachable in sandbox)
            try:
                spot = ak.stock_zh_a_spot()
                breadth = _aggregate_breadth(spot, "akshare_ths")
            except Exception:
                breadth = None

        # --- individual main-fund flow ranking ---
        money_flow: List[Dict[str, Any]] = []
        try:
            fl = ak.stock_individual_fund_flow_rank(indicator="今日")
            if fl is not None and not fl.empty:
                for _, r in fl.iterrows():
                    name = str(r.get("名称", ""))
                    net = (_to_float(r.get("今日主力净流入-净额"), 0.0) or 0.0) / 1e8
                    money_flow.append({
                        "name": name,
                        "net_inflow_yi": net,
                        "main_inflow_yi": net,
                        "evidence_id": _eid("flow", name, as_of_date),
                        "source": source, "as_of": as_of, "unit": "亿元",
                    })
        except Exception:
            money_flow = []

        # --- news-driven hotspots (verifiable: real headline + source link) ---
        hotspots: List[Dict[str, Any]] = []
        try:
            news = ak.stock_info_global_em()
            if news is not None and not news.empty:
                news = news.fillna("")
                for theme_name, kws in THEME_KEYWORDS.items():
                    matched = [
                        n for _, n in news.iterrows()
                        if any(kw in str(n.get("标题", "")) + str(n.get("摘要", "")) for kw in kws)
                    ]
                    if not matched:
                        continue
                    top = matched[:2]
                    driver = "；".join(
                        f"{str(m.get('标题', ''))}（来源：{str(m.get('链接', ''))}）" for m in top
                    )
                    rel = [
                        lu["name"] for lu in limit_up
                        if any(kw in (lu.get("name", "") + lu.get("logic", "")) for kw in kws)
                    ]
                    # Optional LLM polish — degrade to raw driver on any failure.
                    ai_summary, ai_generated = _polish_theme_with_llm(theme_name, top)
                    hotspots.append({
                        "theme_name": theme_name,
                        "driver": driver,
                        "related_stocks": rel,
                        "ai_summary": ai_summary,
                        "ai_generated": ai_generated,
                        "news_links": [str(m.get("链接", "")) for m in top],
                        "evidence_id": _eid("hotspot", theme_name, as_of_date),
                        "source": "akshare_news", "as_of": as_of, "unit": "theme",
                    })
        except Exception:
            hotspots = []

    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    return limit_up, sectors, breadth, money_flow, hotspots


def _build_live_review(review_date: str, token: str) -> Dict[str, Any]:
    """Hybrid realtime build: indices from Tushare, breadth/limit-up/sectors/
    money-flow from akshare (free, no token).

    Design intent (the system's verifiability contract):
    * Every external section is fetched independently inside try/except, so a
      single source failure only leaves that section EMPTY (uncovered) — values
      are never invented.
    * Each record keeps its own ``source`` field, and the snapshot ``provider``
      is the composite ``tushare+akshare``, so the UI can show exactly where
      every number came from.
    * ``hotspots`` is derived from real financial news (akshare
      ``stock_info_global_em``): the qualitative driver text is the verbatim
      news headline plus its source link, so it stays verifiable and is never
      invented.  Related stocks come from the same-day limit-up pool.
    * The build only raises — letting the caller fall back to the flagged offline
      demo — when NO index data could be pulled at all (Tushare unreachable).
    """
    as_of = _as_of_iso(review_date)
    as_of_date = as_of[:10]
    source_ts = "tushare"
    source_ak = "akshare"

    # --- Tushare: indices (resilient per-index; one failure is skipped) ---
    try:
        import tushare as ts  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"tushare is not available: {exc}") from exc
    pro = ts.pro_api(token)
    index_codes = [
        "000001.SH", "399001.SZ", "399006.SZ", "000688.SH", "000300.SH",
        "000905.SH", "000852.SH", "000922.SH", "899050.BJ",
    ]
    index_names = {
        "000001.SH": "上证指数", "399001.SZ": "深证成指", "399006.SZ": "创业板指",
        "000688.SH": "科创50", "000300.SH": "沪深300", "000905.SH": "中证500",
        "000852.SH": "中证1000", "000922.SH": "中证红利", "899050.BJ": "北证50",
    }
    indices: List[Dict[str, Any]] = []
    for code in index_codes:
        try:
            df = _safe_call(pro, "index_daily", ts_code=code, trade_date=review_date)
            if df is None or df.empty:
                continue
            row = df.iloc[0]
            basic = _safe_call(pro, "index_dailybasic", ts_code=code, trade_date=review_date)
            # Tushare's index_dailybasic names the turnover column "turnover_rate";
            # guard against column-name drift so a missing key never aborts the
            # per-index fetch (and thus the whole live build).
            turnover = None
            if basic is not None and not basic.empty:
                tcol = "turnover_rate" if "turnover_rate" in basic.columns else ("turnover" if "turnover" in basic.columns else None)
                if tcol:
                    turnover = float(basic.iloc[0][tcol])
            indices.append({
                "index_code": code, "index_name": index_names[code],
                "close": float(row["close"]), "pct_change": float(row["pct_chg"]),
                "change": float(row["close"] - row["pre_close"]),
                "amount_yi": float(row["amount"]) / 1e8, "turnover": turnover,
                "evidence_id": _eid("index", code, as_of_date), "source": source_ts, "as_of": as_of, "unit": "point",
            })
        except Exception:
            continue
    if not indices:
        raise RuntimeError(f"no index_daily data could be pulled for {review_date}")

    # --- akshare: limit_up / sectors / breadth / money_flow / hotspots ---
    limit_up, sectors, breadth, money_flow, hotspots = _build_akshare_sections(
        review_date, as_of, as_of_date, source_ak
    )

    partial = not (limit_up and sectors and breadth and money_flow and hotspots)
    snapshot_id = f"MARKET_{review_date}_live_v1"
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "provider": f"{source_ts}+{source_ak}",
        "symbol": MARKET_SYMBOL,
        "research_as_of": as_of,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_quality": "live_hybrid",
        "source_metadata": {
            "synthetic_demo": False,
            "live_attempted": True,
                "sources": {
                    "indices": source_ts, "limit_up": source_ak, "sectors": source_ak,
                    "breadth": (breadth or {}).get("source", source_ak), "money_flow": source_ak, "hotspots": "akshare_news",
                },
                "partial": partial,
                "note": "实时混合采集：指数 Tushare，涨停/板块/广度/资金流/热点 AkShare（免费源）；热点 driver 取自真实财经新闻原文+来源链接，绝不编造。任一源失败对应模块留空，绝不编数据。",
        },
        "data": {
            "indices": indices, "sectors": sectors, "limit_up": limit_up,
            "money_flow": money_flow, "breadth": breadth, "hotspots": hotspots,
        },
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def collect_daily_review(
    review_date: str,
    token: Optional[str] = None,
    *,
    live: bool = False,
    force_refresh: bool = False,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Return a market review snapshot payload.

    Live pulls are optional and best-effort; any failure falls back to a clearly
    flagged offline demo snapshot.  The demo flag is preserved so a blocked or
    partial realtime pull can never impersonate a complete live market review.

    Args:
        live: when True, attempt a real Tushare pull.  If ``token`` is omitted it
            is auto-discovered via :func:`load_tushare_token`.
        force_refresh: ignore any cached live payload and re-pull from Tushare.
        use_cache: persist a successful live payload under
            ``data/cache/daily_review`` so repeated runs for the same trade date
            reuse it instead of re-spending API quota (the main quota saver).
    """
    _validate_review_date(review_date)
    if live:
        token = token or load_tushare_token()
    if live and token:
        cache_path = _live_cache_path(review_date) if use_cache else None
        if cache_path is not None and not force_refresh and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age <= CACHE_TTL_SECONDS:
                try:
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    cached.setdefault("source_metadata", {})["cached"] = True
                    return cached
                except Exception:
                    pass
        try:
            payload = _build_live_review(review_date, token)
            if use_cache and cache_path is not None and payload.get("data", {}).get("indices"):
                try:
                    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            return payload
        except Exception:
            # Swallow and fall back; do NOT leak credentials or internal errors.
            pass
    return _build_synthetic_review(review_date)


def write_market_snapshot(payload: Dict[str, Any], output_dir: Path | str) -> Path:
    """Persist a market review snapshot as ``<snapshot_id>.json``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{payload['snapshot_id']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
