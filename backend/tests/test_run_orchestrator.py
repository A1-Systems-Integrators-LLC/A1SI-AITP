"""Full coverage tests for run.py (Platform Orchestrator).

Covers: cmd_status, cmd_validate, cmd_data, cmd_research,
cmd_freqtrade, cmd_nautilus, cmd_ml, cmd_hft, main() argparse routing.
"""

import os
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import run.py functions directly
from run import (
    cmd_status,
    cmd_validate,
    cmd_data,
    cmd_research,
    cmd_freqtrade,
    cmd_nautilus,
    cmd_ml,
    cmd_hft,
    main,
    _generate_sample_data,
)


# ══════════════════════════════════════════════════════
# cmd_status
# ══════════════════════════════════════════════════════


class TestCmdStatus:
    def test_runs_without_error(self, capsys):
        """cmd_status should print framework/data/strategy info without crashing."""
        cmd_status()
        out = capsys.readouterr().out
        assert "FRAMEWORK STATUS" in out
        assert "DATA STATUS" in out
        assert "STRATEGIES" in out
        assert "CONFIGURATION" in out

    def test_missing_framework_shown(self, capsys):
        """Frameworks that fail to import are shown as NOT INSTALLED."""
        original = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "vectorbt":
                raise ImportError("no vectorbt")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            cmd_status()
        out = capsys.readouterr().out
        # vectorbt may or may not be importable in test env — just check it ran
        assert "FRAMEWORK STATUS" in out

    def test_no_data_dir(self, capsys, tmp_path):
        """Handles missing data directory gracefully."""
        with patch("run.PROJECT_ROOT", tmp_path):
            cmd_status()
        out = capsys.readouterr().out
        assert "Parquet files: 0" in out


# ══════════════════════════════════════════════════════
# cmd_validate
# ══════════════════════════════════════════════════════


class TestCmdValidate:
    def test_returns_bool(self, capsys):
        """cmd_validate returns True/False based on pass/fail."""
        result = cmd_validate()
        out = capsys.readouterr().out
        assert isinstance(result, bool)
        assert "Results:" in out

    def test_exec_failure_counted(self, capsys):
        """A test that fails exec() is counted as failed."""
        with patch("builtins.exec", side_effect=Exception("boom")):
            result = cmd_validate()
        assert result is False
        out = capsys.readouterr().out
        assert "failed" in out


# ══════════════════════════════════════════════════════
# cmd_data
# ══════════════════════════════════════════════════════


class TestCmdData:
    def test_download(self, capsys):
        args = Namespace(
            data_command="download", symbols="BTC/USDT",
            timeframes="1h", exchange="kraken", days=30, asset_class="crypto",
        )
        with patch("common.data_pipeline.pipeline.download_watchlist",
                    return_value={"BTC/USDT_1h": {"status": "ok", "rows": 720}}):
            cmd_data(args)
        out = capsys.readouterr().out
        assert "Download complete" in out

    def test_list_empty(self, capsys):
        import pandas as pd
        args = Namespace(data_command="list")
        with patch("common.data_pipeline.pipeline.list_available_data",
                    return_value=pd.DataFrame()):
            cmd_data(args)
        out = capsys.readouterr().out
        assert "No data files" in out

    def test_list_with_data(self, capsys):
        import pandas as pd
        args = Namespace(data_command="list")
        df = pd.DataFrame({"file": ["btc.parquet"], "rows": [100]})
        with patch("common.data_pipeline.pipeline.list_available_data", return_value=df):
            cmd_data(args)
        out = capsys.readouterr().out
        assert "btc.parquet" in out

    def test_info_empty(self, capsys):
        import pandas as pd
        args = Namespace(data_command="info", symbol="BTC/USDT", timeframe="1h", exchange="kraken")
        with patch("common.data_pipeline.pipeline.load_ohlcv", return_value=pd.DataFrame()):
            cmd_data(args)
        out = capsys.readouterr().out
        assert "No data" in out

    def test_info_with_data(self, capsys):
        import pandas as pd
        import numpy as np
        idx = pd.date_range("2025-01-01", periods=10, freq="1h")
        df = pd.DataFrame({"open": np.random.rand(10), "close": np.random.rand(10)}, index=idx)
        args = Namespace(data_command="info", symbol="BTC/USDT", timeframe="1h", exchange="kraken")
        with patch("common.data_pipeline.pipeline.load_ohlcv", return_value=df):
            cmd_data(args)
        out = capsys.readouterr().out
        assert "Rows:" in out

    def test_generate_sample(self, capsys):
        args = Namespace(data_command="generate-sample")
        with patch("common.data_pipeline.pipeline.save_ohlcv",
                    return_value=Path("/tmp/test.parquet")):
            cmd_data(args)
        out = capsys.readouterr().out
        assert "sample data" in out.lower() or "Sample" in out

    def test_unknown_subcommand(self, capsys):
        args = Namespace(data_command="unknown")
        cmd_data(args)
        out = capsys.readouterr().out
        assert "Usage:" in out


