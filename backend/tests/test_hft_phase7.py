"""Phase 7: hftbacktest/ — 100% coverage tests.

Covers all uncovered lines:
  - hft_runner.py: lines 43-48, 113-116, cli_main (170+)
  - strategies/base.py: lines 72, 212
  - strategies/market_maker.py: line 43
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hftbacktest import hft_runner
from hftbacktest.strategies.base import HFTBaseStrategy
from hftbacktest.strategies.market_maker import HFTMarketMaker

# ===================================================================
# hft_runner.py — _load_platform_config() exception paths (lines 43-48)
# ===================================================================


class TestLoadPlatformConfigExceptions:
    def test_import_error_yaml_not_installed(self, tmp_path):
        """Lines 43-45: ImportError when yaml is not available."""
        fake_config = tmp_path / "platform_config.yaml"
        fake_config.write_text("key: value")

        real_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return real_import(name, *args, **kwargs)

        with (
            patch.object(hft_runner, "CONFIG_PATH", fake_config),
            patch("builtins.__import__", side_effect=mock_import),
        ):
            result = hft_runner._load_platform_config()

        assert result == {}

    def test_generic_exception_loading_config(self, tmp_path):
        """Lines 46-48: Generic exception during config loading."""
        fake_config = tmp_path / "platform_config.yaml"
        fake_config.write_text("bad: yaml: [")

        with patch.object(hft_runner, "CONFIG_PATH", fake_config):
            # Force yaml.safe_load to raise by patching at module level
            import yaml as yaml_mod

            with patch.object(yaml_mod, "safe_load", side_effect=RuntimeError("parse error")):
                result = hft_runner._load_platform_config()

        assert result == {}


# ===================================================================
# hft_runner.py — run_hft_backtest() tick generation fallback (lines 113-116)
# ===================================================================


class TestRunHftBacktestTickFallback:
    def test_no_tick_data_and_convert_returns_none(self, tmp_path):
        """Lines 113-116: tick file missing + convert returns None."""
        with (
            patch.object(hft_runner, "TICKS_DIR", tmp_path),
            patch.object(hft_runner, "convert_ohlcv_to_hft_ticks", return_value=None),
            patch.object(hft_runner, "_load_platform_config", return_value={}),
        ):
            result = hft_runner.run_hft_backtest("MarketMaker", "FAKE/USDT", "1h", "kraken")

        assert "error" in result
        assert "No data" in result["error"]


# ===================================================================
# hft_runner.py — cli_main() (lines 170+)
# ===================================================================


class TestHftRunnerCLI:
    def test_convert_command(self):
        """Convert subcommand dispatches to convert_ohlcv_to_hft_ticks."""
        with patch.object(hft_runner, "convert_ohlcv_to_hft_ticks") as mock_convert:
            mock_convert.return_value = Path("/tmp/ticks.npy")
            hft_runner.cli_main(
                ["convert", "--symbol", "ETH/USDT", "--timeframe", "1d", "--exchange", "kraken"]
            )
            mock_convert.assert_called_once_with("ETH/USDT", "1d", "kraken")

    def test_backtest_command(self, capsys):
        """Backtest subcommand dispatches to run_hft_backtest and prints JSON."""
        fake_result = {"strategy": "MarketMaker", "metrics": {"sharpe": 1.5}}
        with patch.object(hft_runner, "run_hft_backtest", return_value=fake_result):
            hft_runner.cli_main(["backtest", "--strategy", "MarketMaker"])
        output = capsys.readouterr().out
        assert "MarketMaker" in output
        assert "1.5" in output

    def test_list_strategies_command(self, capsys):
        """list-strategies subcommand prints strategy names."""
        with patch.object(
            hft_runner, "list_hft_strategies", return_value=["MarketMaker", "GridTrader"]
        ):
            hft_runner.cli_main(["list-strategies"])
        output = capsys.readouterr().out
        assert "MarketMaker" in output
        assert "GridTrader" in output

    def test_test_command(self, capsys):
        """Test subcommand prints OK message and strategy list."""
        with patch.object(hft_runner, "list_hft_strategies", return_value=["MarketMaker"]):
            hft_runner.cli_main(["test"])
        output = capsys.readouterr().out
        assert "hftbacktest module: OK" in output
        assert "MarketMaker" in output

    def test_no_command_prints_help(self, capsys):
        """No subcommand prints help text."""
        hft_runner.cli_main([])
        output = capsys.readouterr().out
        assert "hftbacktest Runner" in output or "usage" in output.lower()


# ===================================================================
# strategies/base.py — line 72 and 212
# ===================================================================


class TestBaseStrategyUncoveredLines:
    def test_on_tick_raises_not_implemented(self):
        """Line 72: on_tick() raises NotImplementedError on base class."""
        strategy = HFTBaseStrategy()
        with pytest.raises(NotImplementedError):
            strategy.on_tick({"timestamp": 0, "price": 100.0, "volume": 0.01, "side": "buy"})

    def test_get_trades_df_empty_when_all_same_side(self):
        """Line 212: return empty DataFrame when FIFO produces no round-trips."""
        strategy = HFTBaseStrategy(config={"max_position": 10.0})
        tick = {
            "timestamp": 1_700_000_000_000_000_000,
            "price": 100.0,
            "volume": 0.01,
            "side": "buy",
        }

        # 3 buy orders, no sells → no round-trip trades
        strategy.submit_order("buy", 100.0, 0.01, tick)
        strategy.submit_order("buy", 100.1, 0.01, tick)
        strategy.submit_order("buy", 100.2, 0.01, tick)

        assert len(strategy.fills) == 3
        df = strategy.get_trades_df()
        assert isinstance(df, pd.DataFrame)
        assert df.empty


# ===================================================================
# strategies/market_maker.py — line 43
# ===================================================================


class TestMarketMakerDrawdownHaltReturn:
    def test_on_tick_returns_early_after_drawdown_halt(self):
        """Line 43: return after check_drawdown_halt() triggers."""
        strategy = HFTMarketMaker(
            config={
                "drawdown_halt_pct": 0.01,  # 1% halt threshold
                "initial_balance": 10000.0,
                "quote_interval": 1,
            }
        )

        # Simulate 2% drawdown from peak → exceeds 1% halt
        strategy.balance = 9800.0
        strategy.peak_balance = 10000.0

        tick = {
            "timestamp": 1_700_000_000_000_000_000,
            "price": 100.0,
            "volume": 0.01,
            "side": "sell",
        }

        fills_before = len(strategy.fills)
        strategy.on_tick(tick)

        assert strategy.halted is True
        assert len(strategy.fills) == fills_before
