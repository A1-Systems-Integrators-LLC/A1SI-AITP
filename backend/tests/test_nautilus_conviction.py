"""Tests for NautilusTrader conviction integration (IEB Phase 6)
==============================================================
Covers: conviction gate, position modifier, exit advisor, stop multiplier,
fail-open behavior, backtest mode bypass, asset class mapping.
"""

import inspect
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Helpers ──────────────────────────────────────────


def _make_ohlcv(n: int = 300, start_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    timestamps = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    returns = np.random.normal(0.0001, 0.01, n)
    prices = start_price * np.exp(np.cumsum(returns))
    noise = np.random.uniform(0.998, 1.002, n)
    open_prices = prices * noise
    close_prices = prices
    high_prices = (
        np.maximum(open_prices, close_prices) * np.random.uniform(1.001, 1.02, n)
    )
    low_prices = (
        np.minimum(open_prices, close_prices) * np.random.uniform(0.98, 0.999, n)
    )
    return pd.DataFrame(
        {
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "volume": np.random.lognormal(10, 1, n),
        },
        index=timestamps,
    )


def _bars_from_df(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of bar dicts."""
    bars = []
    for ts, row in df.iterrows():
        bars.append(
            {
                "timestamp": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            },
        )
    return bars


def _make_strategy(
    cls_name: str = "NautilusTrendFollowing", mode: str = "live", **kwargs,
):
    """Create a strategy instance with the given config."""
    from nautilus.strategies.base import NautilusStrategyBase

    config = {"mode": mode, "symbol": "BTC/USDT", **kwargs}
    strategy = NautilusStrategyBase(config=config)
    strategy.name = cls_name
    return strategy


def _bar_dict(close: float = 100.0) -> dict:
    """Create a minimal bar dict."""
    return {"close": close, "timestamp": pd.Timestamp.now(tz="UTC")}


# ── Asset Class Mapping ──────────────────────────────


class TestStrategyAssetClass:
    def test_crypto_strategies(self):
        from nautilus.strategies.base import STRATEGY_ASSET_CLASS

        assert STRATEGY_ASSET_CLASS["NautilusTrendFollowing"] == "crypto"
        assert STRATEGY_ASSET_CLASS["NautilusMeanReversion"] == "crypto"
        assert STRATEGY_ASSET_CLASS["NautilusVolatilityBreakout"] == "crypto"

    def test_equity_strategies(self):
        from nautilus.strategies.base import STRATEGY_ASSET_CLASS

        assert STRATEGY_ASSET_CLASS["EquityMomentum"] == "equity"
        assert STRATEGY_ASSET_CLASS["EquityMeanReversion"] == "equity"

    def test_forex_strategies(self):
        from nautilus.strategies.base import STRATEGY_ASSET_CLASS

        assert STRATEGY_ASSET_CLASS["ForexTrend"] == "forex"
        assert STRATEGY_ASSET_CLASS["ForexRange"] == "forex"

    def test_get_asset_class_known(self):
        strategy = _make_strategy("ForexTrend")
        assert strategy._get_asset_class() == "forex"

    def test_get_asset_class_unknown_defaults_crypto(self):
        strategy = _make_strategy("UnknownStrategy")
        assert strategy._get_asset_class() == "crypto"


# ── Conviction Gate ──────────────────────────────────


class TestConvictionGate:
    def test_backtest_mode_always_approves(self):
        strategy = _make_strategy(mode="backtest")
        assert strategy._check_conviction_gate() is True

    def test_live_mode_no_signal_approves_fail_open(self):
        strategy = _make_strategy(mode="live")
        patch_path = (
            "nautilus.strategies.base.NautilusStrategyBase._fetch_signal"
        )
        with patch(patch_path, return_value=None):
            assert strategy._check_conviction_gate() is True

    def test_live_mode_approved_signal(self):
        strategy = _make_strategy(mode="live")
        signal = {
            "approved": True, "score": 80.0, "signal_label": "strong_buy",
        }
        patch_path = (
            "nautilus.strategies.base.NautilusStrategyBase._fetch_signal"
        )
        with patch(patch_path, return_value=signal):
            assert strategy._check_conviction_gate() is True

    def test_live_mode_rejected_signal(self):
        strategy = _make_strategy(mode="live")
        signal = {"approved": False, "score": 30.0, "signal_label": "avoid"}
        strategy._signals["BTC/USDT"] = signal
        assert strategy._check_conviction_gate() is False

    def test_cached_signal_used_within_interval(self):
        strategy = _make_strategy(mode="live")
        signal = {"approved": True, "score": 75.0, "signal_label": "buy"}
        strategy._signals["BTC/USDT"] = signal
        strategy._last_signal_fetch = time.monotonic()
        assert strategy._check_conviction_gate() is True

    def test_stale_signal_triggers_refresh(self):
        strategy = _make_strategy(mode="live")
        strategy._last_signal_fetch = 0
        signal = {"approved": True, "score": 70.0, "signal_label": "buy"}
        patch_path = (
            "nautilus.strategies.base.NautilusStrategyBase._fetch_signal"
        )
        with patch(patch_path, return_value=signal):
            assert strategy._check_conviction_gate() is True
            assert strategy._signals.get("BTC/USDT") == signal


# ── Fetch Signal ─────────────────────────────────────


class TestFetchSignal:
    def test_fetch_signal_success(self):
        strategy = _make_strategy("NautilusTrendFollowing", mode="live")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"approved": True, "score": 80}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = strategy._fetch_signal()
            assert result == {"approved": True, "score": 80}
            url = mock_post.call_args[0][0]
            assert "/api/signals/BTC-USDT/entry-check/" in url
            body = mock_post.call_args[1]["json"]
            assert body["strategy"] == "NautilusTrendFollowing"

    def test_fetch_signal_non_200(self):
        strategy = _make_strategy(mode="live")
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("requests.post", return_value=mock_resp):
            assert strategy._fetch_signal() is None

    def test_fetch_signal_exception(self):
        strategy = _make_strategy(mode="live")
        with patch("requests.post", side_effect=ConnectionError("timeout")):
            assert strategy._fetch_signal() is None

    def test_fetch_signal_uses_strategy_name_and_asset_class(self):
        strategy = _make_strategy(
            "EquityMomentum", mode="live", symbol="AAPL/USD",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"approved": True}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            strategy._fetch_signal()
            call_json = mock_post.call_args[1]["json"]
            assert call_json["strategy"] == "EquityMomentum"
            assert call_json["asset_class"] == "equity"


# ── Position Modifier ────────────────────────────────


class TestPositionModifier:
    def test_backtest_mode_returns_1(self):
        strategy = _make_strategy(mode="backtest")
        assert strategy._get_position_modifier() == 1.0

    def test_no_signal_returns_1(self):
        strategy = _make_strategy(mode="live")
        assert strategy._get_position_modifier() == 1.0

    def test_signal_with_modifier(self):
        strategy = _make_strategy(mode="live")
        strategy._signals["BTC/USDT"] = {"position_modifier": 0.7}
        assert strategy._get_position_modifier() == 0.7

    def test_signal_without_modifier_key(self):
        strategy = _make_strategy(mode="live")
        strategy._signals["BTC/USDT"] = {"approved": True}
        assert strategy._get_position_modifier() == 1.0


# ── Exit Advisor ─────────────────────────────────────


class TestExitAdvisor:
    def test_backtest_mode_returns_none(self):
        strategy = _make_strategy(mode="backtest")
        assert strategy._check_exit_advice(_bar_dict()) is None

    def test_no_conviction_returns_none(self):
        strategy = _make_strategy(mode="live")
        with patch("nautilus.strategies.base.HAS_CONVICTION", False):
            assert strategy._check_exit_advice(_bar_dict()) is None

    def test_no_position_returns_none(self):
        strategy = _make_strategy(mode="live")
        strategy.position = None
        assert strategy._check_exit_advice(_bar_dict()) is None

    def test_no_entry_regime_returns_none(self):
        strategy = _make_strategy(mode="live")
        now = pd.Timestamp.now(tz="UTC")
        strategy.position = {
            "entry_price": 100, "size": 1, "entry_time": now,
        }
        strategy._entry_regime = None
        assert strategy._check_exit_advice(_bar_dict()) is None

    def test_exit_advice_triggered(self):
        from common.regime.regime_detector import Regime
        from common.signals.exit_manager import ExitAdvice

        strategy = _make_strategy(mode="live")
        strategy.position = {
            "entry_price": 100,
            "size": 1,
            "entry_time": pd.Timestamp("2024-01-01", tz="UTC"),
        }
        strategy._entry_regime = Regime.STRONG_TREND_UP.value

        df = _make_ohlcv(300)
        for bar in _bars_from_df(df):
            strategy.bars.append(bar)

        mock_advice = ExitAdvice(
            should_exit=True,
            reason="regime deterioration",
            urgency="immediate",
            partial_pct=0.0,
        )
        with (
            patch(
                "nautilus.strategies.base.advise_exit",
                return_value=mock_advice,
            ),
            patch(
                "nautilus.strategies.base.RegimeDetector",
            ) as mock_det,
        ):
            mock_det.return_value.detect.return_value = MagicMock()
            bar = {
                "close": 110,
                "timestamp": pd.Timestamp("2024-01-13 12:00", tz="UTC"),
            }
            result = strategy._check_exit_advice(bar)
            assert result is not None
            assert "conviction_" in result
            assert "regime_deterioration" in result

    def test_exit_advice_not_triggered(self):
        from common.regime.regime_detector import Regime
        from common.signals.exit_manager import ExitAdvice

        strategy = _make_strategy(mode="live")
        strategy.position = {
            "entry_price": 100,
            "size": 1,
            "entry_time": pd.Timestamp("2024-01-01", tz="UTC"),
        }
        strategy._entry_regime = Regime.STRONG_TREND_UP.value

        df = _make_ohlcv(300)
        for bar in _bars_from_df(df):
            strategy.bars.append(bar)

        mock_advice = ExitAdvice(
            should_exit=False,
            reason="",
            urgency="monitor",
            partial_pct=0.0,
        )
        with (
            patch(
                "nautilus.strategies.base.advise_exit",
                return_value=mock_advice,
            ),
            patch(
                "nautilus.strategies.base.RegimeDetector",
            ) as mock_det,
        ):
            mock_det.return_value.detect.return_value = MagicMock()
            bar = {
                "close": 102,
                "timestamp": pd.Timestamp("2024-01-02", tz="UTC"),
            }
            assert strategy._check_exit_advice(bar) is None

    def test_exit_advice_exception_returns_none(self):
        strategy = _make_strategy(mode="live")
        strategy.position = {
            "entry_price": 100,
            "size": 1,
            "entry_time": pd.Timestamp("2024-01-01", tz="UTC"),
        }
        strategy._entry_regime = "TOTALLY_BOGUS"

        df = _make_ohlcv(300)
        for bar in _bars_from_df(df):
            strategy.bars.append(bar)

        bar = {
            "close": 100,
            "timestamp": pd.Timestamp("2024-01-02", tz="UTC"),
        }
        # Regime("TOTALLY_BOGUS") will raise ValueError
        assert strategy._check_exit_advice(bar) is None


# ── Stop Multiplier ──────────────────────────────────


class TestStopMultiplier:
    def test_backtest_mode_returns_1(self):
        strategy = _make_strategy(mode="backtest")
        assert strategy._get_stop_multiplier() == 1.0

    def test_no_conviction_returns_1(self):
        strategy = _make_strategy(mode="live")
        with patch("nautilus.strategies.base.HAS_CONVICTION", False):
            assert strategy._get_stop_multiplier() == 1.0

    def test_regime_aware_multiplier(self):
        strategy = _make_strategy(mode="live")

        df = _make_ohlcv(300)
        for bar in _bars_from_df(df):
            strategy.bars.append(bar)

        with patch(
            "nautilus.strategies.base.RegimeDetector",
        ) as mock_det:
            mock_state = MagicMock()
            mock_state.regime = MagicMock()
            mock_det.return_value.detect.return_value = mock_state
            with patch(
                "nautilus.strategies.base.get_stop_multiplier",
                return_value=0.6,
            ) as mock_gsm:
                result = strategy._get_stop_multiplier()
                assert result == 0.6
                mock_gsm.assert_called_once_with(mock_state.regime)

    def test_stop_multiplier_exception_returns_1(self):
        strategy = _make_strategy(mode="live")

        df = _make_ohlcv(300)
        for bar in _bars_from_df(df):
            strategy.bars.append(bar)

        with patch(
            "nautilus.strategies.base.RegimeDetector",
        ) as mock_det:
            mock_det.return_value.detect.side_effect = ValueError("bad")
            assert strategy._get_stop_multiplier() == 1.0


# ── Record Entry Regime ──────────────────────────────


class TestRecordEntryRegime:
    def test_record_regime(self):
        strategy = _make_strategy(mode="live")
        df = _make_ohlcv(300)

        with patch(
            "nautilus.strategies.base.RegimeDetector",
        ) as mock_det:
            mock_state = MagicMock()
            mock_state.regime.value = "ranging"
            mock_det.return_value.detect.return_value = mock_state
            strategy._record_entry_regime(df)
            assert strategy._entry_regime == "ranging"

    def test_record_regime_no_conviction(self):
        strategy = _make_strategy(mode="live")
        df = _make_ohlcv(300)
        with patch("nautilus.strategies.base.HAS_CONVICTION", False):
            strategy._record_entry_regime(df)
            assert strategy._entry_regime is None

    def test_record_regime_exception(self):
        strategy = _make_strategy(mode="live")
        df = _make_ohlcv(300)
        with patch(
            "nautilus.strategies.base.RegimeDetector",
        ) as mock_det:
            mock_det.return_value.detect.side_effect = Exception("fail")
            strategy._record_entry_regime(df)
            assert strategy._entry_regime is None


# ── on_bar Integration ───────────────────────────────


class TestOnBarConviction:
    """Integration tests verifying conviction flows through on_bar."""

    def _feed_bars(self, strategy, n=250):
        """Feed n bars and return the last bar."""
        df = _make_ohlcv(n)
        bars = _bars_from_df(df)
        for bar in bars:
            strategy.on_bar(bar)
        return bars[-1]

    def test_conviction_rejection_blocks_entry(self):
        """When conviction gate rejects, no position opened."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing(
            config={"mode": "live", "symbol": "BTC/USDT"},
        )
        rejected = {
            "approved": False, "score": 20.0, "signal_label": "avoid",
        }

        with (
            patch.object(strategy, "should_enter", return_value=True),
            patch.object(strategy, "_check_risk_gate", return_value=True),
            patch.object(strategy, "_fetch_signal", return_value=rejected),
        ):
            self._feed_bars(strategy, 250)
            assert strategy.position is None

    def test_conviction_approval_allows_entry(self):
        """When conviction gate approves, position should be opened."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing(
            config={"mode": "live", "symbol": "BTC/USDT"},
        )
        approved = {
            "approved": True,
            "score": 80.0,
            "signal_label": "strong_buy",
            "position_modifier": 1.0,
        }

        with (
            patch.object(strategy, "should_enter", return_value=True),
            patch.object(strategy, "_check_risk_gate", return_value=True),
            patch.object(strategy, "_fetch_signal", return_value=approved),
            patch.object(strategy, "_record_entry_regime"),
        ):
            self._feed_bars(strategy, 250)
            assert strategy.position is not None

    def test_position_modifier_applied(self):
        """Position size should be scaled by conviction modifier."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing(
            config={"mode": "live", "symbol": "BTC/USDT"},
        )
        signal = {"approved": True, "score": 65.0, "position_modifier": 0.4}

        original_size = None

        def capture_size(indicators, entry_price):
            nonlocal original_size
            cls = type(strategy)
            original_size = cls._compute_position_size(
                strategy, indicators, entry_price,
            )
            return original_size

        with (
            patch.object(strategy, "should_enter", return_value=True),
            patch.object(strategy, "_check_risk_gate", return_value=True),
            patch.object(strategy, "_fetch_signal", return_value=signal),
            patch.object(
                strategy, "_compute_position_size", side_effect=capture_size,
            ),
            patch.object(strategy, "_record_entry_regime"),
        ):
            self._feed_bars(strategy, 250)
            if strategy.position and original_size:
                expected = round(original_size * 0.4, 6)
                assert strategy.position["size"] == expected

    def test_backtest_mode_skips_conviction(self):
        """Backtest mode should not call conviction gate."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing(
            config={"mode": "backtest", "symbol": "BTC/USDT"},
        )

        with (
            patch.object(strategy, "should_enter", return_value=True),
            patch.object(strategy, "_fetch_signal") as mock_fetch,
        ):
            self._feed_bars(strategy, 250)
            mock_fetch.assert_not_called()


# ── Native Adapter Conviction ────────────────────────


class TestNativeAdapterConviction:
    """Test conviction integration in the native NT adapter."""

    @pytest.fixture
    def has_nautilus(self):
        """Skip if nautilus_trader not installed."""
        pytest.importorskip("nautilus_trader")

    def test_native_adapter_has_on_bar(self, has_nautilus):
        """Native adapter should have on_bar method."""
        from nautilus.strategies.nt_native import _NativeAdapterBase

        assert hasattr(_NativeAdapterBase, "on_bar")

    def test_native_adapter_enter_long_accepts_size(self, has_nautilus):
        """_enter_long should accept optional size parameter."""
        from nautilus.strategies.nt_native import _NativeAdapterBase

        sig = inspect.signature(_NativeAdapterBase._enter_long)
        params = list(sig.parameters.keys())
        assert "size" in params


# ── Refresh Signal ───────────────────────────────────


class TestRefreshSignal:
    def test_refresh_within_interval_skips(self):
        strategy = _make_strategy(mode="live")
        strategy._last_signal_fetch = time.monotonic()

        with patch.object(strategy, "_fetch_signal") as mock_fetch:
            strategy._refresh_signal()
            mock_fetch.assert_not_called()

    def test_refresh_stale_fetches(self):
        strategy = _make_strategy(mode="live")
        strategy._last_signal_fetch = 0
        signal = {"approved": True, "score": 70}
        with patch.object(strategy, "_fetch_signal", return_value=signal):
            strategy._refresh_signal()
            assert strategy._signals["BTC/USDT"] == signal

    def test_refresh_fetch_failure_updates_timestamp(self):
        strategy = _make_strategy(mode="live")
        strategy._last_signal_fetch = 0
        before = time.monotonic()
        with patch.object(strategy, "_fetch_signal", return_value=None):
            strategy._refresh_signal()
        assert strategy._last_signal_fetch >= before
        assert "BTC/USDT" not in strategy._signals


# ── Init State ───────────────────────────────────────


class TestInitState:
    def test_conviction_state_initialized(self):
        strategy = _make_strategy(mode="live")
        assert strategy._signals == {}
        assert strategy._last_signal_fetch == 0
        assert strategy._entry_regime is None