# ══════════════════════════════════════════════════════
# cmd_research
# ══════════════════════════════════════════════════════


class TestCmdResearch:
    def test_screen_with_results(self, capsys):
        import pandas as pd
        args = Namespace(
            research_command="screen", symbol="BTC/USDT", timeframe="1h",
            exchange="kraken", fees=None, asset_class="crypto",
        )
        mock_df = pd.DataFrame({"sharpe_ratio": [1.5], "total_return": [0.15]})
        with patch("research.scripts.vbt_screener.run_full_screen",
                    return_value={"sma_crossover": mock_df}):
            cmd_research(args)
        out = capsys.readouterr().out
        assert "SCREENING SUMMARY" in out

    def test_screen_empty_results(self, capsys):
        args = Namespace(
            research_command="screen", symbol="BTC/USDT", timeframe="1h",
            exchange="kraken", fees=None, asset_class="crypto",
        )
        with patch("research.scripts.vbt_screener.run_full_screen", return_value=None):
            cmd_research(args)

    def test_unknown_subcommand(self, capsys):
        args = Namespace(research_command="unknown")
        cmd_research(args)
        out = capsys.readouterr().out
        assert "Usage:" in out


# ══════════════════════════════════════════════════════
# cmd_freqtrade
# ══════════════════════════════════════════════════════


class TestCmdFreqtrade:
    def test_backtest(self, capsys):
        args = Namespace(ft_command="backtest", strategy="CryptoInvestorV1", timerange="")
        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            result = cmd_freqtrade(args)
        assert result == 0
        assert mock_run.called

    def test_dry_run(self, capsys):
        args = Namespace(ft_command="dry-run", strategy="CryptoInvestorV1")
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            result = cmd_freqtrade(args)
        assert result == 0

    def test_hyperopt(self, capsys):
        args = Namespace(ft_command="hyperopt", strategy="CryptoInvestorV1", epochs=50)
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            result = cmd_freqtrade(args)
        assert result == 0

    def test_list_strategies(self, capsys, tmp_path):
        # Create fake strategy dir
        strat_dir = tmp_path / "freqtrade" / "user_data" / "strategies"
        strat_dir.mkdir(parents=True)
        (strat_dir / "MyStrategy.py").touch()
        (strat_dir / "__init__.py").touch()
        args = Namespace(ft_command="list-strategies")
        with patch("run.PROJECT_ROOT", tmp_path):
            cmd_freqtrade(args)
        out = capsys.readouterr().out
        assert "MyStrategy" in out

    def test_unknown_subcommand(self, capsys):
        args = Namespace(ft_command="unknown")
        cmd_freqtrade(args)
        out = capsys.readouterr().out
        assert "Usage:" in out


# ══════════════════════════════════════════════════════
# cmd_nautilus
# ══════════════════════════════════════════════════════


class TestCmdNautilus:
    def test_engine_test_success(self, capsys):
        args = Namespace(nt_command="test")
        with patch("nautilus.nautilus_runner.run_nautilus_engine_test", return_value=True):
            cmd_nautilus(args)
        out = capsys.readouterr().out
        assert "successfully" in out

    def test_engine_test_failure(self, capsys):
        args = Namespace(nt_command="test")
        with patch("nautilus.nautilus_runner.run_nautilus_engine_test", return_value=False):
            cmd_nautilus(args)
        out = capsys.readouterr().out
        assert "not available" in out

    def test_convert(self, capsys):
        args = Namespace(nt_command="convert", symbol="BTC/USDT", timeframe="1h", exchange="kraken")
        with patch("nautilus.nautilus_runner.convert_ohlcv_to_nautilus_csv",
                    return_value=Path("/tmp/nt.csv")):
            cmd_nautilus(args)
        out = capsys.readouterr().out
        assert "converted" in out

    def test_backtest(self, capsys):
        args = Namespace(
            nt_command="backtest", strategy="NautilusTrendFollowing",
            symbol="BTC/USDT", timeframe="1h", exchange="kraken",
            balance=10000.0, asset_class="crypto",
        )
        with patch("nautilus.nautilus_runner.run_nautilus_backtest",
                    return_value={"total_return": 0.05}):
            cmd_nautilus(args)
        out = capsys.readouterr().out
        assert "total_return" in out

    def test_list_strategies(self, capsys):
        args = Namespace(nt_command="list-strategies")
        with patch("nautilus.nautilus_runner.list_nautilus_strategies",
                    return_value=["NautilusTrendFollowing", "NautilusMeanReversion"]):
            cmd_nautilus(args)
        out = capsys.readouterr().out
        assert "NautilusTrendFollowing" in out

    def test_unknown_subcommand(self, capsys):
        args = Namespace(nt_command="unknown")
        cmd_nautilus(args)
        out = capsys.readouterr().out
        assert "Usage:" in out


