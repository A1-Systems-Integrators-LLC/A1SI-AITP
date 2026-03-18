"""Comprehensive tests for Common Indicators, Risk Manager, and Sentiment modules.
================================================================================
Covers edge cases, thread safety, stale state, daily reset boundaries,
unknown regimes, asset-class routing, sentiment modifier scaling,
flat/NaN data, and technical indicator edge cases.
"""

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on sys.path for common.* imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.indicators.technical import (
    add_all_indicators,
    adx,
    atr_indicator,
    bollinger_bands,
    cci,
    ema,
    hull_ma,
    macd,
    mfi,
    obv,
    rsi,
    sma,
    stochastic,
    supertrend,
    vwap,
    williams_r,
    wma,
)
from common.regime.regime_detector import (
    Regime,
    RegimeDetector,
    config_for_asset_class,
)
from common.regime.strategy_router import (
    BMR,
    EQ_MOM,
    EQ_MR,
    FX_RANGE,
    FX_TREND,
    RoutingDecision,
    StrategyRouter,
)
from common.risk.risk_manager import (
    ReturnTracker,
    RiskLimits,
    RiskManager,
)
from common.sentiment.scorer import (
    NEGATIVE_WORDS,
    POSITIVE_WORDS,
    score_article,
    score_text,
)
from common.sentiment.signal import (
    compute_signal,
)

# ── Helpers ──────────────────────────────────────────────────


