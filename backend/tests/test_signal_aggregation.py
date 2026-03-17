"""Tests for Phase 1: Signal Aggregation Core (common/signals/)."""

import threading
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from common.regime.regime_detector import Regime, RegimeState
from common.signals.aggregator import CompositeSignal, SignalAggregator
from common.signals.asset_tuning import get_config, get_conviction_threshold
from common.signals.constants import (
    ALIGNMENT_TABLES,
    CRYPTO_ALIGNMENT,
    DEFAULT_WEIGHTS,
    ENTRY_TIER_OFFSETS,
    EQUITY_ALIGNMENT,
    FALLBACK_NEUTRAL,
    FOREX_ALIGNMENT,
    HARD_DISABLE,
    LABEL_AVOID,
    LABEL_BUY,
    LABEL_CAUTIOUS_BUY,
    LABEL_NEUTRAL,
    LABEL_STRONG_BUY,
    REGIME_COOLDOWN_PENALTY,
)
from common.signals.signal_cache import SignalCache
from common.signals.technical_scorers import (
    SCORER_MAP,
    bmr_technical_score,
    civ1_technical_score,
    mean_reversion_technical_score,
    momentum_technical_score,
    vb_technical_score,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def aggregator():
    return SignalAggregator()


@pytest.fixture
def regime_bullish():
    return RegimeState(
        regime=Regime.STRONG_TREND_UP,
        confidence=0.9,
        adx_value=45.0,
        bb_width_percentile=60.0,
        ema_slope=0.5,
        trend_alignment=0.8,
        price_structure_score=0.7,
        transition_probabilities={},
    )


@pytest.fixture
def regime_bearish():
    return RegimeState(
        regime=Regime.STRONG_TREND_DOWN,
        confidence=0.85,
        adx_value=42.0,
        bb_width_percentile=70.0,
        ema_slope=-0.6,
        trend_alignment=-0.9,
        price_structure_score=-0.8,
        transition_probabilities={},
    )


@pytest.fixture
def regime_ranging():
    return RegimeState(
        regime=Regime.RANGING,
        confidence=0.7,
        adx_value=15.0,
        bb_width_percentile=30.0,
        ema_slope=0.0,
        trend_alignment=0.1,
        price_structure_score=0.0,
        transition_probabilities={},
    )


@pytest.fixture
def regime_unknown():
    return RegimeState(
        regime=Regime.UNKNOWN,
        confidence=0.3,
        adx_value=10.0,
        bb_width_percentile=50.0,
        ema_slope=0.0,
        trend_alignment=0.0,
        price_structure_score=0.0,
        transition_probabilities={},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CompositeSignal tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompositeSignal:
    def test_default_values(self):
        sig = CompositeSignal(symbol="BTC/USDT", asset_class="crypto")
        assert sig.symbol == "BTC/USDT"
        assert sig.asset_class == "crypto"
        assert sig.composite_score == 0.0
        assert sig.entry_approved is False
        assert sig.signal_label == LABEL_NEUTRAL
        assert sig.reasoning == []
        assert sig.sources_available == []
        assert sig.hard_disabled is False

    def test_timestamp_auto_set(self):
        before = datetime.now(timezone.utc)
        sig = CompositeSignal(symbol="X", asset_class="crypto")
        assert sig.timestamp >= before

    def test_custom_values(self):
        sig = CompositeSignal(
            symbol="ETH/USDT",
            asset_class="crypto",
            composite_score=80.0,
            signal_label=LABEL_STRONG_BUY,
            entry_approved=True,
            position_modifier=1.0,
            ml_score=75.0,
            ml_confidence=0.85,
        )
        assert sig.composite_score == 80.0
        assert sig.entry_approved is True
        assert sig.ml_score == 75.0


# ═══════════════════════════════════════════════════════════════════════════════
# Constants tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestConstants:
    def test_weights_sum_to_one(self):
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9

    def test_entry_tier_offsets_descending(self):
        offsets = [t[0] for t in ENTRY_TIER_OFFSETS]
        assert offsets == sorted(offsets, reverse=True)

    def test_alignment_tables_all_regimes(self):
        for asset_class, table in ALIGNMENT_TABLES.items():
            for regime in Regime:
                assert regime in table, f"Missing {regime} in {asset_class}"

    def test_crypto_alignment_std_nonzero(self):
        """With shorts enabled, STD alignment is nonzero for all strategies."""
        assert CRYPTO_ALIGNMENT[Regime.STRONG_TREND_DOWN]["CryptoInvestorV1"] > 0
        assert CRYPTO_ALIGNMENT[Regime.STRONG_TREND_DOWN]["VolatilityBreakout"] > 0

    def test_equity_alignment_momentum_in_downtrend(self):
        assert EQUITY_ALIGNMENT[Regime.STRONG_TREND_DOWN]["EquityMomentum"] > 0

    def test_forex_alignment_has_both_strategies(self):
        for regime in Regime:
            row = FOREX_ALIGNMENT[regime]
            assert "ForexTrend" in row
            assert "ForexRange" in row

    def test_hard_disable_empty(self):
        """With shorts enabled, no strategies are hard-disabled."""
        assert len(HARD_DISABLE) == 0

    def test_conviction_threshold_crypto_default(self):
        assert get_conviction_threshold("crypto") == 40


# ═══════════════════════════════════════════════════════════════════════════════
# SignalCache tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSignalCache:
    def test_get_miss(self):
        cache = SignalCache()
        assert cache.get("BTC/USDT") is None

    def test_set_and_get(self):
        cache = SignalCache()
        sig = CompositeSignal(symbol="BTC/USDT", asset_class="crypto")
        cache.set("BTC/USDT", sig)
        assert cache.get("BTC/USDT") is sig

    def test_ttl_expiry(self):
        cache = SignalCache(ttl=0.05)  # 50ms
        sig = CompositeSignal(symbol="X", asset_class="crypto")
        cache.set("X", sig)
        assert cache.get("X") is sig
        time.sleep(0.06)
        assert cache.get("X") is None

    def test_invalidate(self):
        cache = SignalCache()
        sig = CompositeSignal(symbol="X", asset_class="crypto")
        cache.set("X", sig)
        cache.invalidate("X")
        assert cache.get("X") is None

    def test_invalidate_nonexistent(self):
        cache = SignalCache()
        cache.invalidate("nonexistent")  # Should not raise

    def test_invalidate_all(self):
        cache = SignalCache()
        for sym in ["A", "B", "C"]:
            cache.set(sym, CompositeSignal(symbol=sym, asset_class="crypto"))
        assert cache.size() == 3
        cache.invalidate_all()
        assert cache.size() == 0

    def test_size(self):
        cache = SignalCache()
        assert cache.size() == 0
        cache.set("A", CompositeSignal(symbol="A", asset_class="crypto"))
        assert cache.size() == 1

    def test_overwrite(self):
        cache = SignalCache()
        sig1 = CompositeSignal(symbol="X", asset_class="crypto", composite_score=10)
        sig2 = CompositeSignal(symbol="X", asset_class="crypto", composite_score=90)
        cache.set("X", sig1)
        cache.set("X", sig2)
        assert cache.get("X").composite_score == 90

    def test_thread_safety(self):
        cache = SignalCache()
        errors = []

        def writer(name: str):
            try:
                for _i in range(100):
                    cache.set(
                        name, CompositeSignal(symbol=name, asset_class="crypto"),
                    )
            except Exception as e:
                errors.append(e)

        def reader(name: str):
            try:
                for _ in range(100):
                    cache.get(name)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("A",)),
            threading.Thread(target=writer, args=("B",)),
            threading.Thread(target=reader, args=("A",)),
            threading.Thread(target=reader, args=("B",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# Technical Scorers tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCIV1TechnicalScore:
    def test_perfect_bullish(self):
        score = civ1_technical_score(
            rsi=50, ema_short=105, ema_long=100, close=110,
            macd_hist=0.5, volume_ratio=1.5, adx_value=30,
        )
        assert score >= 70

    def test_bearish_alignment(self):
        score = civ1_technical_score(
            rsi=75, ema_short=95, ema_long=100, close=90,
            macd_hist=-0.5, volume_ratio=0.5, adx_value=10,
        )
        assert score < 30

    def test_rsi_sweet_spot(self):
        high = civ1_technical_score(
            rsi=50, ema_short=100, ema_long=100, close=100,
            macd_hist=0, volume_ratio=1, adx_value=25,
        )
        low = civ1_technical_score(
            rsi=80, ema_short=100, ema_long=100, close=100,
            macd_hist=0, volume_ratio=1, adx_value=25,
        )
        assert high > low

    def test_overbought_rsi(self):
        score = civ1_technical_score(
            rsi=80, ema_short=105, ema_long=100, close=110,
            macd_hist=0.1, volume_ratio=1.0, adx_value=30,
        )
        assert 0 <= score <= 100

    def test_ema_partial_alignment(self):
        # close > ema_short but ema_short < ema_long
        score = civ1_technical_score(
            rsi=50, ema_short=98, ema_long=100, close=99,
            macd_hist=0.1, volume_ratio=1, adx_value=25,
        )
        assert 0 <= score <= 100

    def test_very_high_adx(self):
        score = civ1_technical_score(
            rsi=50, ema_short=105, ema_long=100, close=110,
            macd_hist=0.1, volume_ratio=1, adx_value=55,
        )
        assert score > 0

    def test_low_adx(self):
        score = civ1_technical_score(
            rsi=50, ema_short=105, ema_long=100, close=110,
            macd_hist=0.1, volume_ratio=1, adx_value=18,
        )
        assert 0 <= score <= 100

    def test_oversold_rsi(self):
        score = civ1_technical_score(
            rsi=25, ema_short=105, ema_long=100, close=110,
            macd_hist=0.1, volume_ratio=1, adx_value=25,
        )
        assert 0 <= score <= 100

    def test_output_clamped(self):
        score = civ1_technical_score(
            rsi=50, ema_short=105, ema_long=100, close=110,
            macd_hist=100, volume_ratio=100, adx_value=30,
        )
        assert score <= 100

    def test_zero_volume(self):
        score = civ1_technical_score(
            rsi=50, ema_short=105, ema_long=100, close=110,
            macd_hist=0.1, volume_ratio=0, adx_value=25,
        )
        assert 0 <= score <= 100

    def test_rsi_30_to_40_range(self):
        score = civ1_technical_score(
            rsi=35, ema_short=105, ema_long=100, close=110,
            macd_hist=0.1, volume_ratio=1, adx_value=25,
        )
        assert 0 <= score <= 100

    def test_rsi_60_to_70_range(self):
        score = civ1_technical_score(
            rsi=65, ema_short=105, ema_long=100, close=110,
            macd_hist=0.1, volume_ratio=1, adx_value=25,
        )
        assert 0 <= score <= 100

    def test_ema_short_above_long_close_below(self):
        score = civ1_technical_score(
            rsi=50, ema_short=102, ema_long=100, close=99,
            macd_hist=0.1, volume_ratio=1, adx_value=25,
        )
        assert 0 <= score <= 100


class TestBMRTechnicalScore:
    def test_perfect_mean_reversion(self):
        score = bmr_technical_score(
            close=95, bb_lower=95, bb_mid=100, bb_width=0.01,
            rsi=25, stoch_k=15, mfi=15, volume_ratio=1.5,
        )
        assert score >= 70

    def test_no_opportunity(self):
        score = bmr_technical_score(
            close=110, bb_lower=90, bb_mid=100, bb_width=0.10,
            rsi=60, stoch_k=60, mfi=60, volume_ratio=0.5,
        )
        assert score < 30

    def test_below_lower_band(self):
        score = bmr_technical_score(
            close=89, bb_lower=90, bb_mid=100, bb_width=0.02,
            rsi=28, stoch_k=18, mfi=18, volume_ratio=1.2,
        )
        assert score >= 70

    def test_bb_mid_zero_no_crash(self):
        score = bmr_technical_score(
            close=100, bb_lower=95, bb_mid=0, bb_width=0.05,
            rsi=40, stoch_k=40, mfi=40, volume_ratio=1,
        )
        assert 0 <= score <= 100

    def test_rsi_ranges(self):
        scores = []
        for rsi_val in [25, 35, 45, 55]:
            s = bmr_technical_score(
                close=98, bb_lower=95, bb_mid=100, bb_width=0.05,
                rsi=rsi_val, stoch_k=40, mfi=40, volume_ratio=1,
            )
            scores.append(s)
        # Lower RSI should give higher scores
        assert scores[0] > scores[-1]

    def test_stoch_k_ranges(self):
        low = bmr_technical_score(
            close=98, bb_lower=95, bb_mid=100, bb_width=0.05,
            rsi=35, stoch_k=15, mfi=35, volume_ratio=1,
        )
        high = bmr_technical_score(
            close=98, bb_lower=95, bb_mid=100, bb_width=0.05,
            rsi=35, stoch_k=50, mfi=35, volume_ratio=1,
        )
        assert low > high

    def test_mfi_ranges(self):
        low = bmr_technical_score(
            close=98, bb_lower=95, bb_mid=100, bb_width=0.05,
            rsi=35, stoch_k=35, mfi=15, volume_ratio=1,
        )
        high = bmr_technical_score(
            close=98, bb_lower=95, bb_mid=100, bb_width=0.05,
            rsi=35, stoch_k=35, mfi=50, volume_ratio=1,
        )
        assert low > high

    def test_bb_width_squeeze_bonus(self):
        squeeze = bmr_technical_score(
            close=98, bb_lower=95, bb_mid=100, bb_width=0.01,
            rsi=35, stoch_k=35, mfi=35, volume_ratio=1,
        )
        wide = bmr_technical_score(
            close=98, bb_lower=95, bb_mid=100, bb_width=0.10,
            rsi=35, stoch_k=35, mfi=35, volume_ratio=1,
        )
        assert squeeze > wide

    def test_pct_from_lower_ranges(self):
        # Close at 2% above lower
        s1 = bmr_technical_score(
            close=97, bb_lower=95, bb_mid=100, bb_width=0.05,
            rsi=35, stoch_k=35, mfi=35, volume_ratio=1,
        )
        # Close at 8% above lower
        s2 = bmr_technical_score(
            close=103, bb_lower=95, bb_mid=100, bb_width=0.05,
            rsi=35, stoch_k=35, mfi=35, volume_ratio=1,
        )
        assert s1 > s2


class TestVBTechnicalScore:
    def test_perfect_breakout(self):
        score = vb_technical_score(
            close=105, high_n=100, volume_ratio=2.5,
            bb_width=0.08, bb_width_prev=0.05,
            adx_value=35, rsi=55,
        )
        assert score >= 70

    def test_far_from_high(self):
        score = vb_technical_score(
            close=85, high_n=100, volume_ratio=0.8,
            bb_width=0.05, bb_width_prev=0.05,
            adx_value=12, rsi=30,
        )
        assert score < 30

    def test_above_high(self):
        score = vb_technical_score(
            close=102, high_n=100, volume_ratio=2.0,
            bb_width=0.06, bb_width_prev=0.05,
            adx_value=25, rsi=60,
        )
        assert score >= 50

    def test_high_n_zero_no_crash(self):
        score = vb_technical_score(
            close=100, high_n=0, volume_ratio=1,
            bb_width=0.05, bb_width_prev=0.05,
            adx_value=20, rsi=50,
        )
        assert 0 <= score <= 100

    def test_bb_width_prev_zero_no_crash(self):
        score = vb_technical_score(
            close=100, high_n=100, volume_ratio=1,
            bb_width=0.05, bb_width_prev=0,
            adx_value=20, rsi=50,
        )
        assert 0 <= score <= 100

    def test_volume_tiers(self):
        scores = []
        for vr in [0.5, 1.0, 1.5, 2.0]:
            s = vb_technical_score(
                close=99, high_n=100, volume_ratio=vr,
                bb_width=0.06, bb_width_prev=0.05,
                adx_value=25, rsi=55,
            )
            scores.append(s)
        # Higher volume should give higher score
        assert scores[-1] > scores[0]

    def test_adx_ranges(self):
        high_adx = vb_technical_score(
            close=99, high_n=100, volume_ratio=1.5,
            bb_width=0.06, bb_width_prev=0.05,
            adx_value=35, rsi=55,
        )
        low_adx = vb_technical_score(
            close=99, high_n=100, volume_ratio=1.5,
            bb_width=0.06, bb_width_prev=0.05,
            adx_value=10, rsi=55,
        )
        assert high_adx > low_adx

    def test_rsi_sweet_spot(self):
        good = vb_technical_score(
            close=99, high_n=100, volume_ratio=1.5,
            bb_width=0.06, bb_width_prev=0.05,
            adx_value=25, rsi=55,
        )
        overbought = vb_technical_score(
            close=99, high_n=100, volume_ratio=1.5,
            bb_width=0.06, bb_width_prev=0.05,
            adx_value=25, rsi=80,
        )
        assert good > overbought

    def test_breakout_margin_tiers(self):
        at_high = vb_technical_score(
            close=100, high_n=100, volume_ratio=1.5,
            bb_width=0.06, bb_width_prev=0.05,
            adx_value=25, rsi=55,
        )
        near_high = vb_technical_score(
            close=98, high_n=100, volume_ratio=1.5,
            bb_width=0.06, bb_width_prev=0.05,
            adx_value=25, rsi=55,
        )
        far = vb_technical_score(
            close=92, high_n=100, volume_ratio=1.5,
            bb_width=0.06, bb_width_prev=0.05,
            adx_value=25, rsi=55,
        )
        assert at_high > near_high > far

    def test_bb_contraction(self):
        contracting = vb_technical_score(
            close=99, high_n=100, volume_ratio=1.5,
            bb_width=0.04, bb_width_prev=0.05,
            adx_value=25, rsi=55,
        )
        expanding = vb_technical_score(
            close=99, high_n=100, volume_ratio=1.5,
            bb_width=0.08, bb_width_prev=0.05,
            adx_value=25, rsi=55,
        )
        assert expanding > contracting


class TestMomentumAndMeanReversionScorers:
    def test_momentum_delegates_to_civ1(self):
        args = dict(
            rsi=50, ema_short=105, ema_long=100, close=110,
            macd_hist=0.5, volume_ratio=1.5, adx_value=30,
        )
        assert momentum_technical_score(**args) == civ1_technical_score(**args)

    def test_mean_reversion_delegates_to_bmr(self):
        args = dict(
            close=95, bb_lower=95, bb_mid=100, bb_width=0.01,
            rsi=25, stoch_k=15, mfi=15, volume_ratio=1.5,
        )
        assert mean_reversion_technical_score(**args) == bmr_technical_score(**args)


class TestScorerMap:
    def test_all_strategies_mapped(self):
        expected = {
            "CryptoInvestorV1", "BollingerMeanReversion", "VolatilityBreakout",
            "EquityMomentum", "EquityMeanReversion", "ForexTrend", "ForexRange",
        }
        assert set(SCORER_MAP.keys()) == expected

    def test_scorer_types(self):
        assert SCORER_MAP["CryptoInvestorV1"] == "civ1"
        assert SCORER_MAP["BollingerMeanReversion"] == "bmr"
        assert SCORER_MAP["VolatilityBreakout"] == "vb"
        assert SCORER_MAP["EquityMomentum"] == "momentum"
        assert SCORER_MAP["ForexRange"] == "mean_reversion"


# ═══════════════════════════════════════════════════════════════════════════════
# SignalAggregator tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSignalAggregatorHardDisable:
    """With shorts enabled, no strategies are hard-disabled in any regime."""

    def test_civ1_not_blocked_in_strong_downtrend(self, aggregator, regime_bearish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            regime_state=regime_bearish, technical_score=90,
        )
        assert sig.hard_disabled is False
        assert sig.composite_score > 0.0

    def test_vb_not_blocked_in_strong_downtrend(self, aggregator, regime_bearish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "VolatilityBreakout",
            regime_state=regime_bearish, technical_score=85,
        )
        assert sig.hard_disabled is False

    def test_bmr_not_blocked_in_strong_downtrend(self, aggregator, regime_bearish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "BollingerMeanReversion",
            regime_state=regime_bearish, technical_score=70,
        )
        assert sig.hard_disabled is False

    def test_equity_momentum_not_blocked_in_downtrend(self, aggregator, regime_bearish):
        sig = aggregator.compute(
            "AAPL", "equity", "EquityMomentum",
            regime_state=regime_bearish, technical_score=80,
        )
        assert sig.hard_disabled is False


class TestSignalAggregatorCompute:
    @pytest.fixture(autouse=True)
    def _mock_external_modifiers(self):
        """Patch out external API modifiers so compute() tests are deterministic."""
        dom = {"modifier": 0, "regime_label": "neutral", "dominance": 50.0}
        fng = {
            "modifier": 0, "classification": "Neutral",
            "value": 50, "score": 50,
        }
        reddit = {"score": 0, "post_count": 0, "modifier": 0}
        with (
            patch("common.market_data.coingecko.get_dominance_signal", return_value=dom),
            patch("common.market_data.fear_greed.get_fear_greed_signal", return_value=fng),
            patch(
                "common.data_pipeline.reddit_adapter.fetch_reddit_sentiment",
                return_value=reddit,
            ),
            patch("common.market_data.coingecko.get_trending_modifier", return_value=0),
        ):
            yield

    def test_all_sources_strong_buy(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=90,
            regime_state=regime_bullish,
            ml_probability=0.85,
            ml_confidence=0.9,
            sentiment_signal=0.6,
            sentiment_conviction=0.8,
            scanner_score=85,
            win_rate=70,
        )
        assert sig.composite_score >= 75
        assert sig.entry_approved is True
        assert sig.signal_label == LABEL_STRONG_BUY
        assert sig.position_modifier == 1.0
        assert len(sig.sources_available) == 6

    def test_all_sources_weak(self, aggregator, regime_unknown):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=20,
            regime_state=regime_unknown,
            ml_probability=0.3,
            ml_confidence=0.4,
            sentiment_signal=-0.3,
            sentiment_conviction=0.5,
            scanner_score=10,
            win_rate=30,
        )
        assert sig.composite_score < 55
        assert sig.entry_approved is False
        assert sig.signal_label == LABEL_AVOID
        assert sig.position_modifier == 0.0

    def test_no_sources_fallback(self, aggregator):
        sig = aggregator.compute("BTC/USDT", "crypto", "CryptoInvestorV1")
        assert sig.composite_score == FALLBACK_NEUTRAL
        assert sig.signal_label == LABEL_NEUTRAL
        assert "No signal sources available" in sig.reasoning[0]

    def test_technical_only(self, aggregator):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=80,
        )
        # With only technical, it gets full weight (redistributed)
        assert sig.composite_score == 80.0
        assert sig.entry_approved is True
        assert "technical" in sig.sources_available
        assert len(sig.sources_available) == 1

    def test_regime_and_technical(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=80,
            regime_state=regime_bullish,
        )
        assert sig.entry_approved is True
        assert "technical" in sig.sources_available
        assert "regime" in sig.sources_available

    def test_position_modifier_tiers(self, aggregator):
        # Crypto threshold=40: strong_buy=60, buy=50, cautious_buy=40
        # Score >= 60 -> 1.0
        sig60 = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1", technical_score=65,
        )
        assert sig60.position_modifier == 1.0

        # Score 50-59 -> 0.7
        sig50 = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1", technical_score=55,
        )
        assert sig50.position_modifier == 0.7

        # Score 40-49 -> 0.4
        sig40 = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1", technical_score=45,
        )
        assert sig40.position_modifier == 0.4

        # Score < 40 -> 0.0
        sig30 = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1", technical_score=30,
        )
        assert sig30.position_modifier == 0.0

    def test_sentiment_conversion(self, aggregator):
        # sentiment_signal of -1 -> score 0, +1 -> score 100, 0 -> 50
        sig = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1",
            sentiment_signal=0.0,
        )
        assert sig.sentiment_score == 50.0

        sig_bull = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1",
            sentiment_signal=1.0,
        )
        assert sig_bull.sentiment_score == 100.0

        sig_bear = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1",
            sentiment_signal=-1.0,
        )
        assert sig_bear.sentiment_score == 0.0

    def test_ml_probability_conversion(self, aggregator):
        sig = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1",
            ml_probability=0.75,
            ml_confidence=0.9,
        )
        assert sig.ml_score == 75.0
        assert sig.ml_confidence == 0.9

    def test_clamping(self, aggregator):
        sig = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1",
            technical_score=150,  # Above 100
        )
        assert sig.technical_score == 100.0

        sig2 = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1",
            technical_score=-10,  # Below 0
        )
        assert sig2.technical_score == 0.0


