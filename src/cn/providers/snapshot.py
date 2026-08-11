"""Versioned, offline provider for reproducible A-share research."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..domain import CompanyProfile, FinancialStatement, MarketBar
from ..errors import EmptyDataError, UnsupportedSymbolError
from ..symbols import CanonicalSymbol, normalize_cn_symbol
from .base import FinancialDataProvider


class SnapshotProvider(FinancialDataProvider):
    """Load one normalized snapshot without network access or API consumption."""

    name = "snapshot"

    def __init__(self, snapshot_path: Path | str):
        self.path = Path(snapshot_path)
        self._payload = self._load(self.path)
        self._symbol = normalize_cn_symbol(self._payload["symbol"])

    @staticmethod
    def _load(path: Path) -> Dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise EmptyDataError(f"Snapshot does not exist: {path}") from exc
        except json.JSONDecodeError as exc:
            raise EmptyDataError(f"Snapshot is not valid JSON: {path}") from exc
        required = {"schema_version", "snapshot_id", "symbol", "research_as_of", "data"}
        missing = sorted(required - payload.keys())
        if missing:
            raise EmptyDataError(f"Snapshot is missing required fields: {', '.join(missing)}")
        return payload

    def _assert_symbol(self, symbol: CanonicalSymbol) -> None:
        if symbol != self._symbol:
            raise UnsupportedSymbolError(f"Snapshot contains {self._symbol}, not {symbol}.")

    def get_profile(self, symbol: CanonicalSymbol) -> Optional[CompanyProfile]:
        self._assert_symbol(symbol)
        raw = self._payload["data"].get("profile")
        if not raw:
            return None
        return CompanyProfile(symbol=symbol, **raw)

    def get_daily_bars(
        self,
        symbol: CanonicalSymbol,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjustment: str = "RAW",
    ) -> List[MarketBar]:
        self._assert_symbol(symbol)
        bars = []
        for raw in self._payload["data"].get("bars", []):
            if raw.get("adjustment") != adjustment:
                continue
            if start_date and raw["trade_date"] < start_date:
                continue
            if end_date and raw["trade_date"] > end_date:
                continue
            bars.append(MarketBar(symbol=symbol, **raw))
        return bars

    def get_financial_statements(
        self, symbol: CanonicalSymbol, *, research_as_of: Optional[str] = None
    ) -> List[FinancialStatement]:
        self._assert_symbol(symbol)
        cutoff = research_as_of or self._payload["research_as_of"]
        statements = []
        for raw in self._payload["data"].get("statements", []):
            available_at = raw.get("available_at")
            if available_at and available_at > cutoff:
                continue
            statements.append(FinancialStatement(**raw))
        return statements
