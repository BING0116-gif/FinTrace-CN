"""Tests for provider router, circuit breaker, and fallback chain."""

import pytest

from src.cn.domain import CompanyProfile, MarketBar
from src.cn.errors import EmptyDataError, ProviderError, RateLimitError, TimeoutError
from src.cn.providers.base import FinancialDataProvider
from src.cn.providers.cache import ProviderCache
from src.cn.providers.router import CircuitBreakerState, ProviderRouter, build_default_router
from src.cn.symbols import CanonicalSymbol


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _OkProvider(FinancialDataProvider):
    name = "ok"
    def get_profile(self, symbol, **kwargs):
        return CompanyProfile(symbol=symbol, name="OK")
    def get_daily_bars(self, symbol, **kwargs):
        return [MarketBar(symbol=symbol, trade_date="2026-01-01", open=1.0, high=1.1, low=0.9, close=1.0, volume=None, amount=None, adjustment="RAW")]
    def get_financial_statements(self, symbol, **kwargs):
        return []


class _FailingProvider(FinancialDataProvider):
    name = "failing"
    def __init__(self, error=EmptyDataError("no data")):
        self._error = error
    def get_profile(self, symbol, **kwargs):
        raise self._error
    def get_daily_bars(self, symbol, **kwargs):
        raise self._error
    def get_financial_statements(self, symbol, **kwargs):
        raise self._error


class _CooldownProvider(FinancialDataProvider):
    """Simulates a provider that fails N times then succeeds."""
    name = "cooldown"
    def __init__(self, fail_count=1):
        self._remaining = fail_count
    def get_profile(self, symbol, **kwargs):
        if self._remaining > 0:
            self._remaining -= 1
            raise RateLimitError("cooldown")
        return CompanyProfile(symbol=symbol, name="Recovered")

    def get_daily_bars(self, symbol, **kwargs):
        return self.get_profile(symbol, **kwargs)
    def get_financial_statements(self, symbol, **kwargs):
        return []


SYM = CanonicalSymbol("600519", "SH")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_router_uses_primary_when_ok():
    router = ProviderRouter(_OkProvider())
    profile = router.get_profile(SYM)
    assert profile is not None
    assert profile.name == "OK"


def test_router_falls_back_when_primary_fails():
    primary = _FailingProvider(EmptyDataError("no data"))
    fallback = _OkProvider()
    router = ProviderRouter(primary, fallback)
    profile = router.get_profile(SYM)
    assert profile is not None
    assert profile.name == "OK"


def test_router_raises_when_all_fail():
    router = ProviderRouter(_FailingProvider(EmptyDataError("fail")))
    with pytest.raises(ProviderError):
        router.get_profile(SYM)


def test_router_raises_last_error():
    router = ProviderRouter(
        _FailingProvider(EmptyDataError("primary empty")),
        _FailingProvider(EmptyDataError("fallback empty")),
    )
    with pytest.raises(ProviderError, match="fallback empty"):
        router.get_profile(SYM)


def test_cache_hits_avoid_provider_call():
    primary = _FailingProvider(EmptyDataError("should not be called"))
    router = ProviderRouter(primary)
    router.cache.set("profile:get_profile:symbol=600519.SH", CompanyProfile(symbol=SYM, name="Cached"), 60)
    # inject a cache entry with the right key format
    router._cache.set(
        ProviderCache.make_key("profile", "get_profile", symbol=str(SYM)),
        CompanyProfile(symbol=SYM, name="Cached"), 60,
    )
    profile = router.get_profile(SYM)
    assert profile.name == "Cached"


def test_circuit_breaker_opens_after_three_failures():
    primary = _FailingProvider(EmptyDataError("fail"))
    cb = CircuitBreakerState()
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open
    assert cb.failures == 3


def test_circuit_breaker_records_success():
    cb = CircuitBreakerState()
    cb.record_failure()
    cb.record_success()
    assert cb.failures == 0
    assert not cb.is_open


def test_router_skips_open_circuit_breaker():
    """When the primary circuit breaker is open, the router moves to fallback."""
    primary = _FailingProvider(EmptyDataError("breaker open"))
    fallback = _OkProvider()
    router = ProviderRouter(primary, fallback)
    # Manually open the breaker for primary
    router._breakers["failing"].record_failure()
    router._breakers["failing"].record_failure()
    router._breakers["failing"].record_failure()
    assert router._breakers["failing"].is_open
    profile = router.get_profile(SYM)
    assert profile.name == "OK"


def test_router_retries_on_rate_limit_then_falls_back():
    primary = _FailingProvider(RateLimitError("rate limited"))
    fallback = _OkProvider()
    router = ProviderRouter(primary, fallback, max_retries=1, retry_delay_seconds=0.01)
    profile = router.get_profile(SYM)
    assert profile.name == "OK"


def test_build_default_router_requires_at_least_one_provider():
    with pytest.raises(ValueError, match="At least one provider"):
        build_default_router()


def test_build_default_router_with_snapshot_only():
    from src.cn.providers.snapshot import SnapshotProvider
    from pathlib import Path
    snapshot = SnapshotProvider(Path(__file__).parents[1] / "tests" / "fixtures" / "cn" / "600519.SH_illustrative_v1.json")
    router = build_default_router(snapshot_provider=snapshot)
    profile = router.get_profile(SYM)
    assert profile is not None


def test_router_provider_names():
    router = ProviderRouter(_OkProvider(), _FailingProvider(EmptyDataError("x")))
    assert router.provider_names == ["ok", "failing"]


def test_router_cache_property():
    router = ProviderRouter(_OkProvider())
    assert isinstance(router.cache, ProviderCache)


def test_router_bars_route():
    router = ProviderRouter(_OkProvider())
    bars = router.get_daily_bars(SYM)
    assert len(bars) == 1
    assert bars[0].close == 1.0


def test_router_financials_route():
    router = ProviderRouter(_OkProvider())
    stmts = router.get_financial_statements(SYM)
    assert stmts == []