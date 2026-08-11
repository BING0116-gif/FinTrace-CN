"""TTL-based in-memory cache for provider responses.

Cache keys are composite strings built from the provider name, endpoint, and
every parameter value.  Different data categories use different TTLs so that
real-time prices and annual financials are cached for appropriate durations.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


class CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl_seconds: float):
        self.value = value
        self.expires_at = time.monotonic() + ttl_seconds

    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class ProviderCache:
    """Simple thread-safe (GIL) in-memory cache with per-key TTL.

    Exposed as a separate class so that callers can inspect hit/miss counts
    without coupling to the Router internals.
    """

    def __init__(self):
        self._data: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None or entry.is_expired():
            self._misses += 1
            return None
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._data[key] = CacheEntry(value, ttl_seconds)

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def hit_count(self) -> int:
        return self._hits

    @property
    def miss_count(self) -> int:
        return self._misses

    @property
    def size(self) -> int:
        return len(self._data)

    # ------------------------------------------------------------------
    # Cache-key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(provider_name: str, endpoint: str, **params: Any) -> str:
        parts = [provider_name, endpoint]
        for key in sorted(params):
            parts.append(f"{key}={params[key]}")
        return ":".join(parts)


# Default TTLs (seconds) — conservative for A-share research.
CACHE_TTL: Dict[str, float] = {
    "profile": 86400.0,       # 24 h — company profile rarely changes
    "bars": 300.0,             # 5 min — intraday
    "financials": 86400.0,     # 24 h — quarterly snapshots
    "indicators": 86400.0,     # 24 h
    "peers": 86400.0,          # 24 h
}