class TestSignalAggregatorRegimeAlignment:
    def test_civ1_strong_trend_up_high_alignment(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            regime_state=regime_bullish,
        )
        # CIV1 in STRONG_TREND_UP = 95 alignment * 0.9 confidence + 50 * 0.1
        expected = 95 * 0.9 + 50 * 0.1  # 90.5
        assert abs(sig.regime_score - expected) < 1.0

    def test_bmr_ranging_high_alignment(self, aggregator, regime_ranging):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "BollingerMeanReversion",
            regime_state=regime_ranging,
        )
        # BMR in RANGING = 95 * 0.7 + 50 * 0.3 = 81.5
        expected = 95 * 0.7 + 50 * 0.3
        assert abs(sig.regime_score - expected) < 1.0

    def test_unknown_strategy_uses_fallback(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "UnknownStrategy",
            regime_state=regime_bullish,
        )
        # Should fall back to FALLBACK_NEUTRAL for the alignment score
        expected = FALLBACK_NEUTRAL * 0.9 + 50 * 0.1  # 50
        assert abs(sig.regime_score - expected) < 1.0


class TestSignalAggregatorCooldown:
    def test_first_call_no_penalty(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            regime_state=regime_bullish,
        )
        # First call — no cooldown penalty
        raw = 95 * 0.9 + 50 * 0.1
        assert abs(sig.regime_score - raw) < 1.0

    def test_regime_change_triggers_cooldown(self, aggregator, regime_bullish, regime_ranging):
        # First call sets the regime
        aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            regime_state=regime_bullish,
        )
        # Regime change triggers cooldown
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            regime_state=regime_ranging,
        )
        # Should be penalised by REGIME_COOLDOWN_PENALTY
        raw = 15 * 0.7 + 50 * 0.3  # CIV1 in RANGING
        expected = raw * REGIME_COOLDOWN_PENALTY
        assert abs(sig.regime_score - expected) < 1.0

    def test_cooldown_wears_off(self, aggregator, regime_bullish, regime_ranging):
        # Set initial regime
        cooldown_bars = get_config("crypto").regime_cooldown_bars
        aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            regime_state=regime_bullish,
        )
        # Trigger regime change
        for _ in range(cooldown_bars + 1):
            sig = aggregator.compute(
                "BTC/USDT", "crypto", "CryptoInvestorV1",
                regime_state=regime_ranging,
            )
        # After cooldown bars, penalty should be gone
        raw = 15 * 0.7 + 50 * 0.3
        assert abs(sig.regime_score - raw) < 1.0


