"""Tests for BacktestService — wraps Freqtrade, NautilusTrader, hftbacktest."""

from unittest.mock import patch

from analysis.services.backtest import BacktestService


class TestBacktestServiceRunBacktest:
    def test_unknown_framework_returns_error(self):
        result = BacktestService.run_backtest(
            {"framework": "unknown_framework"},
            lambda pct, msg: None,
        )
        assert "error" in result
        assert "Unknown framework" in result["error"]

    def test_routes_to_freqtrade(self):
        with patch.object(
            BacktestService, "_run_freqtrade", return_value={"framework": "freqtrade"},
        ) as mock_ft:
            result = BacktestService.run_backtest(
                {"framework": "freqtrade", "strategy": "TestStrat"},
                lambda pct, msg: None,
            )
            mock_ft.assert_called_once()
            assert result["framework"] == "freqtrade"

    def test_routes_to_nautilus(self):
        with patch.object(
            BacktestService, "_run_nautilus", return_value={"framework": "nautilus"},
        ) as mock_nt:
            result = BacktestService.run_backtest(
                {"framework": "nautilus"},
                lambda pct, msg: None,
            )
            mock_nt.assert_called_once()
            assert result["framework"] == "nautilus"

    def test_routes_to_hftbacktest(self):
        with patch.object(
            BacktestService, "_run_hft", return_value={"framework": "hftbacktest"},
        ) as mock_hft:
            result = BacktestService.run_backtest(
                {"framework": "hftbacktest"},
                lambda pct, msg: None,
            )
            mock_hft.assert_called_once()
            assert result["framework"] == "hftbacktest"

    def test_defaults_to_freqtrade(self):
        with patch.object(
            BacktestService, "_run_freqtrade", return_value={"framework": "freqtrade"},
        ) as mock_ft:
            _result = BacktestService.run_backtest(
                {},
                lambda pct, msg: None,
            )
            mock_ft.assert_called_once()


class TestBacktestServiceFreqtrade:
    def test_missing_config_returns_error(self, tmp_path):
        with patch(
            "analysis.services.backtest.get_freqtrade_dir",
            return_value=tmp_path,
        ):
            progress_calls = []

            def progress_cb(pct, msg):
                progress_calls.append((pct, msg))

            result = BacktestService._run_freqtrade(
                {"strategy": "TestStrat"},
                progress_cb,
            )
            assert "error" in result
            assert "config not found" in result["error"].lower()

    def test_freqtrade_command_not_found(self, tmp_path):
        # Create a fake config file
        config_path = tmp_path / "config.json"
        config_path.write_text('{"stake_currency": "USDT"}')
        (tmp_path / "user_data").mkdir()

        with patch(
            "analysis.services.backtest.get_freqtrade_dir",
            return_value=tmp_path,
        ), patch(
            "analysis.services.backtest.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = BacktestService._run_freqtrade(
                {"strategy": "TestStrat"},
                lambda pct, msg: None,
            )
            assert "error" in result
            assert "not found" in result["error"].lower()


class TestBacktestServiceNautilus:
    def test_nautilus_import_error(self):
        with patch(
            "analysis.services.backtest.ensure_platform_imports",
        ), patch.dict(
            "sys.modules",
            {"nautilus": None, "nautilus.nautilus_runner": None},
        ):
            result = BacktestService._run_nautilus(
                {"strategy": "TrendFollowing"},
                lambda pct, msg: None,
            )
            assert "error" in result

    def test_progress_callback_called(self):
        with patch(
            "analysis.services.backtest.ensure_platform_imports",
        ), patch(
            "nautilus.nautilus_runner.run_nautilus_backtest",
            return_value={"framework": "nautilus", "metrics": {}},
        ), patch(
            "nautilus.nautilus_runner.list_nautilus_strategies",
            return_value=["TrendFollowing"],
        ):
            progress_calls = []

            def progress_cb(pct, msg):
                progress_calls.append((pct, msg))

            _result = BacktestService._run_nautilus(
                {"strategy": "TrendFollowing"},
                progress_cb,
            )
            assert len(progress_calls) > 0
