"""Provider contract used by all A-share domain services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..domain import CompanyProfile, FinancialStatement, MarketBar
from ..symbols import CanonicalSymbol


class FinancialDataProvider(ABC):
    """Read-only contract shared by online providers and saved snapshots."""

    name: str

    @abstractmethod
    def get_profile(self, symbol: CanonicalSymbol) -> Optional[CompanyProfile]:
        raise NotImplementedError

    @abstractmethod
    def get_daily_bars(
        self,
        symbol: CanonicalSymbol,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjustment: str = "RAW",
    ) -> List[MarketBar]:
        raise NotImplementedError

    @abstractmethod
    def get_financial_statements(
        self, symbol: CanonicalSymbol, *, research_as_of: Optional[str] = None
    ) -> List[FinancialStatement]:
        raise NotImplementedError
