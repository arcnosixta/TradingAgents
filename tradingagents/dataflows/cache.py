"""TTL-based in-memory cache for market data requests.

Avoids redundant yfinance / FRED / Alpha Vantage HTTP calls when the same
data is requested repeatedly within a short window (e.g. multiple analysts
reading the same ticker in one run, or a user re-running the same analysis).

Usage:
    from tradingagents.dataflows.cache import market_cache
    data = market_cache.get_or_fetch("yf_history", ticker="NVDA", start="2024-01-01", ...)
"""

from __future__ import annotations

import hashlib
import json
import time
from threading import Lock
from typing import Any, Callable


class TTLCache:
    """Thread-safe in-memory cache with per-entry TTL (time-to-live)."""

    def __init__(self, default_ttl: int = 300):
        """Args:
            default_ttl: Default TTL in seconds (5 minutes).
        """
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()

    def _make_key(self, namespace: str, **kwargs) -> str:
        raw = f"{namespace}:{json.dumps(kwargs, sort_keys=True, default=str)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, namespace: str, **kwargs) -> Any | None:
        key = self._make_key(namespace, **kwargs)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > self.default_ttl:
                del self._store[key]
                return None
            return value

    def set(self, namespace: str, value: Any, ttl: int | None = None, **kwargs):
        key = self._make_key(namespace, **kwargs)
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def invalidate(self, namespace: str, **kwargs):
        key = self._make_key(namespace, **kwargs)
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        with self._lock:
            self._store.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            now = time.monotonic()
            alive = sum(1 for ts, _ in self._store.values() if now - ts <= self.default_ttl)
            return {"total_entries": len(self._store), "alive": alive, "expired": len(self._store) - alive}


# Singleton — import and use directly
market_cache = TTLCache(default_ttl=300)


def cached(namespace: str, ttl: int | None = None):
    """Decorator that caches function results by arguments.

    Example:
        @cached("yf_history", ttl=600)
        def get_history(ticker, start, end):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Build cache key from function name + all args
            cache_kwargs = {"_fn": fn.__name__, "_args": args, **kwargs}
            result = market_cache.get(namespace, **cache_kwargs)
            if result is not None:
                return result
            result = fn(*args, **kwargs)
            market_cache.set(namespace, result, ttl=ttl, **cache_kwargs)
            return result
        wrapper.__wrapped__ = fn
        return wrapper
    return decorator
