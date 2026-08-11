"""Deterministic provider routing with fallback, circuit breaker, and cache.

The router never retries the same provider indefinitely — it stops after a
configurable number of fallback attempts and raises the last error so that
the caller (Agent / ResearchState) can decide whether to attempt recovery.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, TypeVar

from ..domain import CompanyProfile, FinancialStatement, MarketBar
from ..errors import (
    AuthenticationError,
    EmptyDataError,
    PermissionError,
    ProviderError,
    RateLimitError,
    TimeoutError,
    UnsupportedSymbolError,
)
from ..symbols import CanonicalSymbol
from .base import FinancialDataProvider
from .cache import CACHE_TTL, ProviderCache

T = TypeVar("T")


@dataclass
class CircuitBreakerState:
    """Tracks consecutive failures for a single provider."""

    failures: int = 0
    opened_at: Optional[float] = None
    cooldown_seconds: float = 60.0

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        return time.monotonic() - self.opened_at < self.cooldown_seconds

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= 3:
            self.opened_at = time.monotonic()

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None


# Each error type maps to a specific routing decision.
_ROUTING_TABLE: Dict[type, str] = {
    RateLimitError: "cooldown_then_fallback",
    TimeoutError: "retry_then_fallback",
    AuthenticationError: "fail_fast",
    PermissionError: "fail_fast",
    EmptyDataError: "fallback",
    UnsupportedSymbolError: "fail_fast",
    ProviderError: "fallback",
}


class ProviderRouter:
    """Route requests through a chain of providers with typed error handling.

    Usage::

        router = ProviderRouter(primary, fallback, snapshot)
        profile = router.get_profile(symbol)
        bars = router.get_daily_bars(symbol, start_date="...", end_date="...")
    """

    def __init__(
        self,
        primary: FinancialDataProvider,
        *fallbacks: FinancialDataProvider,
        cache: Optional[ProviderCache] = None,
        max_retries: int = 1,
        retry_delay_seconds: float = 1.0,
    ):
        self._providers: List[FinancialDataProvider] = [primary, *fallbacks]
        self._cache = cache or ProviderCache()
        self._max_retries = max_retries
        self._retry_delay = retry_delay_seconds
        self._breakers: Dict[str, CircuitBreakerState] = {
            provider.name: CircuitBreakerState() for provider in self._providers
        }

    # ------------------------------------------------------------------
    # Public API  — mirrors FinancialDataProvider but adds caching
    # ------------------------------------------------------------------

    def get_profile(self, symbol: CanonicalSymbol) -> Optional[CompanyProfile]:
        cache_key = ProviderCache.make_key("profile", "get_profile", symbol=str(symbol))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = self._route("get_profile", symbol, endpoint="profile")
        if result is not None:
            self._cache.set(cache_key, result, CACHE_TTL["profile"])
        return result

    def get_daily_bars(
        self,
        symbol: CanonicalSymbol,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjustment: str = "RAW",
    ) -> List[MarketBar]:
        cache_key = ProviderCache.make_key(
            "bars", "get_daily_bars", symbol=str(symbol), start_date=start_date or "", end_date=end_date or "", adjustment=adjustment,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = self._route("get_daily_bars", symbol, start_date=start_date, end_date=end_date, adjustment=adjustment, endpoint="bars")
        self._cache.set(cache_key, result, CACHE_TTL["bars"])
        return result

    def get_financial_statements(
        self, symbol: CanonicalSymbol, *, research_as_of: Optional[str] = None
    ) -> List[FinancialStatement]:
        cache_key = ProviderCache.make_key("financials", "get_financial_statements", symbol=str(symbol), research_as_of=research_as_of or "")
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = self._route("get_financial_statements", symbol, research_as_of=research_as_of, endpoint="financials")
        self._cache.set(cache_key, result, CACHE_TTL["financials"])
        return result

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def cache(self) -> ProviderCache:
        return self._cache

    @property
    def provider_names(self) -> List[str]:
        return [p.name for p in self._providers]

    # ------------------------------------------------------------------
    # Internal routing
    # ------------------------------------------------------------------

    def _route(self, method_name: str, symbol: CanonicalSymbol, *, endpoint: str, **kwargs: object) -> T:
        last_error: Optional[Exception] = None
        for provider in self._providers:
            breaker = self._breakers[provider.name]
            if breaker.is_open:
                last_error = ProviderError(f"Circuit breaker open for '{provider.name}'.")
                continue

            method: Callable[..., T] = getattr(provider, method_name)
            for attempt in range(self._max_retries + 1):
                try:
                    result = method(symbol, **kwargs)
                    breaker.record_success()
                    return result
                except (RateLimitError, TimeoutError) as exc:
                    last_error = exc
                    if attempt < self._max_retries:
                        time.sleep(self._retry_delay * (attempt + 1))
                    else:
                        breaker.record_failure()
                except (AuthenticationError, PermissionError, UnsupportedSymbolError) as exc:
                    last_error = exc
                    breaker.record_failure()
                    break  # fail-fast: don't retry, move to next provider
                except (EmptyDataError, ProviderError) as exc:
                    last_error = exc
                    breaker.record_failure()
                    break  # no retry for semantic errors, try next provider

        # All providers exhausted
        raise last_error or ProviderError("All providers failed for an unknown reason.")


def build_default_router(
    *,
    tushare_provider: Optional[FinancialDataProvider] = None,
    akshare_provider: Optional[FinancialDataProvider] = None,
    snapshot_provider: Optional[FinancialDataProvider] = None,
    cache: Optional[ProviderCache] = None,
) -> ProviderRouter:
    """Build a router with the standard A-share fallback chain.

    The chain order is::

        TushareProvider -> AKShareProvider -> SnapshotProvider
    """
    providers: List[FinancialDataProvider] = []
    if tushare_provider is not None:
        providers.append(tushare_provider)
    if akshare_provider is not None:
        providers.append(akshare_provider)
    if snapshot_provider is not None:
        providers.append(snapshot_provider)
    if not providers:
        raise ValueError("At least one provider is required to build a router.")
    return ProviderRouter(providers[0], *providers[1:], cache=cache)