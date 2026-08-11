"""Free, no-API-key A-share provider backed by AKShare (East Money / public sources).

AKShare is a community-maintained wrapper around public Chinese financial websites.
Its APIs may change when upstream pages change — this provider treats every call as
best-effort and raises typed :mod:`..errors` so that the :class:`ProviderRouter` can
fall through to the next provider or snapshot.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from ..domain import CompanyProfile, FinancialStatement, MarketBar
from ..errors import AuthenticationError, EmptyDataError, ProviderError, UnsupportedSymbolError
from ..symbols import CanonicalSymbol
from .base import FinancialDataProvider


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _value(row: Any, name: str) -> Optional[float]:
    raw = row.get(name) if hasattr(row, "get") else None
    if raw is None:
        return None
    try:
        return None if raw != raw else float(raw)  # NaN check
    except (TypeError, ValueError):
        return None


def _iso_date(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()[:10]
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T00:00:00+08:00"
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}T00:00:00+08:00"
    return None


# Maps AKShare English columns → canonical field names for financial statements.
_INCOME_MAP: Dict[str, str] = {
    "OPERATE_INCOME": "revenue",
    "TOTAL_OPERATE_INCOME": "revenue",
    "NETPROFIT": "net_profit",
    "NET_PROFIT_ATSOPC": "net_profit",
    "EBIT": "ebit",
    "EBITDA": "ebitda",
}
_BALANCE_MAP: Dict[str, str] = {
    "TOTAL_ASSETS": "total_assets",
    "TOTAL_LIABILITIES": "total_liabilities",
    "TOTAL_EQUITY": "equity",
    "TOTAL_SHARES": "total_shares",
}
_CASHFLOW_MAP: Dict[str, str] = {
    "OPERATE_CASH_FLOW": "operating_cash_flow",
    "FREE_CASH_FLOW": "free_cash_flow",
}


class AKShareProvider(FinancialDataProvider):
    """Free, no-key provider backed by AKShare (East Money / Sina / public).

    Every call is isolated — no retry, no budget — so that the upstream
    :class:`ProviderRouter` is the sole owner of retry and fallback logic.
    """

    name = "akshare"

    def __init__(self) -> None:
        self._ak: Any = None

    def _import(self) -> Any:
        if self._ak is None:
            try:
                import akshare as ak  # type: ignore[import-untyped]
            except ImportError as exc:
                raise AuthenticationError("Install the optional 'akshare' dependency first.") from exc
            self._ak = ak
        return self._ak

    # ------------------------------------------------------------------
    # Company profile
    # ------------------------------------------------------------------

    def get_profile(self, symbol: CanonicalSymbol) -> Optional[CompanyProfile]:
        ak = self._import()
        try:
            names = ak.stock_info_a_code_name()
        except Exception as exc:
            raise ProviderError(f"AKShare stock_info_a_code_name failed: {exc}") from exc
        code = symbol.code
        row = names[names["code"] == code]
        if row.empty:
            return None
        name = str(row.iloc[0].get("name", ""))
        return CompanyProfile(symbol=symbol, name=name or str(symbol))

    # ------------------------------------------------------------------
    # Daily bars (RAW / QFQ / HFQ)
    # ------------------------------------------------------------------

    def get_daily_bars(
        self,
        symbol: CanonicalSymbol,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjustment: str = "RAW",
    ) -> List[MarketBar]:
        ak = self._import()
        adjust_map = {"RAW": "", "QFQ": "qfq", "HFQ": "hfq"}
        adj = adjust_map.get(adjustment, "")
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol.code,
                period="daily",
                start_date=(start_date or "").replace("-", ""),
                end_date=(end_date or "").replace("-", ""),
                adjust=adj,
            )
        except Exception as exc:
            raise ProviderError(f"AKShare stock_zh_a_hist failed: {exc}") from exc
        if df is None or df.empty:
            raise EmptyDataError(f"No AKShare bars for {symbol} ({adjustment}).")
        bars: List[MarketBar] = []
        for _, row in df.iterrows():
            trade_date = _iso_date(row.get("日期"))
            if not trade_date:
                continue
            bars.append(
                MarketBar(
                    symbol=symbol,
                    trade_date=trade_date[:10],
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=_value(row, "成交量"),
                    amount=_value(row, "成交额"),
                    adjustment=adjustment,
                )
            )
        return bars

    # ------------------------------------------------------------------
    # Financial statements (best-effort from East Money)
    # ------------------------------------------------------------------

    def get_financial_statements(
        self, symbol: CanonicalSymbol, *, research_as_of: Optional[str] = None
    ) -> List[FinancialStatement]:
        ak = self._import()
        cutoff = research_as_of or "9999-12-31T23:59:59+08:00"
        statements: List[FinancialStatement] = []
        for stmt_type, endpoint, field_map in [
            ("income", "stock_profit_sheet_by_report_em", _INCOME_MAP),
            ("balance", "stock_balance_sheet_by_report_em", _BALANCE_MAP),
            ("cashflow", "stock_cash_flow_sheet_by_report_em", _CASHFLOW_MAP),
        ]:
            try:
                endpoint_fn = getattr(ak, endpoint)
                df = endpoint_fn(symbol.code)
            except Exception:
                continue  # best-effort: skip if this statement type fails
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                published_at = _iso_date(row.get("REPORT_DATE") or row.get("END_DATE"))
                if published_at and published_at > cutoff:
                    continue
                values: Dict[str, Optional[float]] = {}
                for col, canonical in field_map.items():
                    if col in row.index:
                        values[canonical] = _value(row, col)
                if not values:
                    continue
                statements.append(
                    FinancialStatement(
                        statement_type=stmt_type,  # type: ignore[arg-type]
                        fiscal_period=str(row.get("REPORT_DATE", row.get("END_DATE", "")))[:10],
                        period_basis="UNKNOWN",
                        published_at=published_at,
                        available_at=published_at,
                        currency="CNY",
                        unit="CNY",
                        values=values,
                    )
                )
        return statements