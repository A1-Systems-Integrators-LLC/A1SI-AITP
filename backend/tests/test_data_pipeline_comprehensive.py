"""Comprehensive tests for the Data Pipeline subsystem.

Covers: exchange failures, partial watchlist downloads, parquet corruption,
concurrent write safety, yfinance adapter, data validation, and incremental
fetch edge cases.
"""

import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.data_pipeline.pipeline import (
    audit_nans,
    check_ohlc_integrity,
    detect_gaps,
    detect_outliers,
    detect_stale_data,
    download_watchlist,
    fetch_ohlcv,
    fetch_ohlcv_multi,
    get_last_timestamp,
    load_ohlcv,
    save_ohlcv,
    validate_data,
)
from common.data_pipeline.yfinance_adapter import (
    _fetch_ohlcv_sync,
    normalize_symbol,
    yfinance_to_platform_symbol,
)

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_ohlcv(
    start: str = "2025-01-01",
    periods: int = 100,
    freq: str = "1h",
    base_price: float = 50000.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a valid OHLCV DataFrame for testing."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    close = base_price + rng.randn(periods).cumsum() * 100
    high = close + rng.uniform(10, 200, periods)
    low = close - rng.uniform(10, 200, periods)
    opn = close + rng.uniform(-100, 100, periods)
    # Ensure OHLC integrity
    high = np.maximum(high, np.maximum(opn, close))
    low = np.minimum(low, np.minimum(opn, close))
    volume = rng.uniform(100, 10000, periods)
    df = pd.DataFrame(
        {"open": opn, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    df.index.name = "timestamp"
    return df


# ──────────────────────────────────────────────
# 1. Exchange Down / Empty Data
# ──────────────────────────────────────────────


class TestExchangeDownEmptyData:
    """Tests for handling exchange failures and empty responses."""

    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_fetch_ohlcv_empty_candles_returns_empty_df(self, mock_get_exchange):
        """Ccxt returning empty list should yield an empty DataFrame."""
        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 100
        mock_exchange.fetch_ohlcv.return_value = []
        mock_get_exchange.return_value = mock_exchange

        result = fetch_ohlcv("BTC/USDT", "1h", since_days=7)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_fetch_ohlcv_symbol_not_on_exchange(self, mock_get_exchange):
        """Symbol not in exchange.markets should return empty DataFrame."""
        mock_exchange = MagicMock()
        mock_exchange.markets = {"ETH/USDT": {}}
        mock_get_exchange.return_value = mock_exchange

        result = fetch_ohlcv("FAKE/PAIR", "1h")
        assert result.empty

    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_fetch_ohlcv_exchange_error_breaks_loop(self, mock_get_exchange):
        """ccxt.ExchangeError should break the fetch loop gracefully."""
        import ccxt

        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 100
        mock_exchange.fetch_ohlcv.side_effect = ccxt.ExchangeError("maintenance")
        mock_get_exchange.return_value = mock_exchange

        result = fetch_ohlcv("BTC/USDT", "1h", since_days=1)
        assert result.empty

    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_fetch_ohlcv_single_batch_returned(self, mock_get_exchange):
        """A single batch of candles should produce a valid DataFrame."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        candles = [
            [now_ms - 3600_000 * i, 100 + i, 110 + i, 90 + i, 105 + i, 1000 + i]
            for i in range(5, 0, -1)
        ]
        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 100
        mock_exchange.fetch_ohlcv.side_effect = [candles, []]
        mock_get_exchange.return_value = mock_exchange

        result = fetch_ohlcv("BTC/USDT", "1h", since_days=1)
        assert len(result) == 5
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]


# ──────────────────────────────────────────────
# 2. Partial Watchlist Download
# ──────────────────────────────────────────────


class TestPartialWatchlistDownload:
    """Some symbols succeed, some fail — verify partial results with error info."""

    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp", return_value=None)
    @patch("common.data_pipeline.pipeline.save_ohlcv")
    def test_partial_success_records_both_ok_and_error(
        self, mock_save, mock_last_ts, mock_fetch,
    ):
        good_df = _make_ohlcv(periods=10)

        def fetch_side_effect(symbol, *a, **kw):
            if symbol == "BTC/USDT":
                return good_df
            raise ConnectionError("exchange down")

        mock_fetch.side_effect = fetch_side_effect
        mock_save.return_value = Path("/tmp/fake.parquet")

        results = download_watchlist(
            symbols=["BTC/USDT", "FAIL/PAIR"],
            timeframes=["1h"],
            exchange_id="kraken",
        )

        assert results["BTC/USDT_1h"]["status"] == "ok"
        assert results["BTC/USDT_1h"]["rows"] == 10
        assert results["FAIL/PAIR_1h"]["status"] == "error"
        assert "exchange down" in results["FAIL/PAIR_1h"]["error"]

    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp", return_value=None)
    def test_all_symbols_empty(self, mock_last_ts, mock_fetch):
        """All symbols returning empty data should be recorded as 'empty'."""
        mock_fetch.return_value = pd.DataFrame()

        results = download_watchlist(
            symbols=["A/USDT", "B/USDT"],
            timeframes=["1h"],
            exchange_id="kraken",
        )
        assert results["A/USDT_1h"]["status"] == "empty"
        assert results["B/USDT_1h"]["status"] == "empty"


# ──────────────────────────────────────────────
# 3. Parquet File Corruption Recovery
# ──────────────────────────────────────────────


class TestParquetCorruptionRecovery:
    """Corrupt parquet files should not crash the pipeline."""

    def test_load_ohlcv_corrupt_file_returns_empty(self, tmp_path):
        """Writing garbage bytes should not crash load_ohlcv."""
        corrupt_path = tmp_path / "kraken_BTC_USDT_1h.parquet"
        corrupt_path.write_bytes(b"THIS IS NOT A PARQUET FILE\x00\xff\xfe")

        result = load_ohlcv("BTC/USDT", "1h", "kraken", directory=tmp_path)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_get_last_timestamp_corrupt_file_returns_none(self, tmp_path):
        """Corrupt parquet in get_last_timestamp should return None, not crash."""
        corrupt_path = tmp_path / "kraken_ETH_USDT_1h.parquet"
        corrupt_path.write_bytes(b"\x00\x01\x02\x03CORRUPT")

        result = get_last_timestamp("ETH/USDT", "1h", "kraken", directory=tmp_path)
        assert result is None

    def test_save_ohlcv_over_corrupt_existing(self, tmp_path):
        """save_ohlcv should handle corrupt existing file gracefully.

        When the existing file is corrupt, pd.read_parquet will raise an
        exception inside the lock. The function should propagate this error
        (it's inside a try/finally for the lock, not a try/except for reads).
        """
        corrupt_path = tmp_path / "kraken_BTC_USDT_1h.parquet"
        corrupt_path.write_bytes(b"CORRUPT DATA")

        new_df = _make_ohlcv(periods=5)
        # save_ohlcv tries to read existing then merge — corrupt existing raises
        with pytest.raises((OSError, ValueError)):
            save_ohlcv(new_df, "BTC/USDT", "1h", "kraken", directory=tmp_path)

    def test_validate_data_on_corrupt_file(self, tmp_path):
        """validate_data should return a failing report for corrupt files."""
        corrupt_path = tmp_path / "kraken_BTC_USDT_1h.parquet"
        corrupt_path.write_bytes(b"NOT PARQUET")

        report = validate_data(
            "BTC/USDT", "1h", "kraken", directory=tmp_path,
        )
        assert report.passed is False
        assert report.rows == 0
        assert "No data found" in report.issues_summary


# ──────────────────────────────────────────────
# 4. Concurrent Write Safety (fcntl locking)
# ──────────────────────────────────────────────


class TestConcurrentWriteSafety:
    """Verify fcntl file locking prevents data corruption on concurrent writes."""

    def test_concurrent_saves_no_data_loss(self, tmp_path):
        """Two threads saving to the same file should not lose data."""
        df1 = _make_ohlcv(start="2025-01-01", periods=50, seed=1)
        df2 = _make_ohlcv(start="2025-01-03 02:00:00", periods=50, seed=2)

        errors = []

        def writer(df):
            try:
                save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer, args=(df1,))
        t2 = threading.Thread(target=writer, args=(df2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"Errors during concurrent write: {errors}"

        # Load result — should have data from both writes, deduplicated
        result = load_ohlcv("BTC/USDT", "1h", "kraken", directory=tmp_path)
        assert not result.empty
        # Should contain unique timestamps from both DataFrames
        combined_unique = pd.concat([df1, df2]).index.unique()
        assert len(result) == len(combined_unique)

    def test_lock_file_created(self, tmp_path):
        """save_ohlcv should create a .lock file alongside the parquet."""
        df = _make_ohlcv(periods=5)
        save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)

        lock_path = tmp_path / "kraken_BTC_USDT_1h.parquet.lock"
        assert lock_path.exists()


# ──────────────────────────────────────────────
# 5. yfinance Adapter Tests
# ──────────────────────────────────────────────


class TestYfinanceSymbolNormalization:
    """Test symbol normalization between platform and yfinance formats."""

    def test_equity_aapl_usd_to_aapl(self):
        assert normalize_symbol("AAPL/USD", "equity") == "AAPL"

    def test_equity_plain_symbol_unchanged(self):
        assert normalize_symbol("MSFT", "equity") == "MSFT"

    def test_equity_index_symbol_unchanged(self):
        assert normalize_symbol("^GSPC", "equity") == "^GSPC"

    def test_forex_eur_usd_to_yfinance(self):
        assert normalize_symbol("EUR/USD", "forex") == "EURUSD=X"

    def test_forex_gbp_jpy(self):
        assert normalize_symbol("GBP/JPY", "forex") == "GBPJPY=X"

    def test_crypto_passthrough(self):
        assert normalize_symbol("BTC/USDT", "crypto") == "BTC/USDT"

    def test_reverse_equity_aapl(self):
        assert yfinance_to_platform_symbol("AAPL", "equity") == "AAPL/USD"

    def test_reverse_forex_eurusd(self):
        assert yfinance_to_platform_symbol("EURUSD=X", "forex") == "EUR/USD"

    def test_reverse_equity_index(self):
        assert yfinance_to_platform_symbol("^GSPC", "equity") == "^GSPC"


class TestYfinanceFetch:
    """Test _fetch_ohlcv_sync with mocked yfinance."""

    def test_fetch_valid_equity(self):
        dates = pd.date_range("2025-01-01", periods=10, freq="1d", tz="UTC")
        mock_df = pd.DataFrame(
            {
                "Open": range(10),
                "High": range(1, 11),
                "Low": range(10),
                "Close": range(10),
                "Volume": [1000] * 10,
            },
            index=dates,
        )
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_df
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = _fetch_ohlcv_sync("AAPL/USD", "1d", 30, "equity")
        assert len(result) == 10
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]
        assert result.index.name == "timestamp"

    def test_fetch_returns_empty_for_invalid_symbol(self):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = _fetch_ohlcv_sync("INVALID/SYM", "1d", 30, "equity")
        assert result.empty

    def test_fetch_forex_symbol_normalization(self):
        dates = pd.date_range("2025-01-01", periods=5, freq="1d", tz="UTC")
        mock_df = pd.DataFrame(
            {
                "Open": [1.1] * 5,
                "High": [1.2] * 5,
                "Low": [1.0] * 5,
                "Close": [1.15] * 5,
                "Volume": [0] * 5,
            },
            index=dates,
        )
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_df
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = _fetch_ohlcv_sync("EUR/USD", "1d", 30, "forex")
        assert not result.empty
        # Verify Ticker was called with normalized symbol
        mock_yf.Ticker.assert_called_with("EURUSD=X")


# ──────────────────────────────────────────────
# 6. Data Validation: OHLCV violations, gaps, outliers
# ──────────────────────────────────────────────


class TestOHLCIntegrity:
    """Test OHLC constraint checking."""

    def test_valid_ohlcv_no_violations(self):
        df = _make_ohlcv(periods=50)
        violations = check_ohlc_integrity(df)
        assert violations == []

    def test_high_below_close_detected(self):
        df = _make_ohlcv(periods=10)
        # Set high below close for one row
        df.iloc[3, df.columns.get_loc("high")] = df.iloc[3]["close"] - 10
        violations = check_ohlc_integrity(df)
        assert len(violations) >= 1
        assert "High" in violations[0]["reason"]

    def test_low_above_open_detected(self):
        df = _make_ohlcv(periods=10)
        # Set low above open for one row
        df.iloc[5, df.columns.get_loc("low")] = df.iloc[5]["open"] + 10
        violations = check_ohlc_integrity(df)
        assert len(violations) >= 1
        assert "Low" in violations[0]["reason"]

    def test_negative_volume_not_caught_by_ohlc_check(self):
        """check_ohlc_integrity only checks O/H/L/C, not volume sign."""
        df = _make_ohlcv(periods=5)
        df.iloc[2, df.columns.get_loc("volume")] = -100
        violations = check_ohlc_integrity(df)
        # Negative volume is not an OHLC violation
        assert violations == []

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        violations = check_ohlc_integrity(df)
        assert violations == []


class TestGapDetection:
    """Test gap detection in time series data."""

    def test_no_gaps_in_continuous_data(self):
        df = _make_ohlcv(start="2025-01-01", periods=24, freq="1h")
        gaps = detect_gaps(df, "1h")
        assert gaps == []

    def test_detects_gap_in_hourly_data(self):
        # Create data with a 5-hour gap
        dates1 = pd.date_range("2025-01-01", periods=10, freq="1h", tz="UTC")
        dates2 = pd.date_range("2025-01-01 15:00", periods=10, freq="1h", tz="UTC")
        all_dates = dates1.append(dates2)
        df = pd.DataFrame(
            {
                "open": range(20),
                "high": range(1, 21),
                "low": range(20),
                "close": range(20),
                "volume": [100] * 20,
            },
            index=all_dates,
        )
        gaps = detect_gaps(df, "1h")
        assert len(gaps) >= 1
        assert gaps[0]["missing_candles"] > 0

    def test_empty_dataframe_no_gaps(self):
        gaps = detect_gaps(pd.DataFrame(), "1h")
        assert gaps == []

    def test_single_row_no_gaps(self):
        df = _make_ohlcv(periods=1)
        gaps = detect_gaps(df, "1h")
        assert gaps == []


class TestOutlierDetection:
    def test_detects_price_spike(self):
        df = _make_ohlcv(periods=20, base_price=100)
        # Inject a 50% spike
        df.iloc[10, df.columns.get_loc("close")] = df.iloc[9]["close"] * 1.6
        outliers = detect_outliers(df, price_spike_pct=0.20)
        spike_outliers = [o for o in outliers if "spike" in o["reason"].lower()]
        assert len(spike_outliers) >= 1

    def test_detects_zero_volume(self):
        df = _make_ohlcv(periods=10)
        # detect_outliers skips the first zero-volume entry (may be partial candle)
        # so we need at least 2 zero-volume rows to get a detection
        df.iloc[3, df.columns.get_loc("volume")] = 0
        df.iloc[5, df.columns.get_loc("volume")] = 0
        outliers = detect_outliers(df)
        zero_vol = [o for o in outliers if "Zero volume" in o["reason"]]
        assert len(zero_vol) >= 1

    def test_no_outliers_in_clean_data(self):
        # Use very stable prices to avoid false positives
        dates = pd.date_range("2025-01-01", periods=20, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "open": [100.0] * 20,
                "high": [101.0] * 20,
                "low": [99.0] * 20,
                "close": [100.0] * 20,
                "volume": [1000.0] * 20,
            },
            index=dates,
        )
        outliers = detect_outliers(df)
        assert outliers == []


class TestAuditNans:
    def test_detects_nan_columns(self):
        df = _make_ohlcv(periods=10)
        df.iloc[3, df.columns.get_loc("volume")] = np.nan
        df.iloc[7, df.columns.get_loc("close")] = np.nan
        result = audit_nans(df)
        assert "volume" in result
        assert "close" in result
        assert result["volume"] == 1
        assert result["close"] == 1

    def test_no_nans_returns_empty(self):
        df = _make_ohlcv(periods=10)
        result = audit_nans(df)
        assert result == {}


class TestStaleDataDetection:
    def test_recent_data_not_stale(self):
        df = _make_ohlcv(
            start=(datetime.now(timezone.utc) - timedelta(hours=10)).strftime(
                "%Y-%m-%d %H:%M",
            ),
            periods=10,
            freq="1h",
        )
        is_stale, hours = detect_stale_data(df, max_stale_hours=24.0)
        assert not is_stale
        assert hours < 24.0

    def test_old_data_is_stale(self):
        df = _make_ohlcv(start="2020-01-01", periods=10, freq="1h")
        is_stale, hours = detect_stale_data(df, max_stale_hours=2.0)
        assert is_stale
        assert hours > 1000

    def test_empty_df_is_stale(self):
        is_stale, hours = detect_stale_data(pd.DataFrame())
        assert is_stale
        assert hours == float("inf")


# ──────────────────────────────────────────────
# 7. Incremental Fetch Edge Cases
# ──────────────────────────────────────────────


class TestIncrementalEdgeCases:
    """Edge cases for incremental data fetch."""

    def test_get_last_timestamp_corrupt_parquet(self, tmp_path):
        """Corrupt parquet should return None for last timestamp."""
        path = tmp_path / "kraken_SOL_USDT_1h.parquet"
        path.write_bytes(b"\x00JUNK\xff\xfe\x01")
        result = get_last_timestamp("SOL/USDT", "1h", "kraken", directory=tmp_path)
        assert result is None

    def test_get_last_timestamp_empty_parquet(self, tmp_path):
        """Empty but valid parquet should return None."""
        empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        empty_df.index.name = "timestamp"
        path = tmp_path / "kraken_SOL_USDT_1h.parquet"
        empty_df.to_parquet(path)

        result = get_last_timestamp("SOL/USDT", "1h", "kraken", directory=tmp_path)
        assert result is None

    def test_save_then_load_roundtrip(self, tmp_path):
        """Data should survive a save/load roundtrip without loss."""
        df = _make_ohlcv(periods=50)
        save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)
        loaded = load_ohlcv("BTC/USDT", "1h", "kraken", directory=tmp_path)
        assert len(loaded) == 50
        # Parquet may drop index freq metadata, so compare values only
        pd.testing.assert_frame_equal(df, loaded, check_freq=False)

    def test_incremental_save_merges_data(self, tmp_path):
        """Saving new data to an existing file should merge and deduplicate."""
        df1 = _make_ohlcv(start="2025-01-01", periods=10, seed=1)
        df2 = _make_ohlcv(start="2025-01-01 08:00", periods=10, seed=2)

        save_ohlcv(df1, "BTC/USDT", "1h", "kraken", directory=tmp_path)
        save_ohlcv(df2, "BTC/USDT", "1h", "kraken", directory=tmp_path)

        loaded = load_ohlcv("BTC/USDT", "1h", "kraken", directory=tmp_path)
        # Overlapping timestamps should be deduplicated (keep last)
        combined_unique = pd.concat([df1, df2]).index.unique()
        assert len(loaded) == len(combined_unique)
        assert not loaded.index.duplicated().any()

    def test_load_with_date_filter(self, tmp_path):
        """load_ohlcv start/end filtering should work correctly."""
        df = _make_ohlcv(start="2025-01-01", periods=48, freq="1h")
        save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)

        filtered = load_ohlcv(
            "BTC/USDT",
            "1h",
            "kraken",
            directory=tmp_path,
            start="2025-01-01 12:00",
            end="2025-01-01 23:00",
        )
        assert len(filtered) <= 12
        assert len(filtered) > 0

    def test_load_nonexistent_returns_empty(self, tmp_path):
        """Loading from a nonexistent file should return empty DataFrame."""
        result = load_ohlcv("NOPE/NOPE", "1d", "kraken", directory=tmp_path)
        assert result.empty


# ──────────────────────────────────────────────
# 8. fetch_ohlcv_multi Routing
# ──────────────────────────────────────────────


class TestFetchOhlcvMultiRouting:
    """Verify correct routing by asset class."""

    @patch("common.data_pipeline.pipeline.fetch_ohlcv")
    def test_crypto_routes_to_ccxt(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        fetch_ohlcv_multi("BTC/USDT", "1h", asset_class="crypto")
        mock_fetch.assert_called_once()

    @patch("common.data_pipeline.yfinance_adapter._fetch_ohlcv_sync")
    def test_equity_routes_to_yfinance(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        fetch_ohlcv_multi("AAPL/USD", "1d", asset_class="equity")
        mock_fetch.assert_called_once()

    @patch("common.data_pipeline.yfinance_adapter._fetch_ohlcv_sync")
    def test_forex_routes_to_yfinance(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        fetch_ohlcv_multi("EUR/USD", "1h", asset_class="forex")
        mock_fetch.assert_called_once()


# ──────────────────────────────────────────────
# 9. Full validate_data Integration
# ──────────────────────────────────────────────


class TestValidateDataIntegration:
    """End-to-end validation on saved parquet files."""

    def test_validate_clean_data_passes(self, tmp_path):
        """Clean, recent data should pass validation."""
        df = _make_ohlcv(
            start=(datetime.now(timezone.utc) - timedelta(hours=50)).strftime(
                "%Y-%m-%d %H:%M",
            ),
            periods=48,
            freq="1h",
        )
        save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)
        report = validate_data(
            "BTC/USDT", "1h", "kraken",
            directory=tmp_path, max_stale_hours=100.0,
        )
        assert report.rows == 48
        assert report.ohlc_violations == []
        assert report.passed is True

    def test_validate_stale_data_fails(self, tmp_path):
        """Old data should be flagged as stale."""
        df = _make_ohlcv(start="2020-01-01", periods=10)
        save_ohlcv(df, "BTC/USDT", "1h", "kraken", directory=tmp_path)
        report = validate_data(
            "BTC/USDT", "1h", "kraken",
            directory=tmp_path, max_stale_hours=1.0,
        )
        assert report.is_stale is True
        assert report.passed is False
        assert any("stale" in s.lower() for s in report.issues_summary)

    def test_validate_missing_file(self, tmp_path):
        """Missing data file should produce a failing report."""
        report = validate_data("NO/DATA", "1h", "kraken", directory=tmp_path)
        assert report.passed is False
        assert report.rows == 0