class TestSignalAggregatorWeightRedistribution:
    @pytest.fixture(autouse=True)
    def _mock_external_modifiers(self):
        dom = {"modifier": 0, "regime_label": "neutral", "dominance": 50.0}
        fng = {
            "modifier": 0, "classification": "Neutral",
            "value": 50, "score": 50,
        }
        reddit = {"score": 0, "post_count": 0, "modifier": 0}
        with (
            patch("common.market_data.coingecko.get_dominance_signal", return_value=dom),
            patch("common.market_data.fear_greed.get_fear_greed_signal", return_value=fng),
            patch(
                "common.data_pipeline.reddit_adapter.fetch_reddit_sentiment",
                return_value=reddit,
            ),
            patch("common.market_data.coingecko.get_trending_modifier", return_value=0),
        ):
            yield

    def test_single_source_gets_full_weight(self, aggregator):
        sig = aggregator.compute(
            "X", "crypto", "CIV1",
            technical_score=80,
        )
        assert sig.composite_score == 80.0

    def test_two_sources_redistributed(self, aggregator):
        sig = aggregator.compute(
            "X", "crypto", "CIV1",
            technical_score=80,
            scanner_score=60,
        )
        # tech weight = 0.22, scanner weight = 0.05
        # Redistributed: tech = 0.22/0.27, scanner = 0.05/0.27
        expected = 80 * (0.22 / 0.27) + 60 * (0.05 / 0.27)
        assert abs(sig.composite_score - expected) < 0.5

    def test_custom_weights(self):
        agg = SignalAggregator(weights={"technical": 0.5, "ml": 0.5})
        sig = agg.compute(
            "X", "crypto", "CIV1",
            technical_score=80,
            ml_probability=0.6,
        )
        expected = 80 * 0.5 + 60 * 0.5
        assert abs(sig.composite_score - expected) < 0.5


