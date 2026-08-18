"""Offline provider for the market review snapshot.

Mirrors ``src/cn/providers/snapshot.py``: it loads one normalized, versioned
JSON snapshot without touching the network or consuming any API budget.  The
provider never manufactures facts; if the file is missing or malformed it raises
``EmptyDataError`` exactly like the stock snapshot provider.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..errors import EmptyDataError
from .schema import (
    BreadthStats,
    FlowRow,
    Hotspot,
    IndexQuote,
    LimitUpRow,
    MarketReviewSnapshot,
    SectorRank,
)


class DailyReviewSnapshotProvider:
    """Load one market review snapshot for read-only, audited presentation."""

    name = "market_review"

    def __init__(self, snapshot_path: Path | str):
        self.path = Path(snapshot_path)
        self._payload = self._load(self.path)
        self.snapshot = MarketReviewSnapshot.from_payload(self._payload)

    @staticmethod
    def _load(path: Path) -> Dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise EmptyDataError(f"Market review snapshot does not exist: {path}") from exc
        except json.JSONDecodeError as exc:
            raise EmptyDataError(f"Market review snapshot is not valid JSON: {path}") from exc
        required = {"schema_version", "snapshot_id", "research_as_of", "data"}
        missing = sorted(required - payload.keys())
        if missing:
            raise EmptyDataError(
                f"Market review snapshot is missing required fields: {', '.join(missing)}"
            )
        return payload

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "DailyReviewSnapshotProvider":
        """Build a provider from an in-memory payload (tests / analysis)."""
        obj = cls.__new__(cls)
        obj.path = Path("<in-memory>")
        obj._payload = dict(payload)
        obj.snapshot = MarketReviewSnapshot.from_payload(payload)
        return obj

    # ---- metadata ------------------------------------------------------
    @property
    def snapshot_id(self) -> str:
        return self.snapshot.snapshot_id

    @property
    def research_as_of(self) -> str:
        return self.snapshot.research_as_of

    @property
    def provider(self) -> str:
        return self.snapshot.provider

    @property
    def data_quality(self) -> str:
        return self.snapshot.data_quality

    @property
    def source_metadata(self) -> Dict[str, Any]:
        return self.snapshot.source_metadata

    def is_synthetic_demo(self) -> bool:
        return self.snapshot.is_synthetic_demo

    # ---- typed accessors ----------------------------------------------
    def get_indices(self) -> List[IndexQuote]:
        return self.snapshot.indices

    def get_sectors(self) -> List[SectorRank]:
        return self.snapshot.sectors

    def get_breadth(self) -> Optional[BreadthStats]:
        return self.snapshot.breadth

    def get_limit_up(self) -> List[LimitUpRow]:
        return self.snapshot.limit_up

    def get_money_flow(self) -> List[FlowRow]:
        return self.snapshot.money_flow

    def get_hotspots(self) -> List[Hotspot]:
        return self.snapshot.hotspots

    def payload(self) -> Dict[str, Any]:
        return self._payload
