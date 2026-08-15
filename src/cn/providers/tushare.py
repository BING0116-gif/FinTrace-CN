"""Budget-guarded Tushare Pro adapter for canonical A-share data.

Online access is disabled by default.  Callers must explicitly grant a small
request budget for an approved operation; the adapter never retries by itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from ..domain import CompanyProfile, FinancialStatement, MarketBar
from ..errors import AuthenticationError, EmptyDataError, PermissionError
from ..symbols import CanonicalSymbol
from .base import FinancialDataProvider


@dataclass
class TushareCallBudget:
    """A local, auditable cap on real provider calls (not Tushare points)."""

    max_calls: int = 0
    used_calls: int = 0

    def consume(self, endpoint: str) -> None:
        if self.used_calls >= self.max_calls:
            raise PermissionError(
                f"Tushare call budget exhausted before '{endpoint}' "
                f"({self.used_calls}/{self.max_calls})."
            )
        self.used_calls += 1


def _value(row: Any, name: str) -> Optional[float]:
    value = row.get(name) if hasattr(row, "get") else None
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_date(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}T00:00:00+08:00"


def _period_basis(end_date: str, end_type: Any, *, statement_type: str) -> str:
    mapping = {"1": "Q1", "2": "H1", "3": "9M", "4": "FY"}
    period = mapping.get(str(end_type), "UNKNOWN")
    year = str(end_date)[:4]
    suffix = "_END" if statement_type == "balance" else "_CUMULATIVE"
    return f"{year}{period}{suffix}"


class TushareProvider(FinancialDataProvider):
    """Tushare adapter with explicit call budgeting and no hidden retries."""

    name = "tushare"

    def __init__(self, token: str, *, call_budget: Optional[TushareCallBudget] = None):
        if not token:
            raise AuthenticationError("TUSHARE_TOKEN is required for TushareProvider.")
        self._token = token
        self.call_budget = call_budget or TushareCallBudget()
        self._client: Any = None

    @classmethod
    def from_environment(cls, *, max_calls: int = 0) -> "TushareProvider":
        return cls(
            os.getenv("TUSHARE_TOKEN", "").strip(),
            call_budget=TushareCallBudget(max_calls=max_calls),
        )

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import tushare as ts
            except ImportError as exc:
                raise AuthenticationError("Install the optional 'tushare' dependency first.") from exc
            self._client = ts.pro_api(self._token)
        return self._client

    def _call(self, endpoint: str, **params: Any) -> Any:
        self.call_budget.consume(endpoint)
        frame = getattr(self._get_client(), endpoint)(**params)
        if frame is None or frame.empty:
            raise EmptyDataError(f"Tushare '{endpoint}' returned no data.")
        return frame

    def get_profile(self, symbol: CanonicalSymbol) -> Optional[CompanyProfile]:
        frame = self._call(
            "stock_basic",
            ts_code=str(symbol),
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
        row = frame.iloc[0]
        return CompanyProfile(
            symbol=symbol,
            name=str(row["name"]),
            industry_standard="tushare_stock_basic",
            industry_level="industry",
            industry_name=str(row.get("industry") or "") or None,
        )

    def get_daily_bars(
        self,
        symbol: CanonicalSymbol,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjustment: str = "RAW",
    ) -> List[MarketBar]:
        if adjustment != "RAW":
            raise PermissionError("TushareProvider v1 only exposes RAW bars; use a dedicated adj-factor path.")
        frame = self._call(
            "daily",
            ts_code=str(symbol),
            start_date=(start_date or "").replace("-", ""),
            end_date=(end_date or "").replace("-", ""),
        )
        return [
            MarketBar(
                symbol=symbol,
                trade_date=f"{str(row['trade_date'])[:4]}-{str(row['trade_date'])[4:6]}-{str(row['trade_date'])[6:8]}",
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=_value(row, "vol"),
                amount=_value(row, "amount"),
                adjustment="RAW",
            )
            for _, row in frame.iterrows()
        ]

    def get_financial_statements(
        self, symbol: CanonicalSymbol, *, research_as_of: Optional[str] = None
    ) -> List[FinancialStatement]:
        frames = {
            "income": self._call("income", ts_code=str(symbol)),
            "balance": self._call("balancesheet", ts_code=str(symbol)),
            "cashflow": self._call("cashflow", ts_code=str(symbol)),
        }
        # Tushare can return multiple revisions for one statement endpoint and
        # period.  The canonical schema has one evidence ID per metric/period,
        # so retain the latest available disclosure deterministically.
        statements_by_period: Dict[tuple[str, str], FinancialStatement] = {}
        value_maps: Dict[str, Dict[str, str]] = {
            "income": {"revenue": "revenue", "net_profit": "n_income_attr_p", "ebit": "ebit", "ebitda": "ebitda"},
            "balance": {"total_assets": "total_assets", "total_liabilities": "total_liab", "equity": "total_hldr_eqy_exc_min_int", "total_shares": "total_share"},
            "cashflow": {"operating_cash_flow": "n_cashflow_act", "free_cash_flow": "free_cashflow"},
        }
        cutoff = research_as_of or "9999-12-31T23:59:59+08:00"
        for statement_type, frame in frames.items():
            # ``comp_type`` describes the issuer category (general company,
            # bank, broker, insurer), not whether a statement is standalone.
            # All of these categories can provide consolidated ``report_type=1``
            # statements.  Restricting this to ``1`` silently discarded every
            # financial-institution statement.
            consolidated = frame[
                (frame["report_type"].astype(str).str.replace(".0", "", regex=False) == "1")
                & frame["comp_type"].astype(str).str.replace(".0", "", regex=False).isin({"1", "2", "3", "4"})
            ]
            for _, row in consolidated.iterrows():
                available_at = _iso_date(row.get("f_ann_date")) or _iso_date(row.get("ann_date"))
                if available_at and available_at > cutoff:
                    continue
                end_date = str(row["end_date"])
                statement = FinancialStatement(
                        statement_type=statement_type,  # type: ignore[arg-type]
                        fiscal_period=end_date,
                        period_basis=_period_basis(end_date, row.get("end_type"), statement_type=statement_type),
                        published_at=_iso_date(row.get("ann_date")),
                        available_at=available_at,
                        currency="CNY",
                        unit="CNY",
                        values={key: _value(row, source) for key, source in value_maps[statement_type].items()},
                        is_restated=str(row.get("update_flag") or "") == "1",
                    )
                key = (statement_type, end_date)
                previous = statements_by_period.get(key)
                if previous is None or (statement.available_at or "") >= (previous.available_at or ""):
                    statements_by_period[key] = statement
        return list(statements_by_period.values())