class TestSignalAggregatorLabels:
    """Labels are now relative to conviction threshold (default crypto = 55)."""

    def test_strong_buy(self, aggregator):
        # threshold + 20 = 75
        assert aggregator._label(80, 55) == LABEL_STRONG_BUY

    def test_buy(self, aggregator):
        # threshold + 10 = 65
        assert aggregator._label(70, 55) == LABEL_BUY

    def test_cautious_buy(self, aggregator):
        # threshold + 0 = 55
        assert aggregator._label(60, 55) == LABEL_CAUTIOUS_BUY

    def test_avoid(self, aggregator):
        assert aggregator._label(40, 55) == LABEL_AVOID

    def test_boundary_75(self, aggregator):
        assert aggregator._label(75, 55) == LABEL_STRONG_BUY

    def test_boundary_65(self, aggregator):
        assert aggregator._label(65, 55) == LABEL_BUY

    def test_boundary_55(self, aggregator):
        assert aggregator._label(55, 55) == LABEL_CAUTIOUS_BUY

    def test_boundary_54(self, aggregator):
        assert aggregator._label(54, 55) == LABEL_AVOID

    def test_equity_threshold_shifts_labels(self, aggregator):
        # Equity threshold = 65, so strong_buy = 85, buy = 75, cautious_buy = 65
        assert aggregator._label(85, 65) == LABEL_STRONG_BUY
        assert aggregator._label(75, 65) == LABEL_BUY
        assert aggregator._label(65, 65) == LABEL_CAUTIOUS_BUY
        assert aggregator._label(64, 65) == LABEL_AVOID


