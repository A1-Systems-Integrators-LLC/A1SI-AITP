"""Tests for incremental data download functionality."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.data_pipeline.pipeline import (
    download_watchlist,
    fetch_ohlcv,
    fetch_ohlcv_multi,
    get_last_timestamp,
    save_ohlcv,
)


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path


@pytest.fixture
def sample_df():
    """Create a sample OHLCV DataFrame."""
    dates = pd.date_range("2025-01-01", periods=10, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": range(10),
            "high": range(1, 11),
            "low": range(10),
            "close": range(10),
            "volume": [100] * 10,
        },
        index=dates,
    )


class TestGetLastTimestamp:
    def test_returns_last_timestamp_from_parquet(self, tmp_data_dir, sample_df):
        save_ohlcv(sample_df, "BTC/USDT", "1h", "kraken", directory=tmp_data_dir)
        result = get_last_timestamp("BTC/USDT", "1h", "kraken", directory=tmp_data_dir)
        assert result is not None
        assert isinstance(result, datetime)
        assert result == sample_df.index.max().to_pydatetime()

    def test_returns_none_for_missing_file(self, tmp_data_dir):
        result = get_last_timestamp("FAKE/PAIR", "1h", "kraken", directory=tmp_data_dir)
        assert result is None

    def test_returns_none_for_empty_dataframe(self, tmp_data_dir):
        empty_df = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
        )
        empty_df.index.name = "timestamp"
        # Write an empty parquet
        path = tmp_data_dir / "kraken_BTC_USDT_1h.parquet"
        empty_df.to_parquet(path)
        result = get_last_timestamp("BTC/USDT", "1h", "kraken", directory=tmp_data_dir)
        assert result is None


class TestFetchOhlcvSinceTimestamp:
    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_uses_since_timestamp_when_provided(self, mock_get_exchange):
        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 1000
        mock_exchange.fetch_ohlcv.return_value = []
        mock_get_exchange.return_value = mock_exchange

        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        fetch_ohlcv("BTC/USDT", "1h", since_timestamp=ts)

        # The fetch_ohlcv call should use the since_timestamp
        call_args = mock_exchange.fetch_ohlcv.call_args
        since_ms = call_args[1].get("since") or call_args[0][2]
        expected_ms = int(ts.timestamp() * 1000)
        assert since_ms == expected_ms

    @patch("common.data_pipeline.pipeline.get_exchange")
    def test_uses_since_days_when_no_timestamp(self, mock_get_exchange):
        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.rateLimit = 1000
        mock_exchange.fetch_ohlcv.return_value = []
        mock_get_exchange.return_value = mock_exchange

        fetch_ohlcv("BTC/USDT", "1h", since_days=30)

        call_args = mock_exchange.fetch_ohlcv.call_args
        since_ms = call_args[1].get("since") or call_args[0][2]
        # Should be roughly 30 days ago
        expected_min = int((datetime.now(timezone.utc) - timedelta(days=31)).timestamp() * 1000)
        expected_max = int((datetime.now(timezone.utc) - timedelta(days=29)).timestamp() * 1000)
        assert expected_min <= since_ms <= expected_max


class TestFetchOhlcvMultiSinceTimestamp:
    @patch("common.data_pipeline.pipeline.fetch_ohlcv")
    def test_passes_since_timestamp_to_crypto(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        fetch_ohlcv_multi("BTC/USDT", "1h", asset_class="crypto", since_timestamp=ts)
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[1]["since_timestamp"] == ts

    @patch("common.data_pipeline.yfinance_adapter._fetch_ohlcv_sync")
    def test_passes_since_timestamp_to_yfinance(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        fetch_ohlcv_multi("AAPL/USD", "1d", asset_class="equity", since_timestamp=ts)
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[1]["since_timestamp"] == ts


class TestDownloadWatchlistIncremental:
    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp")
    def test_passes_last_timestamp_when_data_exists(self, mock_last_ts, mock_fetch):
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        mock_last_ts.return_value = ts
        mock_fetch.return_value = pd.DataFrame()

        download_watchlist(
            symbols=["BTC/USDT"],
            timeframes=["1h"],
            exchange_id="kraken",
        )

        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[1]["since_timestamp"] == ts

    @patch("common.data_pipeline.pipeline.fetch_ohlcv_multi")
    @patch("common.data_pipeline.pipeline.get_last_timestamp")
    def test_passes_none_when_no_existing_data(self, mock_last_ts, mock_fetch):
        mock_last_ts.return_value = None
        mock_fetch.return_value = pd.DataFrame()

        download_watchlist(
            symbols=["BTC/USDT"],
            timeframes=["1h"],
            exchange_id="kraken",
        )

        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[1]["since_timestamp"] is None
