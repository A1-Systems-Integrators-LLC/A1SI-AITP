"""
Gate 2+3 Validation: VolatilityBreakout
========================================
Sprint 2, Item 2.3

Validates the VolatilityBreakout strategy by replicating its
entry/exit logic in VectorBT, running parameter sweep + walk-forward +
perturbation robustness.

Entry Logic (replicated from Freqtrade strategy):
    - Close > N-period high (breakout)
    - Volume ratio > volume_factor
    - BB width expanding
    - ADX in range [adx_low, adx_high] and rising
    - RSI in range [rsi_low, rsi_high]
    - Volume > 0

Exit Logic:
    - RSI > sell_rsi_threshold (exhaustion)
    - OR close crosses below EMA(20) with volume confirmation

Usage:
    python validate_volatility_breakout.py --symbol BTC/USDT --timeframe 1h
    python validate_volatility_breakout.py --synthetic
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

from common.indicators.technical import (  # noqa: E402
    adx,
    bollinger_bands,
    ema,
    rsi,
    sma,
)
from validation_engine import (  # noqa: E402
    run_validation,
    save_report,
    generate_synthetic_ohlcv,
    DEFAULT_FEES,
)

logger = logging.getLogger("validate_vb")

# ── Parameter grid matching Freqtrade hyperopt ranges ─────────
# Reduced for CI: 3 * 3 * 3 * 3 * 3 * 3 = 729 combinations
PARAM_GRID = {
    "breakout_period": [10, 20, 30],
    "volume_factor": [1.2, 1.8, 3.0],
    "adx_low": [10, 15, 20],
    "adx_high": [20, 25, 35],
    "rsi_low": [35, 40, 50],
    "rsi_high": [60, 65, 70, 75],
    "adx_tolerance": [0.0, 0.5, 1.0],
    "sell_rsi_threshold": [80, 85, 95],
}

STOPLOSS = 0.03  # -3% hard stop (matches Freqtrade strategy)


def volatility_breakout_signals(
    df: pd.DataFrame, params: dict
) -> tuple[pd.Series, pd.Series]:
    """
    Replicate VolatilityBreakout entry/exit logic using pure pandas indicators.

    Parameters:
        breakout_period: N-period high lookback (10-30)
        volume_factor: Volume spike multiplier (1.2-3.0)
        adx_low: ADX lower bound (10-20)
        adx_high: ADX upper bound (20-35)
        rsi_low: RSI entry lower bound (35-50)
        sell_rsi_threshold: RSI exit threshold (80-95)
    """
    close = df["close"]
    high = df["high"]
    volume = df["volume"]

    # Indicators
    n_high = high.rolling(window=int(params["breakout_period"])).max().shift(1)
    rsi_14 = rsi(close, 14)
    adx_14 = adx(df, 14)
    ema_20 = ema(close, 20)
    volume_sma = sma(volume, 20)
    volume_ratio = volume / volume_sma
    bb = bollinger_bands(close, 20, 2.0)
    bb_width = bb["bb_width"]
    bb_width_expanding = bb_width > bb_width.shift(1)

    rsi_high = int(params.get("rsi_high", 70))
    adx_tolerance = float(params.get("adx_tolerance", 0.5))

    # Entry: all conditions must be true
    entries = (
        (close > n_high)  # Breakout above N-period high
        & (volume_ratio > float(params["volume_factor"]))  # Volume spike
        & bb_width_expanding  # Volatility expanding
        & (adx_14 >= float(params["adx_low"]))  # ADX in range
        & (adx_14 <= float(params["adx_high"]))
        & (adx_14 > adx_14.shift(1) - adx_tolerance)  # ADX rising (with tolerance)
        & (rsi_14 >= float(params["rsi_low"]))  # RSI in neutral zone
        & (rsi_14 <= rsi_high)
        & (volume > 0)
    )

    # Exit: exhaustion or trend failure
    exits = (rsi_14 > float(params["sell_rsi_threshold"])) | (
        (close < ema_20)
        & (close.shift(1) >= ema_20.shift(1))
        & (volume_ratio > 1.0)
    )

    return entries.fillna(False), exits.fillna(False)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Gate 2+3 Validation: VolatilityBreakout"
    )
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe")
    parser.add_argument("--exchange", default="kraken", help="Exchange")
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
        strategy_name="VolatilityBreakout",
        df=df,
        signal_fn=volatility_breakout_signals,
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
