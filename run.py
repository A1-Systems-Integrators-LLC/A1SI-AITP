#!/usr/bin/env python3
"""
Crypto-Investor Platform Orchestrator
=======================================
Master CLI that coordinates all framework tiers:
    - Data Pipeline (shared OHLCV acquisition)
    - VectorBT Research (rapid strategy screening)
    - Freqtrade (crypto backtesting & live trading)
    - NautilusTrader (multi-asset execution)
    - Risk Management (global position/drawdown limits)

Usage:
    python run.py status                     # Show platform status
    python run.py data download              # Download market data
    python run.py data list                  # List available data
    python run.py research screen            # Run VectorBT strategy screens
    python run.py freqtrade backtest         # Run Freqtrade backtests
    python run.py freqtrade dry-run          # Start Freqtrade paper trading
    python run.py nautilus test              # Test NautilusTrader engine
    python run.py validate                   # Validate all framework installs
"""

import os
import subprocess
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

LOGO = r"""
  ╔══════════════════════════════════════════════════════╗
  ║         CRYPTO-INVESTOR PLATFORM v0.1.0              ║
  ║  Research → Backtest → Validate → Deploy             ║
  ╚══════════════════════════════════════════════════════╝
"""


def cmd_status():
    """Show platform status: installed frameworks, data, and config."""
    print(LOGO)
    print("=" * 56)
    print("  FRAMEWORK STATUS")
    print("=" * 56)

    frameworks = {
        "freqtrade": "freqtrade",
        "nautilus_trader": "nautilus_trader",
        "vectorbt": "vectorbt",
        "hftbacktest": "hftbacktest",
        "ccxt": "ccxt",
        "pandas": "pandas",
        "numpy": "numpy",
        "talib": "talib",
    }

    for display_name, module_name in frameworks.items():
        try:
            mod = __import__(module_name)
            version = getattr(mod, "__version__", "installed")
            print(f"  ✅ {display_name:20s} {version}")
        except ImportError:
            print(f"  ❌ {display_name:20s} NOT INSTALLED")

    # Check data
    print("\n" + "=" * 56)
    print("  DATA STATUS")
    print("=" * 56)
    data_dir = PROJECT_ROOT / "data" / "processed"
    parquet_files = list(data_dir.glob("*.parquet")) if data_dir.exists() else []
    print(f"  Parquet files: {len(parquet_files)}")
    for f in parquet_files[:10]:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"    {f.name} ({size_mb:.1f} MB)")
    if len(parquet_files) > 10:
        print(f"    ... and {len(parquet_files) - 10} more")

    # Check strategies
    print("\n" + "=" * 56)
    print("  STRATEGIES")
    print("=" * 56)
    strat_dir = PROJECT_ROOT / "freqtrade" / "user_data" / "strategies"
    strategies = list(strat_dir.glob("*.py")) if strat_dir.exists() else []
    for s in strategies:
        if not s.name.startswith("__"):
            print(f"  📊 {s.stem}")

    # Check research results
    results_dir = PROJECT_ROOT / "research" / "results"
    result_dirs = list(results_dir.iterdir()) if results_dir.exists() else []
    result_dirs = [d for d in result_dirs if d.is_dir()]
    print(f"\n  Research result sets: {len(result_dirs)}")

    # Config check
    print("\n" + "=" * 56)
    print("  CONFIGURATION")
    print("=" * 56)
    config_file = PROJECT_ROOT / "configs" / "platform_config.yaml"
    ft_config = PROJECT_ROOT / "freqtrade" / "config.json"
    print(f"  Platform config: {'✅' if config_file.exists() else '❌'} {config_file}")
    print(f"  Freqtrade config: {'✅' if ft_config.exists() else '❌'} {ft_config}")

    # Environment variables
    env_keys = ["BINANCE_API_KEY", "BYBIT_API_KEY", "TELEGRAM_BOT_TOKEN"]
    print(f"\n  Environment:")
    for key in env_keys:
        status = "✅ set" if os.environ.get(key) else "⚠️  not set"
        print(f"    {key}: {status}")

    print()


