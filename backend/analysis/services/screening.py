"""Screener service — wraps VectorBT screener for the web app."""

import logging
from collections.abc import Callable

from core.platform_bridge import ensure_platform_imports

logger = logging.getLogger("screener_service")

STRATEGY_TYPES = [
    {
        "name": "sma_crossover", "label": "SMA Crossover",
        "description": "Fast/slow MA crossover",
    },
    {
        "name": "rsi_mean_reversion",
        "label": "RSI Mean Reversion",
        "description": "RSI oversold/overbought",
    },
    {
        "name": "bollinger_breakout",
        "label": "Bollinger Breakout",
        "description": "BB upper/lower break",
    },
    {
        "name": "ema_rsi_combo",
        "label": "EMA + RSI Combo",
        "description": "EMA trend + RSI pullback",
    },
]


class ScreenerService:
    @staticmethod
    def run_full_screen(params: dict, progress_cb: Callable) -> dict:
        ensure_platform_imports()
        from common.data_pipeline.pipeline import load_ohlcv
        from common.indicators.technical import ema, rsi, sma

        symbol = params.get("symbol", "BTC/USDT")
        timeframe = params.get("timeframe", "1h")
        exchange = params.get("exchange", "binance")
        fees = params.get("fees", 0.001)

        progress_cb(0.05, f"Loading {symbol} {timeframe} data...")
        df = load_ohlcv(symbol, timeframe, exchange)
        if df.empty:
            return {"error": f"No data available for {symbol} {timeframe} on {exchange}"}

        close = df["close"]
        all_results = {}
        strategies = ["sma_crossover", "rsi_mean_reversion", "bollinger_breakout", "ema_rsi_combo"]

        for i, strategy in enumerate(strategies):
            step = (i + 1) / len(strategies)
            progress_cb(0.1 + step * 0.85, f"Running {strategy}...")
            try:
                import vectorbt as vbt

                if strategy == "sma_crossover":
                    result_df = _screen_sma(close, vbt, fees)
                elif strategy == "rsi_mean_reversion":
                    result_df = _screen_rsi(df, vbt, fees)
                elif strategy == "bollinger_breakout":
                    result_df = _screen_bollinger(df, vbt, sma, fees)
                elif strategy == "ema_rsi_combo":
                    result_df = _screen_ema_rsi(df, vbt, ema, rsi, fees)
                else:
                    continue

                if result_df is not None and not result_df.empty:
                    top = result_df.head(10)
                    all_results[strategy] = {
                        "total_combinations": len(result_df),
                        "top_results": top.reset_index(drop=True).to_dict(orient="records"),
                        "summary": {
                            "top_sharpe": float(top["sharpe_ratio"].iloc[0])
                            if "sharpe_ratio" in top.columns else None,
                            "top_return": float(top["total_return"].iloc[0])
                            if "total_return" in top.columns else None,
                        },
                    }
            except ImportError:
                all_results[strategy] = {"error": "VectorBT not installed"}
            except Exception as e:
                logger.exception(f"Strategy {strategy} failed")
                all_results[strategy] = {"error": str(e)}

        progress_cb(1.0, "Screening complete")
        return {
            "symbol": symbol, "timeframe": timeframe,
            "exchange": exchange, "strategies": all_results,
        }


def _screen_sma(close, vbt, fees: float):
    import pandas as pd

    fast_windows = list(range(5, 50, 5))
    slow_windows = list(range(20, 200, 10))
    fast_ma, slow_ma = vbt.MA.run_combs(
        close, window=fast_windows + slow_windows, r=2,
        short_names=["fast", "slow"],
    )
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    pf = vbt.Portfolio.from_signals(
        close, entries=entries, exits=exits,
        fees=fees, freq="1h", init_cash=10000,
    )
    results = pd.DataFrame({
        "total_return": pf.total_return(),
        "sharpe_ratio": pf.sharpe_ratio(),
        "max_drawdown": pf.max_drawdown(),
        "win_rate": pf.trades.win_rate(),
        "num_trades": pf.trades.count(),
    })
    return results.sort_values("sharpe_ratio", ascending=False)


def _screen_rsi(df, vbt, fees: float):
    import pandas as pd
    from common.indicators.technical import rsi

    close = df["close"]
    results = []
    for period in [7, 10, 14, 21]:
        rsi_val = rsi(close, period)
        for os_lvl in [20, 25, 30, 35]:
            for ob_lvl in [65, 70, 75, 80]:
                if os_lvl >= ob_lvl:
                    continue
                try:
                    entries = rsi_val < os_lvl
                    exits = rsi_val > ob_lvl
                    pf = vbt.Portfolio.from_signals(
                        close, entries=entries, exits=exits,
                        fees=fees, freq="1h", init_cash=10000,
                    )
                    results.append({
                        "rsi_period": period,
                        "oversold": os_lvl,
                        "overbought": ob_lvl,
                        "total_return": pf.total_return(),
                        "sharpe_ratio": pf.sharpe_ratio(),
                        "max_drawdown": pf.max_drawdown(),
                        "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                        "num_trades": pf.trades.count(),
                    })
                except Exception:
                    pass
    df_r = pd.DataFrame(results)
    return df_r.sort_values("sharpe_ratio", ascending=False) if not df_r.empty else df_r


def _screen_bollinger(df, vbt, sma_fn, fees: float):
    import pandas as pd

    close = df["close"]
    results = []
    for period in [10, 15, 20, 25, 30]:
        mid = sma_fn(close, period)
        std = close.rolling(window=period).std()
        for std_mult in [1.5, 2.0, 2.5, 3.0]:
            upper = mid + (std * std_mult)
            lower = mid - (std * std_mult)
            try:
                entries = close > upper
                exits = close < lower
                pf = vbt.Portfolio.from_signals(
                    close, entries=entries, exits=exits,
                    fees=fees, freq="1h", init_cash=10000,
                )
                results.append({
                    "bb_period": period, "bb_std": std_mult,
                    "total_return": pf.total_return(),
                    "sharpe_ratio": pf.sharpe_ratio(),
                    "max_drawdown": pf.max_drawdown(),
                    "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                    "num_trades": pf.trades.count(),
                })
            except Exception:
                pass
    df_r = pd.DataFrame(results)
    return df_r.sort_values("sharpe_ratio", ascending=False) if not df_r.empty else df_r


def _screen_ema_rsi(df, vbt, ema_fn, rsi_fn, fees: float):
    import pandas as pd

    close = df["close"]
    rsi_14 = rsi_fn(close, 14)
    results = []
    for ema_p in [20, 50, 100]:
        ema_val = ema_fn(close, ema_p)
        for rsi_entry in [30, 35, 40]:
            try:
                entries = (close > ema_val) & (rsi_14 < rsi_entry)
                exits = (close < ema_val) | (rsi_14 > 75)
                pf = vbt.Portfolio.from_signals(
                    close, entries=entries, exits=exits,
                    fees=fees, freq="1h", init_cash=10000,
                )
                results.append({
                    "ema_period": ema_p, "rsi_entry": rsi_entry,
                    "total_return": pf.total_return(),
                    "sharpe_ratio": pf.sharpe_ratio(),
                    "max_drawdown": pf.max_drawdown(),
                    "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                    "num_trades": pf.trades.count(),
                })
            except Exception:
                pass
    df_r = pd.DataFrame(results)
    return df_r.sort_values("sharpe_ratio", ascending=False) if not df_r.empty else df_r
