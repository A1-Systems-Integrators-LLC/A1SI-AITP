"""Tests for sample data generation
=================================
Verifies that synthetic OHLCV data can be generated, saved, and loaded
correctly for all framework tiers.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestSampleDataGeneration:
    """Test synthetic data generation and storage."""

    def _generate_sample_df(self, periods=100, start_price=42000.0):
        """Generate a synthetic OHLCV DataFrame."""
        np.random.seed(42)
        timestamps = pd.date_range("2024-01-01", periods=periods, freq="1h", tz="UTC")
        returns = np.random.normal(0.00002, 0.015, periods)
        prices = start_price * np.exp(np.cumsum(returns))
        noise = np.random.uniform(0.995, 1.005, periods)
        opens = prices * noise
        highs = prices * np.random.uniform(1.001, 1.025, periods)
        lows = prices * np.random.uniform(0.975, 0.999, periods)

        return pd.DataFrame(
            {
                "open": opens,
                "high": np.maximum(highs, np.maximum(opens, prices)),
                "low": np.minimum(lows, np.minimum(opens, prices)),
                "close": prices,
                "volume": np.random.lognormal(15, 1.5, periods),
            },
            index=timestamps,
        )

    def test_generated_data_shape(self):
        """Sample data has correct columns and row count."""
        df = self._generate_sample_df(200)
        assert len(df) == 200
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_ohlc_integrity(self):
        """High >= max(open, close) and low <= min(open, close)."""
        df = self._generate_sample_df(500)
        assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
        assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()

    def test_no_nans(self):
        """Generated data has no NaN values."""
        df = self._generate_sample_df()
        assert df.isna().sum().sum() == 0

    def test_positive_prices(self):
        """All prices should be positive."""
        df = self._generate_sample_df()
        for col in ["open", "high", "low", "close"]:
            assert (df[col] > 0).all()

    def test_positive_volume(self):
        """All volumes should be positive."""
        df = self._generate_sample_df()
        assert (df["volume"] > 0).all()

    def test_save_and_load_roundtrip(self, tmp_path):
        """Data survives save/load Parquet roundtrip."""
        from common.data_pipeline.pipeline import load_ohlcv, save_ohlcv

        df = self._generate_sample_df(100)
        save_ohlcv(df, "BTC/USDT", "1h", "binance", directory=tmp_path)
        loaded = load_ohlcv("BTC/USDT", "1h", "binance", directory=tmp_path)
        assert len(loaded) == 100
        assert list(loaded.columns) == ["open", "high", "low", "close", "volume"]
        # Parquet roundtrip may drop index freq metadata, so compare values
        np.testing.assert_allclose(loaded["close"].values, df["close"].values)
        np.testing.assert_allclose(loaded["volume"].values, df["volume"].values)

    def test_nautilus_can_consume_sample_data(self, tmp_path):
        """NautilusTrader runner can process generated sample data."""
        from common.data_pipeline.pipeline import save_ohlcv

        df = self._generate_sample_df(300)
        save_ohlcv(df, "TEST/USDT", "1h", "testexch", directory=tmp_path)

        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing(config={"mode": "backtest"})
        for ts, row in df.iterrows():
            bar = {
                "timestamp": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            strategy.on_bar(bar)
        strategy.on_stop()
        trades_df = strategy.get_trades_df()
        # Should complete without error; trades depend on data
        assert isinstance(trades_df, pd.DataFrame)

    def test_hft_can_consume_sample_data(self):
        """HFT runner can process synthetic tick data from OHLCV."""
        from common.data_pipeline.pipeline import to_hftbacktest_ticks
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        df = self._generate_sample_df(50)
        ticks = to_hftbacktest_ticks(df, "1h")
        assert ticks.shape == (200, 4)

        strategy = HFTMarketMaker(config={"max_position": 10.0})
        strategy.run(ticks)
        # Should complete without error
        assert isinstance(strategy.fills, list)
