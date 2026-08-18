"""Versioned, offline-first schema for the FinTrace-CN market review snapshot.

The market review snapshot is intentionally *isostructural* with the existing
per-stock research snapshot so it reuses the same Provider / Evidence /
Validator infrastructure.  Every market datum carries ``evidence_id`` /
``source`` / ``as_of`` / ``unit`` so a daily review can be audited exactly like
an individual-stock research report.

Top-level contract (mirrors ``src/cn/providers/snapshot.py``):

    schema_version, snapshot_id, provider, symbol, research_as_of,
    fetched_at, data_quality, source_metadata,
    data{indices, sectors, limit_up, money_flow, breadth, hotspots}
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from ..errors import EmptyDataError

SCHEMA_VERSION = "market-review-1.0.0"
MARKET_SYMBOL = "CN_MARKET"

# Offline demo snapshots must never be mistaken for live quotes.  These are the
# only acceptable values for ``provider`` / ``data_quality`` on a fallback file.
SYNTHETIC_DATA_QUALITY = "illustrative_test_fixture_not_for_research"
SYNTHETIC_PROVIDER = "synthetic_demo"


class _Base:
    """Shared round-trip helpers for the typed market sub-entities."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_Base":
        known = {key: data[key] for key in cls.__dataclass_fields__ if key in data}
        return cls(**known)  # type: ignore[arg-type]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IndexQuote(_Base):
    index_code: str
    index_name: str
    close: float
    pct_change: float
    change: float
    amount_yi: float = 0.0          # 成交额（亿元）
    turnover: Optional[float] = None  # 换手率（%）
    evidence_id: str = ""
    source: str = ""
    as_of: str = ""
    unit: str = "point"


@dataclass(frozen=True)
class SectorRank(_Base):
    sector_name: str
    sector_type: str = "industry"   # "industry" | "concept"
    pct_change: float = 0.0
    leading_stock: str = ""
    net_inflow_yi: float = 0.0      # 主力净流入（亿元）
    evidence_id: str = ""
    source: str = ""
    as_of: str = ""
    unit: str = "percent"


@dataclass(frozen=True)
class LimitUpRow(_Base):
    code: str
    name: str
    board_days: int = 1             # 连板天数
    close: float = 0.0
    pct_change: float = 0.0
    limit_order_yi: float = 0.0     # 封单金额（亿元）
    logic: str = ""                 # 涨停逻辑 / 题材
    evidence_id: str = ""
    source: str = ""
    as_of: str = ""
    unit: str = "CNY"


@dataclass(frozen=True)
class FlowRow(_Base):
    name: str
    net_inflow_yi: float = 0.0      # 主力净流入（亿元）
    main_inflow_yi: float = 0.0
    evidence_id: str = ""
    source: str = ""
    as_of: str = ""
    unit: str = "亿元"


@dataclass(frozen=True)
class BreadthStats(_Base):
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0
    total_amount_yi: float = 0.0    # 全市场成交额（亿元）
    turnover: Optional[float] = None  # 整体换手率（%）
    evidence_id: str = ""
    source: str = ""
    as_of: str = ""
    unit: str = "家"


@dataclass(frozen=True)
class Hotspot(_Base):
    theme_name: str
    driver: str = ""                # 核心驱动（原文直引，可验证底线，永远保留）
    related_stocks: List[str] = None  # type: ignore[assignment]
    ai_summary: Optional[str] = None   # LLM 润色后的核心驱动；无则为原文 driver
    ai_generated: bool = False         # True=该条 driver 由 LLM 生成，前端须标注
    news_links: Optional[List[str]] = None  # 原始新闻来源链接（可验证）
    evidence_id: str = ""
    source: str = ""
    as_of: str = ""
    unit: str = "theme"


@dataclass(frozen=True)
class MarketReviewSnapshot:
    """Typed, validated wrapper around a market review snapshot payload."""

    schema_version: str
    snapshot_id: str
    provider: str
    symbol: str
    research_as_of: str
    fetched_at: str
    data_quality: str
    source_metadata: Dict[str, Any]
    indices: List[IndexQuote]
    sectors: List[SectorRank]
    limit_up: List[LimitUpRow]
    money_flow: List[FlowRow]
    breadth: Optional[BreadthStats]
    hotspots: List[Hotspot]

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "MarketReviewSnapshot":
        required = {"schema_version", "snapshot_id", "research_as_of", "data"}
        missing = sorted(required - payload.keys())
        if missing:
            raise EmptyDataError(
                f"Market review snapshot is missing required fields: {', '.join(missing)}"
            )
        data = payload.get("data") or {}
        breadth_raw = data.get("breadth")
        return cls(
            schema_version=payload["schema_version"],
            snapshot_id=payload["snapshot_id"],
            provider=payload.get("provider", "unknown"),
            symbol=payload.get("symbol", MARKET_SYMBOL),
            research_as_of=payload["research_as_of"],
            fetched_at=payload.get("fetched_at", ""),
            data_quality=payload.get("data_quality", "unknown"),
            source_metadata=payload.get("source_metadata") or {},
            indices=[IndexQuote.from_dict(item) for item in data.get("indices", [])],
            sectors=[SectorRank.from_dict(item) for item in data.get("sectors", [])],
            limit_up=[LimitUpRow.from_dict(item) for item in data.get("limit_up", [])],
            money_flow=[FlowRow.from_dict(item) for item in data.get("money_flow", [])],
            breadth=BreadthStats.from_dict(breadth_raw) if breadth_raw else None,
            hotspots=[Hotspot.from_dict(item) for item in data.get("hotspots", [])],
        )

    def to_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "provider": self.provider,
            "symbol": self.symbol,
            "research_as_of": self.research_as_of,
            "fetched_at": self.fetched_at,
            "data_quality": self.data_quality,
            "source_metadata": self.source_metadata,
            "data": {
                "indices": [item.to_dict() for item in self.indices],
                "sectors": [item.to_dict() for item in self.sectors],
                "limit_up": [item.to_dict() for item in self.limit_up],
                "money_flow": [item.to_dict() for item in self.money_flow],
                "breadth": self.breadth.to_dict() if self.breadth else None,
                "hotspots": [item.to_dict() for item in self.hotspots],
            },
        }

    @property
    def is_synthetic_demo(self) -> bool:
        flagged = bool(self.source_metadata.get("synthetic_demo"))
        return flagged or self.data_quality == SYNTHETIC_DATA_QUALITY or self.provider == SYNTHETIC_PROVIDER
