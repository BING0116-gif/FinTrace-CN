"""Provider-neutral schemas for verifiable A-share research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from .symbols import CanonicalSymbol


PriceAdjustment = Literal["RAW", "QFQ", "HFQ"]


@dataclass(frozen=True)
class CompanyProfile:
    symbol: CanonicalSymbol
    name: str
    currency: str = "CNY"
    industry_standard: Optional[str] = None
    industry_level: Optional[str] = None
    industry_code: Optional[str] = None
    industry_name: Optional[str] = None
    entity_type: Literal["operating_company", "financial_institution"] = "operating_company"
    source_url: Optional[str] = None


@dataclass(frozen=True)
class MarketBar:
    symbol: CanonicalSymbol
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]
    amount: Optional[float]
    adjustment: PriceAdjustment
    trading_status: Optional[str] = None
    adj_factor: Optional[float] = None


@dataclass(frozen=True)
class FinancialStatement:
    """A normalized statement record with sufficient point-in-time metadata."""

    statement_type: Literal["income", "balance", "cashflow"]
    fiscal_period: str
    period_basis: str
    published_at: Optional[str]
    available_at: Optional[str]
    currency: str
    unit: str
    values: Dict[str, Optional[float]]
    source_url: Optional[str] = None
    is_restated: bool = False


@dataclass(frozen=True)
class ResearchSnapshot:
    schema_version: str
    snapshot_id: str
    provider: str
    symbol: CanonicalSymbol
    research_as_of: str
    fetched_at: str
    profile: Optional[CompanyProfile] = None
    bars: List[MarketBar] = field(default_factory=list)
    statements: List[FinancialStatement] = field(default_factory=list)
    data_quality: str = "provider_normalized"
