"""
Gate 2+3 Validation: BollingerMeanReversion
=============================================
Sprint 1, Item 1.3

Validates the BollingerMeanReversion mean-reversion strategy by replicating
its entry/exit logic in VectorBT, running parameter sweep + walk-forward +
perturbation robustness.

Entry Logic (replicated from Freqtrade strategy):
    - Close < BB lower band — below lower Bollinger Band
    - RSI(14) < threshold — oversold
    - Volume ratio > volume_factor — volume spike
    - ADX(14) < 30 — ranging market (mean-reversion favorable)
    - RSI > 10 — not extreme downtrend
    - Volume > 0

Exit Logic:
    - Close > BB middle band — mean reversion target
    - OR RSI > sell threshold

Usage:
    python validate_bollinger_mean_reversion.py --symbol BTC/USDT --timeframe 1h
    python validate_bollinger_mean_reversion.py --synthetic
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

from common.indicators.technical import rsi, bollinger_bands, sma, adx  # noqa: E402
from validation_engine import (  # noqa: E402
    run_validation,
    save_report,
    generate_synthetic_ohlcv,
    DEFAULT_FEES,
)

logger = logging.getLogger("validate_bmr")

# ── Parameter grid matching Freqtrade hyperopt ranges ─────────
PARAM_GRID = {
    "bb_period": [15, 20, 25, 30],
    "bb_std": [1.5, 2.0, 2.5, 3.0],
    "rsi_threshold": [25, 30, 35, 40],
    "volume_factor": [1.0, 1.5, 2.0, 2.5],
    "sell_rsi_threshold": [55, 60, 65, 70, 75],
}
# Total: 4^4 * 5 = 1280 combinations

STOPLOSS = 0.04  # -4% hard stop (matches Freqtrade strategy)


def bollinger_mr_signals(
    df: pd.DataFrame, params: dict
) -> tuple[pd.Series, pd.Series]:
    """
    Replicate BollingerMeanReversion entry/exit logic using pure pandas indicators.

    Parameters:
        bb_period: Bollinger Band period (15-30)
        bb_std: Bollinger Band std dev multiplier (1.5-3.0)
        rsi_threshold: RSI entry threshold (25-40)
        volume_factor: Volume spike multiplier (1.0-2.5)
        sell_rsi_threshold: RSI exit threshold (55-75)
    """
    close = df["close"]
    volume = df["volume"]

    bb = bollinger_bands(close, int(params["bb_period"]), float(params["bb_std"]))
    rsi_14 = rsi(close, 14)
    adx_14 = adx(df, 14)
    volume_sma = sma(volume, 20)
    volume_ratio = volume / volume_sma

    # Entry: all conditions must be true
    entries = (
        (close < bb["bb_lower"])  # Below lower Bollinger Band
        & (rsi_14 < params["rsi_threshold"])  # Oversold
        & (volume_ratio > float(params["volume_factor"]))  # Volume spike
        & (adx_14 < 30)  # Ranging market
        & (rsi_14 > 10)  # Not extreme downtrend
        & (volume > 0)
    )

    # Exit: any condition triggers
    exits = (close > bb["bb_mid"]) | (rsi_14 > params["sell_rsi_threshold"])

    return entries.fillna(False), exits.fillna(False)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Gate 2+3 Validation: BollingerMeanReversion"
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
        strategy_name="BollingerMeanReversion",
        df=df,
        signal_fn=bollinger_mr_signals,
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