def cmd_validate():
    """Validate all framework installations with import tests."""
    print(LOGO)
    print("Running framework validation...\n")

    tests = [
        ("freqtrade", "from freqtrade.strategy import IStrategy; print('Freqtrade IStrategy: OK')"),
        ("nautilus_trader", "from nautilus_trader.backtest.engine import BacktestEngine; print('NautilusTrader BacktestEngine: OK')"),
        ("vectorbt", "import vectorbt as vbt; print(f'VectorBT Portfolio: OK')"),
        ("ccxt", "import ccxt; e = ccxt.binance(); print(f'CCXT Binance: OK, {len(e.describe()[\"api\"])} API groups')"),
        ("pandas+numpy", "import pandas as pd; import numpy as np; print(f'Pandas {pd.__version__}, NumPy {np.__version__}: OK')"),
        ("talib", "import talib; print(f'TA-Lib functions: {len(talib.get_functions())} available')"),
        ("indicators", "from common.indicators.technical import add_all_indicators; print('Shared indicators: OK')"),
        ("data_pipeline", "from common.data_pipeline.pipeline import fetch_ohlcv, load_ohlcv; print('Data pipeline: OK')"),
        ("risk_manager", "from common.risk.risk_manager import RiskManager; rm = RiskManager(); print(f'Risk manager: OK, limits={rm.limits}')"),
    ]

    passed = 0
    failed = 0
    for name, code in tests:
        try:
            exec(code)
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)} tests")
    return failed == 0


def cmd_data(args):
    """Data pipeline commands."""
    from common.data_pipeline.pipeline import (
        download_watchlist, list_available_data, load_ohlcv, fetch_ohlcv, save_ohlcv
    )

    if args.data_command == "download":
        symbols = args.symbols.split(",") if args.symbols else None
        timeframes = args.timeframes.split(",") if args.timeframes else None
        results = download_watchlist(
            symbols=symbols,
            timeframes=timeframes,
            exchange_id=args.exchange,
            since_days=args.days,
        )
        print(f"\nDownload complete: {len(results)} items processed")
        for k, v in results.items():
            print(f"  {k}: {v['status']} ({v.get('rows', 'N/A')} rows)")

    elif args.data_command == "list":
        available = list_available_data()
        if available.empty:
            print("No data files found. Run: python run.py data download")
        else:
            print(available.to_string(index=False))

    elif args.data_command == "info":
        df = load_ohlcv(args.symbol, args.timeframe, args.exchange)
        if df.empty:
            print(f"No data for {args.symbol} {args.timeframe}")
        else:
            print(f"Symbol:    {args.symbol}")
            print(f"Timeframe: {args.timeframe}")
            print(f"Rows:      {len(df)}")
            print(f"Start:     {df.index.min()}")
            print(f"End:       {df.index.max()}")
            print(f"\n{df.describe().to_string()}")

    elif args.data_command == "generate-sample":
        _generate_sample_data()
    else:
        print("Usage: python run.py data {download|list|info|generate-sample}")


def _generate_sample_data():
    """Generate synthetic OHLCV data for testing without exchange access."""
    import numpy as np
    import pandas as pd
    from common.data_pipeline.pipeline import save_ohlcv

    print("Generating synthetic sample data for testing...")

    np.random.seed(42)
    days = 365
    periods = days * 24  # 1h candles

    for symbol, start_price in [
        ("BTC/USDT", 42000), ("ETH/USDT", 2200), ("SOL/USDT", 95),
        ("BNB/USDT", 310), ("XRP/USDT", 0.55),
    ]:
        timestamps = pd.date_range(
            end=datetime.now(), periods=periods, freq="1h", tz="UTC"
        )

        # Generate realistic price movement with drift and volatility
        returns = np.random.normal(0.00002, 0.015, periods)  # slight upward drift
        prices = start_price * np.exp(np.cumsum(returns))

        # Generate OHLCV
        noise = np.random.uniform(0.995, 1.005, periods)
        opens = prices * noise
        highs = prices * np.random.uniform(1.001, 1.025, periods)
        lows = prices * np.random.uniform(0.975, 0.999, periods)
        closes = prices
        volumes = np.random.lognormal(mean=15, sigma=1.5, size=periods)

        df = pd.DataFrame({
            "open": opens,
            "high": np.maximum(highs, np.maximum(opens, closes)),
            "low": np.minimum(lows, np.minimum(opens, closes)),
            "close": closes,
            "volume": volumes,
        }, index=timestamps)

        for tf, resample_rule in [("1h", None), ("4h", "4h"), ("1d", "1D")]:
            if resample_rule:
                resampled = df.resample(resample_rule).agg({
                    "open": "first", "high": "max", "low": "min",
                    "close": "last", "volume": "sum",
                }).dropna()
            else:
                resampled = df

            path = save_ohlcv(resampled, symbol, tf, "binance")
            print(f"  ✅ {symbol} {tf}: {len(resampled)} rows → {path.name}")

    print("\nSample data generation complete!")


