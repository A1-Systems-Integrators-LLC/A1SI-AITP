"""Tests for Alpha Phase 2 — Data Sources.

Covers: Fear & Greed, Reddit sentiment, CoinGecko expanded, DefiLlama TVL,
FRED adapter, dynamic economic calendar, signal weight rebalance, aggregator
modifiers, and scheduled task executors.
"""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ── Fear & Greed Index ──────────────────────────────────────────────────────


class TestFearGreedIndex:
    """Tests for common.market_data.fear_greed."""

    def _import(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.market_data.fear_greed import (
            clear_cache,
            fetch_fear_greed,
            get_fear_greed_signal,
        )
        clear_cache()
        return fetch_fear_greed, get_fear_greed_signal, clear_cache

    @patch("common.market_data.fear_greed.requests.get")
    def test_fetch_fear_greed_success(self, mock_get):
        fetch, _, clear = self._import()
        clear()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"value": "25", "value_classification": "Extreme Fear"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = fetch()
        assert result is not None
        assert result["value"] == 25
        assert result["classification"] == "Extreme Fear"

    @patch("common.market_data.fear_greed.requests.get")
    def test_fetch_fear_greed_failure(self, mock_get):
        _, _, clear = self._import()
        clear()
        from common.market_data.fear_greed import fetch_fear_greed
        mock_get.side_effect = Exception("timeout")
        result = fetch_fear_greed()
        assert result is None

    @patch("common.market_data.fear_greed.requests.get")
    def test_fear_greed_cache(self, mock_get):
        fetch, _, clear = self._import()
        clear()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"value": "50", "value_classification": "Neutral"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        fetch()
        fetch()  # Second call should use cache
        assert mock_get.call_count == 1

    def test_signal_extreme_fear(self):
        _, get_signal, _ = self._import()
        signal = get_signal(data={"value": 10, "classification": "Extreme Fear"})
        assert signal["modifier"] == 10
        assert signal["score"] >= 70

    def test_signal_extreme_greed(self):
        _, get_signal, _ = self._import()
        signal = get_signal(data={"value": 85, "classification": "Extreme Greed"})
        assert signal["modifier"] == -10
        assert signal["score"] <= 30

    def test_signal_neutral(self):
        _, get_signal, _ = self._import()
        signal = get_signal(data={"value": 50, "classification": "Neutral"})
        assert signal["modifier"] == 0

    @patch("common.market_data.fear_greed.fetch_fear_greed")
    def test_signal_none(self, mock_fetch):
        _, get_signal, _ = self._import()
        mock_fetch.return_value = None
        signal = get_signal(data=None)
        assert signal["modifier"] == 0
        assert signal["value"] is None


# ── Reddit Sentiment ────────────────────────────────────────────────────────


class TestRedditSentiment:
    """Tests for common.data_pipeline.reddit_adapter."""

    def _import(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.data_pipeline.reddit_adapter import (
            RedditPost,
            clear_cache,
            fetch_reddit_sentiment,
            score_post,
        )
        clear_cache()
        return RedditPost, score_post, fetch_reddit_sentiment, clear_cache

    def test_score_post_bullish(self):
        post_cls, score_post, _, _ = self._import()
        post = post_cls(
            title="BTC bullish breakout moon pump!",
            selftext="",
            score=100,
            upvote_ratio=0.9,
            subreddit="Bitcoin",
            created_utc=time.time(),
        )
        s = score_post(post)
        assert s > 0

    def test_score_post_bearish(self):
        post_cls, score_post, _, _ = self._import()
        post = post_cls(
            title="Crypto crash dump selloff incoming",
            selftext="",
            score=50,
            upvote_ratio=0.8,
            subreddit="CryptoCurrency",
            created_utc=time.time(),
        )
        s = score_post(post)
        assert s < 0

    def test_score_post_neutral(self):
        post_cls, score_post, _, _ = self._import()
        post = post_cls(
            title="What happened today?",
            selftext="",
            score=10,
            upvote_ratio=0.5,
            subreddit="ethereum",
            created_utc=time.time(),
        )
        s = score_post(post)
        assert s == 0.0

    @patch("common.data_pipeline.reddit_adapter.fetch_subreddit_posts")
    def test_fetch_reddit_sentiment_aggregation(self, mock_fetch):
        post_cls, _, fetch_sentiment, clear = self._import()
        clear()
        mock_fetch.return_value = [
            post_cls("BTC moon pump rally", "", 100, 0.9, "Bitcoin", time.time()),
            post_cls("crash dump sell", "", 50, 0.8, "Bitcoin", time.time()),
        ]
        result = fetch_sentiment()
        assert "score" in result
        assert "post_count" in result
        assert "modifier" in result
        assert "signal_score" in result
        assert 0 <= result["signal_score"] <= 100

    @patch("common.data_pipeline.reddit_adapter.fetch_subreddit_posts")
    def test_reddit_empty_posts(self, mock_fetch):
        _, _, fetch_sentiment, clear = self._import()
        clear()
        mock_fetch.return_value = []
        result = fetch_sentiment()
        assert result["score"] == 0.0
        assert result["modifier"] == 0


# ── CoinGecko Expanded ──────────────────────────────────────────────────────


class TestCoinGeckoExpanded:
    """Tests for CoinGecko trending + DeFi additions."""

    def _import(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.market_data.coingecko import (
            clear_cache,
            fetch_global_defi_data,
            fetch_trending_coins,
            get_trending_modifier,
        )
        clear_cache()
        return fetch_trending_coins, get_trending_modifier, fetch_global_defi_data

    @patch("common.market_data.coingecko.requests.get")
    def test_fetch_trending_coins(self, mock_get):
        fetch_trending, _, _ = self._import()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "coins": [
                    {"item": {"id": "btc", "name": "Bitcoin",
                              "symbol": "btc", "market_cap_rank": 1}},
                    {"item": {"id": "eth", "name": "Ethereum",
                              "symbol": "eth", "market_cap_rank": 2}},
                ]
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()
        coins = fetch_trending()
        assert len(coins) == 2
        assert coins[0]["symbol"] == "BTC"

    @patch("common.market_data.coingecko.fetch_trending_coins")
    def test_trending_modifier_found(self, mock_trending):
        _, get_mod, _ = self._import()
        mock_trending.return_value = [
            {"symbol": "BTC"},
            {"symbol": "ETH"},
        ]
        assert get_mod("BTC/USDT") == 3

    @patch("common.market_data.coingecko.fetch_trending_coins")
    def test_trending_modifier_not_found(self, mock_trending):
        _, get_mod, _ = self._import()
        mock_trending.return_value = [{"symbol": "BTC"}]
        assert get_mod("SOL/USDT") == 0

    @patch("common.market_data.coingecko.requests.get")
    def test_fetch_global_defi_data(self, mock_get):
        _, _, fetch_defi = self._import()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "data": {
                    "defi_market_cap": "100000000000",
                    "eth_market_cap": "200000000000",
                    "defi_dominance": "3.5",
                    "top_coin_name": "Lido",
                }
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = fetch_defi()
        assert result is not None
        assert result["defi_dominance"] == 3.5


# ── DefiLlama TVL ───────────────────────────────────────────────────────────


class TestDefiLlamaTVL:
    """Tests for common.market_data.defillama."""

    def _import(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.market_data.defillama import clear_cache, fetch_chain_tvl, get_tvl_signal
        clear_cache()
        return fetch_chain_tvl, get_tvl_signal

    @patch("common.market_data.defillama.requests.get")
    def test_fetch_chain_tvl(self, mock_get):
        fetch, _ = self._import()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "Ethereum", "tvl": 50_000_000_000},
                {"name": "Solana", "tvl": 5_000_000_000},
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = fetch()
        assert "Ethereum" in result
        assert result["Ethereum"]["native_token"] == "ETH"

    @patch("common.market_data.defillama.fetch_chain_tvl")
    def test_tvl_signal_found(self, mock_tvl):
        _, get_signal = self._import()
        mock_tvl.return_value = {
            "Ethereum": {"tvl": 50_000_000_000, "native_token": "ETH"},
        }
        signal = get_signal("ETH/USDT")
        assert signal["chain"] == "Ethereum"
        assert signal["tvl"] == 50_000_000_000

    @patch("common.market_data.defillama.fetch_chain_tvl")
    def test_tvl_signal_not_found(self, mock_tvl):
        _, get_signal = self._import()
        mock_tvl.return_value = {"Ethereum": {"tvl": 50e9, "native_token": "ETH"}}
        signal = get_signal("DOGE/USDT")
        assert signal["chain"] is None

    @patch("common.market_data.defillama.fetch_chain_tvl")
    def test_tvl_signal_failure(self, mock_tvl):
        _, get_signal = self._import()
        mock_tvl.return_value = None
        signal = get_signal("ETH/USDT")
        assert signal["modifier"] == 0


# ── FRED Adapter ────────────────────────────────────────────────────────────


class TestFREDAdapter:
    """Tests for common.market_data.fred_adapter."""

    def _import(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.market_data.fred_adapter import (
            _compute_macro_score,
            clear_cache,
            fetch_macro_snapshot,
            fetch_series_latest,
        )
        clear_cache()
        return fetch_series_latest, fetch_macro_snapshot, _compute_macro_score

    @patch.dict("os.environ", {"FRED_API_KEY": "test_key"})
    @patch("common.market_data.fred_adapter.requests.get")
    def test_fetch_series_latest(self, mock_get):
        fetch, _, _ = self._import()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"observations": [{"value": "5.33"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = fetch("DFF")
        assert result == 5.33

    @patch.dict("os.environ", {}, clear=True)
    def test_fetch_series_no_api_key(self):
        fetch, _, _ = self._import()
        import os
        old = os.environ.pop("FRED_API_KEY", None)
        try:
            result = fetch("DFF")
            assert result is None
        finally:
            if old:
                os.environ["FRED_API_KEY"] = old

    def test_macro_score_all_bullish(self):
        _, _, compute = self._import()
        score = compute(fed_funds=1.5, yield_curve=1.0, vix=12.0, dxy=92.0)
        assert score > 65

    def test_macro_score_all_bearish(self):
        _, _, compute = self._import()
        score = compute(fed_funds=6.0, yield_curve=-1.0, vix=35.0, dxy=110.0)
        assert score < 30

    def test_macro_score_all_none(self):
        _, _, compute = self._import()
        score = compute(None, None, None, None)
        assert score == 50.0


# ── Dynamic Economic Calendar ───────────────────────────────────────────────


class TestEconomicCalendar:
    """Tests for common.calendar.economic_events."""

    def _import(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.calendar.economic_events import (
            _parse_ff_date,
            clear_ff_cache,
            fetch_forexfactory_events,
            get_position_modifier,
            get_upcoming_events,
        )
        clear_ff_cache()
        return get_upcoming_events, get_position_modifier, fetch_forexfactory_events, _parse_ff_date

    @patch("common.calendar.economic_events.requests.get")
    def test_fetch_forexfactory_events(self, mock_get):
        _, _, fetch_ff, _ = self._import()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"title": "NFP", "impact": "High", "country": "USD", "date": "2026-03-20T08:30:00"},
                {"title": "GDP", "impact": "Low", "country": "USD", "date": "2026-03-20T10:00:00"},
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()
        events = fetch_ff()
        assert len(events) == 1  # Only High, not Low
        assert events[0]["name"] == "NFP"
        assert events[0]["impact"] == "high"

    @patch("common.calendar.economic_events.fetch_forexfactory_events")
    def test_get_upcoming_events_uses_ff_first(self, mock_ff):
        get_events, _, _, _ = self._import()
        now = datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc)
        mock_ff.return_value = [
            {
                "name": "CPI Release",
                "impact": "high",
                "date_str": "2026-03-17T14:00:00+00:00",
                "affected_currencies": ["USD"],
            },
        ]
        events = get_events(hours=4, now=now)
        assert len(events) == 1
        assert events[0]["name"] == "CPI Release"

    @patch("common.calendar.economic_events.fetch_forexfactory_events")
    def test_fallback_to_static_when_ff_empty(self, mock_ff):
        get_events, _, _, _ = self._import()
        mock_ff.return_value = []
        # Use a time near a known FOMC date
        now = datetime(2026, 1, 28, 0, 0, tzinfo=timezone.utc)
        events = get_events(hours=48, now=now)
        fomc = [e for e in events if "FOMC" in e["name"]]
        assert len(fomc) >= 1

    @patch("common.calendar.economic_events.fetch_forexfactory_events")
    def test_fallback_to_static_when_no_ff_in_window(self, mock_ff):
        get_events, _, _, _ = self._import()
        # FF returns events but none in the window
        mock_ff.return_value = [
            {
                "name": "Some Event",
                "impact": "high",
                "date_str": "2099-01-01T00:00:00+00:00",
                "affected_currencies": ["USD"],
            },
        ]
        now = datetime(2026, 1, 28, 0, 0, tzinfo=timezone.utc)
        events = get_events(hours=48, now=now)
        # Should fall back to static FOMC dates
        fomc = [e for e in events if "FOMC" in e["name"]]
        assert len(fomc) >= 1

    def test_parse_ff_date_iso(self):
        _, _, _, parse = self._import()
        dt = parse("2026-03-17T14:00:00+00:00")
        assert dt is not None
        assert dt.year == 2026

    def test_parse_ff_date_naive(self):
        _, _, _, parse = self._import()
        dt = parse("2026-03-17T14:00:00")
        assert dt is not None
        assert dt.tzinfo is not None  # Should add UTC

    def test_parse_ff_date_invalid(self):
        _, _, _, parse = self._import()
        assert parse("not-a-date") is None

    def test_position_modifier_high_impact_close(self):
        _, get_mod, _, _ = self._import()
        # Mock upcoming events within 2 hours
        now = datetime(2026, 1, 28, 0, 0, tzinfo=timezone.utc)
        mod = get_mod(symbol="EUR/USD", asset_class="forex", hours=48, now=now)
        # FOMC on Jan 28 should reduce position
        assert mod <= 1.0

    def test_position_modifier_non_forex(self):
        _, get_mod, _, _ = self._import()
        assert get_mod(symbol="BTC/USDT", asset_class="crypto") == 1.0


# ── Signal Weight Rebalance ─────────────────────────────────────────────────


class TestSignalWeightRebalance:
    """Tests for updated DEFAULT_WEIGHTS in constants.py."""

    def test_weights_sum_to_one(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.signals.constants import DEFAULT_WEIGHTS
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.001

    def test_macro_weight_exists(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert "macro" in DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["macro"] == 0.00

    def test_sentiment_weight(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["sentiment"] == 0.05

    def test_technical_weight(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["technical"] == 0.50

    def test_regime_weight(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["regime"] == 0.30


# ── Aggregator Modifiers ────────────────────────────────────────────────────


def _make_regime_state(regime, confidence=0.8):
    """Helper to create a RegimeState with required fields."""
    import sys
    sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
    from common.regime.regime_detector import RegimeState
    return RegimeState(
        regime=regime,
        confidence=confidence,
        adx_value=30.0,
        bb_width_percentile=50.0,
        ema_slope=0.01,
        trend_alignment=0.5,
        price_structure_score=0.6,
    )


class TestAggregatorModifiers:
    """Tests for new modifiers in aggregator.py."""

    def _import(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.signals.aggregator import SignalAggregator
        return SignalAggregator

    def test_macro_score_in_compute(self):
        agg_cls = self._import()
        from common.regime.regime_detector import Regime
        agg = agg_cls()
        result = agg.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=60,
            regime_state=_make_regime_state(Regime.WEAK_TREND_UP),
            macro_score=75,
        )
        assert "macro" in result.sources_available
        assert result.composite_score > 0

    @patch("common.market_data.fear_greed.get_fear_greed_signal")
    @patch("common.market_data.coingecko.get_dominance_signal")
    def test_fear_greed_modifier_applied(self, mock_dom, mock_fg):
        agg_cls = self._import()
        from common.regime.regime_detector import Regime
        mock_dom.return_value = {"modifier": 0, "regime_label": "neutral", "dominance": 50.0}
        mock_fg.return_value = {
            "modifier": 10, "classification": "Extreme Fear",
            "value": 10, "score": 75,
        }
        agg = agg_cls()
        result = agg.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=50,
            regime_state=_make_regime_state(Regime.WEAK_TREND_UP),
        )
        # Fear & Greed +10 should boost composite
        fg_reason = [r for r in result.reasoning if "Fear & Greed" in r]
        assert len(fg_reason) >= 1

    @patch("common.data_pipeline.reddit_adapter.fetch_reddit_sentiment")
    @patch("common.market_data.coingecko.get_dominance_signal")
    @patch("common.market_data.fear_greed.get_fear_greed_signal")
    def test_reddit_modifier_applied(self, mock_fg, mock_dom, mock_reddit):
        agg_cls = self._import()
        from common.regime.regime_detector import Regime
        mock_dom.return_value = {"modifier": 0, "regime_label": "neutral", "dominance": 50.0}
        mock_fg.return_value = {
            "modifier": 0, "classification": "Neutral",
            "value": 50, "score": 50,
        }
        mock_reddit.return_value = {"score": 0.5, "post_count": 50, "modifier": 5}
        agg = agg_cls()
        result = agg.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=50,
            regime_state=_make_regime_state(Regime.WEAK_TREND_UP),
        )
        reddit_reason = [r for r in result.reasoning if "Reddit" in r]
        assert len(reddit_reason) >= 1

    @patch("common.market_data.coingecko.get_trending_modifier")
    @patch("common.market_data.coingecko.get_dominance_signal")
    @patch("common.market_data.fear_greed.get_fear_greed_signal")
    @patch("common.data_pipeline.reddit_adapter.fetch_reddit_sentiment")
    def test_trending_modifier_applied(self, mock_reddit, mock_fg, mock_dom, mock_trending):
        agg_cls = self._import()
        from common.regime.regime_detector import Regime
        mock_dom.return_value = {"modifier": 0, "regime_label": "neutral", "dominance": 50.0}
        mock_fg.return_value = {
            "modifier": 0, "classification": "Neutral",
            "value": 50, "score": 50,
        }
        mock_reddit.return_value = {"score": 0, "post_count": 0, "modifier": 0}
        mock_trending.return_value = 3
        agg = agg_cls()
        result = agg.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=50,
            regime_state=_make_regime_state(Regime.WEAK_TREND_UP),
        )
        trending_reason = [r for r in result.reasoning if "Trending" in r]
        assert len(trending_reason) >= 1

    def test_modifiers_only_for_crypto(self):
        """Fear & Greed, Reddit, trending should NOT apply to equity/forex."""
        agg_cls = self._import()
        from common.regime.regime_detector import Regime
        agg = agg_cls()
        result = agg.compute(
            "AAPL", "equity", "EquityMomentum",
            technical_score=60,
            regime_state=_make_regime_state(Regime.WEAK_TREND_UP),
        )
        # No crypto-specific modifiers in reasoning
        crypto_reasons = [
            r for r in result.reasoning
            if any(k in r for k in ["Fear & Greed", "Reddit", "Trending", "BTC dominance"])
        ]
        assert len(crypto_reasons) == 0


# ── Scheduled Task Executors ────────────────────────────────────────────────


class TestScheduledTaskExecutors:
    """Tests for new task executors in task_registry.py."""

    @pytest.fixture(autouse=True)
    def _setup_path(self):
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        import os

        import django
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()

    def _progress(self, pct, msg):
        pass

    def test_task_registry_has_new_executors(self):
        from core.services.task_registry import TASK_REGISTRY
        assert "fear_greed_refresh" in TASK_REGISTRY
        assert "reddit_sentiment_refresh" in TASK_REGISTRY
        assert "coingecko_trending_refresh" in TASK_REGISTRY
        assert "macro_data_refresh" in TASK_REGISTRY

    @patch("common.market_data.fear_greed.get_fear_greed_signal")
    def test_fear_greed_executor(self, mock_signal):
        from core.services.task_registry import TASK_REGISTRY
        mock_signal.return_value = {"value": 30, "label": "Fear", "modifier": 5}
        result = TASK_REGISTRY["fear_greed_refresh"]({}, self._progress)
        assert result["status"] == "completed"

    @patch("common.data_pipeline.reddit_adapter.fetch_reddit_sentiment")
    def test_reddit_sentiment_executor(self, mock_sentiment):
        from core.services.task_registry import TASK_REGISTRY
        mock_sentiment.return_value = {"score": 0.2, "post_count": 50, "modifier": 3}
        result = TASK_REGISTRY["reddit_sentiment_refresh"]({}, self._progress)
        assert result["status"] == "completed"

    @patch("common.market_data.coingecko.fetch_global_defi_data")
    @patch("common.market_data.coingecko.fetch_trending_coins")
    def test_coingecko_trending_executor(self, mock_trending, mock_defi):
        from core.services.task_registry import TASK_REGISTRY
        mock_trending.return_value = [{"symbol": "BTC"}]
        mock_defi.return_value = {"defi_dominance": 3.5}
        result = TASK_REGISTRY["coingecko_trending_refresh"]({}, self._progress)
        assert result["status"] == "completed"
        assert result["trending_count"] == 1

    @patch("common.market_data.fred_adapter.fetch_macro_snapshot")
    def test_macro_data_executor(self, mock_snapshot):
        from core.services.task_registry import TASK_REGISTRY
        mock_snapshot.return_value = {"macro_score": 55.0, "vix": 18.0}
        result = TASK_REGISTRY["macro_data_refresh"]({}, self._progress)
        assert result["status"] == "completed"

    def test_total_task_registry_count(self):
        """Verify registry has all expected executors."""
        from core.services.task_registry import TASK_REGISTRY
        # Should be 28 total (24 original + 4 new)
        assert len(TASK_REGISTRY) >= 28


# ── Scheduled Tasks in Settings ─────────────────────────────────────────────


class TestScheduledTaskSettings:
    """Tests for DEFAULT_SCHEDULED_TASKS in settings.py."""

    @pytest.fixture(autouse=True)
    def _setup_django(self):
        import os
        import sys
        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django
        django.setup()

    def test_fear_greed_task_configured(self):
        from django.conf import settings
        tasks = settings.SCHEDULED_TASKS
        assert "fear_greed_refresh" in tasks
        assert tasks["fear_greed_refresh"]["interval_seconds"] == 3600

    def test_reddit_sentiment_task_configured(self):
        from django.conf import settings
        tasks = settings.SCHEDULED_TASKS
        assert "reddit_sentiment_refresh" in tasks
        assert tasks["reddit_sentiment_refresh"]["interval_seconds"] == 1800

    def test_coingecko_trending_task_configured(self):
        from django.conf import settings
        tasks = settings.SCHEDULED_TASKS
        assert "coingecko_trending_refresh" in tasks
        assert tasks["coingecko_trending_refresh"]["interval_seconds"] == 1800

    def test_macro_data_task_configured(self):
        from django.conf import settings
        tasks = settings.SCHEDULED_TASKS
        assert "macro_data_refresh" in tasks
        assert tasks["macro_data_refresh"]["interval_seconds"] == 14400

    def test_economic_calendar_interval_updated(self):
        from django.conf import settings
        tasks = settings.SCHEDULED_TASKS
        assert tasks["economic_calendar"]["interval_seconds"] == 14400
