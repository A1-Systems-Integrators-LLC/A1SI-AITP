"""
Tests for NautilusTrader Runner and Engine
==========================================
Covers: CLI argument parsing, engine creation, venue setup,
instrument factories, bar type building, data conversion,
strategy registry, error handling, and result persistence.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Helpers ──────────────────────────────────────────


def _make_ohlcv(n: int = 300, start_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data with valid price constraints."""
    np.random.seed(42)
    timestamps = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    returns = np.random.normal(0.0001, 0.01, n)
    prices = start_price * np.exp(np.cumsum(returns))
    noise = np.random.uniform(0.998, 1.002, n)
    open_prices = prices * noise
    close_prices = prices
    high_prices = np.maximum(open_prices, close_prices) * np.random.uniform(1.001, 1.02, n)
    low_prices = np.minimum(open_prices, close_prices) * np.random.uniform(0.98, 0.999, n)
    return pd.DataFrame(
        {
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "volume": np.random.lognormal(10, 1, n),
        },
        index=timestamps,
    )


# ── CLI Argument Parsing Tests ───────────────────────


class TestRunnerCLI:
    """Test the argparse CLI in nautilus_runner."""

    def test_backtest_command_parses_defaults(self):
        """Backtest subcommand should set default values."""
        import argparse

        from nautilus.nautilus_runner import __name__ as _  # ensure module loads

        # Re-create the parser logic from the module
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        bt = sub.add_parser("backtest")
        bt.add_argument("--strategy", required=True)
        bt.add_argument("--symbol", default="BTC/USDT")
        bt.add_argument("--timeframe", default="1h")
        bt.add_argument("--exchange", default="kraken")
        bt.add_argument("--balance", type=float, default=10000.0)
        bt.add_argument(
            "--asset-class",
            choices=["crypto", "equity", "forex"],
            default="crypto",
        )

        args = parser.parse_args(["backtest", "--strategy", "NautilusTrendFollowing"])
        assert args.command == "backtest"
        assert args.strategy == "NautilusTrendFollowing"
        assert args.symbol == "BTC/USDT"
        assert args.timeframe == "1h"
        assert args.exchange == "kraken"
        assert args.balance == 10000.0
        assert args.asset_class == "crypto"

    def test_backtest_command_parses_custom_args(self):
        """Backtest subcommand should accept overrides."""
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        bt = sub.add_parser("backtest")
        bt.add_argument("--strategy", required=True)
        bt.add_argument("--symbol", default="BTC/USDT")
        bt.add_argument("--timeframe", default="1h")
        bt.add_argument("--exchange", default="kraken")
        bt.add_argument("--balance", type=float, default=10000.0)
        bt.add_argument(
            "--asset-class",
            choices=["crypto", "equity", "forex"],
            default="crypto",
        )

        args = parser.parse_args([
            "backtest",
            "--strategy", "EquityMomentum",
            "--symbol", "AAPL/USD",
            "--timeframe", "1d",
            "--exchange", "NYSE",
            "--balance", "50000",
            "--asset-class", "equity",
        ])
        assert args.strategy == "EquityMomentum"
        assert args.symbol == "AAPL/USD"
        assert args.timeframe == "1d"
        assert args.exchange == "NYSE"
        assert args.balance == 50000.0
        assert args.asset_class == "equity"

    def test_convert_command_parses(self):
        """Convert subcommand should parse symbol/timeframe/exchange."""
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        conv = sub.add_parser("convert")
        conv.add_argument("--symbol", default="BTC/USDT")
        conv.add_argument("--timeframe", default="1h")
        conv.add_argument("--exchange", default="kraken")

        args = parser.parse_args(["convert", "--symbol", "ETH/USDT", "--timeframe", "4h"])
        assert args.command == "convert"
        assert args.symbol == "ETH/USDT"
        assert args.timeframe == "4h"
        assert args.exchange == "kraken"

    def test_list_strategies_command(self):
        """list-strategies subcommand should parse without arguments."""
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        sub.add_parser("list-strategies")

        args = parser.parse_args(["list-strategies"])
        assert args.command == "list-strategies"

    def test_invalid_asset_class_rejected(self):
        """Invalid asset class choice should raise SystemExit."""
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        bt = sub.add_parser("backtest")
        bt.add_argument("--strategy", required=True)
        bt.add_argument(
            "--asset-class",
            choices=["crypto", "equity", "forex"],
            default="crypto",
        )

        with pytest.raises(SystemExit):
            parser.parse_args(["backtest", "--strategy", "X", "--asset-class", "bonds"])


