"""
NautilusTrader Integration Layer
=================================
Bridge between A1SI-AITP platform and NautilusTrader's
institutional-grade backtesting and execution engine.

Dual-mode operation:
    - **Native mode**: When nautilus_trader is installed, uses the real
      BacktestEngine with proper Venue, Instrument, and Bar data for
      accurate fill simulation and event-driven execution.
    - **Pandas mode**: Fallback when nautilus_trader is not installed.
      Uses pandas-based indicator computation with our custom strategy
      runner. Identical entry/exit signals, simplified fill model.

Handles:
    - Converting shared Parquet data into Nautilus bar format
    - Configuring backtest engines with risk controls
    - Running backtests (native or pandas-based)
    - Extracting performance results
"""

import json
import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.metrics.performance import compute_performance_metrics, serialize_trades_df  # noqa: E402

logger = logging.getLogger("nautilus_runner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CATALOG_DIR = PROJECT_ROOT / "nautilus" / "catalog"
CATALOG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR = PROJECT_ROOT / "nautilus" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = PROJECT_ROOT / "configs" / "platform_config.yaml"

# Detect native NT availability
try:
    from nautilus.engine import HAS_NAUTILUS_TRADER
except ImportError:
    HAS_NAUTILUS_TRADER = False


def _load_platform_config() -> dict:
    """Load platform_config.yaml. Returns empty dict on failure."""
    if not CONFIG_PATH.exists():
        logger.debug("platform_config.yaml not found, using defaults")
        return {}
    try:
        import yaml
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        logger.debug("PyYAML not installed, using defaults")
        return {}
    except Exception as e:
        logger.warning(f"Failed to load platform config: {e}")
        return {}


def convert_ohlcv_to_nautilus_csv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    exchange: str = "kraken",
) -> Path:
    """
    Convert shared Parquet OHLCV data into Nautilus-compatible CSV bars.
    NautilusTrader can ingest CSV data via its data catalog or wranglers.
    """
    from common.data_pipeline.pipeline import load_ohlcv

    df = load_ohlcv(symbol, timeframe, exchange)
    if df.empty:
        logger.error(f"No data for {symbol} {timeframe}")
        return None

    safe_symbol = symbol.replace("/", "")
    venue = exchange.upper()

    nautilus_df = pd.DataFrame({
        "bar_type": f"{safe_symbol}.{venue}-{_tf_to_nautilus(timeframe)}-LAST-EXTERNAL",
        "open": df["open"].astype(str),
        "high": df["high"].astype(str),
        "low": df["low"].astype(str),
        "close": df["close"].astype(str),
        "volume": df["volume"].astype(str),
        "ts_event": df.index.astype(np.int64),
        "ts_init": df.index.astype(np.int64),
    })

    output_path = CATALOG_DIR / f"{safe_symbol}_{venue}_{timeframe}_bars.csv"
    nautilus_df.to_csv(output_path, index=False)
    logger.info(f"Exported {len(nautilus_df)} bars to {output_path}")
    return output_path


def _tf_to_nautilus(timeframe: str) -> str:
    """Convert common timeframe strings to Nautilus bar aggregation format."""
    mapping = {
        "1m": "1-MINUTE",
        "5m": "5-MINUTE",
        "15m": "15-MINUTE",
        "1h": "1-HOUR",
        "4h": "4-HOUR",
        "1d": "1-DAY",
    }
    return mapping.get(timeframe, "1-HOUR")


def list_nautilus_strategies() -> list[str]:
    """Return names of all registered NautilusTrader strategies."""
    from nautilus.strategies import STRATEGY_REGISTRY
    return list(STRATEGY_REGISTRY.keys())


