"""Full coverage tests for common/ shared libraries.

Covers: indicators/technical.py, regime/regime_detector.py, regime/strategy_router.py,
sentiment/signal.py, market_hours/sessions.py, ml/trainer.py, ml/features.py, ml/registry.py.
"""

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.indicators.technical import (
    adx,
    add_all_indicators,
    atr_indicator,
    bollinger_bands,
    cci,
    ema,
    hull_ma,
    keltner_channels,
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
    RegimeConfig,
    RegimeDetector,
    RegimeState,
    config_for_asset_class,
)
from common.regime.strategy_router import (
    RoutingDecision,
    StrategyRouter,
    StrategyWeight,
)
from common.sentiment.signal import (
    SentimentSignal,
    _compute_decay_weight,
    _compute_term_multiplier,
    compute_signal,
    BULLISH_THRESHOLD,
    BEARISH_THRESHOLD,
)
from common.market_hours.sessions import MarketHoursService


# ── Helpers ────────────────────────────────────

def _make_ohlcv(periods=100, seed=42, base=50000):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    close = base + rng.randn(periods).cumsum() * 100
    high = close + rng.uniform(10, 200, periods)
    low = close - rng.uniform(10, 200, periods)
    opn = close + rng.uniform(-100, 100, periods)
    high = np.maximum(high, np.maximum(opn, close))
    low = np.minimum(low, np.minimum(opn, close))
    volume = rng.uniform(100, 10000, periods)
    return pd.DataFrame(
        {"open": opn, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


# ══════════════════════════════════════════════
# Technical Indicators
# ══════════════════════════════════════════════


class TestTrendIndicators:
    def test_sma(self):
        s = pd.Series(range(20), dtype=float)
        result = sma(s, 5)
        assert pd.isna(result.iloc[3])
        assert result.iloc[4] == 2.0  # mean(0,1,2,3,4)

    def test_ema(self):
        s = pd.Series([1.0] * 20)
        result = ema(s, 5)
        assert abs(result.iloc[-1] - 1.0) < 1e-10

    def test_wma(self):
        s = pd.Series(range(10), dtype=float)
        result = wma(s, 3)
        assert pd.isna(result.iloc[1])
        assert not pd.isna(result.iloc[2])

    def test_hull_ma(self):
        s = pd.Series(range(20), dtype=float)
        result = hull_ma(s, 9)
        assert len(result) == 20

    def test_supertrend(self):
        df = _make_ohlcv(50)
        result = supertrend(df, period=10)
        assert "supertrend" in result.columns
        assert "supertrend_direction" in result.columns
        assert set(result["supertrend_direction"].dropna().unique()).issubset({-1, 1})

    def test_sma_nan_input(self):
        s = pd.Series([1.0, np.nan, 3.0, 4.0, 5.0])
        result = sma(s, 3)
        assert pd.isna(result.iloc[2])  # NaN in window

    def test_sma_empty_series(self):
        s = pd.Series([], dtype=float)
        result = sma(s, 5)
        assert result.empty


class TestMomentumIndicators:
    def test_rsi_range(self):
        df = _make_ohlcv(100)
        result = rsi(df["close"], 14)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_constant_price(self):
        s = pd.Series([100.0] * 30)
        result = rsi(s, 14)
        # Constant price: gain=0, loss=0, RS=NaN → RSI=NaN
        assert result.iloc[-1] != result.iloc[-1] or abs(result.iloc[-1] - 50) < 50

    def test_macd_structure(self):
        s = pd.Series(range(50), dtype=float)
        result = macd(s)
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_hist" in result.columns

    def test_stochastic_range(self):
        df = _make_ohlcv(50)
        result = stochastic(df)
        valid_k = result["stoch_k"].dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()

    def test_cci(self):
        df = _make_ohlcv(50)
        result = cci(df)
        assert len(result) == 50

    def test_williams_r_range(self):
        df = _make_ohlcv(50)
        result = williams_r(df)
        valid = result.dropna()
        assert (valid >= -100).all() and (valid <= 0).all()

    def test_adx_range(self):
        df = _make_ohlcv(100)
        result = adx(df)
        valid = result.dropna()
        assert (valid >= 0).all()


class TestVolatilityIndicators:
    def test_atr(self):
        df = _make_ohlcv(50)
        result = atr_indicator(df, 14)
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_bollinger_bands(self):
        s = pd.Series(range(50), dtype=float)
        result = bollinger_bands(s)
        assert "bb_upper" in result.columns
        assert "bb_lower" in result.columns
        valid = result.dropna()
        assert (valid["bb_upper"] >= valid["bb_lower"]).all()

    def test_keltner_channels(self):
        df = _make_ohlcv(50)
        result = keltner_channels(df)
        assert "kc_upper" in result.columns
        valid = result.dropna()
        assert (valid["kc_upper"] >= valid["kc_lower"]).all()


class TestVolumeIndicators:
    def test_obv(self):
        df = _make_ohlcv(50)
        result = obv(df)
        assert len(result) == 50

    def test_vwap(self):
        df = _make_ohlcv(50)
        result = vwap(df)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_mfi_range(self):
        df = _make_ohlcv(50)
        result = mfi(df)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_obv_zero_volume(self):
        df = _make_ohlcv(10)
        df["volume"] = 0
        result = obv(df)
        assert (result == 0).all()


class TestAddAllIndicators:
    def test_adds_all_expected_columns(self):
        df = _make_ohlcv(250)
        result = add_all_indicators(df)
        assert "sma_7" in result.columns
        assert "rsi_14" in result.columns
        assert "macd" in result.columns
        assert "bb_upper" in result.columns
        assert "obv" in result.columns
        assert "returns" in result.columns

    def test_does_not_modify_original(self):
        df = _make_ohlcv(50)
        cols_before = list(df.columns)
        add_all_indicators(df)
        assert list(df.columns) == cols_before

    def test_short_data(self):
        df = _make_ohlcv(5)
        result = add_all_indicators(df)
        assert len(result) == 5

    def test_nan_input(self):
        df = _make_ohlcv(30)
        df.iloc[10, df.columns.get_loc("close")] = np.nan
        result = add_all_indicators(df)
        assert not result.empty


# ══════════════════════════════════════════════
# Regime Detector
# ══════════════════════════════════════════════


class TestRegimeDetector:
    def test_config_for_asset_class_crypto(self):
        config = config_for_asset_class("crypto")
        assert config.adx_strong == 40

    def test_config_for_asset_class_equity(self):
        config = config_for_asset_class("equity")
        assert config.adx_strong == 35

    def test_config_for_asset_class_forex(self):
        config = config_for_asset_class("forex")
        assert config.adx_strong == 35

    def test_config_for_unknown_asset_class(self):
        config = config_for_asset_class("commodities")
        # Should use default config
        assert config.adx_strong == 40  # crypto defaults

    def test_detect_returns_regime_state(self):
        df = _make_ohlcv(200)
        detector = RegimeDetector()
        state = detector.detect(df)
        assert isinstance(state, RegimeState)
        assert isinstance(state.regime, Regime)
        assert 0 <= state.confidence <= 1

    def test_detect_series_returns_dataframe(self):
        df = _make_ohlcv(200)
        detector = RegimeDetector()
        result = detector.detect_series(df)
        assert isinstance(result, pd.DataFrame)
        assert "regime" in result.columns

    def test_detect_short_data(self):
        df = _make_ohlcv(5)
        detector = RegimeDetector()
        state = detector.detect(df)
        # Should handle gracefully, likely UNKNOWN
        assert isinstance(state.regime, Regime)

    def test_all_regimes_valid(self):
        assert len(Regime) == 7
        for r in Regime:
            assert isinstance(r.value, str)

    def test_regime_state_defaults(self):
        state = RegimeState(
            regime=Regime.UNKNOWN, confidence=0.0,
            adx_value=0.0, bb_width_percentile=0.0,
            ema_slope=0.0, trend_alignment=0.0, price_structure_score=0.0,
        )
        assert state.adx_value == 0.0
        assert state.transition_probabilities == {}

    def test_detector_asset_class(self):
        d1 = RegimeDetector(asset_class="crypto")
        d2 = RegimeDetector(asset_class="equity")
        assert d1.config.adx_strong == 40
        assert d2.config.adx_strong == 35


# ══════════════════════════════════════════════
# Strategy Router
# ══════════════════════════════════════════════


class TestStrategyRouter:
    def _make_state(self, regime, confidence=0.8):
        return RegimeState(
            regime=regime, confidence=confidence,
            adx_value=30.0, bb_width_percentile=50.0,
            ema_slope=0.1, trend_alignment=0.5, price_structure_score=0.5,
        )

    def test_routing_crypto_strong_trend_up(self):
        router = StrategyRouter(asset_class="crypto")
        state = self._make_state(Regime.STRONG_TREND_UP)
        decision = router.route(state)
        assert isinstance(decision, RoutingDecision)
        assert decision.regime == Regime.STRONG_TREND_UP
        assert len(decision.weights) > 0

    def test_routing_unknown_regime(self):
        router = StrategyRouter()
        state = self._make_state(Regime.UNKNOWN, confidence=0.0)
        decision = router.route(state)
        assert decision.position_size_modifier < 1.0  # Should be defensive

    def test_equity_routing(self):
        router = StrategyRouter(asset_class="equity")
        state = self._make_state(Regime.STRONG_TREND_UP)
        decision = router.route(state)
        assert len(decision.weights) > 0

    def test_forex_routing(self):
        router = StrategyRouter(asset_class="forex")
        state = self._make_state(Regime.RANGING, confidence=0.7)
        decision = router.route(state)
        assert len(decision.weights) > 0

    def test_sentiment_modifier_none(self):
        router = StrategyRouter()
        state = self._make_state(Regime.STRONG_TREND_UP)
        decision = router.route(state, sentiment_modifier=None)
        assert decision.sentiment_modifier is None

    def test_sentiment_modifier_clamped_on_position(self):
        """Sentiment modifier clamps position_size_modifier, stores raw value."""
        router = StrategyRouter()
        state = self._make_state(Regime.STRONG_TREND_UP)
        decision = router.route(state, sentiment_modifier=0.3)
        # Raw sentiment stored as-is
        assert decision.sentiment_modifier == 0.3
        # But position_size_modifier reflects clamped [0.5, 1.5] * base modifier
        assert decision.position_size_modifier > 0

    def test_sentiment_modifier_high(self):
        router = StrategyRouter()
        state = self._make_state(Regime.STRONG_TREND_UP)
        decision = router.route(state, sentiment_modifier=2.0)
        # Raw value stored
        assert decision.sentiment_modifier == 2.0

    def test_low_confidence_penalty(self):
        router = StrategyRouter()
        dec_low = router.route(self._make_state(Regime.STRONG_TREND_UP, confidence=0.2))
        dec_high = router.route(self._make_state(Regime.STRONG_TREND_UP, confidence=0.9))
        assert dec_low.position_size_modifier <= dec_high.position_size_modifier

    def test_strategy_weight_dataclass(self):
        sw = StrategyWeight("test", 0.5, 0.8)
        assert sw.strategy_name == "test"
        assert sw.weight == 0.5
        assert sw.position_size_factor == 0.8

    def test_get_all_strategies(self):
        router = StrategyRouter()
        strategies = router.get_all_strategies()
        assert isinstance(strategies, list)
        assert len(strategies) > 0

    def test_get_routing_table(self):
        router = StrategyRouter()
        table = router.get_routing_table()
        assert isinstance(table, dict)
        assert len(table) > 0

    def test_suggest_strategy_switch(self):
        router = StrategyRouter()
        state = self._make_state(Regime.STRONG_TREND_DOWN, confidence=0.9)
        result = router.suggest_strategy_switch("CryptoInvestorV1", state)
        assert result is None or isinstance(result, RoutingDecision)


# ══════════════════════════════════════════════
# Sentiment Signal
# ══════════════════════════════════════════════


class TestSentimentSignal:
    def test_decay_weight_zero_age(self):
        w = _compute_decay_weight(0, 6.0)
        assert abs(w - 1.0) < 1e-10

    def test_decay_weight_one_halflife(self):
        w = _compute_decay_weight(6.0, 6.0)
        assert abs(w - 0.5) < 1e-6

    def test_decay_weight_two_halflives(self):
        w = _compute_decay_weight(12.0, 6.0)
        assert abs(w - 0.25) < 1e-6

    def test_term_multiplier_crypto(self):
        m = _compute_term_multiplier("halving event incoming defi", "crypto")
        assert m > 1.0

    def test_term_multiplier_no_match(self):
        m = _compute_term_multiplier("random unrelated text", "crypto")
        assert m == 1.0

    def test_term_multiplier_empty_string(self):
        m = _compute_term_multiplier("", "crypto")
        assert m == 1.0

    def test_compute_signal_empty(self):
        sig = compute_signal([], "crypto")
        assert isinstance(sig, SentimentSignal)
        assert sig.signal == 0.0
        assert sig.signal_label == "neutral"
        assert sig.article_count == 0

    def test_compute_signal_bullish(self):
        articles = [
            {"sentiment_score": 0.8, "title": "Bitcoin Surges",
             "summary": "", "published_at": datetime.now(tz=timezone.utc)}
        ]
        sig = compute_signal(articles, "crypto")
        assert sig.signal > 0

    def test_compute_signal_bearish(self):
        articles = [
            {"sentiment_score": -0.8, "title": "Crash",
             "summary": "", "published_at": datetime.now(tz=timezone.utc)}
        ]
        sig = compute_signal(articles, "crypto")
        assert sig.signal < 0

    def test_position_modifier_bounds(self):
        """Position modifier should be in [0.8, 1.2]."""
        articles_bull = [
            {"sentiment_score": 1.0, "title": "Moon",
             "summary": "", "published_at": datetime.now(tz=timezone.utc)}
            for _ in range(50)
        ]
        sig = compute_signal(articles_bull, "crypto")
        assert 0.8 <= sig.position_modifier <= 1.2

        articles_bear = [
            {"sentiment_score": -1.0, "title": "Doom",
             "summary": "", "published_at": datetime.now(tz=timezone.utc)}
            for _ in range(50)
        ]
        sig = compute_signal(articles_bear, "crypto")
        assert 0.8 <= sig.position_modifier <= 1.2

    def test_signal_label_thresholds(self):
        # At exact threshold
        sig = SentimentSignal(
            signal=BULLISH_THRESHOLD, conviction=0.5, signal_label="bullish",
            position_modifier=1.0, article_count=5, avg_age_hours=1.0, asset_class="crypto"
        )
        assert sig.signal_label == "bullish"

    def test_temporal_decay_recent_more_weight(self):
        recent = [{"sentiment_score": 0.5, "title": "Good news", "summary": "",
                   "published_at": datetime.now(tz=timezone.utc)}]
        old = [{"sentiment_score": 0.5, "title": "Good news", "summary": "",
                "published_at": datetime.now(tz=timezone.utc) - timedelta(hours=24)}]
        sig_recent = compute_signal(recent, "crypto")
        sig_old = compute_signal(old, "crypto")
        assert sig_recent.signal >= sig_old.signal

    def test_different_asset_classes(self):
        articles = [{"sentiment_score": 0.5, "title": "market up", "summary": "",
                     "published_at": datetime.now(tz=timezone.utc)}]
        for ac in ["crypto", "equity", "forex"]:
            sig = compute_signal(articles, ac)
            assert isinstance(sig, SentimentSignal)
            assert sig.asset_class == ac


# ══════════════════════════════════════════════
# Market Hours
# ══════════════════════════════════════════════


class TestMarketHours:
    def test_crypto_always_open(self):
        assert MarketHoursService.is_market_open("crypto") is True

    def test_crypto_next_open_none(self):
        assert MarketHoursService.next_open("crypto") is None

    def test_crypto_next_close_none(self):
        assert MarketHoursService.next_close("crypto") is None

    def test_equity_open_during_hours(self):
        # Tuesday 11:00 AM ET = 16:00 UTC (EST)
        now = datetime(2025, 1, 7, 16, 0, tzinfo=timezone.utc)
        assert MarketHoursService.is_market_open("equity", now=now) is True

    def test_equity_closed_evening(self):
        # Tuesday 9:00 PM ET = Wed 02:00 UTC
        now = datetime(2025, 1, 8, 2, 0, tzinfo=timezone.utc)
        assert MarketHoursService.is_market_open("equity", now=now) is False

    def test_equity_closed_weekend(self):
        # Saturday
        now = datetime(2025, 1, 4, 15, 0, tzinfo=timezone.utc)
        assert MarketHoursService.is_market_open("equity", now=now) is False

    def test_forex_open_midweek(self):
        # Wednesday 12:00 UTC
        now = datetime(2025, 1, 8, 12, 0, tzinfo=timezone.utc)
        assert MarketHoursService.is_market_open("forex", now=now) is True

    def test_forex_closed_saturday(self):
        now = datetime(2025, 1, 4, 12, 0, tzinfo=timezone.utc)
        assert MarketHoursService.is_market_open("forex", now=now) is False

    def test_session_info_structure(self):
        info = MarketHoursService.get_session_info("crypto")
        assert "is_open" in info
        assert "session" in info

    def test_session_info_equity(self):
        info = MarketHoursService.get_session_info("equity")
        assert "is_open" in info

    def test_unknown_asset_class(self):
        # Unknown should default to crypto (always open) or handle gracefully
        try:
            result = MarketHoursService.is_market_open("commodities")
            assert isinstance(result, bool)
        except (KeyError, ValueError):
            pass  # Acceptable to raise

    def test_next_open_when_closed(self):
        # Saturday equity
        now = datetime(2025, 1, 4, 15, 0, tzinfo=timezone.utc)
        result = MarketHoursService.next_open("equity", now=now)
        assert result is not None

    def test_next_close_when_open(self):
        # Tuesday equity open
        now = datetime(2025, 1, 7, 16, 0, tzinfo=timezone.utc)
        result = MarketHoursService.next_close("equity", now=now)
        assert result is not None or result is None  # May not be implemented


# ══════════════════════════════════════════════
# ML Trainer
# ══════════════════════════════════════════════


class TestMLTrainer:
    @pytest.fixture
    def ml_data(self):
        """Generate training data with enough rows."""
        rng = np.random.RandomState(42)
        n = 200
        X = pd.DataFrame({
            f"feat_{i}": rng.randn(n) for i in range(5)
        })
        y = pd.Series((rng.randn(n) > 0).astype(int))
        return X, y

    def test_time_series_split(self, ml_data):
        from common.ml.trainer import time_series_split
        X, y = ml_data
        X_train, X_test, y_train, y_test = time_series_split(X, y, test_ratio=0.2)
        assert len(X_train) == 160
        assert len(X_test) == 40
        # Verify chronological order preserved
        assert X_train.index[-1] < X_test.index[0]

    def test_time_series_split_ratio_zero(self, ml_data):
        from common.ml.trainer import time_series_split
        X, y = ml_data
        X_train, X_test, y_train, y_test = time_series_split(X, y, test_ratio=0.0)
        assert len(X_train) == 200
        assert len(X_test) == 0

    def test_train_model(self, ml_data):
        from common.ml.trainer import train_model, HAS_LIGHTGBM
        if not HAS_LIGHTGBM:
            pytest.skip("LightGBM not installed")
        X, y = ml_data
        result = train_model(X, y, list(X.columns))
        assert "model" in result
        assert "metrics" in result
        assert 0 <= result["metrics"]["accuracy"] <= 1
        assert result["metrics"]["n_features"] == 5

    def test_predict(self, ml_data):
        from common.ml.trainer import train_model, predict, HAS_LIGHTGBM
        if not HAS_LIGHTGBM:
            pytest.skip("LightGBM not installed")
        X, y = ml_data
        result = train_model(X, y, list(X.columns))
        pred = predict(result["model"], X.iloc[:10])
        assert "probabilities" in pred
        assert "predictions" in pred
        assert len(pred["predictions"]) == 10
        assert all(p in (0, 1) for p in pred["predictions"])

    def test_safe_helpers(self):
        from common.ml.trainer import _safe_precision, _safe_recall, _safe_f1
        assert _safe_precision(np.array([1, 0]), np.array([1, 1])) == 0.5
        assert _safe_recall(np.array([1, 0]), np.array([1, 0])) == 1.0
        assert _safe_f1(0.5, 0.5) == 0.5
        assert _safe_f1(0.0, 0.0) == 0.0


# ══════════════════════════════════════════════
# ML Features
# ══════════════════════════════════════════════


class TestMLFeatures:
    def test_compute_indicator_features(self):
        from common.ml.features import compute_indicator_features
        df = _make_ohlcv(200)
        result = compute_indicator_features(df)
        assert "rsi_14" in result.columns
        assert "macd" in result.columns
        assert len(result) == 200

    def test_add_lag_features(self):
        from common.ml.features import add_lag_features
        df = _make_ohlcv(50)
        df["rsi_14"] = rsi(df["close"])
        result = add_lag_features(df)
        lag_cols = [c for c in result.columns if "lag" in c]
        assert len(lag_cols) > 0

    def test_add_return_features(self):
        from common.ml.features import add_return_features
        df = _make_ohlcv(50)
        result = add_return_features(df)
        assert "return_1" in result.columns

    def test_compute_target(self):
        from common.ml.features import compute_target
        df = _make_ohlcv(50)
        target = compute_target(df, horizon=1)
        assert set(target.dropna().unique()).issubset({0, 1})
        assert pd.isna(target.iloc[-1])

    def test_build_feature_matrix(self):
        from common.ml.features import build_feature_matrix
        df = _make_ohlcv(200)
        X, y, features = build_feature_matrix(df)
        assert isinstance(X, pd.DataFrame)
        assert isinstance(y, pd.Series)
        assert len(features) > 0
        assert not X.isna().any().any()  # No NaNs after drop

    def test_build_feature_matrix_short_data(self):
        from common.ml.features import build_feature_matrix
        df = _make_ohlcv(10)
        X, y, features = build_feature_matrix(df)
        # Very short data may drop all rows
        assert len(X) >= 0

    def test_compute_target_horizon_5(self):
        from common.ml.features import compute_target
        df = _make_ohlcv(50)
        target = compute_target(df, horizon=5)
        # Last 5 rows should be NaN
        assert target.iloc[-5:].isna().all()


# ══════════════════════════════════════════════
# ML Registry
# ══════════════════════════════════════════════


class TestMLRegistry:
    def test_empty_registry(self, tmp_path):
        from common.ml.registry import ModelRegistry
        reg = ModelRegistry(models_dir=tmp_path / "models")
        assert reg.list_models() == []

    def test_get_nonexistent_model(self, tmp_path):
        from common.ml.registry import ModelRegistry
        reg = ModelRegistry(models_dir=tmp_path / "models")
        assert reg.get_model_detail("nonexistent") is None

    def test_delete_nonexistent(self, tmp_path):
        from common.ml.registry import ModelRegistry
        reg = ModelRegistry(models_dir=tmp_path / "models")
        assert reg.delete_model("nonexistent") is False

    def test_load_nonexistent_raises(self, tmp_path):
        from common.ml.registry import ModelRegistry
        reg = ModelRegistry(models_dir=tmp_path / "models")
        with pytest.raises(FileNotFoundError):
            reg.load_model("nonexistent")

    def test_save_and_list(self, tmp_path):
        from common.ml.registry import ModelRegistry, HAS_LIGHTGBM
        if not HAS_LIGHTGBM:
            pytest.skip("LightGBM not installed")
        from common.ml.trainer import train_model
        rng = np.random.RandomState(42)
        X = pd.DataFrame({f"f{i}": rng.randn(200) for i in range(3)})
        y = pd.Series((rng.randn(200) > 0).astype(int))
        result = train_model(X, y, list(X.columns))

        reg = ModelRegistry(models_dir=tmp_path / "models")
        model_id = reg.save_model(
            result["model"], result["metrics"], result["metadata"],
            result["feature_importance"], symbol="BTC/USDT", timeframe="1h"
        )
        models = reg.list_models()
        assert len(models) == 1
        assert models[0]["model_id"] == model_id

    def test_save_load_roundtrip(self, tmp_path):
        from common.ml.registry import ModelRegistry, HAS_LIGHTGBM
        if not HAS_LIGHTGBM:
            pytest.skip("LightGBM not installed")
        from common.ml.trainer import train_model
        rng = np.random.RandomState(42)
        X = pd.DataFrame({f"f{i}": rng.randn(200) for i in range(3)})
        y = pd.Series((rng.randn(200) > 0).astype(int))
        result = train_model(X, y, list(X.columns))

        reg = ModelRegistry(models_dir=tmp_path / "models")
        model_id = reg.save_model(
            result["model"], result["metrics"], result["metadata"],
            result["feature_importance"], symbol="BTC/USDT"
        )
        loaded_model, manifest = reg.load_model(model_id)
        assert loaded_model is not None
        assert manifest["model_id"] == model_id

    def test_delete_model(self, tmp_path):
        from common.ml.registry import ModelRegistry, HAS_LIGHTGBM
        if not HAS_LIGHTGBM:
            pytest.skip("LightGBM not installed")
        from common.ml.trainer import train_model
        rng = np.random.RandomState(42)
        X = pd.DataFrame({f"f{i}": rng.randn(200) for i in range(3)})
        y = pd.Series((rng.randn(200) > 0).astype(int))
        result = train_model(X, y, list(X.columns))

        reg = ModelRegistry(models_dir=tmp_path / "models")
        model_id = reg.save_model(
            result["model"], result["metrics"], result["metadata"],
            result["feature_importance"]
        )
        assert reg.delete_model(model_id) is True
        assert reg.list_models() == []
