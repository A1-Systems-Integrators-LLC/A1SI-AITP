"""yfinance Data Adapter
=====================
Fetches equities and forex OHLCV data via Yahoo Finance.
Normalizes symbols between platform format and yfinance format.
Output: standard OHLCV DataFrame compatible with the shared Parquet pipeline.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

logger = logging.getLogger("data_pipeline.yfinance")

# ──────────────────────────────────────────────
# Symbol Normalization
# ──────────────────────────────────────────────

# Platform uses BASE/QUOTE format everywhere.
# yfinance uses different conventions:
#   Equity: "AAPL" (no /USD)
#   Index:  "^GSPC"
#   Forex:  "EURUSD=X"

_INDEX_SYMBOLS = {"^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX"}


def normalize_symbol(symbol: str, asset_class: str) -> str:
    """Convert platform symbol to yfinance symbol.

    Equity: AAPL/USD -> AAPL, SPY/USD -> SPY, ^GSPC -> ^GSPC
    Forex:  EUR/USD -> EURUSD=X
    """
    if asset_class == "equity":
        if symbol in _INDEX_SYMBOLS:
            return symbol
        if "/" in symbol:
            return symbol.split("/", maxsplit=1)[0]
        return symbol

    if asset_class == "forex":
        if "/" in symbol:
            base, quote = symbol.split("/")
            return f"{base}{quote}=X"
        return symbol

    # Crypto passthrough (shouldn't be called but be safe)
    return symbol


def yfinance_to_platform_symbol(yf_symbol: str, asset_class: str) -> str:
    """Convert yfinance symbol back to platform format.

    Equity: AAPL -> AAPL/USD, ^GSPC -> ^GSPC
    Forex:  EURUSD=X -> EUR/USD
    """
    if asset_class == "equity":
        if yf_symbol in _INDEX_SYMBOLS:
            return yf_symbol
        return f"{yf_symbol}/USD"

    if asset_class == "forex":
        if yf_symbol.endswith("=X"):
            pair = yf_symbol[:-2]  # Remove =X
            if len(pair) == 6:
                return f"{pair[:3]}/{pair[3:]}"
        return yf_symbol

    return yf_symbol


# ──────────────────────────────────────────────
# Timeframe Mapping
# ──────────────────────────────────────────────

_TF_TO_YF_INTERVAL = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",  # yfinance doesn't have 4h; fetch 1h and resample
    "1d": "1d",
}

_TF_TO_YF_PERIOD = {
    "1m": "7d",    # yfinance limit: 7 days for 1m
    "5m": "60d",   # 60 days for 5m
    "15m": "60d",
    "1h": "730d",  # 2 years for 1h
    "4h": "730d",
    "1d": "max",
}

# Max days yfinance supports for intraday
_INTRADAY_MAX_DAYS = {
    "1m": 7,
    "5m": 60,
    "15m": 60,
    "1h": 730,
    "4h": 730,
    "1d": 9999,
}


def _get_yf_interval(timeframe: str) -> str:
    return _TF_TO_YF_INTERVAL.get(timeframe, "1d")


# ──────────────────────────────────────────────
# Data Fetching
# ──────────────────────────────────────────────


def _fetch_ohlcv_sync(
    symbol: str,
    timeframe: str = "1d",
    since_days: int = 365,
    asset_class: str = "equity",
    since_timestamp: "datetime | None" = None,
) -> pd.DataFrame:
    """Synchronous yfinance OHLCV fetch. Use fetch_ohlcv_yfinance for async.

    If since_timestamp is provided, fetches data from that point instead of since_days.
    """
    import yfinance as yf

    yf_symbol = normalize_symbol(symbol, asset_class)
    yf_interval = _get_yf_interval(timeframe)

    max_days = _INTRADAY_MAX_DAYS.get(timeframe, 9999)
    if since_days > max_days:
        logger.warning(
            f"yfinance {timeframe} limited to {max_days} days, "
            f"requested {since_days} — clamping",
        )
        since_days = max_days

    if since_timestamp is not None:
        start = since_timestamp
        logger.info(
            f"Incremental update {yf_symbol} ({asset_class}) {yf_interval} "
            f"from {since_timestamp}",
        )
    else:
        start = datetime.now(timezone.utc) - timedelta(days=since_days)
        logger.info(
            f"Fetching {yf_symbol} ({asset_class}) {yf_interval} "
            f"from yfinance ({since_days} days)...",
        )
    end = datetime.now(timezone.utc)

    ticker = yf.Ticker(yf_symbol)
    df = ticker.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=yf_interval,
        auto_adjust=True,
    )

    if df.empty:
        logger.warning(f"No data returned for {yf_symbol}")
        return pd.DataFrame()

    # Normalize columns to standard OHLCV
    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    # Keep only OHLCV columns
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = 0.0

    df = df[["open", "high", "low", "close", "volume"]]

    # Ensure UTC timezone
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    df.index.name = "timestamp"

    # Resample to 4h if needed
    if timeframe == "4h" and yf_interval == "1h":
        df = df.resample("4h").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

    # Remove duplicates
    df = df[~df.index.duplicated(keep="last")].sort_index()

    logger.info(f"Fetched {len(df)} candles for {yf_symbol} {timeframe}")
    return df


async def fetch_ohlcv_yfinance(
    symbol: str,
    timeframe: str = "1d",
    since_days: int = 365,
    asset_class: str = "equity",
    since_timestamp: "datetime | None" = None,
) -> pd.DataFrame:
    """Async wrapper around yfinance OHLCV fetch."""
    return await asyncio.to_thread(
        _fetch_ohlcv_sync, symbol, timeframe, since_days, asset_class,
        since_timestamp=since_timestamp,
    )


def _fetch_ticker_sync(symbol: str, asset_class: str) -> dict:
    """Fetch current ticker data for a single symbol."""
    import yfinance as yf

    yf_symbol = normalize_symbol(symbol, asset_class)
    ticker = yf.Ticker(yf_symbol)
    info = ticker.fast_info

    price = getattr(info, "last_price", 0.0) or 0.0
    prev_close = getattr(info, "previous_close", price) or price
    change_24h = ((price - prev_close) / prev_close * 100) if prev_close else 0.0

    return {
        "symbol": symbol,
        "price": price,
        "volume_24h": getattr(info, "last_volume", 0) or 0,
        "change_24h": round(change_24h, 2),
        "high_24h": getattr(info, "day_high", 0.0) or 0.0,
        "low_24h": getattr(info, "day_low", 0.0) or 0.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_ticker_yfinance(symbol: str, asset_class: str) -> dict:
    """Async wrapper for single ticker fetch."""
    return await asyncio.to_thread(_fetch_ticker_sync, symbol, asset_class)


def _fetch_tickers_sync(symbols: list[str], asset_class: str) -> list[dict]:
    """Fetch current ticker data for multiple symbols."""
    results = []
    for symbol in symbols:
        try:
            results.append(_fetch_ticker_sync(symbol, asset_class))
        except Exception as e:
            logger.error(f"Error fetching ticker {symbol}: {e}")
    return results


async def fetch_tickers_yfinance(symbols: list[str], asset_class: str) -> list[dict]:
    """Async wrapper for multiple ticker fetch."""
    return await asyncio.to_thread(_fetch_tickers_sync, symbols, asset_class)
