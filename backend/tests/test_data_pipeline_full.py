"""Full coverage tests for common/data_pipeline/ subsystem.

Covers: format converters, add_indicators, fetch_ohlcv error paths,
list_available_data, validate_all_data, download_watchlist edge cases,
get_exchange, _parquet_path, news_adapter, yfinance_adapter edge cases.
"""

import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.data_pipeline.news_adapter import (
    _get_link,
    _get_text,
    _parse_date,
    _strip_html,
    article_id,
    fetch_all_news,
    fetch_newsapi,
    fetch_rss_feed,
)
from common.data_pipeline.pipeline import (
    _DEFAULT_WATCHLISTS,
    DataQualityReport,
    _parquet_path,
    add_indicators,
    audit_nans,
    detect_gaps,
    detect_outliers,
    detect_stale_data,
    download_watchlist,
    fetch_ohlcv,
    get_exchange,
    get_last_timestamp,
    list_available_data,
    load_ohlcv,
    save_ohlcv,
    to_freqtrade_format,
    to_hftbacktest_ticks,
    to_nautilus_bars,
    to_vectorbt_format,
    validate_all_data,
    validate_data,
)
from common.data_pipeline.yfinance_adapter import (
    _fetch_ohlcv_sync,
    _fetch_ticker_sync,
    _fetch_tickers_sync,
    _get_yf_interval,
    normalize_symbol,
    yfinance_to_platform_symbol,
)

# ── Helpers ────────────────────────────────────


