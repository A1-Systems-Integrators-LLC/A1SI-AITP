"""
VectorBT Strategy Research & Screening Engine
==============================================
Rapid strategy screening using vectorized backtesting.
Screens thousands of parameter combinations in seconds.

Workflow:
    1. Load data from shared pipeline
    2. Run parameter sweeps across strategy variants
    3. Rank results by composite score
    4. Export top candidates for Freqtrade/Nautilus event-driven backtesting
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import vectorbt as vbt

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.data_pipeline.pipeline import load_ohlcv, PROCESSED_DIR
from common.indicators.technical import sma, ema, rsi, atr_indicator

logger = logging.getLogger("vbt_screener")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RESULTS_DIR = PROJECT_ROOT / "research" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────
# Strategy Definitions
# ──────────────────────────────────────────────

def screen_sma_crossover(
    close: pd.Series,
    fast_windows: list = None,
    slow_windows: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen SMA crossover strategies across parameter grid.

    Tests all combinations of fast/slow moving average windows.
    """
    if fast_windows is None:
        fast_windows = list(range(5, 50, 5))
    if slow_windows is None:
        slow_windows = list(range(20, 200, 10))

    logger.info(
        f"Screening SMA crossover: {len(fast_windows)} fast x {len(slow_windows)} slow "
        f"= {len(fast_windows) * len(slow_windows)} combinations"
    )

    # VectorBT parameter sweep
    fast_ma, slow_ma = vbt.MA.run_combs(
        close,
        window=fast_windows + slow_windows,
        r=2,
        short_names=["fast", "slow"],
    )

    # Generate entries/exits from crossovers
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run portfolio simulation
    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        fees=fees,
        freq="1h",
        init_cash=10000,
    )

    # Extract metrics
    results = pd.DataFrame({
        "total_return": pf.total_return(),
        "sharpe_ratio": pf.sharpe_ratio(),
        "max_drawdown": pf.max_drawdown(),
        "win_rate": pf.trades.win_rate(),
        "profit_factor": pf.trades.profit_factor(),
        "num_trades": pf.trades.count(),
        "avg_trade_pnl": pf.trades.pnl.mean(),
    })

    results = results.sort_values("sharpe_ratio", ascending=False)
    logger.info(f"Screening complete. Top Sharpe: {results['sharpe_ratio'].iloc[0]:.3f}")
    return results


