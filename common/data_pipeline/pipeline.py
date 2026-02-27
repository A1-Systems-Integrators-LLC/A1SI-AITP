"""
A1SI-AITP Shared Data Pipeline
=====================================
Unified data acquisition, storage, and retrieval layer that feeds
all framework tiers: VectorBT (research), Freqtrade (crypto), NautilusTrader (multi-asset).

Data is stored in Parquet format for fast columnar reads across all frameworks.
"""

import fcntl
import os
import sys
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

import ccxt
import numpy as np
import pandas as pd

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LOGS_DIR = BASE_DIR / "logs"

for d in [RAW_DIR, PROCESSED_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "data_pipeline.log", mode="a"),
    ],
)
logger = logging.getLogger("data_pipeline")


# ──────────────────────────────────────────────
# Exchange Factory
# ──────────────────────────────────────────────

def get_exchange(exchange_id: str = "kraken", sandbox: bool = True) -> ccxt.Exchange:
    """Create a CCXT exchange instance with optional sandbox mode."""
    exchange_class = getattr(ccxt, exchange_id)
    config = {
        "enableRateLimit": True,
        "options": {"defaultType": "spot", "adjustForTimeDifference": True},
    }

    # Load API keys from environment if available
    api_key = os.environ.get(f"{exchange_id.upper()}_API_KEY")
    secret = os.environ.get(f"{exchange_id.upper()}_SECRET")
    if api_key and secret:
        config["apiKey"] = api_key
        config["secret"] = secret

    exchange = exchange_class(config)

    if sandbox and exchange.urls.get("test"):
        exchange.set_sandbox_mode(True)
        logger.info(f"Exchange {exchange_id} initialized in SANDBOX mode")
    else:
        logger.info(f"Exchange {exchange_id} initialized (sandbox={'available' if sandbox else 'off'})")

    return exchange


# ──────────────────────────────────────────────
# OHLCV Data Fetching
# ──────────────────────────────────────────────

