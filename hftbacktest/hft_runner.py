"""
hftbacktest Runner
===================
Bridge between A1SI-AITP platform and hftbacktest HFT simulation.

Handles:
    - Converting OHLCV Parquet data to synthetic tick arrays
    - Configuring and running HFT backtests
    - Extracting performance results
"""

import json
import sys
import logging
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("hft_runner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CATALOG_DIR = PROJECT_ROOT / "hftbacktest" / "catalog"
CATALOG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR = PROJECT_ROOT / "hftbacktest" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
TICKS_DIR = PROJECT_ROOT / "data" / "ticks"
TICKS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = PROJECT_ROOT / "configs" / "platform_config.yaml"


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


def convert_ohlcv_to_hft_ticks(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    exchange: str = "kraken",
) -> Path:
    """
    Convert OHLCV Parquet data to synthetic tick numpy arrays.

    Generates 4 ticks per bar (O/H/L/C) with interpolated timestamps.
    This is a development approximation — real HFT requires actual tick data.

    Returns path to saved .npy file.
    """
    from common.data_pipeline.pipeline import load_ohlcv, to_hftbacktest_ticks

    df = load_ohlcv(symbol, timeframe, exchange)
    if df.empty:
        logger.error(f"No data for {symbol} {timeframe}")
        return None

    logger.info(f"Converting {len(df)} bars to synthetic ticks...")
    tick_array = to_hftbacktest_ticks(df, timeframe)

    safe_symbol = symbol.replace("/", "")
    output_path = TICKS_DIR / f"{exchange}_{safe_symbol}_{timeframe}_ticks.npy"
    np.save(output_path, tick_array)
    logger.info(f"Saved {len(tick_array)} ticks to {output_path}")
    return output_path


def list_hft_strategies() -> list[str]:
    """Return names of all registered HFT strategies."""
    from hftbacktest.strategies import STRATEGY_REGISTRY
    return list(STRATEGY_REGISTRY.keys())


def run_hft_backtest(
    strategy_name: str,
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    exchange: str = "kraken",
    latency_ns: int = 1_000_000,
    initial_balance: float = 10000.0,
) -> dict:
    """
    Run an HFT backtest using one of the registered strategies.

    Loads tick data (generating from OHLCV if needed), runs the strategy,
    and computes performance metrics.
    """
    from hftbacktest.strategies import STRATEGY_REGISTRY
    from common.metrics.performance import compute_performance_metrics, serialize_trades_df

    if strategy_name not in STRATEGY_REGISTRY:
        available = ", ".join(STRATEGY_REGISTRY.keys())
        return {"error": f"Unknown strategy '{strategy_name}'. Available: {available}"}

    # Load or generate tick data
    safe_symbol = symbol.replace("/", "")
    tick_path = TICKS_DIR / f"{exchange}_{safe_symbol}_{timeframe}_ticks.npy"

    if not tick_path.exists():
        logger.info("Tick data not found, generating from OHLCV...")
        tick_path = convert_ohlcv_to_hft_ticks(symbol, timeframe, exchange)
        if tick_path is None:
            return {"error": f"No data for {symbol} {timeframe} on {exchange}"}

    tick_array = np.load(tick_path)
    logger.info(f"Running HFT backtest: {strategy_name} on {len(tick_array)} ticks")

    # Build config: platform_config.yaml defaults → function args
    platform_cfg = _load_platform_config()
    hft_cfg = platform_cfg.get("hftbacktest", {})
    strategy_defaults = hft_cfg.get("strategies", {}).get(strategy_name, {})

    config = {
        "fee_rate": hft_cfg.get("fee_rate", 0.0002),
        **strategy_defaults,
        "initial_balance": initial_balance,
        "latency_ns": latency_ns,
    }

    # Instantiate strategy
    strategy_cls = STRATEGY_REGISTRY[strategy_name]
    strategy = strategy_cls(config=config)

    # Run
    strategy.run(tick_array)

    # Collect results
    trades_df = strategy.get_trades_df()
    metrics = compute_performance_metrics(trades_df)

    result = {
        "framework": "hftbacktest",
        "strategy": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "exchange": exchange,
        "initial_balance": initial_balance,
        "latency_ns": latency_ns,
        "ticks_processed": len(tick_array),
        "total_fills": len(strategy.fills),
        "final_position": strategy.position,
        "gross_pnl": round(strategy.gross_pnl, 2),
        "total_fees": round(strategy.total_fees, 4),
        "metrics": metrics,
        "trades": serialize_trades_df(trades_df),
    }

    # Save results
    result_path = RESULTS_DIR / f"{strategy_name}_{safe_symbol}_{timeframe}.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"Results saved to {result_path}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="hftbacktest Runner")
    sub = parser.add_subparsers(dest="command")

    # Convert data
    conv = sub.add_parser("convert", help="Convert OHLCV data to tick format")
    conv.add_argument("--symbol", default="BTC/USDT")
    conv.add_argument("--timeframe", default="1h")
    conv.add_argument("--exchange", default="kraken")

    # Backtest
    bt = sub.add_parser("backtest", help="Run HFT backtest")
    bt.add_argument("--strategy", required=True, help="Strategy name from registry")
    bt.add_argument("--symbol", default="BTC/USDT")
    bt.add_argument("--timeframe", default="1h")
    bt.add_argument("--exchange", default="kraken")
    bt.add_argument("--latency", type=int, default=1_000_000, help="Latency in nanoseconds")
    bt.add_argument("--balance", type=float, default=10000.0)

    # List strategies
    sub.add_parser("list-strategies", help="List registered strategies")

    # Test
    sub.add_parser("test", help="Test hftbacktest basic functionality")

    args = parser.parse_args()

    if args.command == "convert":
        convert_ohlcv_to_hft_ticks(args.symbol, args.timeframe, args.exchange)
    elif args.command == "backtest":
        result = run_hft_backtest(
            args.strategy, args.symbol, args.timeframe, args.exchange,
            args.latency, args.balance,
        )
        print(json.dumps(result, indent=2, default=str))
    elif args.command == "list-strategies":
        for name in list_hft_strategies():
            print(f"  {name}")
    elif args.command == "test":
        print("hftbacktest module: OK")
        strategies = list_hft_strategies()
        print(f"Registered strategies: {strategies}")
    else:
        parser.print_help()