# ── Timeframe Mapping Tests ─────────────────────────


class TestTimeframeMapping:
    """Test _tf_to_nautilus and _parse_bar_spec mappings."""

    def test_tf_to_nautilus_known_timeframes(self):
        from nautilus.nautilus_runner import _tf_to_nautilus

        assert _tf_to_nautilus("1m") == "1-MINUTE"
        assert _tf_to_nautilus("5m") == "5-MINUTE"
        assert _tf_to_nautilus("15m") == "15-MINUTE"
        assert _tf_to_nautilus("1h") == "1-HOUR"
        assert _tf_to_nautilus("4h") == "4-HOUR"
        assert _tf_to_nautilus("1d") == "1-DAY"

    def test_tf_to_nautilus_unknown_defaults_to_hour(self):
        from nautilus.nautilus_runner import _tf_to_nautilus

        assert _tf_to_nautilus("2h") == "1-HOUR"
        assert _tf_to_nautilus("unknown") == "1-HOUR"

    def test_parse_bar_spec_known(self):
        from nautilus.engine import _parse_bar_spec

        assert _parse_bar_spec("1m") == (1, "MINUTE")
        assert _parse_bar_spec("1h") == (1, "HOUR")
        assert _parse_bar_spec("1d") == (1, "DAY")
        assert _parse_bar_spec("5m") == (5, "MINUTE")
        assert _parse_bar_spec("4h") == (4, "HOUR")

    def test_parse_bar_spec_unknown_defaults(self):
        from nautilus.engine import _parse_bar_spec

        assert _parse_bar_spec("3h") == (1, "HOUR")
        assert _parse_bar_spec("") == (1, "HOUR")


# ── Engine Creation Tests ────────────────────────────


class TestEngineCreation:
    """Test create_backtest_engine with different options."""

    def test_create_engine_default_config(self):
        from nautilus.engine import create_backtest_engine

        engine = create_backtest_engine()
        assert engine is not None
        engine.dispose()

    def test_create_engine_custom_trader_id(self):
        from nautilus.engine import create_backtest_engine

        engine = create_backtest_engine(trader_id="TEST-TRADER-001")
        assert engine is not None
        engine.dispose()

    def test_create_engine_custom_log_level(self):
        from nautilus.engine import create_backtest_engine

        engine = create_backtest_engine(log_level="ERROR")
        assert engine is not None
        engine.dispose()


# ── Venue Setup Tests ────────────────────────────────


class TestVenueSetup:
    """Test add_venue with various configurations."""

    def test_add_venue_default(self):
        from nautilus.engine import add_venue, create_backtest_engine

        engine = create_backtest_engine(log_level="WARNING")
        venue = add_venue(engine, "KRAKEN", starting_balance=5000.0)
        assert venue is not None
        assert str(venue) == "KRAKEN"
        engine.dispose()

    def test_add_venue_custom_balance(self):
        from nautilus.engine import add_venue, create_backtest_engine

        engine = create_backtest_engine(log_level="WARNING")
        venue = add_venue(engine, "BINANCE", starting_balance=100000.0)
        assert venue is not None
        engine.dispose()

    def test_add_venue_for_crypto(self):
        from nautilus.engine import add_venue_for_asset_class, create_backtest_engine

        engine = create_backtest_engine(log_level="WARNING")
        venue = add_venue_for_asset_class(engine, "crypto", starting_balance=10000.0)
        assert str(venue) == "BINANCE"
        engine.dispose()

    def test_add_venue_for_equity(self):
        from nautilus.engine import add_venue_for_asset_class, create_backtest_engine

        engine = create_backtest_engine(log_level="WARNING")
        venue = add_venue_for_asset_class(engine, "equity", starting_balance=50000.0)
        assert str(venue) == "NYSE"
        engine.dispose()

    def test_add_venue_for_forex(self):
        from nautilus.engine import add_venue_for_asset_class, create_backtest_engine

        engine = create_backtest_engine(log_level="WARNING")
        venue = add_venue_for_asset_class(engine, "forex", starting_balance=10000.0)
        assert str(venue) == "FXCM"
        engine.dispose()

    def test_add_venue_for_unknown_asset_class_defaults_to_binance(self):
        from nautilus.engine import add_venue_for_asset_class, create_backtest_engine

        engine = create_backtest_engine(log_level="WARNING")
        venue = add_venue_for_asset_class(engine, "commodities", starting_balance=10000.0)
        assert str(venue) == "BINANCE"
        engine.dispose()


