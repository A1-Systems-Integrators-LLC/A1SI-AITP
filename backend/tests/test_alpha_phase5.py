"""Tests for Phase 5 — New Strategies.

Covers 5 new Freqtrade strategies, their configs, and alignment matrix entries.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1].parent
STRATEGIES_DIR = PROJECT_ROOT / "freqtrade" / "user_data" / "strategies"
CONFIGS_DIR = PROJECT_ROOT / "freqtrade"

# Add strategies dir to sys.path for direct imports
if str(STRATEGIES_DIR) not in sys.path:
    sys.path.insert(0, str(STRATEGIES_DIR))

# Skip strategy tests if TA-Lib or freqtrade not installed (CI)
_has_talib = importlib.util.find_spec("talib") is not None
_has_freqtrade = importlib.util.find_spec("freqtrade") is not None
_skip_no_talib = pytest.mark.skipif(
    not (_has_talib and _has_freqtrade),
    reason="Requires talib + freqtrade (not in CI)",
)

STRATEGY_NAMES = [
    "MomentumShort", "GridDCA", "MomentumScalper15m",
    "SentimentEventTrader", "TrendReversal",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_ohlcv(n: int = 200, *, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "open": close + rng.normal(0, 0.3, n),
        "high": close + abs(rng.normal(0, 1, n)),
        "low": close - abs(rng.normal(0, 1, n)),
        "close": close,
        "volume": rng.integers(100, 10000, n).astype(float),
        "date": pd.date_range("2025-01-01", periods=n, freq="1h"),
    })


def _import_strategy(name: str):
    """Import a strategy class by name from the strategies dir."""
    mod = importlib.import_module(name)
    return getattr(mod, name)


def _make_strategy(name: str):
    """Create a strategy instance bypassing IStrategy.__init__."""
    cls = _import_strategy(name)
    s = cls.__new__(cls)
    s.dp = MagicMock()
    s.dp.runmode = None
    s.dp.current_whitelist.return_value = ["BTC/USDT", "ETH/USDT"]
    s.dp.get_analyzed_dataframe.return_value = (pd.DataFrame(), None)
    # Ensure hyperopt params have .value
    for attr_name in dir(cls):
        attr = getattr(cls, attr_name, None)
        if hasattr(attr, "value"):
            setattr(s, attr_name, attr)
    return s


# ===================================================================
# Strategy class attribute tests
# ===================================================================

@_skip_no_talib
class TestMomentumShortAttributes:
    def test_imports(self):
        assert _import_strategy("MomentumShort") is not None

    def test_interface_version(self):
        assert _import_strategy("MomentumShort").INTERFACE_VERSION == 3

    def test_can_short(self):
        assert _import_strategy("MomentumShort").can_short is True

    def test_timeframe(self):
        assert _import_strategy("MomentumShort").timeframe == "1h"

    def test_stoploss(self):
        assert _import_strategy("MomentumShort").stoploss == -0.06

    def test_no_long_entries(self):
        s = _make_strategy("MomentumShort")
        df = _make_ohlcv()
        df = s.populate_indicators(df, {"pair": "BTC/USDT"})
        df = s.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert (df["enter_long"] == 0).all()

    def test_custom_leverage(self):
        s = _make_strategy("MomentumShort")
        assert s.custom_leverage(
            "BTC/USDT", None, 100, 5, 10, None, "short",
        ) == 3.0
        assert s.custom_leverage(
            "BTC/USDT", None, 100, 5, 2, None, "short",
        ) == 2.0


@_skip_no_talib
class TestGridDCAAttributes:
    def test_imports(self):
        assert _import_strategy("GridDCA") is not None

    def test_can_short(self):
        assert _import_strategy("GridDCA").can_short is True

    def test_timeframe(self):
        assert _import_strategy("GridDCA").timeframe == "1h"

    def test_stoploss(self):
        assert _import_strategy("GridDCA").stoploss == -0.04

    def test_position_adjustment_enabled(self):
        assert _import_strategy("GridDCA").position_adjustment_enable is True

    def test_custom_leverage_lower(self):
        s = _make_strategy("GridDCA")
        assert s.custom_leverage(
            "BTC/USDT", None, 100, 5, 10, None, "long",
        ) == 2.0


@_skip_no_talib
class TestMomentumScalper15mAttributes:
    def test_imports(self):
        assert _import_strategy("MomentumScalper15m") is not None

    def test_timeframe(self):
        assert _import_strategy("MomentumScalper15m").timeframe == "15m"

    def test_stoploss(self):
        assert _import_strategy("MomentumScalper15m").stoploss == -0.015

    def test_tight_roi(self):
        roi = _import_strategy("MomentumScalper15m").minimal_roi
        assert roi["0"] == 0.008
        assert roi["15"] == 0.005
        assert roi["45"] == 0.003


@_skip_no_talib
class TestSentimentEventTraderAttributes:
    def test_imports(self):
        assert _import_strategy("SentimentEventTrader") is not None

    def test_can_short(self):
        assert _import_strategy("SentimentEventTrader").can_short is True

    def test_timeframe(self):
        assert _import_strategy("SentimentEventTrader").timeframe == "1h"

    def test_stoploss(self):
        assert _import_strategy("SentimentEventTrader").stoploss == -0.05

    def test_sentiment_score_column(self):
        s = _make_strategy("SentimentEventTrader")
        s._sentiment_scores = {}
        df = _make_ohlcv()
        df = s.populate_indicators(df, {"pair": "BTC/USDT"})
        assert "sentiment_score" in df.columns


@_skip_no_talib
class TestTrendReversalAttributes:
    def test_imports(self):
        assert _import_strategy("TrendReversal") is not None

    def test_can_short(self):
        assert _import_strategy("TrendReversal").can_short is True

    def test_timeframe(self):
        assert _import_strategy("TrendReversal").timeframe == "1h"

    def test_stoploss(self):
        assert _import_strategy("TrendReversal").stoploss == -0.06

    def test_startup_candle_count(self):
        assert _import_strategy("TrendReversal").startup_candle_count == 100

    def test_divergence_indicators(self):
        s = _make_strategy("TrendReversal")
        df = _make_ohlcv()
        df = s.populate_indicators(df, {"pair": "BTC/USDT"})
        assert "bullish_divergence" in df.columns
        assert "bearish_divergence" in df.columns
        assert "macd_hist_prev" in df.columns


# ===================================================================
# Populate indicators / entry / exit tests
# ===================================================================

@_skip_no_talib
class TestMomentumShortSignals:
    @pytest.fixture()
    def strategy(self):
        return _make_strategy("MomentumShort")

    def test_indicators_populated(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        for col in [
            "ema_fast", "ema_slow", "rsi", "macd", "macd_signal",
            "macd_hist", "macd_hist_prev", "adx", "atr",
            "volume_sma", "volume_ratio",
        ]:
            assert col in df.columns, f"Missing indicator: {col}"

    def test_exit_short_conditions(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert "exit_short" in df.columns
        assert "exit_long" in df.columns
        assert (df["exit_long"] == 0).all()


@_skip_no_talib
class TestGridDCASignals:
    @pytest.fixture()
    def strategy(self):
        return _make_strategy("GridDCA")

    def test_indicators_populated(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        for col in ["bb_upper", "bb_middle", "bb_lower", "rsi", "adx", "atr"]:
            assert col in df.columns

    def test_entry_trend_columns(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert "enter_long" in df.columns
        assert "enter_short" in df.columns

    def test_exit_at_bb_middle(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert "exit_long" in df.columns
        assert "exit_short" in df.columns

    def test_adjust_trade_position_not_losing_enough(self, strategy):
        """DCA should not trigger if not losing > 2%."""
        trade = MagicMock()
        trade.stake_amount = 100
        trade.pair = "BTC/USDT"
        result = strategy.adjust_trade_position(
            trade, None, 100, -0.01, 10, 1000, 100, 100, -0.01, -0.01,
        )
        assert result is None

    def test_adjust_trade_position_dca_triggered(self, strategy):
        """DCA triggers when losing > 2% and ADX still ranging."""
        trade = MagicMock()
        trade.stake_amount = 100
        trade.pair = "BTC/USDT"

        mock_df = _make_ohlcv(50)
        mock_df["adx"] = 20
        strategy.dp.get_pair_dataframe.return_value = mock_df

        result = strategy.adjust_trade_position(
            trade, None, 100, -0.03, 10, 1000, 100, 100, -0.03, -0.03,
        )
        assert result == 50.0

    def test_adjust_trade_position_breakout_no_dca(self, strategy):
        """DCA should NOT trigger if ADX shows breakout."""
        trade = MagicMock()
        trade.stake_amount = 100
        trade.pair = "BTC/USDT"

        mock_df = _make_ohlcv(50)
        mock_df["adx"] = 35
        strategy.dp.get_pair_dataframe.return_value = mock_df

        result = strategy.adjust_trade_position(
            trade, None, 100, -0.03, 10, 1000, 100, 100, -0.03, -0.03,
        )
        assert result is None

    def test_adjust_trade_position_empty_dataframe(self, strategy):
        """DCA should return None if dataframe is empty."""
        trade = MagicMock()
        trade.stake_amount = 100
        trade.pair = "BTC/USDT"
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame()

        result = strategy.adjust_trade_position(
            trade, None, 100, -0.03, 10, 1000, 100, 100, -0.03, -0.03,
        )
        assert result is None


@_skip_no_talib
class TestMomentumScalper15mSignals:
    @pytest.fixture()
    def strategy(self):
        return _make_strategy("MomentumScalper15m")

    def test_indicators_populated(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        for col in [
            "ema_fast", "ema_slow", "rsi", "macd_hist",
            "macd_hist_prev", "adx", "atr", "volume_sma", "volume_ratio",
        ]:
            assert col in df.columns

    def test_entry_crossover_logic(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert "enter_long" in df.columns
        assert "enter_short" in df.columns

    def test_exit_trend(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert "exit_long" in df.columns
        assert "exit_short" in df.columns


@_skip_no_talib
class TestSentimentEventTraderSignals:
    @pytest.fixture()
    def strategy(self):
        s = _make_strategy("SentimentEventTrader")
        s._sentiment_scores = {}
        return s

    def test_indicators_with_sentiment(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        assert "sentiment_score" in df.columns
        assert (df["sentiment_score"] == 0.0).all()

    def test_cached_sentiment_applied(self, strategy):
        strategy._sentiment_scores["BTC/USDT"] = 0.85
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        assert (df["sentiment_score"] == 0.85).all()

    def test_long_entry_on_positive_sentiment(self, strategy):
        strategy._sentiment_scores["BTC/USDT"] = 0.85
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert df["enter_long"].sum() > 0

    def test_short_entry_on_negative_sentiment(self, strategy):
        strategy._sentiment_scores["BTC/USDT"] = -0.85
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert df["enter_short"].sum() > 0

    def test_no_entries_neutral_sentiment(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert df["enter_long"].sum() == 0
        assert df["enter_short"].sum() == 0

    def test_exit_on_sentiment_reversal(self, strategy):
        strategy._sentiment_scores["BTC/USDT"] = -0.5
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert df["exit_long"].sum() > 0

    def test_get_cached_signal_no_conviction(self, strategy):
        result = strategy._get_cached_signal("BTC/USDT")
        assert result is None


@_skip_no_talib
class TestTrendReversalSignals:
    @pytest.fixture()
    def strategy(self):
        return _make_strategy("TrendReversal")

    def test_indicators_populated(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        for col in [
            "rsi", "macd", "macd_signal", "macd_hist", "macd_hist_prev",
            "adx", "adx_prev", "atr", "ema_21", "ema_50", "ema_100",
            "bullish_divergence", "bearish_divergence",
        ]:
            assert col in df.columns

    def test_entry_trend(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert "enter_long" in df.columns
        assert "enter_short" in df.columns

    def test_exit_trend(self, strategy):
        df = _make_ohlcv()
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert "exit_long" in df.columns
        assert "exit_short" in df.columns


# ===================================================================
# Conviction integration tests
# ===================================================================

@_skip_no_talib
class TestConvictionIntegration:
    """All 5 strategies should have conviction helper methods."""

    @pytest.mark.parametrize("name", STRATEGY_NAMES)
    def test_has_custom_stoploss_method(self, name):
        cls = _import_strategy(name)
        assert hasattr(cls, "custom_stoploss")
        assert cls.use_custom_stoploss is True

    @pytest.mark.parametrize("name", STRATEGY_NAMES)
    def test_has_confirm_trade_entry(self, name):
        assert hasattr(_import_strategy(name), "confirm_trade_entry")

    @pytest.mark.parametrize("name", STRATEGY_NAMES)
    def test_has_custom_exit(self, name):
        assert hasattr(_import_strategy(name), "custom_exit")

    @pytest.mark.parametrize("name", STRATEGY_NAMES)
    def test_has_bot_loop_start(self, name):
        assert hasattr(_import_strategy(name), "bot_loop_start")

    @pytest.mark.parametrize("name", STRATEGY_NAMES)
    def test_has_custom_stake_amount(self, name):
        assert hasattr(_import_strategy(name), "custom_stake_amount")

    @pytest.mark.parametrize("name", STRATEGY_NAMES)
    def test_has_custom_leverage(self, name):
        assert hasattr(_import_strategy(name), "custom_leverage")


# ===================================================================
# Custom stoploss tests
# ===================================================================

@_skip_no_talib
class TestCustomStoploss:
    @pytest.fixture()
    def _mock_dp(self):
        dp = MagicMock()
        mock_df = pd.DataFrame({"atr": [50.0] * 10})
        dp.get_pair_dataframe.return_value = mock_df
        return dp

    def test_momentum_short_stoploss(self, _mock_dp):
        s = _make_strategy("MomentumShort")
        s.dp = _mock_dp
        stop = s.custom_stoploss(
            "BTC/USDT", MagicMock(), None, 1000, 0.0, False,
        )
        assert stop < 0

    def test_momentum_short_profit_tightening(self, _mock_dp):
        s = _make_strategy("MomentumShort")
        s.dp = _mock_dp
        stop_low = s.custom_stoploss(
            "BTC/USDT", MagicMock(), None, 1000, 0.01, False,
        )
        stop_high = s.custom_stoploss(
            "BTC/USDT", MagicMock(), None, 1000, 0.06, False,
        )
        assert stop_high >= stop_low

    def test_grid_dca_stoploss(self, _mock_dp):
        s = _make_strategy("GridDCA")
        s.dp = _mock_dp
        stop = s.custom_stoploss(
            "BTC/USDT", MagicMock(), None, 1000, 0.0, False,
        )
        assert stop < 0

    def test_scalper_stoploss(self, _mock_dp):
        s = _make_strategy("MomentumScalper15m")
        s.dp = _mock_dp
        stop = s.custom_stoploss(
            "BTC/USDT", MagicMock(), None, 1000, 0.0, False,
        )
        assert stop < 0

    def test_sentiment_stoploss(self, _mock_dp):
        s = _make_strategy("SentimentEventTrader")
        s.dp = _mock_dp
        stop = s.custom_stoploss(
            "BTC/USDT", MagicMock(), None, 1000, 0.0, False,
        )
        assert stop < 0

    def test_reversal_stoploss(self, _mock_dp):
        s = _make_strategy("TrendReversal")
        s.dp = _mock_dp
        stop = s.custom_stoploss(
            "BTC/USDT", MagicMock(), None, 1000, 0.0, False,
        )
        assert stop < 0


# ===================================================================
# Config file tests
# ===================================================================

class TestConfigFiles:
    CONFIGS = {
        "config_short.json": {
            "port": 8085, "strategy": "MomentumShort",
            "stake": 60, "max_trades": 3,
        },
        "config_grid.json": {
            "port": 8086, "strategy": "GridDCA",
            "stake": 40, "max_trades": 5,
        },
        "config_scalp.json": {
            "port": 8087, "strategy": "MomentumScalper15m",
            "stake": 50, "max_trades": 3,
        },
        "config_sentiment.json": {
            "port": 8088, "strategy": "SentimentEventTrader",
            "stake": 60, "max_trades": 3,
        },
        "config_reversal.json": {
            "port": 8089, "strategy": "TrendReversal",
            "stake": 60, "max_trades": 3,
        },
    }

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_exists(self, config_name):
        assert (CONFIGS_DIR / config_name).exists()

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_valid_json(self, config_name):
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_futures_mode(self, config_name):
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        assert data["trading_mode"] == "futures"
        assert data["margin_mode"] == "isolated"

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_stoploss_on_exchange(self, config_name):
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        assert data["order_types"]["stoploss_on_exchange"] is True

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_api_port(self, config_name):
        expected = self.CONFIGS[config_name]
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        assert data["api_server"]["listen_port"] == expected["port"]

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_stake_amount(self, config_name):
        expected = self.CONFIGS[config_name]
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        assert data["stake_amount"] == expected["stake"]

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_kraken_exchange(self, config_name):
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        assert data["exchange"]["name"] == "kraken"

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_blacklist_stablecoins(self, config_name):
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        blacklist = data["exchange"]["pair_blacklist"]
        assert "USDC/USDT" in blacklist
        assert "XAUT/USDT" in blacklist

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_dry_run(self, config_name):
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        assert data["dry_run"] is True

    @pytest.mark.parametrize("config_name", CONFIGS)
    def test_config_swap_type(self, config_name):
        with open(CONFIGS_DIR / config_name) as f:
            data = json.load(f)
        assert data["exchange"]["ccxt_config"]["defaultType"] == "swap"


# ===================================================================
# Alignment matrix tests
# ===================================================================

class TestAlignmentMatrices:
    REGIMES = [
        "STRONG_TREND_UP", "WEAK_TREND_UP", "RANGING",
        "WEAK_TREND_DOWN", "STRONG_TREND_DOWN",
        "HIGH_VOLATILITY", "UNKNOWN",
    ]

    def _get_regime_key(self, regime_str):
        """Convert string regime name to the actual key used in dict."""
        from common.signals.constants import CRYPTO_ALIGNMENT
        for key in CRYPTO_ALIGNMENT:
            key_name = key.name if hasattr(key, "name") else str(key)
            if key_name == regime_str or str(key) == regime_str:
                return key
        if regime_str in CRYPTO_ALIGNMENT:
            return regime_str
        msg = f"Regime {regime_str} not found"
        raise KeyError(msg)

    def test_all_strategies_in_crypto_alignment(self):
        from common.signals.constants import CRYPTO_ALIGNMENT
        for regime_str in self.REGIMES:
            key = self._get_regime_key(regime_str)
            for strategy in STRATEGY_NAMES:
                assert strategy in CRYPTO_ALIGNMENT[key], \
                    f"{strategy} missing from [{regime_str}]"

    def test_alignment_scores_valid_range(self):
        from common.signals.constants import CRYPTO_ALIGNMENT
        for regime_str in self.REGIMES:
            key = self._get_regime_key(regime_str)
            for strategy in STRATEGY_NAMES:
                score = CRYPTO_ALIGNMENT[key][strategy]
                assert 0 <= score <= 100

    def test_momentum_short_best_in_strong_trend_down(self):
        from common.signals.constants import CRYPTO_ALIGNMENT
        key = self._get_regime_key("STRONG_TREND_DOWN")
        assert CRYPTO_ALIGNMENT[key]["MomentumShort"] >= 80

    def test_grid_dca_best_in_ranging(self):
        from common.signals.constants import CRYPTO_ALIGNMENT
        key = self._get_regime_key("RANGING")
        assert CRYPTO_ALIGNMENT[key]["GridDCA"] >= 90

    def test_all_strategies_in_partial_profit_targets(self):
        from common.signals.constants import PARTIAL_PROFIT_TARGETS
        for strategy in STRATEGY_NAMES:
            assert strategy in PARTIAL_PROFIT_TARGETS
            targets = PARTIAL_PROFIT_TARGETS[strategy]
            assert len(targets) >= 1
            for entry in targets:
                assert len(entry) == 3
                threshold, fraction, label = entry
                assert 0 < threshold <= 1
                assert 0 < fraction <= 1
                assert isinstance(label, str)

    def test_all_strategies_in_max_hold_hours(self):
        from common.signals.constants import MAX_HOLD_HOURS
        for strategy in STRATEGY_NAMES:
            assert strategy in MAX_HOLD_HOURS
            assert MAX_HOLD_HOURS[strategy] > 0

    def test_scalper_shortest_hold(self):
        from common.signals.constants import MAX_HOLD_HOURS
        assert MAX_HOLD_HOURS["MomentumScalper15m"] == 12.0

    def test_trend_reversal_longest_hold(self):
        from common.signals.constants import MAX_HOLD_HOURS
        assert MAX_HOLD_HOURS["TrendReversal"] == 120.0


# ===================================================================
# Strategy file existence tests
# ===================================================================

@_skip_no_talib
class TestStrategyFiles:
    @pytest.mark.parametrize("name", STRATEGY_NAMES)
    def test_strategy_file_exists(self, name):
        assert (STRATEGIES_DIR / f"{name}.py").exists()

    @pytest.mark.parametrize("name", STRATEGY_NAMES)
    def test_strategy_has_docstring(self, name):
        cls = _import_strategy(name)
        assert cls.__doc__ is not None
