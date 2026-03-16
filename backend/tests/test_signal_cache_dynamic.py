"""Tests for dynamic signal cache TTL with regime awareness."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from analysis.services.signal_service import (
    SIGNAL_CACHE_MAX_SIZE,
    _evict_lru,
    _get_cache_ttl,
    _signal_cache,
    _signal_cache_lock,
    _signal_cache_order,
    clear_signal_cache,
    get_cache_stats,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_signal_cache()
    yield
    clear_signal_cache()


class TestDynamicCacheTTL:
    def test_hv_regime_gets_30s_ttl(self):
        assert _get_cache_ttl("HIGH_VOLATILITY") == 30

    def test_ranging_regime_gets_120s_ttl(self):
        assert _get_cache_ttl("RANGING") == 120

    def test_default_regime_gets_60s_ttl(self):
        assert _get_cache_ttl(None) == 60

    def test_unknown_regime_string_gets_default(self):
        assert _get_cache_ttl("SOME_NEW_REGIME") == 60

    def test_strong_trend_down_gets_30s(self):
        assert _get_cache_ttl("STRONG_TREND_DOWN") == 30


class TestCacheStats:
    def test_initial_stats_zero(self):
        stats = get_cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

    @patch("analysis.services.signal_service.SignalService._get_aggregator")
    @patch("analysis.services.signal_service.SignalService._get_regime_state")
    @patch("analysis.services.signal_service.SignalService._get_technical_score", return_value=None)
    @patch(
        "analysis.services.signal_service.SignalService._get_ml_prediction",
        return_value=(None, None),
    )
    @patch(
        "analysis.services.signal_service.SignalService._get_sentiment_signal",
        return_value=(None, None),
    )
    @patch("analysis.services.signal_service.SignalService._get_scanner_score", return_value=None)
    @patch("analysis.services.signal_service.SignalService._get_win_rate", return_value=None)
    def test_cache_miss_then_hit(self, *mocks):
        from analysis.services.signal_service import SignalService

        mock_signal = MagicMock()
        mock_signal.symbol = "BTC/USDT"
        mock_signal.asset_class = "crypto"
        mock_signal.timestamp.isoformat.return_value = "2026-01-01T00:00:00"
        mock_signal.composite_score = 50.0
        mock_signal.signal_label = "neutral"
        mock_signal.entry_approved = False
        mock_signal.position_modifier = 1.0
        mock_signal.hard_disabled = False
        mock_signal.technical_score = None
        mock_signal.regime_score = None
        mock_signal.ml_score = None
        mock_signal.sentiment_score = None
        mock_signal.scanner_score = None
        mock_signal.screen_score = None
        mock_signal.ml_confidence = None
        mock_signal.sentiment_conviction = None
        mock_signal.regime_confidence = None
        mock_signal.sources_available = 0
        mock_signal.reasoning = []
        mocks[6].return_value.compute.return_value = mock_signal
        mocks[5].return_value = None  # regime_state

        SignalService.get_signal("BTC/USDT", "crypto")
        stats1 = get_cache_stats()
        assert stats1["misses"] == 1

        SignalService.get_signal("BTC/USDT", "crypto")
        stats2 = get_cache_stats()
        assert stats2["hits"] == 1


class TestLRUEviction:
    def test_eviction_at_max_size(self):
        with _signal_cache_lock:
            for i in range(SIGNAL_CACHE_MAX_SIZE + 10):
                key = f"key_{i}"
                _signal_cache[key] = (time.monotonic(), {"_regime": None})
                _signal_cache_order.append(key)
            _evict_lru()
        assert len(_signal_cache) == SIGNAL_CACHE_MAX_SIZE

    def test_eviction_removes_oldest(self):
        with _signal_cache_lock:
            for i in range(SIGNAL_CACHE_MAX_SIZE + 5):
                key = f"key_{i}"
                _signal_cache[key] = (time.monotonic(), {"_regime": None})
                _signal_cache_order.append(key)
            _evict_lru()
        # First 5 keys should be evicted
        assert "key_0" not in _signal_cache
        assert "key_4" not in _signal_cache
        assert f"key_{SIGNAL_CACHE_MAX_SIZE + 4}" in _signal_cache


class TestThreadSafety:
    def test_concurrent_cache_access(self):
        """Verify no deadlocks with concurrent reads."""
        errors = []

        def writer():
            try:
                with _signal_cache_lock:
                    key = f"thread_{threading.current_thread().name}"
                    _signal_cache[key] = (time.monotonic(), {"_regime": "RANGING"})
                    _signal_cache_order.append(key)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert len(errors) == 0