# ── Instrument Creation Tests ────────────────────────


class TestInstrumentCreation:
    """Test crypto/equity/forex instrument factories."""

    def test_create_crypto_instrument_btc(self):
        from nautilus.engine import create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "KRAKEN")
        assert "BTCUSDT" in str(inst.id)
        assert "KRAKEN" in str(inst.id)
        assert inst.price_precision == 2
        assert inst.size_precision == 6

    def test_create_crypto_instrument_eth(self):
        from nautilus.engine import create_crypto_instrument

        inst = create_crypto_instrument("ETH/USDT", "BINANCE")
        assert "ETHUSDT" in str(inst.id)
        assert "BINANCE" in str(inst.id)

    def test_create_equity_instrument(self):
        from nautilus.engine import create_equity_instrument

        inst = create_equity_instrument("AAPL/USD", "NYSE")
        assert "AAPLUSD" in str(inst.id)
        assert "NYSE" in str(inst.id)
        assert inst.price_precision == 2
        assert inst.size_precision == 2

    def test_create_equity_instrument_zero_fees(self):
        from nautilus.engine import create_equity_instrument

        inst = create_equity_instrument("MSFT/USD", "NYSE")
        assert inst.maker_fee == Decimal("0.0")
        assert inst.taker_fee == Decimal("0.0")

    def test_create_forex_instrument(self):
        from nautilus.engine import create_forex_instrument

        inst = create_forex_instrument("EUR/USD", "FXCM")
        assert "EURUSD" in str(inst.id)
        assert "FXCM" in str(inst.id)
        assert inst.price_precision == 5
        assert inst.size_precision == 2

    def test_create_forex_instrument_fee(self):
        from nautilus.engine import create_forex_instrument

        inst = create_forex_instrument("GBP/JPY", "FXCM")
        assert inst.maker_fee == Decimal("0.00003")

    def test_create_instrument_for_asset_class_crypto(self):
        from nautilus.engine import create_instrument_for_asset_class

        inst = create_instrument_for_asset_class("BTC/USDT", "crypto")
        assert "BTCUSDT" in str(inst.id)
        assert inst.price_precision == 2
        assert inst.size_precision == 6

    def test_create_instrument_for_asset_class_equity(self):
        from nautilus.engine import create_instrument_for_asset_class

        inst = create_instrument_for_asset_class("AAPL/USD", "equity")
        assert "AAPLUSD" in str(inst.id)
        assert inst.price_precision == 2
        assert inst.size_precision == 2

    def test_create_instrument_for_asset_class_forex(self):
        from nautilus.engine import create_instrument_for_asset_class

        inst = create_instrument_for_asset_class("EUR/USD", "forex")
        assert "EURUSD" in str(inst.id)
        assert inst.price_precision == 5

    def test_create_instrument_for_asset_class_custom_venue(self):
        from nautilus.engine import create_instrument_for_asset_class

        inst = create_instrument_for_asset_class("BTC/USDT", "crypto", venue_name="KRAKEN")
        assert "KRAKEN" in str(inst.id)

    def test_create_instrument_for_asset_class_default_venues(self):
        """Each asset class should map to its default venue when none specified."""
        from nautilus.engine import create_instrument_for_asset_class

        crypto = create_instrument_for_asset_class("BTC/USDT", "crypto")
        equity = create_instrument_for_asset_class("AAPL/USD", "equity")
        forex = create_instrument_for_asset_class("EUR/USD", "forex")

        assert "BINANCE" in str(crypto.id)
        assert "NYSE" in str(equity.id)
        assert "FXCM" in str(forex.id)