class TestSignalAggregatorReasoning:
    def test_reasoning_includes_strategy(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=80,
            regime_state=regime_bullish,
        )
        assert any("CryptoInvestorV1" in r for r in sig.reasoning)
        assert any("strong_trend_up" in r for r in sig.reasoning)

    def test_reasoning_includes_rejection(self, aggregator):
        sig = aggregator.compute(
            "X", "crypto", "CryptoInvestorV1",
            technical_score=30,
        )
        assert any("REJECTED" in r for r in sig.reasoning)

    def test_reasoning_lists_sources(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=80,
            regime_state=regime_bullish,
            ml_probability=0.7,
        )
        starts = ("technical", "regime", "ml")
        source_lines = [r for r in sig.reasoning if r.strip().startswith(starts)]
        assert len(source_lines) == 3


class TestSignalAggregatorAssetClasses:
    def test_equity_alignment_used(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "AAPL", "equity", "EquityMomentum",
            regime_state=regime_bullish,
        )
        # EquityMomentum in STRONG_TREND_UP = 95
        expected = 95 * 0.9 + 50 * 0.1
        assert abs(sig.regime_score - expected) < 1.0

    def test_forex_alignment_used(self, aggregator, regime_ranging):
        sig = aggregator.compute(
            "EUR/USD", "forex", "ForexRange",
            regime_state=regime_ranging,
        )
        # ForexRange in RANGING = 95
        expected = 95 * 0.7 + 50 * 0.3
        assert abs(sig.regime_score - expected) < 1.0

    def test_unknown_asset_class_falls_back_to_crypto(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "X", "unknown_asset", "CryptoInvestorV1",
            regime_state=regime_bullish,
        )
        # Should use crypto alignment table as fallback
        expected = 95 * 0.9 + 50 * 0.1
        assert abs(sig.regime_score - expected) < 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration-style tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSignalAggregatorIntegration:
    def test_cache_integration(self, aggregator, regime_bullish):
        cache = SignalCache()
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=85,
            regime_state=regime_bullish,
        )
        cache.set("BTC/USDT", sig)
        cached = cache.get("BTC/USDT")
        assert cached.composite_score == sig.composite_score
        assert cached.entry_approved == sig.entry_approved

    def test_multiple_symbols_independent(self, aggregator, regime_bullish, regime_ranging):
        sig1 = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=85, regime_state=regime_bullish,
        )
        sig2 = aggregator.compute(
            "ETH/USDT", "crypto", "BollingerMeanReversion",
            technical_score=75, regime_state=regime_ranging,
        )
        assert sig1.composite_score != sig2.composite_score
        assert sig1.symbol == "BTC/USDT"
        assert sig2.symbol == "ETH/USDT"

    def test_full_pipeline_crypto(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=85,
            regime_state=regime_bullish,
            ml_probability=0.78,
            ml_confidence=0.85,
            sentiment_signal=0.4,
            sentiment_conviction=0.7,
            scanner_score=80,
            win_rate=65,
        )
        assert isinstance(sig, CompositeSignal)
        assert sig.symbol == "BTC/USDT"
        assert sig.asset_class == "crypto"
        assert 0 <= sig.composite_score <= 100
        assert sig.signal_label in {
            LABEL_STRONG_BUY, LABEL_BUY, LABEL_CAUTIOUS_BUY, LABEL_NEUTRAL, LABEL_AVOID,
        }
        assert 0 <= sig.position_modifier <= 1.0
        assert len(sig.reasoning) > 0
        assert len(sig.sources_available) == 6

    def test_full_pipeline_equity(self, aggregator, regime_bullish):
        sig = aggregator.compute(
            "AAPL", "equity", "EquityMomentum",
            technical_score=75,
            regime_state=regime_bullish,
            ml_probability=0.65,
            sentiment_signal=0.2,
        )
        assert sig.asset_class == "equity"
        assert 0 <= sig.composite_score <= 100
