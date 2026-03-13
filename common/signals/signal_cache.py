"""Thread-safe TTL cache for composite signals."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common.signals.aggregator import CompositeSignal

DEFAULT_TTL_SECONDS = 300  # 5 minutes


class SignalCache:
    """Thread-safe cache for CompositeSignal objects with per-entry TTL."""

    def __init__(self, ttl: float = DEFAULT_TTL_SECONDS):
        self._ttl = ttl
        self._store: dict[str, tuple[float, CompositeSignal]] = {}
        self._lock = threading.Lock()

    def get(self, symbol: str) -> CompositeSignal | None:
        """Return cached signal if present and not expired, else None."""
        with self._lock:
            entry = self._store.get(symbol)
            if entry is None:
                return None
            ts, signal = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[symbol]
                return None
            return signal

    def set(self, symbol: str, signal: CompositeSignal) -> None:
        """Store a signal with current timestamp."""
        with self._lock:
            self._store[symbol] = (time.monotonic(), signal)

    def invalidate(self, symbol: str) -> None:
        """Remove a specific symbol from the cache."""
        with self._lock:
            self._store.pop(symbol, None)

    def invalidate_all(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        """Number of entries (including possibly expired)."""
        with self._lock:
            return len(self._store)