# ── Bar Type Building Tests ──────────────────────────


class TestBarTypeBuilding:
    """Test build_bar_type with different timeframes."""

    def test_build_bar_type_1h(self):
        from nautilus.engine import build_bar_type, create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "1h")
        bar_str = str(bar_type)
        assert "HOUR" in bar_str
        assert "BTCUSDT" in bar_str

    def test_build_bar_type_1d(self):
        from nautilus.engine import build_bar_type, create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "1d")
        assert "DAY" in str(bar_type)

    def test_build_bar_type_5m(self):
        from nautilus.engine import build_bar_type, create_crypto_instrument

        inst = create_crypto_instrument("ETH/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "5m")
        assert "MINUTE" in str(bar_type)

    def test_build_bar_type_contains_last_external(self):
        from nautilus.engine import build_bar_type, create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "1h")
        bar_str = str(bar_type)
        assert "LAST" in bar_str
        assert "EXTERNAL" in bar_str

    def test_build_bar_type_unknown_timeframe_defaults_to_hour(self):
        from nautilus.engine import build_bar_type, create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "2h")
        assert "HOUR" in str(bar_type)


# ── Data Conversion Tests ────────────────────────────


class TestDataConversion:
    """Test convert_df_to_bars with valid/invalid/empty DataFrames."""

    def test_convert_valid_dataframe(self):
        from nautilus.engine import build_bar_type, convert_df_to_bars, create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "1h")
        df = _make_ohlcv(20)
        bars = convert_df_to_bars(df, bar_type, price_precision=2, size_precision=6)
        assert len(bars) == 20

    def test_convert_single_row(self):
        from nautilus.engine import build_bar_type, convert_df_to_bars, create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "1h")
        df = _make_ohlcv(1)
        bars = convert_df_to_bars(df, bar_type, price_precision=2, size_precision=6)
        assert len(bars) == 1

    def test_convert_empty_dataframe(self):
        from nautilus.engine import build_bar_type, convert_df_to_bars, create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "1h")
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df.index = pd.DatetimeIndex([], tz="UTC")
        bars = convert_df_to_bars(df, bar_type, price_precision=2, size_precision=6)
        assert len(bars) == 0

    def test_convert_respects_price_precision(self):
        from nautilus.engine import build_bar_type, convert_df_to_bars, create_forex_instrument

        inst = create_forex_instrument("EUR/USD", "FXCM")
        bar_type = build_bar_type(inst.id, "1h")
        df = _make_ohlcv(5, start_price=1.1)
        bars = convert_df_to_bars(df, bar_type, price_precision=5, size_precision=2)
        assert len(bars) == 5

    def test_convert_large_dataset(self):
        from nautilus.engine import build_bar_type, convert_df_to_bars, create_crypto_instrument

        inst = create_crypto_instrument("BTC/USDT", "BINANCE")
        bar_type = build_bar_type(inst.id, "1h")
        df = _make_ohlcv(1000)
        bars = convert_df_to_bars(df, bar_type, price_precision=2, size_precision=6)
        assert len(bars) == 1000


# ── Strategy Registry Tests ──────────────────────────