def cmd_research(args):
    """VectorBT research commands."""
    if args.research_command == "screen":
        from research.scripts.vbt_screener import run_full_screen
        results = run_full_screen(
            symbol=args.symbol,
            timeframe=args.timeframe,
            exchange=args.exchange,
            fees=args.fees,
        )
        if results:
            print("\n=== SCREENING SUMMARY ===")
            for name, df in results.items():
                if hasattr(df, '__len__') and len(df) > 0:
                    top = df.head(1)
                    sr = top["sharpe_ratio"].iloc[0] if "sharpe_ratio" in top.columns else "N/A"
                    ret = top["total_return"].iloc[0] if "total_return" in top.columns else "N/A"
                    print(f"  {name}: Best Sharpe={sr:.3f}, Return={ret:.2%}" if isinstance(sr, float) else f"  {name}: {sr}")
    else:
        print("Usage: python run.py research screen [--symbol BTC/USDT] [--timeframe 1h]")


def cmd_freqtrade(args):
    """Freqtrade commands."""
    ft_config = PROJECT_ROOT / "freqtrade" / "config.json"

    if args.ft_command == "backtest":
        strategy = args.strategy or "CryptoInvestorV1"
        timerange = args.timerange or ""
        cmd = [
            sys.executable, "-m", "freqtrade", "backtesting",
            "--config", str(ft_config),
            "--strategy", strategy,
            "--strategy-path", str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies"),
            "--datadir", str(PROJECT_ROOT / "data" / "processed"),
        ]
        if timerange:
            cmd.extend(["--timerange", timerange])

        print(f"Running Freqtrade backtest: {strategy}")
        print(f"Command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        return result.returncode

    elif args.ft_command == "dry-run":
        cmd = [
            sys.executable, "-m", "freqtrade", "trade",
            "--config", str(ft_config),
            "--strategy", args.strategy or "CryptoInvestorV1",
            "--strategy-path", str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies"),
        ]
        print(f"Starting Freqtrade dry-run (paper trading)...")
        print(f"Command: {' '.join(cmd)}")
        print("Press Ctrl+C to stop.\n")
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        return result.returncode

    elif args.ft_command == "hyperopt":
        strategy = args.strategy or "CryptoInvestorV1"
        epochs = args.epochs or 100
        cmd = [
            sys.executable, "-m", "freqtrade", "hyperopt",
            "--config", str(ft_config),
            "--strategy", strategy,
            "--strategy-path", str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies"),
            "--hyperopt-loss", "SharpeHyperOptLossDaily",
            "--epochs", str(epochs),
            "-j", "2",
        ]
        print(f"Running hyperopt for {strategy} ({epochs} epochs)...")
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        return result.returncode

    elif args.ft_command == "list-strategies":
        strat_dir = PROJECT_ROOT / "freqtrade" / "user_data" / "strategies"
        for f in strat_dir.glob("*.py"):
            if not f.name.startswith("__"):
                print(f"  📊 {f.stem}")

    else:
        print("Usage: python run.py freqtrade {backtest|dry-run|hyperopt|list-strategies}")


def cmd_nautilus(args):
    """NautilusTrader commands."""
    if args.nt_command == "test":
        from nautilus.nautilus_runner import run_nautilus_backtest_example
        engine = run_nautilus_backtest_example()
        if engine:
            print("✅ NautilusTrader engine initialized successfully")
        else:
            print("❌ NautilusTrader engine failed to initialize")

    elif args.nt_command == "convert":
        from nautilus.nautilus_runner import convert_ohlcv_to_nautilus_csv
        path = convert_ohlcv_to_nautilus_csv(args.symbol, args.timeframe, args.exchange)
        if path:
            print(f"✅ Data converted: {path}")

    else:
        print("Usage: python run.py nautilus {test|convert}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Crypto-Investor Platform Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py status                          Show platform status
  python run.py validate                        Validate all installs
  python run.py data generate-sample            Generate test data
  python run.py data download --symbols BTC/USDT,ETH/USDT
  python run.py research screen --symbol BTC/USDT
  python run.py freqtrade backtest --strategy CryptoInvestorV1
  python run.py freqtrade dry-run
  python run.py nautilus test
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # Status
    sub.add_parser("status", help="Show platform status")

    # Validate
    sub.add_parser("validate", help="Validate all framework installations")

    # Data
    data_parser = sub.add_parser("data", help="Data pipeline commands")
    data_sub = data_parser.add_subparsers(dest="data_command")
    dl = data_sub.add_parser("download", help="Download OHLCV data")
    dl.add_argument("--symbols", default=None, help="Comma-separated symbols")
    dl.add_argument("--timeframes", default=None, help="Comma-separated timeframes")
    dl.add_argument("--exchange", default="binance")
    dl.add_argument("--days", type=int, default=365)
    data_sub.add_parser("list", help="List available data")
    info = data_sub.add_parser("info", help="Show data file info")
    info.add_argument("symbol")
    info.add_argument("--timeframe", default="1h")
    info.add_argument("--exchange", default="binance")
    data_sub.add_parser("generate-sample", help="Generate synthetic test data")

    # Research
    res_parser = sub.add_parser("research", help="VectorBT research commands")
    res_sub = res_parser.add_subparsers(dest="research_command")
    scr = res_sub.add_parser("screen", help="Run strategy screener")
    scr.add_argument("--symbol", default="BTC/USDT")
    scr.add_argument("--timeframe", default="1h")
    scr.add_argument("--exchange", default="binance")
    scr.add_argument("--fees", type=float, default=0.001)

    # Freqtrade
    ft_parser = sub.add_parser("freqtrade", help="Freqtrade commands")
    ft_sub = ft_parser.add_subparsers(dest="ft_command")
    bt = ft_sub.add_parser("backtest", help="Run backtest")
    bt.add_argument("--strategy", default="CryptoInvestorV1")
    bt.add_argument("--timerange", default="")
    dr = ft_sub.add_parser("dry-run", help="Start paper trading")
    dr.add_argument("--strategy", default="CryptoInvestorV1")
    ho = ft_sub.add_parser("hyperopt", help="Optimize strategy parameters")
    ho.add_argument("--strategy", default="CryptoInvestorV1")
    ho.add_argument("--epochs", type=int, default=100)
    ft_sub.add_parser("list-strategies", help="List available strategies")

    # NautilusTrader
    nt_parser = sub.add_parser("nautilus", help="NautilusTrader commands")
    nt_sub = nt_parser.add_subparsers(dest="nt_command")
    nt_sub.add_parser("test", help="Test engine initialization")
    nt_conv = nt_sub.add_parser("convert", help="Convert data to Nautilus format")
    nt_conv.add_argument("--symbol", default="BTC/USDT")
    nt_conv.add_argument("--timeframe", default="1h")
    nt_conv.add_argument("--exchange", default="binance")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "validate":
        cmd_validate()
    elif args.command == "data":
        cmd_data(args)
    elif args.command == "research":
        cmd_research(args)
    elif args.command == "freqtrade":
        cmd_freqtrade(args)
    elif args.command == "nautilus":
        cmd_nautilus(args)
    else:
        print(LOGO)
        parser.print_help()


if __name__ == "__main__":
    main()