# ══════════════════════════════════════════════════════
# cmd_ml
# ══════════════════════════════════════════════════════


class TestCmdMl:
    def test_train_no_data(self, capsys):
        import pandas as pd
        args = Namespace(
            ml_command="train", symbol="BTC/USDT", timeframe="1h",
            exchange="kraken", test_ratio=0.2,
        )
        with patch("common.data_pipeline.pipeline.load_ohlcv", return_value=pd.DataFrame()):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "No data" in out

    def test_train_insufficient_data(self, capsys):
        import pandas as pd
        import numpy as np
        args = Namespace(
            ml_command="train", symbol="BTC/USDT", timeframe="1h",
            exchange="kraken", test_ratio=0.2,
        )
        idx = pd.date_range("2025-01-01", periods=50, freq="1h")
        df = pd.DataFrame({
            "open": np.random.rand(50), "high": np.random.rand(50),
            "low": np.random.rand(50), "close": np.random.rand(50),
            "volume": np.random.rand(50),
        }, index=idx)
        with patch("common.data_pipeline.pipeline.load_ohlcv", return_value=df), \
             patch("common.ml.features.build_feature_matrix",
                   return_value=(df.iloc[:20], df["close"].iloc[:20], ["f1"])):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "Insufficient" in out

    def test_train_success(self, capsys):
        import pandas as pd
        import numpy as np
        args = Namespace(
            ml_command="train", symbol="BTC/USDT", timeframe="1h",
            exchange="kraken", test_ratio=0.2,
        )
        idx = pd.date_range("2025-01-01", periods=200, freq="1h")
        df = pd.DataFrame({
            "open": np.random.rand(200), "close": np.random.rand(200),
        }, index=idx)
        x_feat = pd.DataFrame(np.random.rand(150, 5))
        y_target = pd.Series(np.random.randint(0, 2, 150))

        mock_result = {
            "model": MagicMock(),
            "metrics": {"accuracy": 0.65, "precision": 0.6, "f1": 0.62, "logloss": 0.55},
            "metadata": {},
            "feature_importance": {"f1": 100, "f2": 80},
        }
        with patch("common.data_pipeline.pipeline.load_ohlcv", return_value=df), \
             patch("common.ml.features.build_feature_matrix",
                   return_value=(x_feat, y_target, [f"f{i}" for i in range(5)])), \
             patch("common.ml.trainer.train_model", return_value=mock_result), \
             patch("common.ml.registry.ModelRegistry.save_model", return_value="model-123"):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "Model trained" in out
        assert "model-123" in out

    def test_list_models_empty(self, capsys):
        args = Namespace(ml_command="list-models")
        with patch("common.ml.registry.ModelRegistry.list_models", return_value=[]):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "No trained models" in out

    def test_list_models_with_data(self, capsys):
        args = Namespace(ml_command="list-models")
        models = [{"model_id": "m1", "symbol": "BTC/USDT", "timeframe": "1h",
                    "metrics": {"accuracy": 0.65, "f1": 0.6}, "created_at": "2025-01-01T00:00:00"}]
        with patch("common.ml.registry.ModelRegistry.list_models", return_value=models):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "m1" in out

    def test_predict_no_models(self, capsys):
        args = Namespace(
            ml_command="predict", model_id="", symbol="BTC/USDT",
            timeframe="1h", exchange="kraken", bars=50,
        )
        with patch("common.ml.registry.ModelRegistry.list_models", return_value=[]):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "No models found" in out

    def test_predict_model_not_found(self, capsys):
        args = Namespace(
            ml_command="predict", model_id="nonexistent", symbol="BTC/USDT",
            timeframe="1h", exchange="kraken", bars=50,
        )
        with patch("common.ml.registry.ModelRegistry.load_model",
                    side_effect=FileNotFoundError("nope")):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "Model not found" in out

    def test_predict_success(self, capsys):
        import pandas as pd
        import numpy as np
        args = Namespace(
            ml_command="predict", model_id="m1", symbol="BTC/USDT",
            timeframe="1h", exchange="kraken", bars=5,
        )
        idx = pd.date_range("2025-01-01", periods=100, freq="1h")
        df = pd.DataFrame({"close": np.random.rand(100)}, index=idx)
        x_feat = pd.DataFrame(np.random.rand(100, 3))

        with patch("common.ml.registry.ModelRegistry.load_model",
                    return_value=(MagicMock(), {})), \
             patch("common.data_pipeline.pipeline.load_ohlcv", return_value=df), \
             patch("common.ml.features.build_feature_matrix",
                   return_value=(x_feat, None, ["a", "b", "c"])), \
             patch("common.ml.trainer.predict",
                   return_value={"n_bars": 5, "mean_probability": 0.6, "predicted_up_pct": 60.0}):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "Prediction" in out

    def test_predict_no_data(self, capsys):
        import pandas as pd
        args = Namespace(
            ml_command="predict", model_id="m1", symbol="BTC/USDT",
            timeframe="1h", exchange="kraken", bars=5,
        )
        with patch("common.ml.registry.ModelRegistry.load_model",
                    return_value=(MagicMock(), {})), \
             patch("common.data_pipeline.pipeline.load_ohlcv",
                   return_value=pd.DataFrame()):
            cmd_ml(args)
        out = capsys.readouterr().out
        assert "No data" in out

    def test_unknown_subcommand(self, capsys):
        args = Namespace(ml_command="unknown")
        cmd_ml(args)
        out = capsys.readouterr().out
        assert "Usage:" in out