class TestStrategyRegistry:
    """Test that all 7 strategies are discoverable via both registries."""

    def test_pandas_registry_has_seven(self):
        from nautilus.strategies import STRATEGY_REGISTRY

        assert len(STRATEGY_REGISTRY) == 7

    def test_pandas_registry_expected_keys(self):
        from nautilus.strategies import STRATEGY_REGISTRY

        expected = {
            "NautilusTrendFollowing",
            "NautilusMeanReversion",
            "NautilusVolatilityBreakout",
            "EquityMomentum",
            "EquityMeanReversion",
            "ForexTrend",
            "ForexRange",
        }
        assert set(STRATEGY_REGISTRY.keys()) == expected

    def test_native_registry_has_seven(self):
        from nautilus.strategies.nt_native import NATIVE_STRATEGY_REGISTRY

        assert len(NATIVE_STRATEGY_REGISTRY) == 7

    def test_native_registry_expected_keys(self):
        from nautilus.strategies.nt_native import NATIVE_STRATEGY_REGISTRY

        expected = {
            "NativeTrendFollowing",
            "NativeMeanReversion",
            "NativeVolatilityBreakout",
            "NativeEquityMomentum",
            "NativeEquityMeanReversion",
            "NativeForexTrend",
            "NativeForexRange",
        }
        assert set(NATIVE_STRATEGY_REGISTRY.keys()) == expected

    def test_list_nautilus_strategies_returns_all_seven(self):
        from nautilus.nautilus_runner import list_nautilus_strategies

        names = list_nautilus_strategies()
        assert len(names) == 7
        assert "NautilusTrendFollowing" in names
        assert "ForexRange" in names

    def test_all_registry_entries_are_classes(self):
        from nautilus.strategies import STRATEGY_REGISTRY

        for name, cls in STRATEGY_REGISTRY.items():
            assert isinstance(cls, type), f"{name} should be a class"


# ── Runner Error Handling Tests ──────────────────────


class TestRunnerErrorHandling:
    """Test graceful error handling for invalid inputs."""

    def test_unknown_strategy_returns_error(self):
        from nautilus.nautilus_runner import run_nautilus_backtest

        result = run_nautilus_backtest("NonExistentStrategy", "BTC/USDT", "1h", "kraken")
        assert "error" in result
        assert "Unknown strategy" in result["error"]
        assert "NonExistentStrategy" in result["error"]

    def test_unknown_strategy_lists_available(self):
        from nautilus.nautilus_runner import run_nautilus_backtest

        result = run_nautilus_backtest("FakeStrategy", "BTC/USDT", "1h", "kraken")
        assert "Available" in result["error"]
        assert "NautilusTrendFollowing" in result["error"]

    def test_missing_data_returns_error(self):
        """When no parquet data exists for the symbol, should return error."""
        from nautilus.nautilus_runner import run_nautilus_backtest

        result = run_nautilus_backtest(
            "NautilusTrendFollowing",
            "NONEXISTENT/PAIR",
            "1h",
            "nonexistent_exchange",
        )
        assert "error" in result
        assert "No data" in result["error"]


# ── Runner Backtest Execution Tests ──────────────────


class TestRunnerBacktest:
    """Test actual backtest execution paths."""

    def test_pandas_backtest_produces_result(self):
        from nautilus.nautilus_runner import _run_pandas_backtest

        df = _make_ohlcv(300)
        result = _run_pandas_backtest(
            "NautilusTrendFollowing", df, "BTC/USDT", "1h", "kraken", 10000.0,
        )
        assert result["engine"] == "pandas"
        assert result["framework"] == "nautilus"
        assert result["strategy"] == "NautilusTrendFollowing"
        assert result["symbol"] == "BTC/USDT"
        assert result["bars_processed"] == 300
        assert "metrics" in result
        assert "trades" in result

    def test_pandas_backtest_all_crypto_strategies(self):
        """Each crypto strategy should run via pandas without error."""
        from nautilus.nautilus_runner import _run_pandas_backtest

        df = _make_ohlcv(300)
        for name in ["NautilusTrendFollowing", "NautilusMeanReversion", "NautilusVolatilityBreakout"]:
            result = _run_pandas_backtest(name, df, "BTC/USDT", "1h", "kraken", 10000.0)
            assert "error" not in result, f"{name} returned error: {result.get('error')}"
            assert result["strategy"] == name

    def test_pandas_backtest_equity_strategies(self):
        from nautilus.nautilus_runner import _run_pandas_backtest

        df = _make_ohlcv(300, start_price=150.0)
        for name in ["EquityMomentum", "EquityMeanReversion"]:
            result = _run_pandas_backtest(name, df, "AAPL/USD", "1d", "nyse", 50000.0)
            assert "error" not in result, f"{name} returned error: {result.get('error')}"
            assert result["strategy"] == name

    def test_pandas_backtest_forex_strategies(self):
        from nautilus.nautilus_runner import _run_pandas_backtest

        df = _make_ohlcv(300, start_price=1.1)
        for name in ["ForexTrend", "ForexRange"]:
            result = _run_pandas_backtest(name, df, "EUR/USD", "1h", "fxcm", 10000.0)
            assert "error" not in result, f"{name} returned error: {result.get('error')}"
            assert result["strategy"] == name

    def test_native_backtest_runs_with_real_data(self):
        """Native engine backtest with synthetic data saved to parquet."""
        from common.data_pipeline.pipeline import save_ohlcv
        from nautilus.nautilus_runner import run_nautilus_backtest

        df = _make_ohlcv(300)
        save_ohlcv(df, "NTEST/USDT", "1h", "testexch")
        result = run_nautilus_backtest(
            "NautilusTrendFollowing", "NTEST/USDT", "1h", "testexch", 10000.0,
        )
        assert "error" not in result
        assert result["engine"] in ("native", "pandas")
        assert result["bars_processed"] == 300


# ── Result Saving Tests ─────────────────────────────


class TestResultSaving:
    """Test _save_result writes JSON correctly."""

    def test_save_result_creates_json_file(self, tmp_path):
        from nautilus.nautilus_runner import _save_result, RESULTS_DIR

        result = {
            "framework": "nautilus",
            "engine": "pandas",
            "strategy": "TestStrategy",
            "metrics": {"total_return": 0.05},
        }
        _save_result(result, "TestStrategy", "BTC/USDT", "1h")
        expected_path = RESULTS_DIR / "TestStrategy_BTCUSDT_1h.json"
        assert expected_path.exists()
        loaded = json.loads(expected_path.read_text())
        assert loaded["strategy"] == "TestStrategy"
        assert loaded["metrics"]["total_return"] == 0.05
        # Cleanup
        expected_path.unlink(missing_ok=True)

    def test_save_result_symbol_slash_removed(self, tmp_path):
        from nautilus.nautilus_runner import _save_result, RESULTS_DIR

        _save_result({"strategy": "X"}, "X", "ETH/USDT", "4h")
        expected_path = RESULTS_DIR / "X_ETHUSDT_4h.json"
        assert expected_path.exists()
        expected_path.unlink(missing_ok=True)


# ── Platform Config Loading Tests ────────────────────


class TestPlatformConfigLoading:
    """Test _load_platform_config fallback behavior."""

    def test_load_platform_config_returns_dict(self):
        from nautilus.nautilus_runner import _load_platform_config

        cfg = _load_platform_config()
        assert isinstance(cfg, dict)

    def test_load_nautilus_config_returns_dict(self):
        from nautilus.engine import _load_nautilus_config

        cfg = _load_nautilus_config()
        assert isinstance(cfg, dict)

    def test_load_platform_config_missing_file(self):
        """When config file does not exist, should return empty dict."""
        from nautilus.nautilus_runner import _load_platform_config

        with patch("nautilus.nautilus_runner.CONFIG_PATH", Path("/nonexistent/path.yaml")):
            cfg = _load_platform_config()
            assert cfg == {}


# ── Engine Test Function ─────────────────────────────


class TestEngineTestFunction:
    """Test run_nautilus_engine_test."""

    def test_engine_test_returns_true(self):
        from nautilus.nautilus_runner import run_nautilus_engine_test

        assert run_nautilus_engine_test() is True

    def test_has_nautilus_trader_is_true(self):
        from nautilus.engine import HAS_NAUTILUS_TRADER

        assert HAS_NAUTILUS_TRADER is True


# ── Native Name Mapping Tests ────────────────────────


class TestNativeNameMapping:
    """Test the native_name_map in _run_native_backtest."""

    def test_all_pandas_strategies_have_native_mapping(self):
        """Every pandas strategy should map to a native adapter name."""
        native_name_map = {
            "NautilusTrendFollowing": "NativeTrendFollowing",
            "NautilusMeanReversion": "NativeMeanReversion",
            "NautilusVolatilityBreakout": "NativeVolatilityBreakout",
            "EquityMomentum": "NativeEquityMomentum",
            "EquityMeanReversion": "NativeEquityMeanReversion",
            "ForexTrend": "NativeForexTrend",
            "ForexRange": "NativeForexRange",
        }

        from nautilus.strategies import STRATEGY_REGISTRY
        from nautilus.strategies.nt_native import NATIVE_STRATEGY_REGISTRY

        for pandas_name in STRATEGY_REGISTRY:
            native_name = native_name_map.get(pandas_name)
            assert native_name is not None, f"No native mapping for {pandas_name}"
            assert native_name in NATIVE_STRATEGY_REGISTRY, (
                f"Native adapter {native_name} not in NATIVE_STRATEGY_REGISTRY"
            )


