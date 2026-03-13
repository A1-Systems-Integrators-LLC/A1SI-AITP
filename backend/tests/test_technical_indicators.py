"""Tests for technical indicators — 16 pure-pandas indicator functions."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.indicators.technical import (
    add_all_indicators,
    atr_indicator,
    bollinger_bands,
    cci,
    ema,
    keltner_channels,
    macd,
    mfi,
    obv,
    rsi,
    sma,
    stochastic,
    supertrend,
    williams_r,
    wma,
)


@pytest.fixture(scope="module")
def ohlcv_df():
    """300 rows of synthetic OHLCV data with a cumulative random walk."""
    np.random.seed(99)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.1
    volume = np.random.randint(1000, 100000, size=n).astype(float)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
    )


class TestTrendIndicators:
    def test_sma_returns_series_with_initial_nans(self, ohlcv_df):
        result = sma(ohlcv_df["close"], 20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv_df)
        assert result.iloc[:19].isna().all()
        assert result.iloc[19:].notna().all()

    def test_ema_returns_series(self, ohlcv_df):
        result = ema(ohlcv_df["close"], 20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv_df)

    def test_wma_returns_series(self, ohlcv_df):
        result = wma(ohlcv_df["close"], 20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv_df)

    def test_supertrend_columns_and_direction(self, ohlcv_df):
        result = supertrend(ohlcv_df)
        assert "supertrend" in result.columns
        assert "supertrend_direction" in result.columns
        valid = result["supertrend_direction"].dropna()
        assert set(valid.unique()).issubset({1, -1})


class TestMomentumIndicators:
    def test_rsi_bounded_0_100(self, ohlcv_df):
        result = rsi(ohlcv_df["close"], 14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_macd_columns(self, ohlcv_df):
        result = macd(ohlcv_df["close"])
        assert set(result.columns) == {"macd", "macd_signal", "macd_hist"}

    def test_stochastic_columns_and_k_bounded(self, ohlcv_df):
        result = stochastic(ohlcv_df)
        assert set(result.columns) == {"stoch_k", "stoch_d"}
        valid_k = result["stoch_k"].dropna()
        assert (valid_k >= 0).all()
        assert (valid_k <= 100).all()

    def test_williams_r_bounded_minus100_to_0(self, ohlcv_df):
        result = williams_r(ohlcv_df)
        valid = result.dropna()
        assert (valid >= -100).all()
        assert (valid <= 0).all()

    def test_cci_returns_series(self, ohlcv_df):
        result = cci(ohlcv_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv_df)


class TestVolatilityIndicators:
    def test_atr_non_negative(self, ohlcv_df):
        result = atr_indicator(ohlcv_df, 14)
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_bollinger_bands_columns(self, ohlcv_df):
        result = bollinger_bands(ohlcv_df["close"])
        assert set(result.columns) == {"bb_upper", "bb_mid", "bb_lower", "bb_width", "bb_pct"}

    def test_bollinger_upper_above_lower(self, ohlcv_df):
        result = bollinger_bands(ohlcv_df["close"]).dropna()
        assert (result["bb_upper"] >= result["bb_lower"]).all()

    def test_keltner_channels_columns(self, ohlcv_df):
        result = keltner_channels(ohlcv_df)
        assert set(result.columns) == {"kc_upper", "kc_mid", "kc_lower"}


class TestVolumeIndicators:
    def test_obv_returns_series(self, ohlcv_df):
        result = obv(ohlcv_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv_df)

    def test_mfi_bounded_0_100(self, ohlcv_df):
        result = mfi(ohlcv_df)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


class TestAddAllIndicators:
    def test_adds_at_least_20_columns(self, ohlcv_df):
        result = add_all_indicators(ohlcv_df)
        new_cols = set(result.columns) - set(ohlcv_df.columns)
        assert len(new_cols) >= 25

    def test_contains_expected_columns(self, ohlcv_df):
        result = add_all_indicators(ohlcv_df)
        assert "rsi_14" in result.columns
        assert "bb_upper" in result.columns
        assert "obv" in result.columns

    def test_preserves_original_columns(self, ohlcv_df):
        result = add_all_indicators(ohlcv_df)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns
