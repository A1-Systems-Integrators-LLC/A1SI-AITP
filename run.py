#!/usr/bin/env python3
"""
A1SI-AITP Platform Orchestrator
=================================
Master CLI that coordinates all framework tiers:
    - Data Pipeline (shared OHLCV acquisition)
    - VectorBT Research (rapid strategy screening)
    - Freqtrade (crypto backtesting & live trading)
    - NautilusTrader (multi-asset execution)
    - hftbacktest (HFT simulation)
    - ML Pipeline (feature engineering, training, prediction)
    - Risk Management (global position/drawdown limits)

Usage:
    python run.py status                     # Show platform status
    python run.py data download              # Download market data
    python run.py data list                  # List available data
    python run.py research screen            # Run VectorBT strategy screens
    python run.py freqtrade backtest         # Run Freqtrade backtests
    python run.py freqtrade dry-run          # Start Freqtrade paper trading
    python run.py nautilus test              # Test NautilusTrader engine
    python run.py nautilus backtest          # Run NautilusTrader backtest
    python run.py nautilus list-strategies   # List Nautilus strategies
    python run.py hft backtest              # Run HFT backtest
    python run.py hft list-strategies       # List HFT strategies
    python run.py ml train                  # Train ML model
    python run.py ml list-models            # List trained models
    python run.py ml predict                # Run prediction
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
  ║            A1SI-AITP PLATFORM v0.1.0                 ║
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
            print(f"  📊 Freqtrade: {s.stem}")

    # Nautilus strategies
    try:
        from nautilus.strategies import STRATEGY_REGISTRY as NT_REG
        for name in NT_REG:
            print(f"  📊 Nautilus: {name}")
    except ImportError:
        pass

    # HFT strategies
    try:
        from hftbacktest.strategies import STRATEGY_REGISTRY as HFT_REG
        for name in HFT_REG:
            print(f"  📊 HFT: {name}")
    except ImportError:
        pass

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
    print("\n  Environment:")
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
        ("nautilus_strategies", "from nautilus.strategies import STRATEGY_REGISTRY; assert len(STRATEGY_REGISTRY) >= 3; print(f'Nautilus strategies: {len(STRATEGY_REGISTRY)} registered')"),
        ("vectorbt", "import vectorbt as vbt; print(f'VectorBT Portfolio: OK')"),
        ("hftbacktest_module", "from hftbacktest.strategies import STRATEGY_REGISTRY; assert len(STRATEGY_REGISTRY) >= 1; print(f'HFT strategies: {len(STRATEGY_REGISTRY)} registered')"),
        ("ccxt", "import ccxt; e = ccxt.binance(); print(f'CCXT Binance: OK, {len(e.describe()[\"api\"])} API groups')"),
        ("pandas+numpy", "import pandas as pd; import numpy as np; print(f'Pandas {pd.__version__}, NumPy {np.__version__}: OK')"),
        ("talib", "import talib; print(f'TA-Lib functions: {len(talib.get_functions())} available')"),
        ("ml_features", "from common.ml.features import build_feature_matrix; print('ML features: OK')"),
        ("ml_trainer", "from common.ml.trainer import HAS_LIGHTGBM; print(f'ML trainer: OK (lightgbm={HAS_LIGHTGBM})')"),
        ("ml_registry", "from common.ml.registry import ModelRegistry; print('ML registry: OK')"),
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
        download_watchlist, list_available_data, load_ohlcv
    )

    if args.data_command == "download":
        symbols = args.symbols.split(",") if args.symbols else None
        timeframes = args.timeframes.split(",") if args.timeframes else None
        asset_class = getattr(args, "asset_class", "crypto")
        results = download_watchlist(
            symbols=symbols,
            timeframes=timeframes,
            exchange_id=args.exchange,
            since_days=args.days,
            asset_class=asset_class,
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

            path = save_ohlcv(resampled, symbol, tf, "kraken")
            print(f"  ✅ {symbol} {tf}: {len(resampled)} rows → {path.name}")

    print("\nSample data generation complete!")


def cmd_research(args):
    """VectorBT research commands."""
    if args.research_command == "screen":
        from research.scripts.vbt_screener import run_full_screen
        asset_class = getattr(args, "asset_class", "crypto")
        results = run_full_screen(
            symbol=args.symbol,
            timeframe=args.timeframe,
            exchange=args.exchange,
            fees=args.fees,
            asset_class=asset_class,
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
        print("Starting Freqtrade dry-run (paper trading)...")
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
        from nautilus.nautilus_runner import run_nautilus_engine_test
        success = run_nautilus_engine_test()
        if success:
            print("✅ NautilusTrader engine initialized successfully")
        else:
            print("❌ NautilusTrader engine not available (install with: pip install nautilus_trader)")

    elif args.nt_command == "convert":
        from nautilus.nautilus_runner import convert_ohlcv_to_nautilus_csv
        path = convert_ohlcv_to_nautilus_csv(args.symbol, args.timeframe, args.exchange)
        if path:
            print(f"✅ Data converted: {path}")

    elif args.nt_command == "backtest":
        from nautilus.nautilus_runner import run_nautilus_backtest
        asset_class = getattr(args, "asset_class", "crypto")
        result = run_nautilus_backtest(
            args.strategy, args.symbol, args.timeframe, args.exchange, args.balance,
            asset_class=asset_class,
        )
        print(json.dumps(result, indent=2, default=str))

    elif args.nt_command == "list-strategies":
        from nautilus.nautilus_runner import list_nautilus_strategies
        for name in list_nautilus_strategies():
            print(f"  📊 {name}")

    else:
        print("Usage: python run.py nautilus {test|convert|backtest|list-strategies}")


def cmd_ml(args):
    """ML pipeline commands."""
    if args.ml_command == "train":
        from common.ml.features import build_feature_matrix
        from common.ml.registry import ModelRegistry
        from common.ml.trainer import train_model
        from common.data_pipeline.pipeline import load_ohlcv

        symbol = args.symbol
        timeframe = args.timeframe
        exchange = args.exchange

        print(f"Loading data: {symbol} {timeframe} ({exchange})...")
        df = load_ohlcv(symbol, timeframe, exchange)
        if df.empty:
            print(f"❌ No data for {symbol} {timeframe}. Run: python run.py data generate-sample")
            return

        print(f"Building features from {len(df)} bars...")
        x_feat, y_target, feature_names = build_feature_matrix(df)
        print(f"Feature matrix: {len(x_feat)} rows x {len(feature_names)} features")

        if len(x_feat) < 100:
            print(f"❌ Insufficient data: {len(x_feat)} rows (need >= 100)")
            return

        print("Training LightGBM model...")
        result = train_model(x_feat, y_target, feature_names, test_ratio=args.test_ratio)

        registry = ModelRegistry()
        model_id = registry.save_model(
            model=result["model"],
            metrics=result["metrics"],
            metadata=result["metadata"],
            feature_importance=result["feature_importance"],
            symbol=symbol,
            timeframe=timeframe,
        )

        print(f"\n✅ Model trained and saved: {model_id}")
        print(f"  Accuracy:  {result['metrics']['accuracy']:.4f}")
        print(f"  Precision: {result['metrics']['precision']:.4f}")
        print(f"  F1 Score:  {result['metrics']['f1']:.4f}")
        print(f"  Log Loss:  {result['metrics']['logloss']:.6f}")

        # Show top features
        top = sorted(result["feature_importance"].items(), key=lambda x: x[1], reverse=True)[:5]
        print("\n  Top features:")
        for name, score in top:
            print(f"    {name}: {score:.0f}")

    elif args.ml_command == "list-models":
        from common.ml.registry import ModelRegistry

        registry = ModelRegistry()
        models = registry.list_models()
        if not models:
            print("No trained models found. Run: python run.py ml train")
            return

        print(f"\n{'Model ID':<40} {'Symbol':<12} {'TF':<6} {'Acc':<8} {'F1':<8} {'Created'}")
        print("-" * 90)
        for m in models:
            metrics = m.get("metrics", {})
            print(
                f"{m['model_id']:<40} {m.get('symbol', ''):<12} {m.get('timeframe', ''):<6} "
                f"{metrics.get('accuracy', 0):<8.4f} {metrics.get('f1', 0):<8.4f} "
                f"{m.get('created_at', '')[:19]}"
            )

    elif args.ml_command == "predict":
        from common.ml.features import build_feature_matrix
        from common.ml.registry import ModelRegistry
        from common.ml.trainer import predict
        from common.data_pipeline.pipeline import load_ohlcv

        model_id = args.model_id
        if not model_id:
            # Use latest model
            registry = ModelRegistry()
            models = registry.list_models()
            if not models:
                print("❌ No models found. Run: python run.py ml train")
                return
            model_id = models[0]["model_id"]
            print(f"Using latest model: {model_id}")

        registry = ModelRegistry()
        try:
            model, manifest = registry.load_model(model_id)
        except FileNotFoundError:
            print(f"❌ Model not found: {model_id}")
            return

        symbol = args.symbol
        timeframe = args.timeframe
        exchange = args.exchange

        df = load_ohlcv(symbol, timeframe, exchange)
        if df.empty:
            print(f"❌ No data for {symbol} {timeframe}")
            return

        x_feat, _y, _names = build_feature_matrix(df)
        x_recent = x_feat.tail(args.bars)

        result = predict(model, x_recent)
        print(f"\nPrediction ({model_id}):")
        print(f"  Symbol:       {symbol} {timeframe}")
        print(f"  Bars:         {result['n_bars']}")
        print(f"  Mean P(up):   {result['mean_probability']:.4f}")
        print(f"  Predicted up: {result['predicted_up_pct']:.1f}%")

    else:
        print("Usage: python run.py ml {train|list-models|predict}")


def cmd_hft(args):
    """hftbacktest commands."""
    if args.hft_command == "backtest":
        from hftbacktest.hft_runner import run_hft_backtest
        result = run_hft_backtest(
            args.strategy, args.symbol, args.timeframe, args.exchange,
            args.latency, args.balance,
        )
        print(json.dumps(result, indent=2, default=str))

    elif args.hft_command == "convert":
        from hftbacktest.hft_runner import convert_ohlcv_to_hft_ticks
        path = convert_ohlcv_to_hft_ticks(args.symbol, args.timeframe, args.exchange)
        if path:
            print(f"✅ Tick data generated: {path}")

    elif args.hft_command == "list-strategies":
        from hftbacktest.hft_runner import list_hft_strategies
        for name in list_hft_strategies():
            print(f"  📊 {name}")

    elif args.hft_command == "test":
        from hftbacktest.hft_runner import list_hft_strategies
        strategies = list_hft_strategies()
        print(f"✅ hftbacktest module loaded, {len(strategies)} strategies registered")

    else:
        print("Usage: python run.py hft {backtest|convert|list-strategies|test}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="A1SI-AITP Platform Orchestrator",
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
  python run.py nautilus backtest --strategy NautilusTrendFollowing
  python run.py nautilus list-strategies
  python run.py hft backtest --strategy MarketMaker
  python run.py hft list-strategies
  python run.py ml train --symbol BTC/USDT
  python run.py ml list-models
  python run.py ml predict --model-id <id>
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
    dl.add_argument("--exchange", default="kraken")
    dl.add_argument("--days", type=int, default=365)
    dl.add_argument("--asset-class", default="crypto", choices=["crypto", "equity", "forex"],
                    dest="asset_class", help="Asset class")
    data_sub.add_parser("list", help="List available data")
    info = data_sub.add_parser("info", help="Show data file info")
    info.add_argument("symbol")
    info.add_argument("--timeframe", default="1h")
    info.add_argument("--exchange", default="kraken")
    data_sub.add_parser("generate-sample", help="Generate synthetic test data")

    # Research
    res_parser = sub.add_parser("research", help="VectorBT research commands")
    res_sub = res_parser.add_subparsers(dest="research_command")
    scr = res_sub.add_parser("screen", help="Run strategy screener")
    scr.add_argument("--symbol", default="BTC/USDT")
    scr.add_argument("--timeframe", default="1h")
    scr.add_argument("--exchange", default="kraken")
    scr.add_argument("--fees", type=float, default=None)
    scr.add_argument("--asset-class", default="crypto", choices=["crypto", "equity", "forex"],
                    dest="asset_class", help="Asset class")

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
    nt_conv.add_argument("--exchange", default="kraken")
    nt_bt = nt_sub.add_parser("backtest", help="Run NautilusTrader backtest")
    nt_bt.add_argument("--strategy", required=True, help="Strategy name from registry")
    nt_bt.add_argument("--symbol", default="BTC/USDT")
    nt_bt.add_argument("--timeframe", default="1h")
    nt_bt.add_argument("--exchange", default="kraken")
    nt_bt.add_argument("--balance", type=float, default=10000.0)
    nt_bt.add_argument("--asset-class", default="crypto", choices=["crypto", "equity", "forex"],
                       dest="asset_class", help="Asset class")
    nt_sub.add_parser("list-strategies", help="List registered strategies")

    # ML pipeline
    ml_parser = sub.add_parser("ml", help="ML pipeline commands")
    ml_sub = ml_parser.add_subparsers(dest="ml_command")
    ml_train = ml_sub.add_parser("train", help="Train ML model")
    ml_train.add_argument("--symbol", default="BTC/USDT")
    ml_train.add_argument("--timeframe", default="1h")
    ml_train.add_argument("--exchange", default="kraken")
    ml_train.add_argument("--test-ratio", type=float, default=0.2)
    ml_sub.add_parser("list-models", help="List trained models")
    ml_pred = ml_sub.add_parser("predict", help="Run prediction")
    ml_pred.add_argument("--model-id", default="", dest="model_id")
    ml_pred.add_argument("--symbol", default="BTC/USDT")
    ml_pred.add_argument("--timeframe", default="1h")
    ml_pred.add_argument("--exchange", default="kraken")
    ml_pred.add_argument("--bars", type=int, default=50)

    # hftbacktest
    hft_parser = sub.add_parser("hft", help="hftbacktest commands")
    hft_sub = hft_parser.add_subparsers(dest="hft_command")
    hft_bt = hft_sub.add_parser("backtest", help="Run HFT backtest")
    hft_bt.add_argument("--strategy", required=True, help="Strategy name from registry")
    hft_bt.add_argument("--symbol", default="BTC/USDT")
    hft_bt.add_argument("--timeframe", default="1h")
    hft_bt.add_argument("--exchange", default="kraken")
    hft_bt.add_argument("--latency", type=int, default=1_000_000, help="Latency in ns")
    hft_bt.add_argument("--balance", type=float, default=10000.0)
    hft_conv = hft_sub.add_parser("convert", help="Convert OHLCV to tick data")
    hft_conv.add_argument("--symbol", default="BTC/USDT")
    hft_conv.add_argument("--timeframe", default="1h")
    hft_conv.add_argument("--exchange", default="kraken")
    hft_sub.add_parser("list-strategies", help="List registered strategies")
    hft_sub.add_parser("test", help="Test hftbacktest module")

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
    elif args.command == "ml":
        cmd_ml(args)
    elif args.command == "hft":
        cmd_hft(args)
    else:
        print(LOGO)
        parser.print_help()


if __name__ == "__main__":
    main()