# ── OHLCV CSV Conversion Tests ───────────────────────


class TestOHLCVConversion:
    """Test convert_ohlcv_to_nautilus_csv."""

    def test_convert_with_valid_data(self):
        from common.data_pipeline.pipeline import save_ohlcv
        from nautilus.nautilus_runner import convert_ohlcv_to_nautilus_csv

        df = _make_ohlcv(50)
        save_ohlcv(df, "CSVTEST/USDT", "1h", "testexch")
        path = convert_ohlcv_to_nautilus_csv("CSVTEST/USDT", "1h", "testexch")
        assert path is not None
        assert path.exists()
        csv_df = pd.read_csv(path)
        assert len(csv_df) == 50
        expected_cols = {"bar_type", "open", "high", "low", "close", "volume", "ts_event", "ts_init"}
        assert expected_cols.issubset(set(csv_df.columns))

    def test_convert_with_no_data_returns_none(self):
        from nautilus.nautilus_runner import convert_ohlcv_to_nautilus_csv

        result = convert_ohlcv_to_nautilus_csv("NODATA/PAIR", "1h", "noexchange")
        assert result is None


# ── BacktestResult Persistence Tests ─────────────────


class TestBacktestResultPersistence:
    """Test BacktestResult model creation after runs (Django integration)."""

    @pytest.fixture(autouse=True)
    def _setup_django(self):
        """Ensure Django is configured for model tests."""
        import django
        import os

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        try:
            django.setup()
        except RuntimeError:
            pass  # Already configured

    def test_backtest_result_model_exists(self):
        from analysis.models import BacktestResult

        assert BacktestResult is not None
        assert hasattr(BacktestResult, "framework")
        assert hasattr(BacktestResult, "strategy_name")
        assert hasattr(BacktestResult, "symbol")
        assert hasattr(BacktestResult, "timeframe")
        assert hasattr(BacktestResult, "asset_class")
        assert hasattr(BacktestResult, "metrics")
        assert hasattr(BacktestResult, "trades")

    @pytest.mark.django_db
    def test_backtest_result_creation(self):
        from analysis.models import BackgroundJob, BacktestResult

        job = BackgroundJob.objects.create(
            job_type="nautilus_backtest",
            status="completed",
        )
        result = BacktestResult.objects.create(
            job=job,
            framework="nautilus",
            asset_class="crypto",
            strategy_name="NautilusTrendFollowing",
            symbol="BTC/USDT",
            timeframe="1h",
            metrics={"total_return": 0.05, "sharpe_ratio": 1.2},
            trades=[{"entry": 100, "exit": 105}],
        )
        assert result.id is not None
        assert result.framework == "nautilus"
        assert result.strategy_name == "NautilusTrendFollowing"
        assert result.asset_class == "crypto"

    @pytest.mark.django_db
    def test_backtest_result_query_by_framework(self):
        from analysis.models import BackgroundJob, BacktestResult

        job = BackgroundJob.objects.create(
            job_type="nautilus_backtest",
            status="completed",
        )
        BacktestResult.objects.create(
            job=job,
            framework="nautilus",
            strategy_name="NautilusTrendFollowing",
            symbol="BTC/USDT",
            timeframe="1h",
            metrics={},
            trades=[],
        )
        BacktestResult.objects.create(
            job=job,
            framework="freqtrade",
            strategy_name="CryptoInvestorV1",
            symbol="BTC/USDT",
            timeframe="1h",
            metrics={},
            trades=[],
        )
        nautilus_results = BacktestResult.objects.filter(framework="nautilus")
        assert nautilus_results.count() >= 1
        for r in nautilus_results:
            assert r.framework == "nautilus"
