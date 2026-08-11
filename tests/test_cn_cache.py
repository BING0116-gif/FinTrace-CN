"""Tests for the TTL provider cache."""
import time

from src.cn.providers.cache import CACHE_TTL, ProviderCache


def test_cache_miss_returns_none():
    cache = ProviderCache()
    assert cache.get("nonexistent") is None


def test_cache_set_and_get():
    cache = ProviderCache()
    cache.set("greeting", "hello", ttl_seconds=60)
    assert cache.get("greeting") == "hello"


def test_cache_expiry():
    cache = ProviderCache()
    cache.set("ephemeral", 42, ttl_seconds=0.1)
    assert cache.get("ephemeral") == 42
    time.sleep(0.15)
    assert cache.get("ephemeral") is None


def test_cache_invalidate():
    cache = ProviderCache()
    cache.set("key", "value", ttl_seconds=60)
    cache.invalidate("key")
    assert cache.get("key") is None


def test_cache_clear():
    cache = ProviderCache()
    cache.set("a", 1, ttl_seconds=60)
    cache.set("b", 2, ttl_seconds=60)
    cache.clear()
    assert cache.size == 0
    assert cache.hit_count == 0


def test_cache_hit_miss_counts():
    cache = ProviderCache()
    assert cache.hit_count == 0
    assert cache.miss_count == 0
    cache.get("miss")  # miss
    cache.set("hit", "x", ttl_seconds=60)
    cache.get("hit")  # hit
    assert cache.hit_count == 1
    assert cache.miss_count == 1


def test_make_key_includes_all_params():
    key = ProviderCache.make_key("tushare", "get_profile", symbol="600519.SH")
    assert "tushare" in key
    assert "get_profile" in key
    assert "600519.SH" in key


def test_make_key_sorts_params():
    k1 = ProviderCache.make_key("p", "e", a="1", b="2")
    k2 = ProviderCache.make_key("p", "e", b="2", a="1")
    assert k1 == k2


def test_cache_ttl_defaults_exist():
    assert "profile" in CACHE_TTL
    assert "bars" in CACHE_TTL
    assert "financials" in CACHE_TTL
    assert CACHE_TTL["profile"] > CACHE_TTL["bars"]  # profile TTL >> bars TTL