"""Indicator service — wraps common.indicators.technical for the web app."""

import logging

from core.platform_bridge import ensure_platform_imports

logger = logging.getLogger("indicator_service")

AVAILABLE_INDICATORS = [
    "sma_7", "sma_14", "sma_21", "sma_50", "sma_100", "sma_200",
    "ema_7", "ema_14", "ema_21", "ema_50", "ema_100", "ema_200",
    "rsi_14", "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_mid", "bb_lower",
    "atr_14", "stoch_k", "stoch_d",
    "obv", "volume_sma_20", "volume_ratio",
]


class IndicatorService:
    @staticmethod
    def list_available() -> list[str]:
        return AVAILABLE_INDICATORS

    @staticmethod
    def compute(
        symbol: str,
        timeframe: str,
        exchange: str,
        indicators: list[str] | None = None,
        limit: int = 500,
    ) -> dict:
        """Load Parquet data, compute indicators, return as dict."""
        import numpy as np

        ensure_platform_imports()
        from common.data_pipeline.pipeline import load_ohlcv
        from common.indicators.technical import add_all_indicators

        df = load_ohlcv(symbol, timeframe, exchange)
        if df.empty:
            return {"error": f"No data for {symbol} {timeframe} on {exchange}", "data": []}

        df_with_ind = add_all_indicators(df)

        base_cols = ["open", "high", "low", "close", "volume"]
        if indicators:
            valid = [c for c in indicators if c in df_with_ind.columns]
            cols = base_cols + valid
        else:
            cols = [c for c in df_with_ind.columns if c in base_cols or c in AVAILABLE_INDICATORS]

        result = df_with_ind[cols].tail(limit)

        records = []
        for ts, row in result.iterrows():
            rec = {"timestamp": int(ts.timestamp() * 1000)}
            for col in cols:
                val = row[col]
                rec[col] = None if (isinstance(val, float) and np.isnan(val)) else float(val)
            records.append(rec)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange": exchange,
            "count": len(records),
            "columns": cols,
            "data": records,
        }