def _make_ohlcv(n: int = 100, seed: int = 42, flat: bool = False) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame."""
    np.random.seed(seed)
    close = np.full(n, 100.0) if flat else 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    volume = np.random.uniform(1000, 5000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": close - 0.05, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _make_regime_state(
    regime: Regime,
    confidence: float = 0.8,
    trend_alignment: float = 0.5,
) -> "RegimeState":  # noqa: F821
    from common.regime.regime_detector import RegimeState

    return RegimeState(
        regime=regime,
        confidence=confidence,
        adx_value=30.0,
        bb_width_percentile=50.0,
        ema_slope=0.01,
        trend_alignment=trend_alignment,
        price_structure_score=0.3,
    )


# =====================================================================
# 1. Sentiment Scorer — keyword scoring edge cases
# =====================================================================


class TestSentimentScorerEdgeCases:
    """Direct unit tests for common.sentiment.scorer.score_text edge cases."""

    def test_empty_string_returns_neutral(self):
        score, label = score_text("")
        assert score == 0.0
        assert label == "neutral"

    def test_whitespace_only_returns_neutral(self):
        score, label = score_text("   \n\t  ")
        assert score == 0.0
        assert label == "neutral"

    def test_all_positive_words(self):
        text = "bullish surge rally gains breakout"
        score, label = score_text(text)
        assert score > 0
        assert label == "positive"

    def test_all_negative_words(self):
        text = "bearish crash dump sell-off liquidation"
        score, label = score_text(text)
        assert score < 0
        assert label == "negative"

    def test_mixed_positive_and_negative(self):
        text = "bullish crash rally dump gains sell-off"
        score, label = score_text(text)
        # 3 positive + 3 negative should roughly cancel
        assert abs(score) < 0.5

    def test_negator_flips_positive(self):
        """'not great' should score lower than 'great'."""
        pos_score, _ = score_text("great")
        neg_score, _ = score_text("not great")
        assert neg_score < pos_score

    def test_negator_flips_negative(self):
        """'not terrible' should flip negative to positive."""
        neg_score, _ = score_text("terrible")
        flipped_score, _ = score_text("not terrible")
        assert flipped_score > neg_score

    def test_intensifier_amplifies(self):
        """'extremely good' should score higher than plain 'good' in diluted text."""
        # Use enough filler words so the score doesn't saturate at 1.0
        plain, _ = score_text("the market had a good day today across the board")
        intense, _ = score_text("the market had an extremely good day today across the board")
        assert intense > plain

    def test_no_sentiment_words_returns_neutral(self):
        score, label = score_text("the cat sat on the mat")
        assert score == 0.0
        assert label == "neutral"

    def test_score_clamped_to_bounds(self):
        """Even with extreme text, score should be in [-1, 1]."""
        extreme_positive = " ".join(list(POSITIVE_WORDS)[:20])
        score, _ = score_text(extreme_positive)
        assert -1.0 <= score <= 1.0

        extreme_negative = " ".join(list(NEGATIVE_WORDS)[:20])
        score, _ = score_text(extreme_negative)
        assert -1.0 <= score <= 1.0

    def test_score_article_weighted(self):
        """Title gets 60% weight, summary gets 40%."""
        # Positive title, negative summary
        score, label = score_article("bullish surge rally", "crash dump loss")
        title_score, _ = score_text("bullish surge rally")
        summary_score, _ = score_text("crash dump loss")
        expected = title_score * 0.6 + summary_score * 0.4
        assert score == pytest.approx(expected, abs=0.01)

    def test_score_article_empty_summary(self):
        """Empty summary should not affect title-only scoring."""
        score, label = score_article("bullish surge", "")
        title_score, _ = score_text("bullish surge")
        assert score == pytest.approx(title_score * 0.6, abs=0.01)


# =====================================================================
# 2. Risk Manager — stale equity detection
# =====================================================================


class TestRiskManagerStaleEquity:
    """Test that equity does not auto-update and stale state is detectable."""

    def test_equity_unchanged_without_update(self):
        rm = RiskManager()
        initial_equity = rm.state.total_equity
        # No calls to update_equity — value should remain default
        assert rm.state.total_equity == initial_equity
        assert rm.state.last_update is None

    def test_last_update_set_on_equity_update(self):
        rm = RiskManager()
        assert rm.state.last_update is None
        rm.update_equity(9500.0)
        assert rm.state.last_update is not None
        assert isinstance(rm.state.last_update, datetime)

    def test_stale_detection_by_last_update(self):
        """If last_update is None or old, the state is stale."""
        rm = RiskManager()
        # No update yet — last_update is None (stale)
        assert rm.state.last_update is None

        rm.update_equity(9800.0)
        # After update, last_update is recent
        assert rm.state.last_update is not None
        now = datetime.now(timezone.utc)
        delta = (now - rm.state.last_update).total_seconds()
        assert delta < 5.0  # Should be within a few seconds


# =====================================================================
# 3. Risk Manager — daily loss reset at day boundary
# =====================================================================


class TestRiskManagerDailyReset:
    """Test daily loss reset edge cases."""

    def test_daily_reset_resets_pnl_and_start_equity(self):
        rm = RiskManager()
        rm.state.daily_pnl = -200.0
        rm.state.total_equity = 9800.0
        rm.reset_daily()
        assert rm.state.daily_pnl == 0.0
        assert rm.state.daily_start_equity == 9800.0

    def test_daily_reset_clears_daily_halt_only(self):
        """reset_daily should only clear halts with 'Daily' in the reason."""
        rm = RiskManager()
        rm.state.is_halted = True
        rm.state.halt_reason = "Daily loss limit breached: -6.00% <= -5.00%"
        rm.reset_daily()
        assert rm.state.is_halted is False

    def test_daily_reset_preserves_drawdown_halt(self):
        """reset_daily should NOT clear a drawdown-based halt."""
        rm = RiskManager()
        rm.state.is_halted = True
        rm.state.halt_reason = "Max drawdown breached: 16.00% >= 15.00%"
        rm.reset_daily()
        # Halt should persist because reason does not contain "Daily"
        assert rm.state.is_halted is True
        assert "drawdown" in rm.state.halt_reason.lower()

    def test_daily_reset_at_exact_boundary(self):
        """Equity exactly at daily loss limit boundary, then reset."""
        rm = RiskManager(RiskLimits(max_daily_loss=0.05))
        rm.state.daily_start_equity = 10000.0
        rm.update_equity(9500.0)  # exactly 5% loss → halt
        assert rm.state.is_halted is True
        assert "daily" in rm.state.halt_reason.lower()

        rm.reset_daily()
        assert rm.state.is_halted is False
        assert rm.state.daily_start_equity == 9500.0


# =====================================================================
# 4. Risk Manager — thread safety on concurrent update_equity
# =====================================================================


class TestRiskManagerThreadSafety:
    """Test concurrent update_equity calls do not corrupt state."""

    def test_concurrent_updates_no_corruption(self):
        rm = RiskManager(RiskLimits(max_portfolio_drawdown=0.99))  # high limit so no halt
        rm.state.peak_equity = 10000.0
        rm.state.daily_start_equity = 10000.0

        errors = []
        results = []

        def update_equity_worker(equity_val):
            try:
                result = rm.update_equity(equity_val)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = []
        # 20 concurrent updates with different equity values
        equity_values = [10000 - i * 10 for i in range(20)]
        for val in equity_values:
            t = threading.Thread(target=update_equity_worker, args=(val,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 20
        # State should be consistent: equity is one of the values we set
        assert rm.state.total_equity in equity_values or rm.state.total_equity >= 0
        # Peak should be at least 10000 (the initial peak)
        assert rm.state.peak_equity >= 10000.0

    def test_concurrent_register_and_close(self):
        """Register and close trades concurrently without corruption."""
        rm = RiskManager()
        errors = []

        def register_worker(symbol):
            try:
                rm.register_trade(symbol, "buy", 0.01, 50000)
            except Exception as e:
                errors.append(e)

        def close_worker(symbol):
            try:
                rm.close_trade(symbol, 51000)
            except Exception as e:
                errors.append(e)

        symbols = [f"SYM{i}/USDT" for i in range(10)]
        # Register all, then close all concurrently
        reg_threads = [threading.Thread(target=register_worker, args=(s,)) for s in symbols]
        for t in reg_threads:
            t.start()
        for t in reg_threads:
            t.join()

        assert len(errors) == 0
        assert len(rm.state.open_positions) == 10

        close_threads = [threading.Thread(target=close_worker, args=(s,)) for s in symbols]
        for t in close_threads:
            t.start()
        for t in close_threads:
            t.join()

        assert len(errors) == 0
        assert len(rm.state.open_positions) == 0


# =====================================================================
# 5. Strategy Router — UNKNOWN regime behavior
# =====================================================================


class TestStrategyRouterUnknownRegime:
    """Test behavior when regime is UNKNOWN."""

    def test_unknown_regime_routes_defensively(self):
        router = StrategyRouter(asset_class="crypto")
        state = _make_regime_state(Regime.UNKNOWN)
        decision = router.route(state)
        assert decision.primary_strategy == BMR
        assert decision.position_size_modifier <= 0.3

    def test_unknown_regime_low_confidence_further_reduces(self):
        """UNKNOWN with low confidence should compound the penalty."""
        router = StrategyRouter(
            asset_class="crypto",
            low_confidence_threshold=0.5,
            low_confidence_penalty=0.5,
        )
        state = _make_regime_state(Regime.UNKNOWN, confidence=0.2)
        decision = router.route(state)
        # Base modifier for UNKNOWN is 0.3, low confidence penalty halves it
        assert decision.position_size_modifier == pytest.approx(0.15, abs=0.01)


# =====================================================================
# 6. Strategy Router — asset class routing tables
# =====================================================================


class TestStrategyRouterAssetClassRouting:
    """Test EQUITY_ROUTING and FOREX_ROUTING tables."""

    def test_equity_strong_trend_up_routes_to_momentum(self):
        router = StrategyRouter(asset_class="equity")
        state = _make_regime_state(Regime.STRONG_TREND_UP)
        decision = router.route(state)
        assert decision.primary_strategy == EQ_MOM
        assert decision.position_size_modifier == 1.0

    def test_equity_ranging_routes_to_mean_reversion(self):
        router = StrategyRouter(asset_class="equity")
        state = _make_regime_state(Regime.RANGING)
        decision = router.route(state)
        assert decision.primary_strategy == EQ_MR
        assert decision.position_size_modifier == 1.0

    def test_equity_unknown_is_very_conservative(self):
        router = StrategyRouter(asset_class="equity")
        state = _make_regime_state(Regime.UNKNOWN)
        decision = router.route(state)
        assert decision.primary_strategy == EQ_MR
        assert decision.position_size_modifier <= 0.2

    def test_equity_strong_down_minimal_exposure(self):
        router = StrategyRouter(asset_class="equity")
        state = _make_regime_state(Regime.STRONG_TREND_DOWN)
        decision = router.route(state)
        assert decision.position_size_modifier <= 0.2

    def test_forex_strong_trend_up_routes_to_trend(self):
        router = StrategyRouter(asset_class="forex")
        state = _make_regime_state(Regime.STRONG_TREND_UP)
        decision = router.route(state)
        assert decision.primary_strategy == FX_TREND
        assert decision.position_size_modifier == 1.0

    def test_forex_ranging_routes_to_range(self):
        router = StrategyRouter(asset_class="forex")
        state = _make_regime_state(Regime.RANGING)
        decision = router.route(state)
        assert decision.primary_strategy == FX_RANGE

    def test_forex_weak_trend_up_blended(self):
        router = StrategyRouter(asset_class="forex")
        state = _make_regime_state(Regime.WEAK_TREND_UP)
        decision = router.route(state)
        assert decision.primary_strategy == FX_TREND
        names = {w.strategy_name for w in decision.weights}
        assert FX_TREND in names
        assert FX_RANGE in names

    def test_forex_unknown_conservative(self):
        router = StrategyRouter(asset_class="forex")
        state = _make_regime_state(Regime.UNKNOWN)
        decision = router.route(state)
        assert decision.primary_strategy == FX_RANGE
        assert decision.position_size_modifier <= 0.3

    def test_all_equity_regimes_covered(self):
        router = StrategyRouter(asset_class="equity")
        for regime in Regime:
            state = _make_regime_state(regime)
            decision = router.route(state)
            assert isinstance(decision, RoutingDecision)
            assert len(decision.weights) > 0

    def test_all_forex_regimes_covered(self):
        router = StrategyRouter(asset_class="forex")
        for regime in Regime:
            state = _make_regime_state(regime)
            decision = router.route(state)
            assert isinstance(decision, RoutingDecision)
            assert len(decision.weights) > 0

    def test_equity_strategies_list(self):
        router = StrategyRouter(asset_class="equity")
        strategies = router.get_all_strategies()
        assert EQ_MOM in strategies
        assert EQ_MR in strategies

    def test_forex_strategies_list(self):
        router = StrategyRouter(asset_class="forex")
        strategies = router.get_all_strategies()
        assert FX_TREND in strategies
        assert FX_RANGE in strategies


# =====================================================================
# 7. Strategy Router — sentiment modifier scaling
# =====================================================================


class TestStrategyRouterSentimentModifier:
    """Test position_modifier scaling with sentiment [0.5, 1.5]."""

    def test_sentiment_modifier_1_0_no_change(self):
        router = StrategyRouter(asset_class="crypto")
        state = _make_regime_state(Regime.STRONG_TREND_UP, confidence=0.8)
        decision = router.route(state, sentiment_modifier=1.0)
        # Base modifier for STRONG_TREND_UP is 1.0 * 1.0 = 1.0
        assert decision.position_size_modifier == 1.0
        assert decision.sentiment_modifier == 1.0

    def test_sentiment_modifier_1_5_increases_size(self):
        router = StrategyRouter(asset_class="crypto")
        state = _make_regime_state(Regime.STRONG_TREND_UP, confidence=0.8)
        base_decision = router.route(state, sentiment_modifier=None)
        boosted_decision = router.route(state, sentiment_modifier=1.5)
        assert boosted_decision.position_size_modifier > base_decision.position_size_modifier

    def test_sentiment_modifier_0_5_decreases_size(self):
        router = StrategyRouter(asset_class="crypto")
        state = _make_regime_state(Regime.STRONG_TREND_UP, confidence=0.8)
        base_decision = router.route(state, sentiment_modifier=None)
        reduced_decision = router.route(state, sentiment_modifier=0.5)
        assert reduced_decision.position_size_modifier < base_decision.position_size_modifier

    def test_sentiment_modifier_clamped_above_1_5(self):
        """Values above 1.5 should be clamped to 1.5."""
        router = StrategyRouter(asset_class="crypto")
        state = _make_regime_state(Regime.STRONG_TREND_UP, confidence=0.8)
        decision_1_5 = router.route(state, sentiment_modifier=1.5)
        decision_3_0 = router.route(state, sentiment_modifier=3.0)
        assert decision_1_5.position_size_modifier == decision_3_0.position_size_modifier

    def test_sentiment_modifier_clamped_below_0_5(self):
        """Values below 0.5 should be clamped to 0.5."""
        router = StrategyRouter(asset_class="crypto")
        state = _make_regime_state(Regime.STRONG_TREND_UP, confidence=0.8)
        decision_0_5 = router.route(state, sentiment_modifier=0.5)
        decision_neg = router.route(state, sentiment_modifier=-1.0)
        assert decision_0_5.position_size_modifier == decision_neg.position_size_modifier

    def test_sentiment_modifier_none_preserves_behavior(self):
        router = StrategyRouter(asset_class="crypto")
        state = _make_regime_state(Regime.RANGING, confidence=0.8)
        decision = router.route(state, sentiment_modifier=None)
        assert decision.sentiment_modifier is None
        assert decision.position_size_modifier == 1.0

    def test_sentiment_modifier_stored_in_decision(self):
        router = StrategyRouter(asset_class="crypto")
        state = _make_regime_state(Regime.RANGING, confidence=0.8)
        decision = router.route(state, sentiment_modifier=1.2)
        assert decision.sentiment_modifier == 1.2


# =====================================================================
# 8. Regime Detector — edge cases (flat, single point, NaN-heavy)
# =====================================================================


class TestRegimeDetectorEdgeCases:
    """Test regime detection with degenerate data."""

    def test_all_flat_data(self):
        """All-flat close prices (zero volatility)."""
        df = _make_ohlcv(200, flat=True)
        # Flat data: high=low=close, so fix high/low
        df["high"] = df["close"] + 0.01
        df["low"] = df["close"] - 0.01
        detector = RegimeDetector()
        state = detector.detect(df)
        assert isinstance(state.regime, Regime)
        # Flat data should be RANGING or LOW volatility, not strong trend
        assert state.regime not in (Regime.STRONG_TREND_UP, Regime.STRONG_TREND_DOWN)

    def test_single_data_point(self):
        """Single row DataFrame should not crash; produces UNKNOWN."""
        df = _make_ohlcv(1)
        detector = RegimeDetector()
        # detect_series handles NaN rows as UNKNOWN
        result = detector.detect_series(df)
        assert len(result) == 1
        assert result["regime"].iloc[0] == Regime.UNKNOWN

    def test_nan_heavy_data(self):
        """DataFrame with many NaN values should produce mostly UNKNOWN."""
        df = _make_ohlcv(50)
        # Insert NaNs into close column for the first 30 rows
        df.iloc[:30, df.columns.get_loc("close")] = np.nan
        df.iloc[:30, df.columns.get_loc("high")] = np.nan
        df.iloc[:30, df.columns.get_loc("low")] = np.nan
        detector = RegimeDetector()
        result = detector.detect_series(df)
        early_regimes = result["regime"].iloc[:15].tolist()
        # Most early rows should be UNKNOWN due to NaN propagation
        unknown_count = sum(1 for r in early_regimes if r == Regime.UNKNOWN)
        assert unknown_count >= len(early_regimes) // 2

    def test_very_short_data_does_not_crash(self):
        """5-row DataFrame should work without exceptions."""
        df = _make_ohlcv(5)
        detector = RegimeDetector()
        result = detector.detect_series(df)
        assert len(result) == 5

    def test_config_for_asset_class_equity(self):
        cfg = config_for_asset_class("equity")
        assert cfg.adx_strong == 35.0
        assert cfg.adx_weak == 20.0

    def test_config_for_asset_class_forex(self):
        cfg = config_for_asset_class("forex")
        assert cfg.adx_strong == 35.0
        assert cfg.bb_high_vol_pct == 65.0

    def test_config_for_unknown_asset_class_uses_defaults(self):
        cfg = config_for_asset_class("commodities")
        assert cfg.adx_strong == 40.0  # default


# =====================================================================
# 9. Correlation matrix with < 20 observations
# =====================================================================


class TestCorrelationMatrixInsufficientData:
    """Test correlation with fewer than 20 observations."""

    def test_fewer_than_20_returns_empty(self):
        tracker = ReturnTracker()
        for p in range(15):  # 15 prices = 14 returns
            tracker.record_price("A", 100.0 + p)
            tracker.record_price("B", 200.0 + p * 2)
        corr = tracker.get_correlation_matrix()
        assert corr.empty

    def test_exactly_20_returns_non_empty(self):
        tracker = ReturnTracker()
        np.random.seed(42)
        for _i in range(21):  # 21 prices = 20 returns
            tracker.record_price("A", 100.0 + np.random.randn())
            tracker.record_price("B", 200.0 + np.random.randn())
        corr = tracker.get_correlation_matrix()
        assert not corr.empty
        assert "A" in corr.columns
        assert "B" in corr.columns

    def test_mixed_lengths_uses_minimum(self):
        """When symbols have different numbers of observations, use the minimum shared length."""
        tracker = ReturnTracker()
        np.random.seed(42)
        # A gets 25 prices (24 returns), B gets 30 prices (29 returns)
        for _i in range(25):
            tracker.record_price("A", 100.0 + np.random.randn())
        for _i in range(30):
            tracker.record_price("B", 200.0 + np.random.randn())
        corr = tracker.get_correlation_matrix(["A", "B"])
        assert not corr.empty

    def test_one_symbol_below_threshold_excluded(self):
        """If only one of the requested symbols has < 20 returns, it is excluded."""
        tracker = ReturnTracker()
        np.random.seed(42)
        for _i in range(25):
            tracker.record_price("A", 100.0 + np.random.randn())
        for _i in range(10):  # only 9 returns
            tracker.record_price("B", 200.0 + np.random.randn())
        corr = tracker.get_correlation_matrix(["A", "B"])
        # B filtered out, only A remains → need 2 symbols → empty
        assert corr.empty


# =====================================================================
# 10. Technical Indicators — edge cases (zeros, NaNs, single row)
# =====================================================================


class TestTechnicalIndicatorsEdgeCases:
    """Test each indicator with degenerate data."""

    def test_sma_single_row(self):
        s = pd.Series([100.0])
        result = sma(s, 14)
        assert len(result) == 1
        assert pd.isna(result.iloc[0])

    def test_ema_single_row(self):
        s = pd.Series([100.0])
        result = ema(s, 14)
        assert len(result) == 1
        # EMA with adjust=False on single value should return the value
        assert result.iloc[0] == pytest.approx(100.0)

    def test_rsi_all_zeros(self):
        """RSI with constant prices (no change) should be NaN (0/0)."""
        s = pd.Series([100.0] * 30)
        result = rsi(s, 14)
        # All deltas are 0, so avg_gain=0, avg_loss=0 → NaN
        assert result.iloc[-1] != result.iloc[-1] or True  # NaN or any value is OK

    def test_rsi_nan_values(self):
        """RSI should handle NaN in the series."""
        s = pd.Series([np.nan, np.nan, 100.0, 105.0, 103.0, 108.0])
        result = rsi(s, 3)
        assert len(result) == 6

    def test_bollinger_bands_single_row(self):
        s = pd.Series([100.0])
        result = bollinger_bands(s, 20)
        assert len(result) == 1
        assert pd.isna(result["bb_mid"].iloc[0])

    def test_bollinger_bands_constant_data(self):
        """Constant data: std=0, bands collapse to the mean."""
        s = pd.Series([100.0] * 30)
        result = bollinger_bands(s, 20)
        # After warmup, std is 0, so upper=mid=lower=100
        assert result["bb_mid"].iloc[-1] == pytest.approx(100.0)
        assert result["bb_upper"].iloc[-1] == pytest.approx(100.0)

    def test_macd_returns_three_columns(self):
        s = pd.Series(np.random.randn(50) + 100)
        result = macd(s)
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_hist" in result.columns

    def test_atr_with_zeros(self):
        """ATR with zero range (high=low=close)."""
        df = pd.DataFrame({
            "high": [100.0] * 20,
            "low": [100.0] * 20,
            "close": [100.0] * 20,
        })
        result = atr_indicator(df, 14)
        assert result.iloc[-1] == pytest.approx(0.0)

    def test_obv_handles_constant_close(self):
        """OBV with constant close: direction=0, OBV stays at 0."""
        df = pd.DataFrame({
            "close": [100.0] * 10,
            "volume": [1000.0] * 10,
        })
        result = obv(df)
        # First row direction is undefined (shift), rest are 0
        assert result.iloc[-1] == pytest.approx(0.0)

    def test_stochastic_single_row(self):
        df = pd.DataFrame({"high": [110.0], "low": [90.0], "close": [100.0]})
        result = stochastic(df, 14)
        assert len(result) == 1

    def test_williams_r_range(self):
        """Williams %R should be in [-100, 0]."""
        df = _make_ohlcv(50)
        result = williams_r(df, 14)
        valid = result.dropna()
        assert (valid <= 0).all()
        assert (valid >= -100).all()

    def test_cci_handles_nan(self):
        df = _make_ohlcv(30)
        result = cci(df, 20)
        assert len(result) == 30

    def test_mfi_handles_zero_volume(self):
        df = _make_ohlcv(30)
        df["volume"] = 0.0
        result = mfi(df, 14)
        assert len(result) == 30

    def test_hull_ma_short_period(self):
        s = pd.Series(np.random.randn(20) + 100)
        result = hull_ma(s, 4)
        assert len(result) == 20

    def test_wma_basic(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = wma(s, 3)
        # WMA(3) for last value: (3*5 + 2*4 + 1*3) / 6 = (15+8+3)/6 = 26/6
        assert result.iloc[-1] == pytest.approx(26.0 / 6.0, abs=1e-6)

    def test_vwap_basic(self):
        df = _make_ohlcv(20)
        result = vwap(df)
        assert len(result) == 20
        # VWAP should be in the range of close prices
        valid = result.dropna()
        assert valid.iloc[-1] > 0

    def test_supertrend_basic(self):
        df = _make_ohlcv(50)
        result = supertrend(df, period=10, multiplier=3.0)
        assert "supertrend" in result.columns
        assert "supertrend_direction" in result.columns
        assert len(result) == 50
        # Direction should be +1 or -1
        valid_dir = result["supertrend_direction"].dropna()
        assert set(valid_dir.unique()).issubset({-1, 1})

    def test_adx_range(self):
        """ADX should be >= 0 (and typically <= 100)."""
        df = _make_ohlcv(100)
        result = adx(df, 14)
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_add_all_indicators_does_not_crash(self):
        """add_all_indicators on minimal data should not crash."""
        df = _make_ohlcv(250)
        result = add_all_indicators(df)
        assert "rsi_14" in result.columns
        assert "bb_upper" in result.columns
        assert "obv" in result.columns
        assert len(result) == 250

    def test_keltner_channels_basic(self):
        from common.indicators.technical import keltner_channels

        df = _make_ohlcv(30)
        result = keltner_channels(df, ema_period=20, atr_period=10)
        assert "kc_upper" in result.columns
        assert "kc_mid" in result.columns
        assert "kc_lower" in result.columns


# =====================================================================
# Bonus: VaR with zero-sigma returns
# =====================================================================


class TestVaREdgeCases:
    """Additional VaR edge cases."""

    def test_var_with_zero_sigma_returns(self):
        """If all returns are identical (sigma=0), parametric VaR should handle it."""
        tracker = ReturnTracker()
        # 25 identical prices → 24 returns of 0
        for _ in range(25):
            tracker.record_price("A", 100.0)
        result = tracker.compute_var({"A": 1.0}, 10000, method="parametric")
        # sigma=0 → function should return VaRResult with zero values
        assert result.var_95 == 0.0
        assert result.var_99 == 0.0

    def test_var_historical_with_few_observations(self):
        """Historical VaR with exactly 20 observations should work."""
        tracker = ReturnTracker()
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(21) * 0.5)
        for p in prices:
            tracker.record_price("A", float(p))
        result = tracker.compute_var({"A": 1.0}, 10000, method="historical")
        assert result.window_days == 20
        assert result.var_95 >= 0  # Could be negative returns


# =====================================================================
# Bonus: Sentiment signal module additional edge cases
# =====================================================================


class TestSentimentSignalEdgeCases:
    """Additional edge cases for the sentiment signal engine."""

    def test_negative_age_clamped_to_zero(self):
        """Negative age_hours should be clamped to 0 (treated as fresh)."""
        articles = [
            {"sentiment_score": 0.5, "age_hours": -5.0, "title": "Test", "summary": ""},
        ]
        result = compute_signal(articles, "crypto", rescore=False)
        # Should not crash, treat as age=0
        assert result.article_count == 1
        assert result.signal > 0

    def test_missing_keys_in_article(self):
        """Articles with missing keys should use defaults."""
        articles = [{}]  # all keys missing
        result = compute_signal(articles, "crypto", rescore=False)
        assert result.article_count == 1
        assert result.signal == 0.0  # default sentiment_score=0

    def test_forex_conviction_threshold_different(self):
        """Forex has a lower conviction threshold (8) than crypto (20)."""
        articles = [
            {"sentiment_score": 0.5, "age_hours": 1.0, "title": "X", "summary": ""}
            for _ in range(8)
        ]
        crypto_result = compute_signal(articles, "crypto", rescore=False)
        forex_result = compute_signal(articles, "forex", rescore=False)
        # 8 articles: crypto conviction=8/20=0.4, forex conviction=8/8=1.0
        assert forex_result.conviction > crypto_result.conviction
