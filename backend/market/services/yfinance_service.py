"""Django service wrapper for yfinance data fetching."""

import logging

logger = logging.getLogger(__name__)


class YFinanceService:
    """Mirrors ExchangeService API but uses yfinance for equity/forex data."""

    async def fetch_ticker(self, symbol: str, asset_class: str = "equity") -> dict:
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from common.data_pipeline.yfinance_adapter import fetch_ticker_yfinance

        return await fetch_ticker_yfinance(symbol, asset_class)

    async def fetch_tickers(
        self, symbols: list[str] | None, asset_class: str = "equity",
    ) -> list[dict]:
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from common.data_pipeline.yfinance_adapter import fetch_tickers_yfinance

        if symbols is None:
            from common.data_pipeline.pipeline import _DEFAULT_WATCHLISTS

            symbols = _DEFAULT_WATCHLISTS.get(asset_class, [])[:10]
        return await fetch_tickers_yfinance(symbols, asset_class)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 100,
        asset_class: str = "equity",
    ) -> list[dict]:
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from common.data_pipeline.yfinance_adapter import fetch_ohlcv_yfinance

        # Convert limit to approximate days
        tf_hours = {"1m": 1 / 60, "5m": 5 / 60, "15m": 0.25, "1h": 1, "4h": 4, "1d": 24}
        hours_per_candle = tf_hours.get(timeframe, 24)
        since_days = max(1, int(limit * hours_per_candle / 24) + 1)

        df = await fetch_ohlcv_yfinance(symbol, timeframe, since_days, asset_class)
        if df.empty:
            return []

        # Return last `limit` candles in API format
        df = df.tail(limit)
        result = []
        for ts, row in df.iterrows():
            result.append({
                "timestamp": int(ts.timestamp() * 1000),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
        return result

    async def close(self):
        """No-op: yfinance doesn't need connection cleanup."""