def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    since_days: int = 365,
    exchange_id: str = "kraken",
    limit_per_request: int = 1000,
) -> pd.DataFrame:
    """
    Fetch OHLCV candlestick data from an exchange.

    Parameters
    ----------
    symbol : str
        Trading pair (e.g., 'BTC/USDT')
    timeframe : str
        Candle timeframe ('1m', '5m', '15m', '1h', '4h', '1d')
    since_days : int
        How many days of historical data to fetch
    exchange_id : str
        CCXT exchange identifier
    limit_per_request : int
        Max candles per API call

    Returns
    -------
    pd.DataFrame
        OHLCV data with datetime index
    """
    exchange = get_exchange(exchange_id, sandbox=False)
    exchange.load_markets()

    if symbol not in exchange.markets:
        logger.error(f"Symbol {symbol} not found on {exchange_id}")
        return pd.DataFrame()

    # Calculate the starting timestamp
    since = int((datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000)

    # Map timeframes to milliseconds for pagination
    tf_ms = {
        "1m": 60_000, "5m": 300_000, "15m": 900_000,
        "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    }
    candle_ms = tf_ms.get(timeframe, 3_600_000)

    all_candles = []
    fetch_since = since

    logger.info(f"Fetching {symbol} {timeframe} from {exchange_id} (last {since_days} days)...")

    while True:
        try:
            candles = exchange.fetch_ohlcv(
                symbol, timeframe, since=fetch_since, limit=limit_per_request
            )
        except ccxt.RateLimitExceeded:
            logger.warning("Rate limit hit, sleeping 10s...")
            time.sleep(10)
            continue
        except ccxt.NetworkError as e:
            logger.error(f"Network error: {e}")
            time.sleep(5)
            continue
        except ccxt.ExchangeError as e:
            logger.error(f"Exchange error: {e}")
            break

        if not candles:
            break

        all_candles.extend(candles)
        last_ts = candles[-1][0]

        # Move cursor forward
        fetch_since = last_ts + candle_ms

        if fetch_since >= int(datetime.now(timezone.utc).timestamp() * 1000):
            break

        # Respect rate limits
        time.sleep(exchange.rateLimit / 1000)

    if not all_candles:
        logger.warning(f"No data returned for {symbol} {timeframe}")
        return pd.DataFrame()

    df = pd.DataFrame(
        all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    logger.info(f"Fetched {len(df)} candles for {symbol} {timeframe}")
    return df


# ──────────────────────────────────────────────
# Parquet Storage
# ──────────────────────────────────────────────

def _parquet_path(
    symbol: str, timeframe: str, exchange_id: str, directory: Path, source: str = "",
) -> Path:
    """Generate a standardized Parquet file path.

    Parameters
    ----------
    source : str
        Override the source prefix (e.g., "yfinance"). Defaults to exchange_id.
    """
    safe_symbol = symbol.replace("/", "_")
    prefix = source or exchange_id
    return directory / f"{prefix}_{safe_symbol}_{timeframe}.parquet"


def save_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    directory: Optional[Path] = None,
) -> Path:
    """Save OHLCV DataFrame to Parquet, merging with existing data.

    Uses file locking to prevent corruption from concurrent writes.
    """
    directory = directory or PROCESSED_DIR
    path = _parquet_path(symbol, timeframe, exchange_id, directory)
    lock_path = path.with_suffix(".parquet.lock")

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            if path.exists():
                existing = pd.read_parquet(path)
                df = pd.concat([existing, df])
                df = df[~df.index.duplicated(keep="last")].sort_index()

            df.to_parquet(path, engine="pyarrow", compression="snappy")
            logger.info(f"Saved {len(df)} rows to {path}")
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

    return path


def load_ohlcv(
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    directory: Optional[Path] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Load OHLCV data from Parquet with optional date filtering."""
    directory = directory or PROCESSED_DIR
    path = _parquet_path(symbol, timeframe, exchange_id, directory)

    if not path.exists():
        logger.warning(f"No data file found at {path}")
        return pd.DataFrame()

    df = pd.read_parquet(path)

    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index <= pd.Timestamp(end, tz="UTC")]

    logger.info(f"Loaded {len(df)} rows from {path}")
    return df


def list_available_data(directory: Optional[Path] = None) -> pd.DataFrame:
    """List all available Parquet data files with metadata."""
    directory = directory or PROCESSED_DIR
    records = []
    for f in directory.glob("*.parquet"):
        parts = f.stem.split("_")
        if len(parts) >= 4:
            exchange = parts[0]
            symbol = f"{parts[1]}/{parts[2]}"
            timeframe = parts[3]
            df = pd.read_parquet(f)
            records.append({
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "rows": len(df),
                "start": df.index.min() if len(df) > 0 else None,
                "end": df.index.max() if len(df) > 0 else None,
                "file": str(f),
            })
    return pd.DataFrame(records)


# ──────────────────────────────────────────────
# Bulk Download
# ──────────────────────────────────────────────

def fetch_ohlcv_multi(
    symbol: str,
    timeframe: str = "1h",
    since_days: int = 365,
    asset_class: str = "crypto",
    exchange_id: str = "kraken",
) -> pd.DataFrame:
    """Fetch OHLCV data routing to the correct data source by asset class.

    crypto  -> CCXT (existing)
    equity  -> yfinance
    forex   -> yfinance
    """
    if asset_class in ("equity", "forex"):
        from common.data_pipeline.yfinance_adapter import _fetch_ohlcv_sync
        return _fetch_ohlcv_sync(symbol, timeframe, since_days, asset_class)
    return fetch_ohlcv(symbol, timeframe, since_days, exchange_id)


# Default watchlists per asset class
_DEFAULT_WATCHLISTS: dict[str, list[str]] = {
    "crypto": [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
        "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
    ],
    "equity": [
        "AAPL/USD", "MSFT/USD", "GOOGL/USD", "AMZN/USD", "NVDA/USD",
        "SPY/USD", "QQQ/USD", "IWM/USD", "GLD/USD", "TLT/USD",
    ],
    "forex": [
        "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD",
        "NZD/USD", "USD/CAD", "EUR/GBP", "EUR/JPY", "GBP/JPY",
        "AUD/JPY", "EUR/CHF", "EUR/AUD", "GBP/CHF", "NZD/JPY",
    ],
}


def download_watchlist(
    symbols: Optional[list] = None,
    timeframes: Optional[list] = None,
    exchange_id: str = "kraken",
    since_days: int = 365,
    asset_class: str = "crypto",
) -> dict:
    """Download OHLCV data for multiple symbols and timeframes."""
    if symbols is None:
        symbols = _DEFAULT_WATCHLISTS.get(asset_class, _DEFAULT_WATCHLISTS["crypto"])
    if timeframes is None:
        if asset_class in ("equity",):
            timeframes = ["1d"]
        elif asset_class == "forex":
            timeframes = ["1h", "4h", "1d"]
        else:
            timeframes = ["1h", "4h", "1d"]

    source = "yfinance" if asset_class in ("equity", "forex") else exchange_id

    results = {}
    total = len(symbols) * len(timeframes)
    done = 0

    for symbol in symbols:
        for tf in timeframes:
            done += 1
            logger.info(f"[{done}/{total}] Downloading {symbol} {tf} ({asset_class})...")
            try:
                df = fetch_ohlcv_multi(
                    symbol, tf, since_days, asset_class, exchange_id,
                )
                if not df.empty:
                    path = save_ohlcv(df, symbol, tf, source)
                    results[f"{symbol}_{tf}"] = {
                        "rows": len(df),
                        "path": str(path),
                        "status": "ok",
                    }
                else:
                    results[f"{symbol}_{tf}"] = {"status": "empty"}
            except Exception as e:
                logger.error(f"Error downloading {symbol} {tf}: {e}")
                results[f"{symbol}_{tf}"] = {"status": "error", "error": str(e)}

    return results


# ──────────────────────────────────────────────
# Data Quality Monitoring
# ──────────────────────────────────────────────

@dataclass
class DataQualityReport:
    """Result of a data quality validation run."""
    symbol: str
    timeframe: str
    exchange: str
    rows: int
    date_range: tuple[Optional[str], Optional[str]]
    gaps: list[dict]           # [{start, end, missing_candles}]
    nan_columns: dict          # {column: nan_count}
    outliers: list[dict]       # [{timestamp, column, value, reason}]
    ohlc_violations: list[dict]  # [{timestamp, reason}]
    is_stale: bool
    stale_hours: float
    passed: bool
    issues_summary: list[str]


def detect_gaps(
    df: pd.DataFrame,
    timeframe: str,
    max_allowed_gaps: int = 0,
) -> list[dict]:
    """
    Detect missing candles in an OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data with datetime index
    timeframe : str
        Expected candle interval ('1m', '5m', '15m', '1h', '4h', '1d')
    max_allowed_gaps : int
        Number of consecutive missing candles before flagging

    Returns
    -------
    list of dicts with gap details: {start, end, missing_candles}
    """
    if df.empty or len(df) < 2:
        return []

    tf_delta = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }
    expected_delta = tf_delta.get(timeframe, timedelta(hours=1))

    gaps = []
    index = df.index
    for i in range(1, len(index)):
        actual_delta = index[i] - index[i - 1]
        if actual_delta > expected_delta * (1 + max_allowed_gaps):
            missing = int(actual_delta / expected_delta) - 1
            gaps.append({
                "start": str(index[i - 1]),
                "end": str(index[i]),
                "missing_candles": missing,
            })

    return gaps


_STALE_THRESHOLDS: dict[str, float] = {
    "crypto": 2.0,
    "equity": 18.0,  # Overnight gap
    "forex": 4.0,
}


def detect_stale_data(
    df: pd.DataFrame,
    max_stale_hours: float = 2.0,
    asset_class: str = "crypto",
) -> tuple[bool, float]:
    """
    Check if data hasn't been updated recently.

    Returns (is_stale, hours_since_last_update).
    Uses per-asset-class thresholds when max_stale_hours is the default.
    """
    if max_stale_hours == 2.0:
        max_stale_hours = _STALE_THRESHOLDS.get(asset_class, 2.0)
    if df.empty:
        return True, float("inf")

    last_ts = df.index.max()
    if last_ts.tzinfo is None:
        last_ts = last_ts.tz_localize("UTC")

    now = datetime.now(timezone.utc)
    hours_since = (now - last_ts).total_seconds() / 3600

    return hours_since > max_stale_hours, round(hours_since, 2)


def audit_nans(df: pd.DataFrame) -> dict[str, int]:
    """Count NaN values per column."""
    nan_counts = df.isna().sum()
    return {col: int(count) for col, count in nan_counts.items() if count > 0}


def detect_outliers(
    df: pd.DataFrame,
    price_spike_pct: float = 0.20,
) -> list[dict]:
    """
    Detect price outliers: single-candle spikes > threshold, zero volumes.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data
    price_spike_pct : float
        Maximum allowed single-candle price change (default 20%)
    """
    outliers = []

    if df.empty or len(df) < 2:
        return outliers

    # Price spikes
    returns = df["close"].pct_change().abs()
    spikes = returns[returns > price_spike_pct]
    for ts, val in spikes.items():
        outliers.append({
            "timestamp": str(ts),
            "column": "close",
            "value": round(float(df.loc[ts, "close"]), 8),
            "reason": f"Price spike: {val:.2%} change in single candle",
        })

    # Zero volume (excluding first row which may be partial)
    zero_vol = df[df["volume"] == 0]
    for ts in zero_vol.index[1:]:  # skip first row
        outliers.append({
            "timestamp": str(ts),
            "column": "volume",
            "value": 0.0,
            "reason": "Zero volume candle",
        })

    return outliers


def check_ohlc_integrity(df: pd.DataFrame) -> list[dict]:
    """
    Verify OHLC constraints: high >= max(open, close), low <= min(open, close).
    """
    violations = []
    if df.empty:
        return violations

    high_violation = df[df["high"] < df[["open", "close"]].max(axis=1)]
    for ts in high_violation.index:
        violations.append({
            "timestamp": str(ts),
            "reason": f"High ({df.loc[ts, 'high']}) < max(Open, Close)",
        })

    low_violation = df[df["low"] > df[["open", "close"]].min(axis=1)]
    for ts in low_violation.index:
        violations.append({
            "timestamp": str(ts),
            "reason": f"Low ({df.loc[ts, 'low']}) > min(Open, Close)",
        })

    return violations


def validate_data(
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    directory: Optional[Path] = None,
    max_stale_hours: float = 2.0,
    price_spike_pct: float = 0.20,
) -> DataQualityReport:
    """
    Run all data quality checks on a Parquet file and return a report.

    Parameters
    ----------
    symbol : str
        Trading pair (e.g., 'BTC/USDT')
    timeframe : str
        Candle timeframe
    exchange_id : str
        Exchange identifier
    directory : Path, optional
        Data directory (defaults to PROCESSED_DIR)
    max_stale_hours : float
        Hours after which data is considered stale
    price_spike_pct : float
        Single-candle price change threshold for outlier detection

    Returns
    -------
    DataQualityReport with all check results
    """
    df = load_ohlcv(symbol, timeframe, exchange_id, directory)

    if df.empty:
        return DataQualityReport(
            symbol=symbol, timeframe=timeframe, exchange=exchange_id,
            rows=0, date_range=(None, None),
            gaps=[], nan_columns={}, outliers=[], ohlc_violations=[],
            is_stale=True, stale_hours=float("inf"),
            passed=False, issues_summary=["No data found"],
        )

    gaps = detect_gaps(df, timeframe)
    is_stale, stale_hours = detect_stale_data(df, max_stale_hours)
    nan_cols = audit_nans(df)
    outlier_list = detect_outliers(df, price_spike_pct)
    ohlc_violations = check_ohlc_integrity(df)

    issues = []
    if gaps:
        total_missing = sum(g["missing_candles"] for g in gaps)
        issues.append(f"{len(gaps)} gaps found ({total_missing} missing candles)")
    if is_stale:
        issues.append(f"Data is stale ({stale_hours:.1f}h since last update)")
    if nan_cols:
        issues.append(f"NaN values in columns: {list(nan_cols.keys())}")
    if outlier_list:
        issues.append(f"{len(outlier_list)} outliers detected")
    if ohlc_violations:
        issues.append(f"{len(ohlc_violations)} OHLC integrity violations")

    date_range = (str(df.index.min()), str(df.index.max()))

    return DataQualityReport(
        symbol=symbol, timeframe=timeframe, exchange=exchange_id,
        rows=len(df), date_range=date_range,
        gaps=gaps, nan_columns=nan_cols, outliers=outlier_list,
        ohlc_violations=ohlc_violations,
        is_stale=is_stale, stale_hours=stale_hours,
        passed=len(issues) == 0, issues_summary=issues,
    )


def validate_all_data(
    directory: Optional[Path] = None,
    max_stale_hours: float = 26.0,
) -> list[DataQualityReport]:
    """
    Run quality checks on all available Parquet files.

    Uses 26h stale threshold by default (allows for weekday gaps in daily data).
    """
    available = list_available_data(directory)
    reports = []

    for _, row in available.iterrows():
        report = validate_data(
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            exchange_id=row["exchange"],
            directory=directory,
            max_stale_hours=max_stale_hours,
        )
        reports.append(report)
        status = "PASS" if report.passed else f"FAIL ({'; '.join(report.issues_summary)})"
        logger.info(f"Quality check {row['symbol']} {row['timeframe']}: {status}")

    passed = sum(1 for r in reports if r.passed)
    logger.info(f"Data quality: {passed}/{len(reports)} files passed")
    return reports


# ──────────────────────────────────────────────
# Format Converters (for framework interop)
# ──────────────────────────────────────────────

def to_freqtrade_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert standard OHLCV to Freqtrade-compatible format."""
    ft_df = df.copy()
    ft_df.index.name = "date"
    ft_df.columns = ["open", "high", "low", "close", "volume"]
    return ft_df


def to_vectorbt_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert standard OHLCV to VectorBT-compatible format (just needs datetime index)."""
    return df.copy()


def to_hftbacktest_ticks(df: pd.DataFrame, timeframe: str = "1h") -> np.ndarray:
    """Convert OHLCV DataFrame to synthetic tick numpy arrays for hftbacktest.

    Generates 4 ticks per bar (O/H/L/C) with interpolated nanosecond timestamps.
    Returns array of shape (N*4, 4): [timestamp_ns, price, volume, side].
    Side: +1 = buy, -1 = sell. This is a development approximation.
    """
    tf_ns_map = {
        "1m": 60_000_000_000,
        "5m": 300_000_000_000,
        "15m": 900_000_000_000,
        "1h": 3_600_000_000_000,
        "4h": 14_400_000_000_000,
        "1d": 86_400_000_000_000,
    }
    interval_ns = tf_ns_map.get(timeframe, 3_600_000_000_000)
    quarter = interval_ns // 4

    ticks = []
    for ts, row in df.iterrows():
        ts_ns = int(ts.value)
        vol = float(row["volume"]) / 4

        ticks.append([ts_ns, float(row["open"]), vol, 1])
        ticks.append([ts_ns + quarter, float(row["high"]), vol, 1])
        ticks.append([ts_ns + 2 * quarter, float(row["low"]), vol, -1])
        side = 1 if float(row["close"]) >= float(row["open"]) else -1
        ticks.append([ts_ns + 3 * quarter, float(row["close"]), vol, side])

    return np.array(ticks, dtype=np.float64)


def to_nautilus_bars(df: pd.DataFrame, symbol: str) -> list:
    """Convert OHLCV DataFrame to a list of dicts for NautilusTrader bar ingestion."""
    bars = []
    for ts, row in df.iterrows():
        bars.append({
            "symbol": symbol,
            "timestamp": ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })
    return bars


# ──────────────────────────────────────────────
# Technical Indicators (shared across frameworks)
# ──────────────────────────────────────────────

def add_indicators(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    """Add common technical indicators to an OHLCV DataFrame."""
    if periods is None:
        periods = [7, 14, 21, 50, 100, 200]

    result = df.copy()

    for p in periods:
        # Simple Moving Average
        result[f"sma_{p}"] = result["close"].rolling(window=p).mean()
        # Exponential Moving Average
        result[f"ema_{p}"] = result["close"].ewm(span=p, adjust=False).mean()

    # RSI (14-period default)
    delta = result["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    result["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = result["close"].ewm(span=12, adjust=False).mean()
    ema26 = result["close"].ewm(span=26, adjust=False).mean()
    result["macd"] = ema12 - ema26
    result["macd_signal"] = result["macd"].ewm(span=9, adjust=False).mean()
    result["macd_hist"] = result["macd"] - result["macd_signal"]

    # Bollinger Bands
    result["bb_mid"] = result["close"].rolling(window=20).mean()
    bb_std = result["close"].rolling(window=20).std()
    result["bb_upper"] = result["bb_mid"] + (bb_std * 2)
    result["bb_lower"] = result["bb_mid"] - (bb_std * 2)
    result["bb_width"] = (result["bb_upper"] - result["bb_lower"]) / result["bb_mid"]

    # ATR (Average True Range)
    high_low = result["high"] - result["low"]
    high_close = (result["high"] - result["close"].shift()).abs()
    low_close = (result["low"] - result["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    result["atr_14"] = true_range.rolling(window=14).mean()

    # Volume indicators
    result["volume_sma_20"] = result["volume"].rolling(window=20).mean()
    result["volume_ratio"] = result["volume"] / result["volume_sma_20"]

    # Returns
    result["returns"] = result["close"].pct_change()
    result["log_returns"] = np.log(result["close"] / result["close"].shift(1))

    return result


# ──────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="A1SI-AITP Data Pipeline")
    sub = parser.add_subparsers(dest="command")

    # Download command
    dl = sub.add_parser("download", help="Download OHLCV data")
    dl.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    dl.add_argument("--timeframes", nargs="+", default=["1h", "4h", "1d"])
    dl.add_argument("--exchange", default="kraken")
    dl.add_argument("--days", type=int, default=365)

    # List command
    sub.add_parser("list", help="List available data files")

    # Info command
    info = sub.add_parser("info", help="Show info about a data file")
    info.add_argument("symbol")
    info.add_argument("--timeframe", default="1h")
    info.add_argument("--exchange", default="kraken")

    args = parser.parse_args()

    if args.command == "download":
        results = download_watchlist(args.symbols, args.timeframes, args.exchange, args.days)
        for k, v in results.items():
            print(f"  {k}: {v['status']} ({v.get('rows', 'N/A')} rows)")

    elif args.command == "list":
        available = list_available_data()
        if available.empty:
            print("No data files found. Run 'download' first.")
        else:
            print(available.to_string(index=False))

    elif args.command == "info":
        df = load_ohlcv(args.symbol, args.timeframe, args.exchange)
        if df.empty:
            print(f"No data found for {args.symbol} {args.timeframe}")
        else:
            print(f"Symbol:    {args.symbol}")
            print(f"Timeframe: {args.timeframe}")
            print(f"Exchange:  {args.exchange}")
            print(f"Rows:      {len(df)}")
            print(f"Start:     {df.index.min()}")
            print(f"End:       {df.index.max()}")
            print(f"\n{df.describe()}")

    else:
        parser.print_help()
