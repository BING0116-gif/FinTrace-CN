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
    return d / f"MARKET_{review_date}_tushare_v1.json"


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
def _build_live_review(review_date: str, token: str) -> Dict[str, Any]:
    """Attempt a real Tushare pull. Raises on any insufficiency so the caller
    can fall back to the flagged offline snapshot."""
    try:
        import tushare as ts  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"tushare is not available: {exc}") from exc

    pro = ts.pro_api(token)
    as_of = _as_of_iso(review_date)
    as_of_date = as_of[:10]
    source = "tushare"

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
        df = _safe_call(pro, "index_daily", ts_code=code, trade_date=review_date)
        if df is None or df.empty:
            raise RuntimeError(f"no index_daily for {code} on {review_date}")
        row = df.iloc[0]
        basic = _safe_call(pro, "index_dailybasic", ts_code=code, trade_date=review_date)
        turnover = float(basic.iloc[0]["turnover"]) if basic is not None and not basic.empty else None
        indices.append({
            "index_code": code, "index_name": index_names[code],
            "close": float(row["close"]), "pct_change": float(row["pct_chg"]),
            "change": float(row["close"] - row["pre_close"]),
            "amount_yi": float(row["amount"]) / 1e8, "turnover": turnover,
            "evidence_id": _eid("index", code, as_of_date), "source": source, "as_of": as_of, "unit": "point",
        })

    # Limit-up / breadth / sectors / money-flow are permission-dependent.  When
    # an endpoint is unavailable we leave that section EMPTY (uncovered) rather
    # than inventing values.  The gate then blocks any deterministic conclusion
    # that depends on the missing section, so a partial live pull can never
    # impersonate a complete realtime market review.
    limit_up: List[Dict[str, Any]] = []
    try:
        limit_df = _safe_call(pro, "limit_list", trade_date=review_date)
        if limit_df is not None and not limit_df.empty:
            limit_up = [
                {
                    "code": str(r["ts_code"]), "name": str(r["name"]),
                    "board_days": int(r.get("ld", 1) or 1),
                    "close": float(r["close"]), "pct_change": float(r.get("pct_chg", 10.0)),
                    "limit_order_yi": float(r.get("limit_amount", 0) or 0) / 1e8,
                    "logic": str(r.get("reason", "") or "未披露"),
                    "evidence_id": _eid("limitup", str(r["ts_code"]), as_of_date),
                    "source": source, "as_of": as_of, "unit": "CNY",
                }
                for _, r in limit_df.iterrows()
            ]
    except Exception:
        limit_up = []

    partial = not limit_up
    snapshot_id = f"MARKET_{review_date}_tushare_v1"
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "provider": source,
        "symbol": MARKET_SYMBOL,
        "research_as_of": as_of,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_quality": "tushare_live",
        "source_metadata": {"synthetic_demo": False, "live_attempted": True, "note": "实时 Tushare 采集。"},
        "data": {"indices": indices, "sectors": [], "limit_up": limit_up, "money_flow": [], "breadth": None, "hotspots": []},
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
