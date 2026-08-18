"""Deterministic gate for daily review conclusions.

This is a lightweight, market-specific reuse of the timestamp / completeness
discipline embodied by ``src/validation/research_gate.py``.  It never calls a
model and never invents facts: it only blocks deterministic conclusions when the
snapshot is missing, malformed, stale, or when a requested inference (e.g. a
next-day forecast) cannot be supported by an offline snapshot.

Offline demo snapshots are explicitly *not* blocked — they are valid offline
artifacts — but they carry a persistent warning so they can never be mistaken
for a live market review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.validation.research_gate import _is_valid_timestamp

from .schema import MarketReviewSnapshot

MAX_REVIEW_AGE_DAYS = 7


@dataclass(frozen=True)
class GateResult:
    valid: bool
    status: str                       # "pass" | "warning" | "blocked"
    conclusion_allowed: bool
    errors: List[str]
    warnings: List[str]
    checks: List[Dict[str, Any]]
    is_synthetic: bool


def review_gate(snapshot: MarketReviewSnapshot) -> GateResult:
    """Return explicit data-quality gates for one market review snapshot."""
    errors: List[str] = []
    warnings: List[str] = []
    checks: List[Dict[str, Any]] = []

    # 1) Review timestamp must be a parseable instant.
    ts_valid = _is_valid_timestamp(snapshot.research_as_of)
    if ts_valid:
        checks.append({"code": "review_timestamp", "label": "复盘时点", "status": "pass",
                       "detail": snapshot.research_as_of,
                       "remediation": "确保 research_as_of 为合法 ISO 时间戳。"})
    else:
        errors.append("invalid_research_as_of")
        checks.append({"code": "review_timestamp", "label": "复盘时点", "status": "blocked",
                       "detail": f"无法解析: {snapshot.research_as_of}",
                       "remediation": "使用 YYYY-MM-DDTHH:MM:SS+08:00 格式。"})

    # 2) Index quotes are the minimum required section.
    if snapshot.indices:
        checks.append({"code": "index_coverage", "label": "指数覆盖", "status": "pass",
                       "detail": f"已覆盖 {len(snapshot.indices)} 个指数",
                       "remediation": "补充缺失指数快照。"})
    else:
        errors.append("missing_indices")
        checks.append({"code": "index_coverage", "label": "指数覆盖", "status": "blocked",
                       "detail": "指数行情为空", "remediation": "采集并重写复盘快照的指数行情。"})

    # 3) Breadth (涨跌家数 / 成交额) gates deterministic market-characteristic conclusions.
    if snapshot.breadth is not None:
        checks.append({"code": "breadth_coverage", "label": "市场广度", "status": "pass",
                       "detail": f"上涨 {snapshot.breadth.up_count} / 下跌 {snapshot.breadth.down_count}",
                       "remediation": "补充涨跌家数与成交额。"})
    else:
        errors.append("missing_breadth")
        checks.append({"code": "breadth_coverage", "label": "市场广度", "status": "blocked",
                       "detail": "广度统计缺失", "remediation": "补全 breadth 字段后再做确定性广度结论。"})

    # 4) Staleness relative to "now".
    if ts_valid:
        try:
            as_of_date = datetime.fromisoformat(snapshot.research_as_of).date()
            age_days = (datetime.now(timezone.utc).date() - as_of_date).days
            if age_days <= MAX_REVIEW_AGE_DAYS:
                checks.append({"code": "review_freshness", "label": "复盘时效", "status": "pass",
                               "detail": f"复盘距今 {age_days} 天", "remediation": "刷新快照后重跑。"})
            else:
                warnings.append("stale_review")
                checks.append({"code": "review_freshness", "label": "复盘时效", "status": "warning",
                               "detail": f"复盘距今 {age_days} 天，已超出 {MAX_REVIEW_AGE_DAYS} 天窗口",
                               "remediation": "重新采集快照后重跑复盘。"})
        except (ValueError, TypeError):
            pass

    # 5) Offline demo flag — never impersonates live quotes.
    is_synthetic = snapshot.is_synthetic_demo
    if is_synthetic:
        warnings.append("synthetic_demo")
        checks.append({"code": "provenance", "label": "数据来源", "status": "warning",
                       "detail": "离线演示快照（synthetic_demo），不代表实时行情",
                       "remediation": "以实时 Tushare 采集并校验后方可作为实盘参考。"})

    blocked = [check for check in checks if check["status"] == "blocked"]
    warn = [check for check in checks if check["status"] == "warning"]
    status = "blocked" if blocked else ("warning" if warn else "pass")
    return GateResult(
        valid=not errors,
        status=status,
        conclusion_allowed=not blocked,
        errors=errors,
        warnings=warnings,
        checks=checks,
        is_synthetic=is_synthetic,
    )