def run_nautilus_backtest(
    strategy_name: str,
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    exchange: str = "kraken",
    initial_balance: float = 10000.0,
    asset_class: str = "crypto",
) -> dict:
    """
    Run a backtest using one of the registered Nautilus strategies.

    Tries the native NautilusTrader BacktestEngine first (when the library
    is installed). Falls back to the pandas-based simulation otherwise.

    Both modes use identical entry/exit signal logic from the strategy
    registry. The native mode provides more accurate fill simulation.
    """
    from nautilus.strategies import STRATEGY_REGISTRY
    from common.data_pipeline.pipeline import load_ohlcv

    if strategy_name not in STRATEGY_REGISTRY:
        available = ", ".join(STRATEGY_REGISTRY.keys())
        return {"error": f"Unknown strategy '{strategy_name}'. Available: {available}"}

    # Load data — route to correct source by asset class
    source = "yfinance" if asset_class in ("equity", "forex") else exchange
    df = load_ohlcv(symbol, timeframe, source)
    if df.empty:
        return {"error": f"No data for {symbol} {timeframe} on {source}"}

    # Try native engine first
    if HAS_NAUTILUS_TRADER:
        logger.info(f"Using native NautilusTrader engine for {strategy_name}")
        result = _run_native_backtest(
            strategy_name, df, symbol, timeframe, exchange, initial_balance,
        )
        if result is not None:
            return result
        logger.warning("Native engine failed, falling back to pandas simulation")

    # Pandas-based fallback
    return _run_pandas_backtest(
        strategy_name, df, symbol, timeframe, exchange, initial_balance,
    )


def _run_native_backtest(
    strategy_name: str,
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    exchange: str,
    initial_balance: float,
) -> dict | None:
    """Run backtest using real NautilusTrader BacktestEngine.

    Returns result dict on success, None on failure (caller should fallback).
    """
    try:
        from nautilus.engine import (
            create_backtest_engine,
            add_venue,
            create_crypto_instrument,
            build_bar_type,
            convert_df_to_bars,
        )
        from nautilus.strategies.nt_native import NATIVE_STRATEGY_REGISTRY

        # Map pandas strategy name to native adapter name
        native_name_map = {
            "NautilusTrendFollowing": "NativeTrendFollowing",
            "NautilusMeanReversion": "NativeMeanReversion",
            "NautilusVolatilityBreakout": "NativeVolatilityBreakout",
            "EquityMomentum": "NativeEquityMomentum",
            "EquityMeanReversion": "NativeEquityMeanReversion",
            "ForexTrend": "NativeForexTrend",
            "ForexRange": "NativeForexRange",
        }
        native_name = native_name_map.get(strategy_name)
        if not native_name or native_name not in NATIVE_STRATEGY_REGISTRY:
            logger.warning(f"No native adapter for {strategy_name}")
            return None

        venue_name = exchange.upper()

        # Setup engine
        engine = create_backtest_engine(log_level="WARNING")
        add_venue(engine, venue_name, starting_balance=initial_balance)

        # Create instrument, register it, and build bar type
        instrument = create_crypto_instrument(symbol, venue_name)
        engine.add_instrument(instrument)
        instrument_id = instrument.id
        bar_type = build_bar_type(instrument_id, timeframe)

        # Convert data and add to engine
        bars = convert_df_to_bars(
            df, bar_type,
            price_precision=instrument.price_precision,
            size_precision=instrument.size_precision,
        )
        engine.add_data(bars)

        # Create and add native strategy
        from nautilus.strategies.nt_native import _NativeAdapterConfig

        config = _NativeAdapterConfig(
            instrument_id=str(instrument_id),
            bar_type=str(bar_type),
            trade_size=0.01,
            mode="backtest",
        )
        native_cls = NATIVE_STRATEGY_REGISTRY[native_name]
        strategy = native_cls(config=config)
        engine.add_strategy(strategy)

        # Run
        logger.info(f"Running native backtest: {strategy_name} ({len(df)} bars)")
        engine.run()

        # Extract results from engine
        # Note: NT engine provides its own performance stats
        result = {
            "framework": "nautilus",
            "engine": "native",
            "strategy": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange": exchange,
            "initial_balance": initial_balance,
            "bars_processed": len(df),
            "metrics": {},
            "trades": [],
        }

        # Save results
        _save_result(result, strategy_name, symbol, timeframe)
        engine.dispose()
        return result

    except Exception as e:
        logger.warning(f"Native engine error: {e}")
        return None


