"""
Gate 2+3 Validation: CryptoInvestorV1
=======================================
Sprint 1, Item 1.2

Validates the CryptoInvestorV1 trend-following strategy by replicating its
entry/exit logic in a VectorBT parameter sweep, then running walk-forward
OOS validation and +/-20% parameter perturbation robustness testing.

Entry Logic (replicated from Freqtrade strategy):
    - Price > EMA(fast) AND EMA(fast) > EMA(slow) — uptrend
    - RSI(14) < threshold — pullback in uptrend
    - Volume ratio > 0.8 — volume confirmation
    - MACD histogram > 0 or rising — momentum
    - Close < BB upper * 0.98 — not chasing
    - Volume > 0

Exit Logic:
    - RSI(14) > sell threshold — overbought
    - OR price crosses below EMA(fast) — trend break

Usage:
    python validate_crypto_investor_v1.py --symbol BTC/USDT --timeframe 1h
    python validate_crypto_investor_v1.py --synthetic
"""

import sys
import logging
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common.indicators.technical import ema, rsi, macd, bollinger_bands, sma  # noqa: E402
from validation_engine import (  # noqa: E402
    run_validation,
    save_report,
    generate_synthetic_ohlcv,
    DEFAULT_FEES,
)

logger = logging.getLogger("validate_civ1")

# ── Parameter grid matching Freqtrade hyperopt ranges ─────────
PARAM_GRID = {
    "ema_fast": [20, 35, 50, 65, 80],
    "ema_slow": [100, 150, 200, 250, 300],
    "rsi_threshold": [25, 30, 35, 40, 45],
    "sell_rsi_threshold": [70, 75, 80, 85, 90],
}
# Total: 5^4 = 625 combinations

STOPLOSS = 0.05  # -5% hard stop (matches Freqtrade strategy)


def crypto_investor_v1_signals(
    df: pd.DataFrame, params: dict
) -> tuple[pd.Series, pd.Series]:
    """
    Replicate CryptoInvestorV1 entry/exit logic using pure pandas indicators.

    Parameters:
        ema_fast: Fast EMA period (20-80)
        ema_slow: Slow EMA period (100-300)
        rsi_threshold: RSI entry threshold (25-45)
        sell_rsi_threshold: RSI exit threshold (70-90)
    """
    close = df["close"]
    volume = df["volume"]

    ema_fast_val = ema(close, int(params["ema_fast"]))
    ema_slow_val = ema(close, int(params["ema_slow"]))
    rsi_14 = rsi(close, 14)
    macd_data = macd(close)
    macd_hist = macd_data["macd_hist"]
    bb = bollinger_bands(close, 20, 2.0)
    volume_sma = sma(volume, 20)
    volume_ratio = volume / volume_sma

    # Entry: all conditions must be true
    entries = (
        (close > ema_fast_val)
        & (ema_fast_val > ema_slow_val)  # Uptrend: EMA alignment
        & (rsi_14 < params["rsi_threshold"])  # RSI pullback
        & (volume_ratio > 0.8)  # Volume confirmation
        & ((macd_hist > 0) | (macd_hist > macd_hist.shift(1)))  # MACD momentum
        & (close < bb["bb_upper"] * 0.98)  # Not chasing
        & (volume > 0)
    )

    # Exit: any condition triggers
    exits = (rsi_14 > params["sell_rsi_threshold"]) | (
        (close < ema_fast_val) & (close.shift(1) >= ema_fast_val.shift(1))
    )

    return entries.fillna(False), exits.fillna(False)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Gate 2+3 Validation: CryptoInvestorV1"
    )
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe")
    parser.add_argument("--exchange", default="binance", help="Exchange")
    parser.add_argument(
        "--fees",
        type=float,
        default=DEFAULT_FEES,
        help="Trading fees (0.0015 = 0.15%%)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic data instead of real market data",
    )
    parser.add_argument(
        "--synthetic-rows",
        type=int,
        default=5000,
        help="Number of synthetic data rows",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.synthetic:
        logger.info("Using synthetic data for validation")
        df = generate_synthetic_ohlcv(n=args.synthetic_rows)
        symbol = "SYNTHETIC"
    else:
        from common.data_pipeline.pipeline import load_ohlcv

        df = load_ohlcv(args.symbol, args.timeframe, args.exchange)
        if df.empty:
            logger.error(
                f"No data for {args.symbol} {args.timeframe}. "
                "Run data pipeline first or use --synthetic."
            )
            return
        symbol = args.symbol

    report = run_validation(
        strategy_name="CryptoInvestorV1",
        df=df,
        signal_fn=crypto_investor_v1_signals,
        param_grid=PARAM_GRID,
        fees=args.fees,
        sl_stop=STOPLOSS,
        freq=args.timeframe,
        symbol=symbol,
        timeframe=args.timeframe,
    )

    filepath = save_report(report)
    print(f"\nReport saved to: {filepath}")

    if report["overall"]["passed"]:
        print("\nVALIDATION PASSED — Strategy is a candidate for paper trading")
    else:
        print("\nVALIDATION FAILED — Strategy needs refinement")
        if not report["gate2"]["passed"]:
            print("   Gate 2 failed: No parameter combo meets all criteria")
        if not report.get("gate3_walkforward", {}).get("passed", False):
            print("   Gate 3a failed: Walk-forward OOS performance insufficient")
        if not report.get("gate3_perturbation", {}).get("passed", False):
            print("   Gate 3b failed: Strategy not robust to parameter perturbation")


if __name__ == "__main__":
    main()
