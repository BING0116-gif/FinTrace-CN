"""Daily market review module for FinTrace-CN.

Offline-first market breadth review that reuses the existing Provider / Evidence
/ Validator infrastructure.  Every market datum is auditable; missing data is
flagged ``未覆盖`` instead of being invented, and offline demo snapshots are
clearly marked ``synthetic_demo`` so they can never impersonate live quotes.
"""

from __future__ import annotations

from .analysis import hotspot_review, panorama_review
from .collector import collect_daily_review, load_tushare_token, write_market_snapshot
from .gate import review_gate
from .provider import DailyReviewSnapshotProvider
from .schema import (
    BreadthStats,
    FlowRow,
    Hotspot,
    IndexQuote,
    LimitUpRow,
    MARKET_SYMBOL,
    MarketReviewSnapshot,
    SCHEMA_VERSION,
    SectorRank,
)

__all__ = [
    "DailyReviewSnapshotProvider",
    "MarketReviewSnapshot",
    "IndexQuote",
    "SectorRank",
    "LimitUpRow",
    "FlowRow",
    "BreadthStats",
    "Hotspot",
    "SCHEMA_VERSION",
    "MARKET_SYMBOL",
    "collect_daily_review",
    "load_tushare_token",
    "write_market_snapshot",
    "panorama_review",
    "hotspot_review",
    "review_gate",
]