def screen_rsi_mean_reversion(
    df: pd.DataFrame,
    rsi_periods: list = None,
    oversold_levels: list = None,
    overbought_levels: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen RSI mean-reversion strategies.

    Buy when RSI drops below oversold, sell when RSI rises above overbought.
    """
    if rsi_periods is None:
        rsi_periods = [7, 10, 14, 21]
    if oversold_levels is None:
        oversold_levels = [20, 25, 30, 35]
    if overbought_levels is None:
        overbought_levels = [65, 70, 75, 80]

    close = df["close"]
    results = []

    for period in rsi_periods:
        rsi_values = rsi(close, period)
        for os_level in oversold_levels:
            for ob_level in overbought_levels:
                if os_level >= ob_level:
                    continue

                entries = rsi_values < os_level
                exits = rsi_values > ob_level

                try:
                    pf = vbt.Portfolio.from_signals(
                        close,
                        entries=entries,
                        exits=exits,
                        fees=fees,
                        freq="1h",
                        init_cash=10000,
                    )

                    results.append({
                        "rsi_period": period,
                        "oversold": os_level,
                        "overbought": ob_level,
                        "total_return": pf.total_return(),
                        "sharpe_ratio": pf.sharpe_ratio(),
                        "max_drawdown": pf.max_drawdown(),
                        "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                        "profit_factor": pf.trades.profit_factor() if pf.trades.count() > 0 else 0,
                        "num_trades": pf.trades.count(),
                    })
                except Exception as e:
                    logger.debug(f"Skipping RSI({period}, {os_level}, {ob_level}): {e}")

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values("sharpe_ratio", ascending=False)
    logger.info(f"RSI screening complete: {len(results_df)} parameter combos tested")
    return results_df


def screen_bollinger_breakout(
    df: pd.DataFrame,
    bb_periods: list = None,
    bb_stds: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen Bollinger Band breakout strategies.

    Buy when price closes above upper band, sell when it closes below lower band.
    """
    if bb_periods is None:
        bb_periods = [10, 15, 20, 25, 30]
    if bb_stds is None:
        bb_stds = [1.5, 2.0, 2.5, 3.0]

    close = df["close"]
    results = []

    for period in bb_periods:
        mid = sma(close, period)
        std = close.rolling(window=period).std()
        for std_mult in bb_stds:
            upper = mid + (std * std_mult)
            lower = mid - (std * std_mult)

            entries = close > upper
            exits = close < lower

            try:
                pf = vbt.Portfolio.from_signals(
                    close,
                    entries=entries,
                    exits=exits,
                    fees=fees,
                    freq="1h",
                    init_cash=10000,
                )
                results.append({
                    "bb_period": period,
                    "bb_std": std_mult,
                    "total_return": pf.total_return(),
                    "sharpe_ratio": pf.sharpe_ratio(),
                    "max_drawdown": pf.max_drawdown(),
                    "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                    "profit_factor": pf.trades.profit_factor() if pf.trades.count() > 0 else 0,
                    "num_trades": pf.trades.count(),
                })
            except Exception as e:
                logger.debug(f"Skipping BB({period}, {std_mult}): {e}")

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values("sharpe_ratio", ascending=False)
    return results_df


def screen_ema_rsi_combo(
    df: pd.DataFrame,
    ema_periods: list = None,
    rsi_entry_levels: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen combined EMA trend + RSI momentum strategies.

    Buy when price > EMA (uptrend) AND RSI < oversold (pullback entry).
    Sell when price < EMA OR RSI > overbought.
    """
    if ema_periods is None:
        ema_periods = [20, 50, 100]
    if rsi_entry_levels is None:
        rsi_entry_levels = [30, 35, 40]

    close = df["close"]
    rsi_14 = rsi(close, 14)
    results = []

    for ema_p in ema_periods:
        ema_val = ema(close, ema_p)
        in_uptrend = close > ema_val

        for rsi_entry in rsi_entry_levels:
            entries = in_uptrend & (rsi_14 < rsi_entry)
            exits = (close < ema_val) | (rsi_14 > 75)

            try:
                pf = vbt.Portfolio.from_signals(
                    close, entries=entries, exits=exits,
                    fees=fees, freq="1h", init_cash=10000,
                )
                results.append({
                    "ema_period": ema_p,
                    "rsi_entry": rsi_entry,
                    "total_return": pf.total_return(),
                    "sharpe_ratio": pf.sharpe_ratio(),
                    "max_drawdown": pf.max_drawdown(),
                    "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                    "num_trades": pf.trades.count(),
                })
            except Exception:
                pass

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values("sharpe_ratio", ascending=False)
    return results_df


# ──────────────────────────────────────────────
# Composite Screener
# ──────────────────────────────────────────────

def run_full_screen(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    exchange: str = "binance",
    fees: float = 0.001,
) -> dict:
    """
    Run all strategy screens for a given symbol and return ranked results.
    """
    logger.info(f"=== Full strategy screen: {symbol} {timeframe} on {exchange} ===")

    df = load_ohlcv(symbol, timeframe, exchange)
    if df.empty:
        logger.error(f"No data available for {symbol} {timeframe}. Run data pipeline first.")
        return {}

    close = df["close"]
    results = {}

    # 1. SMA Crossover
    logger.info("Running SMA crossover screen...")
    try:
        results["sma_crossover"] = screen_sma_crossover(close, fees=fees)
    except Exception as e:
        logger.error(f"SMA crossover screen failed: {e}")

    # 2. RSI Mean Reversion
    logger.info("Running RSI mean-reversion screen...")
    try:
        results["rsi_mean_reversion"] = screen_rsi_mean_reversion(df, fees=fees)
    except Exception as e:
        logger.error(f"RSI screen failed: {e}")

    # 3. Bollinger Breakout
    logger.info("Running Bollinger breakout screen...")
    try:
        results["bollinger_breakout"] = screen_bollinger_breakout(df, fees=fees)
    except Exception as e:
        logger.error(f"Bollinger screen failed: {e}")

    # 4. EMA + RSI Combo
    logger.info("Running EMA+RSI combo screen...")
    try:
        results["ema_rsi_combo"] = screen_ema_rsi_combo(df, fees=fees)
    except Exception as e:
        logger.error(f"EMA+RSI screen failed: {e}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_symbol = symbol.replace("/", "_")
    output_dir = RESULTS_DIR / f"{safe_symbol}_{timeframe}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {}
    for name, df_result in results.items():
        if isinstance(df_result, pd.DataFrame) and not df_result.empty:
            path = output_dir / f"{name}.csv"
            df_result.to_csv(path)
            top = df_result.head(3)
            summary[name] = {
                "total_combos": len(df_result),
                "top_sharpe": float(top["sharpe_ratio"].iloc[0]) if "sharpe_ratio" in top.columns else None,
                "top_return": float(top["total_return"].iloc[0]) if "total_return" in top.columns else None,
            }

    # Save summary
    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info(f"Results saved to {output_dir}")
    logger.info(f"Summary: {json.dumps(summary, indent=2, default=str)}")
    return results


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VectorBT Strategy Screener")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe")
    parser.add_argument("--exchange", default="binance", help="Exchange")
    parser.add_argument("--fees", type=float, default=0.001, help="Trading fees (0.001 = 0.1%%)")

    args = parser.parse_args()
    run_full_screen(args.symbol, args.timeframe, args.exchange, args.fees)
