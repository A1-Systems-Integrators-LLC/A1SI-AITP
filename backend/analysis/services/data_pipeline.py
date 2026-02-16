"""Data pipeline service — wraps common.data_pipeline.pipeline for the web app."""

import logging
from collections.abc import Callable

from core.platform_bridge import ensure_platform_imports, get_processed_dir

logger = logging.getLogger("data_pipeline_service")


class DataPipelineService:
    def __init__(self) -> None:
        ensure_platform_imports()
        self._processed_dir = get_processed_dir()

    def list_available_data(self) -> list[dict]:
        import pandas as pd

        records = []
        for f in self._processed_dir.glob("*.parquet"):
            parts = f.stem.split("_")
            if len(parts) >= 4:
                exchange = parts[0]
                symbol = f"{parts[1]}/{parts[2]}"
                timeframe = parts[3]
                try:
                    df = pd.read_parquet(f)
                    records.append({
                        "exchange": exchange, "symbol": symbol,
                        "timeframe": timeframe, "rows": len(df),
                        "start": str(df.index.min()) if len(df) > 0 else None,
                        "end": str(df.index.max()) if len(df) > 0 else None,
                        "file": f.name,
                    })
                except Exception as e:
                    logger.warning(f"Failed to read {f}: {e}")
        return records

    def get_data_info(self, symbol: str, timeframe: str, exchange: str) -> dict | None:
        import pandas as pd

        safe_symbol = symbol.replace("/", "_")
        path = self._processed_dir / f"{exchange}_{safe_symbol}_{timeframe}.parquet"
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            return {
                "exchange": exchange, "symbol": symbol,
                "timeframe": timeframe, "rows": len(df),
                "start": str(df.index.min()) if len(df) > 0 else None,
                "end": str(df.index.max()) if len(df) > 0 else None,
                "columns": list(df.columns),
                "file_size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            }
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return None

    @staticmethod
    def download_data(params: dict, progress_cb: Callable) -> dict:
        ensure_platform_imports()
        from common.data_pipeline.pipeline import fetch_ohlcv, save_ohlcv

        symbols = params.get("symbols", ["BTC/USDT"])
        timeframes = params.get("timeframes", ["1h"])
        exchange_id = params.get("exchange", "binance")
        since_days = params.get("since_days", 365)

        results = {}
        total = len(symbols) * len(timeframes)
        done = 0
        for symbol in symbols:
            for tf in timeframes:
                done += 1
                progress_cb(done / total, f"Downloading {symbol} {tf} ({done}/{total})")
                try:
                    df = fetch_ohlcv(symbol, tf, since_days, exchange_id)
                    if not df.empty:
                        path = save_ohlcv(df, symbol, tf, exchange_id)
                        results[f"{symbol}_{tf}"] = {
                            "rows": len(df), "path": str(path),
                            "status": "ok",
                        }
                    else:
                        results[f"{symbol}_{tf}"] = {"status": "empty"}
                except Exception as e:
                    logger.error(f"Error downloading {symbol} {tf}: {e}")
                    results[f"{symbol}_{tf}"] = {"status": "error", "error": str(e)}
        return {"downloads": results, "total": total, "completed": done}

    @staticmethod
    def generate_sample_data(params: dict, progress_cb: Callable) -> dict:
        import numpy as np
        import pandas as pd

        ensure_platform_imports()
        from common.data_pipeline.pipeline import save_ohlcv

        symbols = params.get("symbols", ["BTC/USDT", "ETH/USDT"])
        timeframes = params.get("timeframes", ["1h"])
        days = params.get("days", 90)

        results = {}
        total = len(symbols) * len(timeframes)
        done = 0
        for symbol in symbols:
            base_price = {"BTC/USDT": 50000, "ETH/USDT": 3000, "SOL/USDT": 100}.get(symbol, 100)
            for tf in timeframes:
                done += 1
                progress_cb(done / total, f"Generating {symbol} {tf} ({done}/{total})")
                tf_minutes = {
                    "1m": 1, "5m": 5, "15m": 15,
                    "1h": 60, "4h": 240, "1d": 1440,
                }.get(tf, 60)
                n_candles = (days * 24 * 60) // tf_minutes
                timestamps = pd.date_range(
                    end=pd.Timestamp.now(tz="UTC"),
                    periods=n_candles, freq=f"{tf_minutes}min",
                )

                np.random.seed(hash(f"{symbol}_{tf}") % (2**31))
                returns = np.random.normal(0.0001, 0.02, n_candles)
                prices = base_price * np.exp(np.cumsum(returns))

                df = pd.DataFrame({
                    "open": prices * (1 + np.random.uniform(-0.005, 0.005, n_candles)),
                    "high": prices * (1 + np.abs(np.random.normal(0, 0.01, n_candles))),
                    "low": prices * (1 - np.abs(np.random.normal(0, 0.01, n_candles))),
                    "close": prices,
                    "volume": np.random.uniform(100, 10000, n_candles) * (base_price / 100),
                }, index=timestamps)
                df.index.name = "timestamp"

                path = save_ohlcv(df, symbol, tf, "sample")
                results[f"{symbol}_{tf}"] = {"rows": len(df), "path": str(path), "status": "ok"}
        return {"generated": results, "total": total, "completed": done}
