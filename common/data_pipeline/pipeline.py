"""
Crypto-Investor Shared Data Pipeline
=====================================
Unified data acquisition, storage, and retrieval layer that feeds
all framework tiers: VectorBT (research), Freqtrade (crypto), NautilusTrader (multi-asset).

Data is stored in Parquet format for fast columnar reads across all frameworks.
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

import ccxt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

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

def get_exchange(exchange_id: str = "binance", sandbox: bool = True) -> ccxt.Exchange:
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
    exchange_id: str = "binance",
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

def _parquet_path(symbol: str, timeframe: str, exchange_id: str, directory: Path) -> Path:
    """Generate a standardized Parquet file path."""
    safe_symbol = symbol.replace("/", "_")
    return directory / f"{exchange_id}_{safe_symbol}_{timeframe}.parquet"


def save_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    exchange_id: str = "binance",
    directory: Optional[Path] = None,
) -> Path:
    """Save OHLCV DataFrame to Parquet, merging with existing data."""
    directory = directory or PROCESSED_DIR
    path = _parquet_path(symbol, timeframe, exchange_id, directory)

    if path.exists():
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df])
        df = df[~df.index.duplicated(keep="last")].sort_index()

    df.to_parquet(path, engine="pyarrow", compression="snappy")
    logger.info(f"Saved {len(df)} rows to {path}")
    return path


def load_ohlcv(
    symbol: str,
    timeframe: str,
    exchange_id: str = "binance",
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

def download_watchlist(
    symbols: Optional[list] = None,
    timeframes: Optional[list] = None,
    exchange_id: str = "binance",
    since_days: int = 365,
) -> dict:
    """Download OHLCV data for multiple symbols and timeframes."""
    if symbols is None:
        symbols = [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
            "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
        ]
    if timeframes is None:
        timeframes = ["1h", "4h", "1d"]

    results = {}
    total = len(symbols) * len(timeframes)
    done = 0

    for symbol in symbols:
        for tf in timeframes:
            done += 1
            logger.info(f"[{done}/{total}] Downloading {symbol} {tf}...")
            try:
                df = fetch_ohlcv(symbol, tf, since_days, exchange_id)
                if not df.empty:
                    path = save_ohlcv(df, symbol, tf, exchange_id)
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

    parser = argparse.ArgumentParser(description="Crypto-Investor Data Pipeline")
    sub = parser.add_subparsers(dest="command")

    # Download command
    dl = sub.add_parser("download", help="Download OHLCV data")
    dl.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    dl.add_argument("--timeframes", nargs="+", default=["1h", "4h", "1d"])
    dl.add_argument("--exchange", default="binance")
    dl.add_argument("--days", type=int, default=365)

    # List command
    sub.add_parser("list", help="List available data files")

    # Info command
    info = sub.add_parser("info", help="Show info about a data file")
    info.add_argument("symbol")
    info.add_argument("--timeframe", default="1h")
    info.add_argument("--exchange", default="binance")

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
