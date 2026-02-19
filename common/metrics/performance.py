"""
Shared Performance Metrics
===========================
Computes standard trading performance metrics from a trades DataFrame.
Used by NautilusTrader, hftbacktest, and any future framework tier.
"""

import numpy as np
import pandas as pd


def serialize_trades_df(trades_df: pd.DataFrame) -> list[dict]:
    """Serialize a trades DataFrame to a JSON-compatible list of dicts.

    Converts Timestamp columns to strings so the result can be stored
    in Django JSONField or written to JSON files.
    """
    if trades_df.empty:
        return []
    trades_serial = trades_df.copy()
    for col in ["entry_time", "exit_time"]:
        if col in trades_serial.columns:
            trades_serial[col] = trades_serial[col].astype(str)
    return trades_serial.to_dict("records")


def compute_performance_metrics(trades_df: pd.DataFrame) -> dict:
    """
    Compute standard performance metrics from a trades DataFrame.
    Works with output from any framework (Nautilus, Freqtrade, hftbacktest, or VectorBT).

    Expected columns: entry_time, exit_time, pnl, pnl_pct, side
    """
    if trades_df.empty:
        return {"error": "No trades to analyze"}

    total_trades = len(trades_df)
    winners = trades_df[trades_df["pnl"] > 0]
    losers = trades_df[trades_df["pnl"] <= 0]

    total_pnl = trades_df["pnl"].sum()
    win_rate = len(winners) / total_trades if total_trades > 0 else 0

    gross_profit = winners["pnl"].sum() if len(winners) > 0 else 0
    gross_loss = abs(losers["pnl"].sum()) if len(losers) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_win = winners["pnl"].mean() if len(winners) > 0 else 0
    avg_loss = losers["pnl"].mean() if len(losers) > 0 else 0

    # Sharpe-like ratio from trade returns (time-based annualization)
    sharpe = 0
    if "pnl_pct" in trades_df.columns and trades_df["pnl_pct"].std() > 0:
        # Compute annualization factor from actual trade span
        trades_per_year = 252  # fallback
        if (
            "entry_time" in trades_df.columns
            and "exit_time" in trades_df.columns
            and total_trades >= 2
        ):
            first_entry = trades_df["entry_time"].min()
            last_exit = trades_df["exit_time"].max()
            span = (last_exit - first_entry).total_seconds()
            if span > 0:
                seconds_per_year = 365.25 * 24 * 3600
                trades_per_year = total_trades * (seconds_per_year / span)
        sharpe = (
            trades_df["pnl_pct"].mean() / trades_df["pnl_pct"].std()
        ) * np.sqrt(trades_per_year)

    # Max drawdown from cumulative PnL
    cum_pnl = trades_df["pnl"].cumsum()
    running_max = cum_pnl.cummax()
    drawdown = cum_pnl - running_max
    max_drawdown = drawdown.min()

    avg_duration = "N/A"
    if "exit_time" in trades_df.columns and "entry_time" in trades_df.columns:
        avg_duration = str((trades_df["exit_time"] - trades_df["entry_time"]).mean())

    return {
        "total_trades": total_trades,
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 3),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(max_drawdown, 2),
        "best_trade": round(trades_df["pnl"].max(), 2),
        "worst_trade": round(trades_df["pnl"].min(), 2),
        "avg_trade_duration": avg_duration,
    }