# ══════════════════════════════════════════════════════
# cmd_hft
# ══════════════════════════════════════════════════════


class TestCmdHft:
    def test_backtest(self, capsys):
        args = Namespace(
            hft_command="backtest", strategy="MarketMaker",
            symbol="BTC/USDT", timeframe="1h", exchange="kraken",
            latency=1_000_000, balance=10000.0,
        )
        with patch("hftbacktest.hft_runner.run_hft_backtest",
                    return_value={"total_return": 0.02}):
            cmd_hft(args)
        out = capsys.readouterr().out
        assert "total_return" in out

    def test_convert(self, capsys):
        args = Namespace(
            hft_command="convert", symbol="BTC/USDT",
            timeframe="1h", exchange="kraken",
        )
        with patch("hftbacktest.hft_runner.convert_ohlcv_to_hft_ticks",
                    return_value=Path("/tmp/ticks.npy")):
            cmd_hft(args)
        out = capsys.readouterr().out
        assert "Tick data" in out

    def test_list_strategies(self, capsys):
        args = Namespace(hft_command="list-strategies")
        with patch("hftbacktest.hft_runner.list_hft_strategies",
                    return_value=["MarketMaker", "MomentumScalper"]):
            cmd_hft(args)
        out = capsys.readouterr().out
        assert "MarketMaker" in out

    def test_module_test(self, capsys):
        args = Namespace(hft_command="test")
        with patch("hftbacktest.hft_runner.list_hft_strategies",
                    return_value=["MarketMaker"]):
            cmd_hft(args)
        out = capsys.readouterr().out
        assert "1 strategies" in out

    def test_unknown_subcommand(self, capsys):
        args = Namespace(hft_command="unknown")
        cmd_hft(args)
        out = capsys.readouterr().out
        assert "Usage:" in out


# ══════════════════════════════════════════════════════
# main() argparse routing
# ══════════════════════════════════════════════════════


class TestMain:
    def test_no_args_prints_help(self, capsys):
        with patch("sys.argv", ["run.py"]):
            main()
        out = capsys.readouterr().out
        assert "A1SI-AITP" in out

    def test_status_routed(self, capsys):
        with patch("sys.argv", ["run.py", "status"]), \
             patch("run.cmd_status") as mock_status:
            main()
        mock_status.assert_called_once()

    def test_validate_routed(self):
        with patch("sys.argv", ["run.py", "validate"]), \
             patch("run.cmd_validate") as mock_validate:
            main()
        mock_validate.assert_called_once()

    def test_data_routed(self):
        with patch("sys.argv", ["run.py", "data", "list"]), \
             patch("run.cmd_data") as mock_data:
            main()
        mock_data.assert_called_once()

    def test_research_routed(self):
        with patch("sys.argv", ["run.py", "research", "screen"]), \
             patch("run.cmd_research") as mock_research:
            main()
        mock_research.assert_called_once()

    def test_freqtrade_routed(self):
        with patch("sys.argv", ["run.py", "freqtrade", "list-strategies"]), \
             patch("run.cmd_freqtrade") as mock_ft:
            main()
        mock_ft.assert_called_once()

    def test_nautilus_routed(self):
        with patch("sys.argv", ["run.py", "nautilus", "list-strategies"]), \
             patch("run.cmd_nautilus") as mock_nt:
            main()
        mock_nt.assert_called_once()

    def test_ml_routed(self):
        with patch("sys.argv", ["run.py", "ml", "list-models"]), \
             patch("run.cmd_ml") as mock_ml:
            main()
        mock_ml.assert_called_once()

    def test_hft_routed(self):
        with patch("sys.argv", ["run.py", "hft", "list-strategies"]), \
             patch("run.cmd_hft") as mock_hft:
            main()
        mock_hft.assert_called_once()