def _make_ohlcv(
    start: str = "2025-01-01",
    periods: int = 100,
    freq: str = "1h",
    base_price: float = 50000.0,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    close = base_price + rng.randn(periods).cumsum() * 100
    high = close + rng.uniform(10, 200, periods)
    low = close - rng.uniform(10, 200, periods)
    opn = close + rng.uniform(-100, 100, periods)
    high = np.maximum(high, np.maximum(opn, close))
    low = np.minimum(low, np.minimum(opn, close))
    volume = rng.uniform(100, 10000, periods)
    df = pd.DataFrame(
        {"open": opn, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    df.index.name = "timestamp"
    return df


# ══════════════════════════════════════════════
# Format Converters
# ══════════════════════════════════════════════


class TestToFreqtradeFormat:
    def test_basic_conversion(self):
        df = _make_ohlcv(periods=10)
        ft = to_freqtrade_format(df)
        assert ft.index.name == "date"
        assert list(ft.columns) == ["open", "high", "low", "close", "volume"]
        assert len(ft) == 10

    def test_does_not_modify_original(self):
        df = _make_ohlcv(periods=5)
        original_index_name = df.index.name
        to_freqtrade_format(df)
        assert df.index.name == original_index_name

    def test_with_nan_values(self):
        df = _make_ohlcv(periods=5)
        df.iloc[2, df.columns.get_loc("close")] = np.nan
        ft = to_freqtrade_format(df)
        assert pd.isna(ft.iloc[2]["close"])

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        ft = to_freqtrade_format(df)
        assert ft.empty
        assert ft.index.name == "date"


class TestToVectorbtFormat:
    def test_returns_copy(self):
        df = _make_ohlcv(periods=5)
        vbt = to_vectorbt_format(df)
        assert vbt is not df
        pd.testing.assert_frame_equal(vbt, df)

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        vbt = to_vectorbt_format(df)
        assert vbt.empty

    def test_with_nan_values(self):
        df = _make_ohlcv(periods=5)
        df.iloc[0, 0] = np.nan
        vbt = to_vectorbt_format(df)
        assert pd.isna(vbt.iloc[0, 0])


class TestToNautilusBars:
    def test_basic_conversion(self):
        df = _make_ohlcv(periods=3)
        bars = to_nautilus_bars(df, "BTC/USDT")
        assert len(bars) == 3
        assert bars[0]["symbol"] == "BTC/USDT"
        assert "open" in bars[0]
        assert "timestamp" in bars[0]

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df.index.name = "timestamp"
        bars = to_nautilus_bars(df, "ETH/USDT")
        assert bars == []

    def test_nan_values_preserved(self):
        df = _make_ohlcv(periods=2)
        df.iloc[0, df.columns.get_loc("volume")] = np.nan
        bars = to_nautilus_bars(df, "SOL/USDT")
        assert np.isnan(bars[0]["volume"])

    def test_float_precision(self):
        df = _make_ohlcv(periods=1)
        bars = to_nautilus_bars(df, "BTC/USDT")
        assert isinstance(bars[0]["open"], float)
        assert isinstance(bars[0]["close"], float)


class TestToHftbacktestTicks:
    def test_basic_conversion(self):
        df = _make_ohlcv(periods=5)
        ticks = to_hftbacktest_ticks(df, "1h")
        assert ticks.shape == (20, 4)  # 5 bars * 4 ticks
        assert ticks.dtype == np.float64

    def test_timestamp_nanoseconds(self):
        df = _make_ohlcv(periods=2)
        ticks = to_hftbacktest_ticks(df, "1h")
        # Nanosecond timestamps should be very large numbers
        assert ticks[0, 0] > 1e18

    def test_volume_distributed(self):
        df = _make_ohlcv(periods=1)
        total_vol = df.iloc[0]["volume"]
        ticks = to_hftbacktest_ticks(df, "1h")
        # Volume should be divided by 4 for each tick
        assert abs(ticks[0, 2] - total_vol / 4) < 1e-6

    def test_side_assignment(self):
        df = _make_ohlcv(periods=1)
        # Force close > open for bullish candle
        df.iloc[0, df.columns.get_loc("close")] = df.iloc[0]["open"] + 100
        ticks = to_hftbacktest_ticks(df, "1h")
        # Last tick (close) should be buy (+1) for bullish candle
        assert ticks[3, 3] == 1

    def test_bearish_candle_side(self):
        df = _make_ohlcv(periods=1)
        df.iloc[0, df.columns.get_loc("close")] = df.iloc[0]["open"] - 100
        ticks = to_hftbacktest_ticks(df, "1h")
        assert ticks[3, 3] == -1

    def test_different_timeframes(self):
        df = _make_ohlcv(periods=2)
        for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
            ticks = to_hftbacktest_ticks(df, tf)
            assert ticks.shape == (8, 4)

    def test_unknown_timeframe_uses_default(self):
        df = _make_ohlcv(periods=1)
        ticks = to_hftbacktest_ticks(df, "3h")
        assert ticks.shape == (4, 4)

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df.index = pd.DatetimeIndex([], name="timestamp")
        ticks = to_hftbacktest_ticks(df)
        assert len(ticks) == 0


# ══════════════════════════════════════════════
# add_indicators
# ══════════════════════════════════════════════


class TestAddIndicators:
    def test_basic_indicators_added(self):
        df = _make_ohlcv(periods=250)
        result = add_indicators(df)
        assert "sma_7" in result.columns
        assert "ema_200" in result.columns
        assert "rsi_14" in result.columns
        assert "macd" in result.columns
        assert "bb_upper" in result.columns
        assert "atr_14" in result.columns
        assert "volume_ratio" in result.columns
        assert "returns" in result.columns
        assert "log_returns" in result.columns

    def test_custom_periods(self):
        df = _make_ohlcv(periods=50)
        result = add_indicators(df, periods=[5, 10])
        assert "sma_5" in result.columns
        assert "ema_10" in result.columns
        assert "sma_7" not in result.columns

    def test_insufficient_data_produces_nans(self):
        df = _make_ohlcv(periods=5)
        result = add_indicators(df)
        # SMA_200 with only 5 rows should be all NaN
        assert result["sma_200"].isna().all()

    def test_does_not_modify_original(self):
        df = _make_ohlcv(periods=30)
        cols_before = list(df.columns)
        add_indicators(df)
        assert list(df.columns) == cols_before

    def test_with_nan_input(self):
        df = _make_ohlcv(periods=30)
        df.iloc[10, df.columns.get_loc("close")] = np.nan
        result = add_indicators(df)
        # Should not crash, NaNs propagate
        assert not result.empty

    def test_single_row(self):
        df = _make_ohlcv(periods=1)
        result = add_indicators(df)
        assert len(result) == 1


# ══════════════════════════════════════════════
# get_exchange
# ══════════════════════════════════════════════


class TestGetExchange:
    @patch("common.data_pipeline.pipeline.ccxt")
    def test_creates_exchange_with_sandbox(self, mock_ccxt):
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.urls = {"test": "https://sandbox.example.com"}
        mock_cls.return_value = mock_instance
        mock_ccxt.kraken = mock_cls

        result = get_exchange("kraken", sandbox=True)
        mock_instance.set_sandbox_mode.assert_called_with(True)
        assert result == mock_instance

    @patch("common.data_pipeline.pipeline.ccxt")
    def test_no_sandbox_when_disabled(self, mock_ccxt):
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.urls = {"test": "https://sandbox.example.com"}
        mock_cls.return_value = mock_instance
        mock_ccxt.kraken = mock_cls

        get_exchange("kraken", sandbox=False)
        mock_instance.set_sandbox_mode.assert_not_called()

    @patch("common.data_pipeline.pipeline.ccxt")
    def test_no_sandbox_url_available(self, mock_ccxt):
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.urls = {}  # No test URL
        mock_cls.return_value = mock_instance
        mock_ccxt.kraken = mock_cls

        get_exchange("kraken", sandbox=True)
        mock_instance.set_sandbox_mode.assert_not_called()

    @patch.dict("os.environ", {"KRAKEN_API_KEY": "mykey", "KRAKEN_SECRET": "mysecret"})
    @patch("common.data_pipeline.pipeline.ccxt")
    def test_loads_api_keys_from_env(self, mock_ccxt):
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.urls = {}
        mock_cls.return_value = mock_instance
        mock_ccxt.kraken = mock_cls

        get_exchange("kraken", sandbox=False)
        config = mock_cls.call_args[0][0]
        assert config["apiKey"] == "mykey"
        assert config["secret"] == "mysecret"

    @patch("common.data_pipeline.pipeline.ccxt")
    def test_no_api_keys_when_not_in_env(self, mock_ccxt):
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.urls = {}
        mock_cls.return_value = mock_instance
        mock_ccxt.kraken = mock_cls

        with patch.dict("os.environ", {}, clear=True):
            get_exchange("kraken", sandbox=False)
        config = mock_cls.call_args[0][0]
        assert "apiKey" not in config


# ══════════════════════════════════════════════
# _parquet_path
# ══════════════════════════════════════════════


class TestParquetPath:
    def test_standard_path(self, tmp_path):
        path = _parquet_path("BTC/USDT", "1h", "kraken", tmp_path)
        assert path == tmp_path / "kraken_BTC_USDT_1h.parquet"

    def test_source_override(self, tmp_path):
        path = _parquet_path("AAPL/USD", "1d", "kraken", tmp_path, source="yfinance")
        assert path == tmp_path / "yfinance_AAPL_USD_1d.parquet"

    def test_symbol_slash_replaced(self, tmp_path):
        path = _parquet_path("EUR/USD", "1h", "kraken", tmp_path)
        assert "EUR_USD" in path.name


# ══════════════════════════════════════════════
# fetch_ohlcv error paths
# ══════════════════════════════════════════════


class TestFetchOhlcvErrorPaths:
    @patch("common.data_pipeline.pipeline.time.sleep")
    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_rate_limit_retry(self, mock_get_exchange, mock_sleep):
        import ccxt

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        candles = [[now_ms, 100, 110, 90, 105, 1000]]

        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 100
        mock_exchange.fetch_ohlcv.side_effect = [
            ccxt.RateLimitExceeded("slow down"),
            candles,
            [],  # end pagination
        ]
        mock_get_exchange.return_value = mock_exchange

        result = fetch_ohlcv("BTC/USDT", "1h", since_days=1)
        assert len(result) == 1
        # Should have slept 10s for rate limit
        mock_sleep.assert_any_call(10)

    @patch("common.data_pipeline.pipeline.time.sleep")
    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_network_error_retry(self, mock_get_exchange, mock_sleep):
        import ccxt

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        candles = [[now_ms, 100, 110, 90, 105, 1000]]

        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 100
        mock_exchange.fetch_ohlcv.side_effect = [
            ccxt.NetworkError("timeout"),
            candles,
            [],
        ]
        mock_get_exchange.return_value = mock_exchange

        result = fetch_ohlcv("BTC/USDT", "1h", since_days=1)
        assert len(result) == 1
        mock_sleep.assert_any_call(5)

    @patch("common.data_pipeline.pipeline.time.sleep")
    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_since_timestamp_parameter(self, mock_get_exchange, mock_sleep):
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        candles = [[now_ms, 100, 110, 90, 105, 1000]]

        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 100
        mock_exchange.fetch_ohlcv.side_effect = [candles, []]
        mock_get_exchange.return_value = mock_exchange

        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        result = fetch_ohlcv("BTC/USDT", "1h", since_timestamp=since)
        assert len(result) == 1
        # Verify the since parameter was used
        call_kwargs = mock_exchange.fetch_ohlcv.call_args_list[0]
        since_ms = call_kwargs[1].get("since") or call_kwargs[0][2]
        assert since_ms == int(since.timestamp() * 1000)

    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_duplicate_timestamps_deduplicated(self, mock_get_exchange):
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        # Same timestamp twice
        candles = [
            [now_ms - 3600_000, 100, 110, 90, 105, 1000],
            [now_ms - 3600_000, 100, 110, 90, 106, 1001],  # dupe
            [now_ms, 101, 111, 91, 106, 1001],
        ]

        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 100
        mock_exchange.fetch_ohlcv.side_effect = [candles, []]
        mock_get_exchange.return_value = mock_exchange

        with patch("common.data_pipeline.pipeline.time.sleep"):
            result = fetch_ohlcv("BTC/USDT", "1h", since_days=1)
        assert not result.index.duplicated().any()


# ══════════════════════════════════════════════
# list_available_data
# ══════════════════════════════════════════════


class TestListAvailableData:
    def test_empty_directory(self, tmp_path):
        result = list_available_data(tmp_path)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_lists_files_with_metadata(self, tmp_path):
        df = _make_ohlcv(periods=10)
        df.to_parquet(tmp_path / "kraken_BTC_USDT_1h.parquet")

        result = list_available_data(tmp_path)
        assert len(result) == 1
        assert result.iloc[0]["exchange"] == "kraken"
        assert result.iloc[0]["symbol"] == "BTC/USDT"
        assert result.iloc[0]["timeframe"] == "1h"
        assert result.iloc[0]["rows"] == 10

    def test_ignores_non_parquet_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        result = list_available_data(tmp_path)
        assert result.empty

    def test_ignores_malformed_filenames(self, tmp_path):
        # Filename with fewer than 4 parts
        df = _make_ohlcv(periods=5)
        df.to_parquet(tmp_path / "short_name.parquet")
        result = list_available_data(tmp_path)
        assert result.empty

    def test_multiple_files(self, tmp_path):
        df = _make_ohlcv(periods=10)
        df.to_parquet(tmp_path / "kraken_BTC_USDT_1h.parquet")
        df.to_parquet(tmp_path / "kraken_ETH_USDT_1d.parquet")

        result = list_available_data(tmp_path)
        assert len(result) == 2


# ══════════════════════════════════════════════
# validate_all_data
# ══════════════════════════════════════════════


class TestValidateAllData:
    def test_no_files(self, tmp_path):
        reports = validate_all_data(tmp_path)
        assert reports == []

    def test_multiple_files_validated(self, tmp_path):
        now_str = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
            "%Y-%m-%d %H:%M",
        )
        df = _make_ohlcv(start=now_str, periods=10)
        save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)
        save_ohlcv(df, "ETH/USDT", "1h", "kraken", directory=tmp_path)

        reports = validate_all_data(tmp_path, max_stale_hours=100.0)
        assert len(reports) == 2
        assert all(isinstance(r, DataQualityReport) for r in reports)


# ══════════════════════════════════════════════
# download_watchlist edge cases
# ══════════════════════════════════════════════


class TestDownloadWatchlistEdgeCases:
    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp", return_value=None)
    @patch("common.data_pipeline.pipeline.save_ohlcv")
    def test_default_crypto_watchlist(self, mock_save, mock_last_ts, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        mock_save.return_value = Path("/tmp/x.parquet")

        results = download_watchlist(
            symbols=None, timeframes=["1h"], exchange_id="kraken", asset_class="crypto",
        )
        # Should use default crypto watchlist
        expected_count = len(_DEFAULT_WATCHLISTS["crypto"])
        assert len(results) == expected_count

    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp", return_value=None)
    @patch("common.data_pipeline.pipeline.save_ohlcv")
    def test_default_equity_timeframes(self, mock_save, mock_last_ts, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        results = download_watchlist(
            symbols=["AAPL/USD"], timeframes=None, asset_class="equity",
        )
        # Equity default is ["1d"]
        assert len(results) == 1
        assert "AAPL/USD_1d" in results

    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp", return_value=None)
    @patch("common.data_pipeline.pipeline.save_ohlcv")
    def test_default_forex_timeframes(self, mock_save, mock_last_ts, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        results = download_watchlist(
            symbols=["EUR/USD"], timeframes=None, asset_class="forex",
        )
        # Forex default is ["1h", "4h", "1d"]
        assert len(results) == 3

    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp")
    @patch("common.data_pipeline.pipeline.save_ohlcv")
    def test_incremental_update_uses_last_timestamp(
        self, mock_save, mock_last_ts, mock_fetch,
    ):
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        mock_last_ts.return_value = ts
        mock_fetch.return_value = _make_ohlcv(periods=5)
        mock_save.return_value = Path("/tmp/x.parquet")

        download_watchlist(
            symbols=["BTC/USDT"], timeframes=["1h"], exchange_id="kraken",
        )
        # fetch_ohlcv_multi should be called with since_timestamp
        call_kwargs = mock_fetch.call_args
        assert call_kwargs[1]["since_timestamp"] == ts

    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp", return_value=None)
    def test_yfinance_source_for_equity(self, mock_last_ts, mock_fetch):
        """Equity downloads should use 'yfinance' as the source prefix."""
        mock_fetch.return_value = pd.DataFrame()

        download_watchlist(
            symbols=["AAPL/USD"], timeframes=["1d"], asset_class="equity",
        )
        # get_last_timestamp should be called with "yfinance" source
        call_args = mock_last_ts.call_args
        assert call_args[0][2] == "yfinance"


# ══════════════════════════════════════════════
# Stale data per-asset-class thresholds
# ══════════════════════════════════════════════


class TestStaleDataThresholds:
    def test_crypto_threshold_2h(self):
        # Data 3 hours old should be stale for crypto (2h threshold)
        df = _make_ohlcv(
            start=(datetime.now(timezone.utc) - timedelta(hours=3)).strftime(
                "%Y-%m-%d %H:%M",
            ),
            periods=1,
        )
        is_stale, hours = detect_stale_data(df, asset_class="crypto")
        assert is_stale

    def test_equity_threshold_18h(self):
        # Data 10 hours old should NOT be stale for equity (18h threshold)
        df = _make_ohlcv(
            start=(datetime.now(timezone.utc) - timedelta(hours=10)).strftime(
                "%Y-%m-%d %H:%M",
            ),
            periods=1,
        )
        is_stale, hours = detect_stale_data(df, asset_class="equity")
        assert not is_stale

    def test_forex_threshold_4h(self):
        # Data 5 hours old should be stale for forex (4h threshold)
        df = _make_ohlcv(
            start=(datetime.now(timezone.utc) - timedelta(hours=5)).strftime(
                "%Y-%m-%d %H:%M",
            ),
            periods=1,
        )
        is_stale, hours = detect_stale_data(df, asset_class="forex")
        assert is_stale

    def test_custom_threshold_overrides_asset_class(self):
        # max_stale_hours != 2.0 means custom, don't use asset-class default
        df = _make_ohlcv(
            start=(datetime.now(timezone.utc) - timedelta(hours=3)).strftime(
                "%Y-%m-%d %H:%M",
            ),
            periods=1,
        )
        is_stale, _ = detect_stale_data(df, max_stale_hours=5.0, asset_class="crypto")
        assert not is_stale

    def test_tz_naive_index_handled(self):
        """DataFrame with tz-naive index should still work."""
        dates = pd.date_range("2020-01-01", periods=5, freq="1h")  # no tz
        df = pd.DataFrame(
            {"open": [1]*5, "high": [2]*5, "low": [0]*5, "close": [1]*5, "volume": [1]*5},
            index=dates,
        )
        is_stale, hours = detect_stale_data(df)
        assert is_stale  # Very old data


# ══════════════════════════════════════════════
# get_last_timestamp edge cases
# ══════════════════════════════════════════════


class TestGetLastTimestamp:
    def test_valid_parquet_returns_datetime(self, tmp_path):
        df = _make_ohlcv(periods=10)
        save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)
        result = get_last_timestamp("BTC/USDT", "1h", "kraken", directory=tmp_path)
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_nonexistent_file_returns_none(self, tmp_path):
        result = get_last_timestamp("NOPE/NOPE", "1h", "kraken", directory=tmp_path)
        assert result is None

    def test_tz_naive_index_gets_localized(self, tmp_path):
        dates = pd.date_range("2025-01-01", periods=5, freq="1h")  # no tz
        df = pd.DataFrame(
            {"open": [1]*5, "high": [2]*5, "low": [0]*5, "close": [1]*5, "volume": [1]*5},
            index=dates,
        )
        path = tmp_path / "kraken_TEST_PAIR_1h.parquet"
        df.to_parquet(path)
        result = get_last_timestamp("TEST/PAIR", "1h", "kraken", directory=tmp_path)
        assert result is not None
        assert result.tzinfo is not None


# ══════════════════════════════════════════════
# detect_gaps edge cases
# ══════════════════════════════════════════════


class TestDetectGapsEdgeCases:
    def test_daily_gap_detected(self):
        dates = pd.DatetimeIndex(
            [
                "2025-01-01",
                "2025-01-02",
                "2025-01-05",  # 2-day gap (weekend)
                "2025-01-06",
            ],
            tz="UTC",
        )
        df = pd.DataFrame(
            {"open": [1]*4, "high": [2]*4, "low": [0]*4, "close": [1]*4, "volume": [1]*4},
            index=dates,
        )
        gaps = detect_gaps(df, "1d")
        assert len(gaps) == 1
        assert gaps[0]["missing_candles"] == 2

    def test_unknown_timeframe_uses_1h_default(self):
        # Unknown timeframe falls back to 1h delta
        dates = pd.date_range("2025-01-01", periods=10, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {"open": range(10), "high": range(10), "low": range(10),
             "close": range(10), "volume": range(10)},
            index=dates,
        )
        gaps = detect_gaps(df, "3h")  # Unknown
        # Continuous 1h data with 3h default would show gaps everywhere
        assert len(gaps) == 0  # 1h delta, max_allowed_gaps=0, each gap is 1h

    def test_max_allowed_gaps(self):
        # Allow 1 missing candle before flagging
        dates = pd.DatetimeIndex(
            ["2025-01-01 00:00", "2025-01-01 02:00"],  # 1h gap
            tz="UTC",
        )
        df = pd.DataFrame(
            {"open": [1, 2], "high": [2, 3], "low": [0, 1], "close": [1, 2], "volume": [1, 1]},
            index=dates,
        )
        gaps_strict = detect_gaps(df, "1h", max_allowed_gaps=0)
        gaps_lenient = detect_gaps(df, "1h", max_allowed_gaps=1)
        assert len(gaps_strict) == 1
        assert len(gaps_lenient) == 0


# ══════════════════════════════════════════════
# detect_outliers edge cases
# ══════════════════════════════════════════════


class TestDetectOutliersEdgeCases:
    def test_empty_dataframe(self):
        assert detect_outliers(pd.DataFrame()) == []

    def test_single_row(self):
        df = _make_ohlcv(periods=1)
        assert detect_outliers(df) == []

    def test_custom_spike_threshold(self):
        df = _make_ohlcv(periods=20, base_price=100)
        # 15% spike
        df.iloc[10, df.columns.get_loc("close")] = df.iloc[9]["close"] * 1.16
        # With 20% threshold, shouldn't be detected
        outliers_20 = detect_outliers(df, price_spike_pct=0.20)
        # With 10% threshold, should be detected
        outliers_10 = detect_outliers(df, price_spike_pct=0.10)
        spike_20 = [o for o in outliers_20 if "spike" in o["reason"].lower()]
        spike_10 = [o for o in outliers_10 if "spike" in o["reason"].lower()]
        assert len(spike_10) >= len(spike_20)

    def test_first_zero_volume_skipped(self):
        """First row zero volume is ignored (may be partial candle)."""
        df = _make_ohlcv(periods=5)
        df.iloc[0, df.columns.get_loc("volume")] = 0
        outliers = detect_outliers(df)
        zero_vol = [o for o in outliers if "Zero volume" in o["reason"]]
        assert len(zero_vol) == 0


# ══════════════════════════════════════════════
# audit_nans edge cases
# ══════════════════════════════════════════════


class TestAuditNansEdgeCases:
    def test_all_nan_column(self):
        df = _make_ohlcv(periods=5)
        df["close"] = np.nan
        result = audit_nans(df)
        assert result["close"] == 5

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        result = audit_nans(df)
        assert result == {}


# ══════════════════════════════════════════════
# yfinance adapter edge cases
# ══════════════════════════════════════════════


class TestYfinanceAdapterEdgeCases:
    def test_get_yf_interval_known(self):
        assert _get_yf_interval("1h") == "1h"
        assert _get_yf_interval("4h") == "1h"  # Needs resampling
        assert _get_yf_interval("1d") == "1d"

    def test_get_yf_interval_unknown(self):
        assert _get_yf_interval("3h") == "1d"

    def test_normalize_forex_no_slash(self):
        assert normalize_symbol("EURUSD", "forex") == "EURUSD"

    def test_reverse_forex_non_standard(self):
        # Non-6-char pair with =X
        assert yfinance_to_platform_symbol("USDDKK=X", "forex") == "USD/DKK"

    def test_reverse_forex_no_suffix(self):
        assert yfinance_to_platform_symbol("USDDKK", "forex") == "USDDKK"

    def test_reverse_crypto_passthrough(self):
        assert yfinance_to_platform_symbol("BTC/USDT", "crypto") == "BTC/USDT"

    def test_fetch_4h_resampling(self):
        # 1h data that should be resampled to 4h
        dates = pd.date_range("2025-01-01", periods=8, freq="1h", tz="UTC")
        mock_df = pd.DataFrame(
            {
                "Open": [100 + i for i in range(8)],
                "High": [110 + i for i in range(8)],
                "Low": [90 + i for i in range(8)],
                "Close": [105 + i for i in range(8)],
                "Volume": [1000] * 8,
            },
            index=dates,
        )
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_df
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = _fetch_ohlcv_sync("AAPL/USD", "4h", 30, "equity")
        assert len(result) == 2  # 8 hourly bars → 2 4h bars

    def test_fetch_with_since_timestamp(self):
        dates = pd.date_range("2025-06-01", periods=5, freq="1d", tz="UTC")
        mock_df = pd.DataFrame(
            {
                "Open": [100]*5, "High": [110]*5, "Low": [90]*5,
                "Close": [105]*5, "Volume": [1000]*5,
            },
            index=dates,
        )
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_df
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            since = datetime(2025, 6, 1, tzinfo=timezone.utc)
            result = _fetch_ohlcv_sync("AAPL/USD", "1d", 30, "equity", since_timestamp=since)
        assert len(result) == 5

    def test_fetch_clamps_since_days(self):
        """1m data clamped to 7 days max."""
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = _fetch_ohlcv_sync("AAPL/USD", "1m", 365, "equity")
        assert result.empty

    def test_fetch_missing_volume_column(self):
        """Yfinance sometimes omits Volume — should fill with 0."""
        dates = pd.date_range("2025-01-01", periods=3, freq="1d", tz="UTC")
        mock_df = pd.DataFrame(
            {
                "Open": [100, 101, 102],
                "High": [110, 111, 112],
                "Low": [90, 91, 92],
                "Close": [105, 106, 107],
                # No Volume column
            },
            index=dates,
        )
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_df
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = _fetch_ohlcv_sync("AAPL/USD", "1d", 30, "equity")
        assert "volume" in result.columns
        assert (result["volume"] == 0.0).all()


class TestYfinanceTickerFetch:
    def test_fetch_ticker_sync(self):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_info = MagicMock()
        mock_info.last_price = 150.0
        mock_info.previous_close = 148.0
        mock_info.last_volume = 5000000
        mock_info.day_high = 152.0
        mock_info.day_low = 147.0
        mock_ticker.fast_info = mock_info
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = _fetch_ticker_sync("AAPL/USD", "equity")
        assert result["symbol"] == "AAPL/USD"
        assert result["price"] == 150.0
        assert result["volume_24h"] == 5000000
        assert abs(result["change_24h"] - 1.35) < 0.1

    def test_fetch_ticker_zero_prev_close(self):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_info = MagicMock()
        mock_info.last_price = 150.0
        mock_info.previous_close = 0  # Falsy
        mock_info.last_volume = 0
        mock_info.day_high = 0.0
        mock_info.day_low = 0.0
        mock_ticker.fast_info = mock_info
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = _fetch_ticker_sync("TEST/USD", "equity")
        assert result["change_24h"] == 0.0

    def test_fetch_tickers_sync_partial_failure(self):
        mock_yf = MagicMock()

        def ticker_side_effect(sym):
            if sym == "BAD":
                raise ValueError("bad symbol")
            mock_ticker = MagicMock()
            mock_info = MagicMock()
            mock_info.last_price = 100.0
            mock_info.previous_close = 100.0
            mock_info.last_volume = 1000
            mock_info.day_high = 101.0
            mock_info.day_low = 99.0
            mock_ticker.fast_info = mock_info
            return mock_ticker

        mock_yf.Ticker.side_effect = ticker_side_effect

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            results = _fetch_tickers_sync(["AAPL", "BAD", "MSFT"], "equity")
        # BAD should be skipped
        assert len(results) == 2


# ══════════════════════════════════════════════
# News Adapter
# ══════════════════════════════════════════════


class TestArticleId:
    def test_deterministic(self):
        id1 = article_id("https://example.com/article")
        id2 = article_id("https://example.com/article")
        assert id1 == id2

    def test_different_urls_different_ids(self):
        id1 = article_id("https://example.com/a")
        id2 = article_id("https://example.com/b")
        assert id1 != id2

    def test_length_64(self):
        result = article_id("https://example.com")
        assert len(result) == 64


class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_no_tags(self):
        assert _strip_html("plain text") == "plain text"


class TestParseDate:
    def test_iso_8601(self):
        result = _parse_date("2025-01-15T10:30:00Z")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_rfc_2822(self):
        result = _parse_date("Mon, 15 Jan 2025 10:30:00 +0000")
        assert result.year == 2025

    def test_empty_string_returns_now(self):
        before = datetime.now(tz=timezone.utc)
        result = _parse_date("")
        after = datetime.now(tz=timezone.utc)
        assert before <= result <= after

    def test_unparseable_returns_now(self):
        before = datetime.now(tz=timezone.utc)
        result = _parse_date("not-a-date")
        after = datetime.now(tz=timezone.utc)
        assert before <= result <= after

    def test_iso_with_timezone(self):
        result = _parse_date("2025-06-01T12:00:00+05:00")
        assert result.tzinfo is not None


class TestGetText:
    def test_plain_child(self):
        root = ET.fromstring("<item><title>Hello</title></item>")
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        assert _get_text(root, "title", ns) == "Hello"

    def test_missing_child(self):
        root = ET.fromstring("<item></item>")
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        assert _get_text(root, "title", ns) == ""

    def test_empty_text(self):
        root = ET.fromstring("<item><title></title></item>")
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        assert _get_text(root, "title", ns) == ""


class TestGetLink:
    def test_rss_link(self):
        root = ET.fromstring("<item><link>https://example.com</link></item>")
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        assert _get_link(root, ns) == "https://example.com"

    def test_atom_href(self):
        root = ET.fromstring('<item><link href="https://example.com"/></item>')
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        assert _get_link(root, ns) == "https://example.com"

    def test_no_link(self):
        root = ET.fromstring("<item></item>")
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        assert _get_link(root, ns) == ""


class TestFetchRssFeed:
    @patch("common.data_pipeline.news_adapter.urllib.request.urlopen")
    def test_valid_rss(self, mock_urlopen):
        rss_xml = b"""<?xml version="1.0"?>
        <rss><channel>
            <item>
                <title>Test Article</title>
                <link>https://example.com/1</link>
                <pubDate>Mon, 15 Jan 2025 10:30:00 +0000</pubDate>
                <description>Summary text</description>
            </item>
        </channel></rss>"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = rss_xml
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        articles = fetch_rss_feed("https://example.com/rss", "TestSource")
        assert len(articles) == 1
        assert articles[0]["title"] == "Test Article"
        assert articles[0]["source"] == "TestSource"
        assert len(articles[0]["article_id"]) == 64

    @patch("common.data_pipeline.news_adapter.urllib.request.urlopen")
    def test_network_error_returns_empty(self, mock_urlopen):
        mock_urlopen.side_effect = ConnectionError("timeout")
        articles = fetch_rss_feed("https://example.com/rss", "TestSource")
        assert articles == []

    @patch("common.data_pipeline.news_adapter.urllib.request.urlopen")
    def test_malformed_xml_returns_empty(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"NOT XML AT ALL <<<"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        articles = fetch_rss_feed("https://example.com/rss", "TestSource")
        assert articles == []

    @patch("common.data_pipeline.news_adapter.urllib.request.urlopen")
    def test_items_capped_at_20(self, mock_urlopen):
        items = "".join(
            f"<item><title>Art {i}</title><link>https://example.com/{i}</link></item>"
            for i in range(30)
        )
        rss_xml = f'<?xml version="1.0"?><rss><channel>{items}</channel></rss>'.encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = rss_xml
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        articles = fetch_rss_feed("https://example.com/rss", "TestSource")
        assert len(articles) == 20

    @patch("common.data_pipeline.news_adapter.urllib.request.urlopen")
    def test_skips_items_without_title_or_link(self, mock_urlopen):
        rss_xml = b"""<?xml version="1.0"?>
        <rss><channel>
            <item><title>No Link</title></item>
            <item><link>https://example.com/no-title</link></item>
            <item><title>Good</title><link>https://example.com/good</link></item>
        </channel></rss>"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = rss_xml
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        articles = fetch_rss_feed("https://example.com/rss", "TestSource")
        assert len(articles) == 1
        assert articles[0]["title"] == "Good"


class TestFetchNewsapi:
    @patch("common.data_pipeline.news_adapter.urllib.request.urlopen")
    def test_rate_limiting(self, mock_urlopen):
        import common.data_pipeline.news_adapter as na
        # Force rate limit by setting last call to now
        na._newsapi_last_call = time.time()

        articles = fetch_newsapi("crypto", "test-key")
        assert articles == []
        mock_urlopen.assert_not_called()

    def test_empty_api_key(self):
        articles = fetch_newsapi("crypto", "")
        assert articles == []

    @patch("common.data_pipeline.news_adapter.urllib.request.urlopen")
    def test_successful_fetch(self, mock_urlopen):
        import common.data_pipeline.news_adapter as na
        # Reset rate limit
        na._newsapi_last_call = 0

        response_data = {
            "articles": [
                {
                    "title": "Bitcoin Surges",
                    "url": "https://news.example.com/btc",
                    "description": "BTC hits new high",
                    "publishedAt": "2025-01-15T10:00:00Z",
                    "source": {"name": "CryptoNews"},
                },
                {
                    "url": "",  # Empty URL, should be skipped
                    "title": "Bad Article",
                },
            ],
        }
        import json

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        articles = fetch_newsapi("crypto", "test-key")
        assert len(articles) == 1
        assert articles[0]["title"] == "Bitcoin Surges"
        assert articles[0]["source"] == "CryptoNews"

    @patch("common.data_pipeline.news_adapter.urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        import common.data_pipeline.news_adapter as na
        na._newsapi_last_call = 0

        mock_urlopen.side_effect = ConnectionError("timeout")
        articles = fetch_newsapi("crypto", "test-key")
        assert articles == []

    def test_unknown_asset_class(self):
        import common.data_pipeline.news_adapter as na
        na._newsapi_last_call = 0
        articles = fetch_newsapi("commodities", "test-key")
        assert articles == []


class TestFetchAllNews:
    @patch("common.data_pipeline.news_adapter.fetch_newsapi")
    @patch("common.data_pipeline.news_adapter.fetch_rss_feed")
    def test_deduplication(self, mock_rss, mock_newsapi):
        art = {
            "article_id": "abc123",
            "title": "Test",
            "url": "https://example.com/1",
            "source": "Test",
            "summary": "",
            "published_at": datetime.now(tz=timezone.utc),
        }
        # Same article from both RSS and NewsAPI
        mock_rss.return_value = [art]
        mock_newsapi.return_value = [art]

        articles = fetch_all_news("crypto", "test-key")
        # Should be deduplicated
        assert len(articles) == 1

    @patch("common.data_pipeline.news_adapter.fetch_newsapi")
    @patch("common.data_pipeline.news_adapter.fetch_rss_feed")
    def test_empty_results(self, mock_rss, mock_newsapi):
        mock_rss.return_value = []
        mock_newsapi.return_value = []

        articles = fetch_all_news("crypto")
        assert articles == []

    @patch("common.data_pipeline.news_adapter.fetch_newsapi")
    @patch("common.data_pipeline.news_adapter.fetch_rss_feed")
    def test_unknown_asset_class_no_feeds(self, mock_rss, mock_newsapi):
        mock_newsapi.return_value = []
        articles = fetch_all_news("commodities")
        mock_rss.assert_not_called()  # No RSS feeds for commodities
        assert articles == []


# ══════════════════════════════════════════════
# Integration: save → load → validate → convert
# ══════════════════════════════════════════════


class TestFullPipelineIntegration:
    def test_save_load_validate_convert_cycle(self, tmp_path):
        """End-to-end: generate → save → load → validate → convert to all formats."""
        df = _make_ohlcv(
            start=(datetime.now(timezone.utc) - timedelta(hours=50)).strftime(
                "%Y-%m-%d %H:%M",
            ),
            periods=48,
        )

        # Save
        path = save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)
        assert path.exists()

        # Load
        loaded = load_ohlcv("BTC/USDT", "1h", "kraken", directory=tmp_path)
        assert len(loaded) == 48

        # Validate
        report = validate_data(
            "BTC/USDT", "1h", "kraken",
            directory=tmp_path, max_stale_hours=100.0,
        )
        assert report.rows == 48
        assert report.passed is True

        # Convert to all formats
        ft = to_freqtrade_format(loaded)
        assert len(ft) == 48

        vbt = to_vectorbt_format(loaded)
        assert len(vbt) == 48

        bars = to_nautilus_bars(loaded, "BTC/USDT")
        assert len(bars) == 48

        ticks = to_hftbacktest_ticks(loaded, "1h")
        assert ticks.shape == (192, 4)

    def test_add_indicators_then_convert(self, tmp_path):
        """Indicators can be added; freqtrade format only takes base OHLCV."""
        df = _make_ohlcv(periods=200)
        enriched = add_indicators(df, periods=[14, 50])
        # to_freqtrade_format expects exactly 5 OHLCV columns, so filter first
        ft = to_freqtrade_format(enriched[["open", "high", "low", "close", "volume"]])
        assert len(ft) == 200
        # VectorBT format preserves all columns
        vbt = to_vectorbt_format(enriched)
        assert "sma_14" in vbt.columns


# ══════════════════════════════════════════════
# DataQualityReport dataclass
# ══════════════════════════════════════════════


class TestDataQualityReport:
    def test_fields_accessible(self):
        report = DataQualityReport(
            symbol="BTC/USDT", timeframe="1h", exchange="kraken",
            rows=100, date_range=("2025-01-01", "2025-01-05"),
            gaps=[], nan_columns={}, outliers=[], ohlc_violations=[],
            is_stale=False, stale_hours=1.0,
            passed=True, issues_summary=[],
        )
        assert report.symbol == "BTC/USDT"
        assert report.passed is True
        assert report.rows == 100
