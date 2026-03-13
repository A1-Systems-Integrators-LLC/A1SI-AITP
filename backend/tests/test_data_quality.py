"""Tests for data pipeline quality monitoring — Sprint 1, Item 1.4
================================================================
Covers: gap detection, stale data, NaN audit, outlier detection,
OHLC integrity checks, validate_data().
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.data_pipeline.pipeline import (
    DataQualityReport,
    audit_nans,
    check_ohlc_integrity,
    detect_gaps,
    detect_outliers,
    detect_stale_data,
    save_ohlcv,
    validate_data,
)


def _make_ohlcv(n=100, timeframe="1h", start=None, freq=None):
    """Generate a clean OHLCV DataFrame for testing."""
    if freq is None:
        freq_map = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
        freq = freq_map.get(timeframe, "1h")

    if start is None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    index = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    np.random.seed(42)
    close = 50000 + np.cumsum(np.random.randn(n) * 100)
    high = close + np.abs(np.random.randn(n) * 50)
    low = close - np.abs(np.random.randn(n) * 50)
    open_ = close + np.random.randn(n) * 30
    volume = np.abs(np.random.randn(n) * 1000) + 100

    # Ensure OHLC integrity: high >= max(open, close), low <= min(open, close)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


# ── Gap Detection ────────────────────────────────────────────────


class TestDetectGaps:
    def test_no_gaps_in_clean_data(self):
        df = _make_ohlcv(100, "1h")
        gaps = detect_gaps(df, "1h")
        assert len(gaps) == 0

    def test_detects_single_gap(self):
        df = _make_ohlcv(100, "1h")
        # Remove rows 50-52 to create a 3-candle gap
        df = df.drop(df.index[50:53])
        gaps = detect_gaps(df, "1h")
        assert len(gaps) == 1
        assert gaps[0]["missing_candles"] == 3

    def test_detects_multiple_gaps(self):
        df = _make_ohlcv(100, "1h")
        df = df.drop(df.index[20:22])  # 2-candle gap
        df = df.drop(df.index[60:65])  # 5-candle gap
        gaps = detect_gaps(df, "1h")
        assert len(gaps) == 2

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        gaps = detect_gaps(df, "1h")
        assert len(gaps) == 0

    def test_different_timeframes(self):
        df = _make_ohlcv(50, "4h")
        df = df.drop(df.index[25:27])
        gaps = detect_gaps(df, "4h")
        assert len(gaps) == 1
        assert gaps[0]["missing_candles"] == 2


# ── Stale Data Detection ────────────────────────────────────────


class TestDetectStaleData:
    def test_recent_data_not_stale(self):
        now = datetime.now(timezone.utc)
        df = _make_ohlcv(10, "1h", start=now - timedelta(hours=10))
        is_stale, hours = detect_stale_data(df, max_stale_hours=2.0)
        assert is_stale is False

    def test_old_data_is_stale(self):
        old_start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        df = _make_ohlcv(10, "1h", start=old_start)
        is_stale, hours = detect_stale_data(df, max_stale_hours=2.0)
        assert is_stale is True
        assert hours > 100

    def test_empty_is_stale(self):
        df = pd.DataFrame()
        is_stale, hours = detect_stale_data(df)
        assert is_stale is True


# ── NaN Audit ────────────────────────────────────────────────────


class TestAuditNans:
    def test_clean_data_no_nans(self):
        df = _make_ohlcv(50)
        result = audit_nans(df)
        assert len(result) == 0

    def test_detects_nans(self):
        df = _make_ohlcv(50)
        df.loc[df.index[10], "close"] = np.nan
        df.loc[df.index[20], "volume"] = np.nan
        df.loc[df.index[21], "volume"] = np.nan
        result = audit_nans(df)
        assert result["close"] == 1
        assert result["volume"] == 2


# ── Outlier Detection ────────────────────────────────────────────


class TestDetectOutliers:
    def test_clean_data_no_outliers(self):
        df = _make_ohlcv(100)
        outliers = detect_outliers(df, price_spike_pct=0.20)
        assert len(outliers) == 0

    def test_detects_price_spike(self):
        df = _make_ohlcv(100)
        # Inject a 50% spike
        df.iloc[50, df.columns.get_loc("close")] = df.iloc[49]["close"] * 1.5
        outliers = detect_outliers(df, price_spike_pct=0.20)
        spike_outliers = [o for o in outliers if "spike" in o["reason"].lower()]
        assert len(spike_outliers) >= 1

    def test_detects_zero_volume(self):
        df = _make_ohlcv(100)
        df.iloc[30, df.columns.get_loc("volume")] = 0
        df.iloc[40, df.columns.get_loc("volume")] = 0
        outliers = detect_outliers(df)
        zero_vol = [o for o in outliers if "zero volume" in o["reason"].lower()]
        assert len(zero_vol) >= 1  # at least one detected (first row skipped)


# ── OHLC Integrity ───────────────────────────────────────────────


class TestOHLCIntegrity:
    def test_clean_data_no_violations(self):
        df = _make_ohlcv(100)
        violations = check_ohlc_integrity(df)
        assert len(violations) == 0

    def test_detects_high_violation(self):
        df = _make_ohlcv(100)
        # Set high below close
        df.iloc[25, df.columns.get_loc("high")] = df.iloc[25]["close"] - 100
        violations = check_ohlc_integrity(df)
        assert len(violations) >= 1
        assert "High" in violations[0]["reason"]

    def test_detects_low_violation(self):
        df = _make_ohlcv(100)
        # Set low above open
        df.iloc[25, df.columns.get_loc("low")] = df.iloc[25]["open"] + 100
        violations = check_ohlc_integrity(df)
        assert len(violations) >= 1
        assert "Low" in violations[0]["reason"]

    def test_empty_dataframe(self):
        violations = check_ohlc_integrity(pd.DataFrame())
        assert len(violations) == 0


# ── Full Validation ──────────────────────────────────────────────


class TestValidateData:
    def test_validate_missing_file(self, tmp_path):
        report = validate_data("FAKE/PAIR", "1h", "binance", directory=tmp_path)
        assert isinstance(report, DataQualityReport)
        assert report.passed is False
        assert report.rows == 0

    def test_validate_clean_data(self, tmp_path):
        now = datetime.now(timezone.utc)
        df = _make_ohlcv(100, "1h", start=now - timedelta(hours=100))
        save_ohlcv(df, "BTC/USDT", "1h", "binance", directory=tmp_path)

        report = validate_data("BTC/USDT", "1h", "binance", directory=tmp_path, max_stale_hours=200)
        assert report.rows == 100
        assert report.passed is True
        assert len(report.issues_summary) == 0

    def test_validate_data_with_gaps(self, tmp_path):
        now = datetime.now(timezone.utc)
        df = _make_ohlcv(100, "1h", start=now - timedelta(hours=100))
        df = df.drop(df.index[40:45])
        save_ohlcv(df, "BTC/USDT", "1h", "binance", directory=tmp_path)

        report = validate_data("BTC/USDT", "1h", "binance", directory=tmp_path, max_stale_hours=200)
        assert report.passed is False
        assert len(report.gaps) > 0
        assert any("gaps" in issue.lower() for issue in report.issues_summary)