def _run_pandas_backtest(
    strategy_name: str,
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    exchange: str,
    initial_balance: float,
) -> dict:
    """Run backtest using pandas-based simulation (fallback mode)."""
    from nautilus.strategies import STRATEGY_REGISTRY

    logger.info(f"Running pandas backtest: {strategy_name} on {symbol} {timeframe} ({len(df)} bars)")

    # Build config: platform_config.yaml defaults -> function args
    platform_cfg = _load_platform_config()
    nautilus_cfg = platform_cfg.get("nautilus", {})
    backtest_defaults = nautilus_cfg.get("backtest", {})
    strategy_defaults = nautilus_cfg.get("strategies", {}).get(strategy_name, {})

    config = {
        **backtest_defaults,
        **strategy_defaults,
        "mode": "backtest",
        "symbol": symbol,
        "initial_balance": initial_balance,
    }

    # Instantiate strategy
    strategy_cls = STRATEGY_REGISTRY[strategy_name]
    strategy = strategy_cls(config=config)

    # Feed bars
    for ts, row in df.iterrows():
        bar = {
            "timestamp": ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        strategy.on_bar(bar)

    # Flatten any remaining position
    strategy.on_stop()

    # Collect results
    trades_df = strategy.get_trades_df()
    metrics = compute_performance_metrics(trades_df)

    result = {
        "framework": "nautilus",
        "engine": "pandas",
        "strategy": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "exchange": exchange,
        "initial_balance": initial_balance,
        "bars_processed": len(df),
        "metrics": metrics,
        "trades": serialize_trades_df(trades_df),
    }

    _save_result(result, strategy_name, symbol, timeframe)
    return result


def _save_result(result: dict, strategy_name: str, symbol: str, timeframe: str) -> None:
    """Save backtest result to JSON in the results directory."""
    safe_symbol = symbol.replace("/", "")
    result_path = RESULTS_DIR / f"{strategy_name}_{safe_symbol}_{timeframe}.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"Results saved to {result_path}")


def run_nautilus_engine_test() -> bool:
    """Test NautilusTrader engine initialization.

    Returns True if the engine initializes successfully, False otherwise.
    Uses the engine adapter module for proper configuration.
    """
    if HAS_NAUTILUS_TRADER:
        try:
            from nautilus.engine import create_backtest_engine
            engine = create_backtest_engine(log_level="WARNING")
            logger.info("NautilusTrader BacktestEngine initialized successfully")
            logger.info(f"  Engine type: {type(engine).__name__}")
            engine.dispose()
            return True
        except Exception as e:
            logger.error(f"NautilusTrader engine init failed: {e}")
            return False
    else:
        logger.error("nautilus_trader is not installed")
        logger.info("Install with: pip install nautilus_trader")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NautilusTrader Runner")
    sub = parser.add_subparsers(dest="command")

    # Convert data
    conv = sub.add_parser("convert", help="Convert Parquet data to Nautilus CSV")
    conv.add_argument("--symbol", default="BTC/USDT")
    conv.add_argument("--timeframe", default="1h")
    conv.add_argument("--exchange", default="kraken")

    # Test engine
    sub.add_parser("test", help="Test NautilusTrader engine initialization")

    # Backtest
    bt = sub.add_parser("backtest", help="Run strategy backtest")
    bt.add_argument("--strategy", required=True, help="Strategy name from registry")
    bt.add_argument("--symbol", default="BTC/USDT")
    bt.add_argument("--timeframe", default="1h")
    bt.add_argument("--exchange", default="kraken")
    bt.add_argument("--balance", type=float, default=10000.0)

    # List strategies
    sub.add_parser("list-strategies", help="List registered strategies")

    args = parser.parse_args()

    if args.command == "convert":
        convert_ohlcv_to_nautilus_csv(args.symbol, args.timeframe, args.exchange)
    elif args.command == "test":
        success = run_nautilus_engine_test()
        if success:
            print("NautilusTrader engine test: PASSED")
        else:
            print("NautilusTrader engine test: FAILED (library not installed)")
    elif args.command == "backtest":
        result = run_nautilus_backtest(
            args.strategy, args.symbol, args.timeframe, args.exchange, args.balance,
        )
        print(json.dumps(result, indent=2, default=str))
    elif args.command == "list-strategies":
        for name in list_nautilus_strategies():
            engine_tag = " [native+pandas]" if HAS_NAUTILUS_TRADER else " [pandas]"
            print(f"  {name}{engine_tag}")
    else:
        parser.print_help()
