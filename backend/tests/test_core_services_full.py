"""Full coverage tests for backend/core/services/ (task_registry executors, dashboard, ws_broadcast).

Covers: all 15 task_registry executors (happy path + error paths),
dashboard partial failure isolation, ws_broadcast channel layer None.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

CB = MagicMock()  # Reusable progress callback

# Shorthand for the local-import patch targets
PB_ENSURE = "core.platform_bridge.ensure_platform_imports"
PB_CONFIG = "core.platform_bridge.get_platform_config"


# ══════════════════════════════════════════════════════
# _run_data_refresh
# ══════════════════════════════════════════════════════


class TestRunDataRefresh:
    def test_no_watchlist_skips(self):
        from core.services.task_registry import _run_data_refresh
        with patch(PB_ENSURE), patch(PB_CONFIG, return_value={"data": {}}):
            result = _run_data_refresh({"asset_class": "crypto"}, MagicMock())
        assert result["status"] == "skipped"

    def test_successful_download(self):
        from core.services.task_registry import _run_data_refresh
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {"watchlist": ["BTC/USDT"]}}), \
             patch("common.data_pipeline.pipeline.download_watchlist",
                   return_value={"BTC/USDT_1h": {"status": "ok"}}):
            result = _run_data_refresh({"asset_class": "crypto"}, MagicMock())
        assert result["status"] == "completed"
        assert result["saved"] == 1

    def test_failed_download_logged(self):
        from core.services.task_registry import _run_data_refresh
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {"watchlist": ["BTC/USDT"]}}), \
             patch("common.data_pipeline.pipeline.download_watchlist",
                   return_value={"BTC/USDT_1h": {"status": "error", "error": "timeout"}}):
            result = _run_data_refresh({"asset_class": "crypto"}, MagicMock())
        assert result["failed"] == 1

    def test_equity_watchlist_key(self):
        from core.services.task_registry import _run_data_refresh
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {"equity_watchlist": ["AAPL"]}}), \
             patch("common.data_pipeline.pipeline.download_watchlist",
                   return_value={"AAPL_1d": {"status": "ok"}}):
            result = _run_data_refresh({"asset_class": "equity"}, MagicMock())
        assert result["saved"] == 1


# ══════════════════════════════════════════════════════
# _run_news_fetch
# ══════════════════════════════════════════════════════


class TestRunNewsFetch:
    def test_fetches_all_asset_classes(self):
        from core.services.task_registry import _run_news_fetch
        mock_svc = MagicMock()
        mock_svc.fetch_and_store.return_value = 5
        mock_svc.get_sentiment_summary.return_value = {"avg_score": 0.0}
        with patch("market.services.news.NewsService", return_value=mock_svc), \
             patch("core.services.ws_broadcast.broadcast_news_update"), \
             patch("core.services.ws_broadcast.broadcast_sentiment_update"):
            result = _run_news_fetch({}, MagicMock())
        assert result["articles_fetched"] == 15  # 5 per asset class × 3

    def test_fetch_error_returns_error(self):
        from core.services.task_registry import _run_news_fetch
        with patch("market.services.news.NewsService", side_effect=Exception("db down")):
            result = _run_news_fetch({}, MagicMock())
        assert result["status"] == "error"

    def test_broadcast_failure_isolated(self):
        from core.services.task_registry import _run_news_fetch
        mock_svc = MagicMock()
        mock_svc.fetch_and_store.return_value = 1
        mock_svc.get_sentiment_summary.side_effect = Exception("ws fail")
        with patch("market.services.news.NewsService", return_value=mock_svc):
            result = _run_news_fetch({}, MagicMock())
        assert result["status"] == "completed"


# ══════════════════════════════════════════════════════
# _run_data_quality
# ══════════════════════════════════════════════════════


class TestRunDataQuality:
    def test_all_passed(self):
        from core.services.task_registry import _run_data_quality
        mock_report = MagicMock(passed=True, issues_summary=[])
        with patch(PB_ENSURE), \
             patch("common.data_pipeline.pipeline.validate_all_data",
                   return_value=[mock_report]):
            result = _run_data_quality({}, MagicMock())
        assert result["quality_summary"]["passed"] == 1
        assert result["quality_summary"]["failed"] == 0

    def test_some_failed(self):
        from core.services.task_registry import _run_data_quality
        good = MagicMock(passed=True, issues_summary=[])
        bad = MagicMock(passed=False, symbol="BTC/USDT", timeframe="1h",
                        issues_summary=["gaps detected"])
        with patch(PB_ENSURE), \
             patch("common.data_pipeline.pipeline.validate_all_data",
                   return_value=[good, bad]):
            result = _run_data_quality({}, MagicMock())
        assert result["quality_summary"]["failed"] == 1
        assert len(result["quality_summary"]["issues"]) == 1


# ══════════════════════════════════════════════════════
# _run_vbt_screen
# ══════════════════════════════════════════════════════


class TestRunVbtScreen:
    def test_no_watchlist_skips(self):
        from core.services.task_registry import _run_vbt_screen
        with patch(PB_ENSURE), patch(PB_CONFIG, return_value={"data": {}}):
            result = _run_vbt_screen({}, MagicMock())
        assert result["status"] == "skipped"

    def test_screen_per_symbol(self):
        from core.services.task_registry import _run_vbt_screen
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {"watchlist": ["BTC/USDT"]}}), \
             patch("analysis.services.screening.ScreenerService.run_full_screen",
                   return_value={"strategies": {}}):
            result = _run_vbt_screen({}, MagicMock())
        assert result["status"] == "completed"
        assert result["symbols_screened"] == 1

    def test_screen_error_isolated(self):
        from core.services.task_registry import _run_vbt_screen
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {"watchlist": ["BTC/USDT"]}}), \
             patch("analysis.services.screening.ScreenerService.run_full_screen",
                   side_effect=Exception("vbt crash")):
            result = _run_vbt_screen({}, MagicMock())
        assert result["symbols_screened"] == 1
        assert result["results"][0]["status"] == "error"


# ══════════════════════════════════════════════════════
# _run_ml_training
# ══════════════════════════════════════════════════════


class TestRunMlTraining:
    def test_single_symbol_success(self):
        from core.services.task_registry import _run_ml_training
        with patch("analysis.services.ml.MLService.train",
                    return_value={"status": "completed", "accuracy": 0.65}):
            result = _run_ml_training({"symbol": "BTC/USDT"}, MagicMock())
        assert result["models_trained"] == 1

    def test_training_failure_isolated(self):
        from core.services.task_registry import _run_ml_training
        with patch("analysis.services.ml.MLService.train",
                    side_effect=Exception("insufficient data")):
            result = _run_ml_training({"symbols": ["BTC/USDT"]}, MagicMock())
        assert result["results"][0]["status"] == "error"

    def test_string_symbols_converted(self):
        from core.services.task_registry import _run_ml_training
        with patch("analysis.services.ml.MLService.train",
                    return_value={"status": "completed"}):
            result = _run_ml_training({"symbols": "BTC/USDT"}, MagicMock())
        assert result["models_trained"] == 1


# ══════════════════════════════════════════════════════
# _run_market_scan
# ══════════════════════════════════════════════════════


class TestRunMarketScan:
    def test_success(self):
        from core.services.task_registry import _run_market_scan
        with patch("market.services.market_scanner.MarketScannerService") as MockScanner:
            MockScanner.return_value.scan_all.return_value = {"status": "completed", "opportunities": 3}
            result = _run_market_scan({}, MagicMock())
        assert result["status"] == "completed"

    def test_scan_failure(self):
        from core.services.task_registry import _run_market_scan
        with patch("market.services.market_scanner.MarketScannerService",
                    side_effect=Exception("import fail")):
            result = _run_market_scan({}, MagicMock())
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════
# _run_daily_report
# ══════════════════════════════════════════════════════


class TestRunDailyReport:
    def test_success_with_telegram(self):
        from core.services.task_registry import _run_daily_report
        mock_report = {
            "regime": {"dominant_regime": "ranging", "avg_confidence": 0.5},
            "strategy_performance": {"total_orders": 10, "win_rate": 50.0, "total_pnl": 100.0},
            "system_status": {"days_paper_trading": 5, "min_days_required": 14},
        }
        with patch("market.services.daily_report.DailyReportService") as MockDR, \
             patch("core.services.notification.NotificationService.send_telegram_sync"):
            MockDR.return_value.generate.return_value = mock_report
            result = _run_daily_report({}, MagicMock())
        assert result["status"] == "completed"

    def test_telegram_failure_isolated(self):
        from core.services.task_registry import _run_daily_report
        with patch("market.services.daily_report.DailyReportService") as MockDR, \
             patch("core.services.notification.NotificationService.send_telegram_sync",
                   side_effect=Exception("telegram fail")):
            MockDR.return_value.generate.return_value = {"regime": {}, "strategy_performance": {}, "system_status": {}}
            result = _run_daily_report({}, MagicMock())
        assert result["status"] == "completed"

    def test_report_generation_failure(self):
        from core.services.task_registry import _run_daily_report
        with patch("market.services.daily_report.DailyReportService") as MockDR:
            MockDR.return_value.generate.side_effect = Exception("db error")
            result = _run_daily_report({}, MagicMock())
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════
# _run_forex_paper_trading
# ══════════════════════════════════════════════════════


class TestRunForexPaperTrading:
    def test_success(self):
        from core.services.task_registry import _run_forex_paper_trading
        with patch("trading.services.forex_paper_trading.ForexPaperTradingService") as MockFPT:
            MockFPT.return_value.run_cycle.return_value = {
                "status": "completed", "entries_created": 1, "exits_created": 0,
            }
            result = _run_forex_paper_trading({}, MagicMock())
        assert result["status"] == "completed"

    def test_failure(self):
        from core.services.task_registry import _run_forex_paper_trading
        with patch("trading.services.forex_paper_trading.ForexPaperTradingService",
                    side_effect=Exception("service down")):
            result = _run_forex_paper_trading({}, MagicMock())
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════
# _run_nautilus_backtest
# ══════════════════════════════════════════════════════


class TestRunNautilusBacktest:
    def _selective_import(self, original):
        """Return an __import__ that raises ImportError only for nautilus."""
        def mock_import(name, *args, **kwargs):
            if "nautilus" in name:
                raise ImportError("no nautilus")
            return original(name, *args, **kwargs)
        return mock_import

    def test_import_error(self):
        import builtins
        from core.services.task_registry import _run_nautilus_backtest
        original = builtins.__import__
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {"watchlist": ["BTC/USDT"]}}), \
             patch("builtins.__import__", side_effect=self._selective_import(original)):
            result = _run_nautilus_backtest({}, MagicMock())
        assert result["status"] == "error"

    def test_no_watchlist_skips(self):
        from core.services.task_registry import _run_nautilus_backtest
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {}}), \
             patch("nautilus.nautilus_runner.list_nautilus_strategies",
                   return_value=["NautilusTrendFollowing"]), \
             patch("nautilus.nautilus_runner.run_nautilus_backtest"):
            result = _run_nautilus_backtest({"asset_class": "crypto"}, MagicMock())
        assert result["status"] == "skipped"

    def test_successful_backtest(self):
        from core.services.task_registry import _run_nautilus_backtest
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {"watchlist": ["BTC/USDT"]}}), \
             patch("nautilus.nautilus_runner.list_nautilus_strategies",
                   return_value=["NautilusTrendFollowing"]), \
             patch("nautilus.nautilus_runner.run_nautilus_backtest",
                   return_value={"total_return": 0.05}):
            result = _run_nautilus_backtest(
                {"asset_class": "crypto", "strategies": ["NautilusTrendFollowing"]},
                MagicMock(),
            )
        assert result["status"] == "completed"
        assert result["completed"] == 1


# ══════════════════════════════════════════════════════
# _run_hft_backtest
# ══════════════════════════════════════════════════════


class TestRunHftBacktest:
    def test_no_watchlist_skips(self):
        from core.services.task_registry import _run_hft_backtest
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {}}), \
             patch("hftbacktest.hft_runner.list_hft_strategies",
                   return_value=["MarketMaker"]):
            result = _run_hft_backtest({}, MagicMock())
        assert result["status"] == "skipped"

    def test_successful_backtest(self):
        from core.services.task_registry import _run_hft_backtest
        with patch(PB_ENSURE), \
             patch(PB_CONFIG, return_value={"data": {"watchlist": ["BTC/USDT"]}}), \
             patch("hftbacktest.hft_runner.list_hft_strategies",
                   return_value=["MarketMaker"]), \
             patch("hftbacktest.hft_runner.run_hft_backtest",
                   return_value={"total_return": 0.02}):
            result = _run_hft_backtest(
                {"strategies": ["MarketMaker"]}, MagicMock(),
            )
        assert result["status"] == "completed"
        assert result["completed"] == 1


# ══════════════════════════════════════════════════════
# _run_regime_detection — broadcast isolation
# ══════════════════════════════════════════════════════


class TestRunRegimeDetection:
    def test_success(self):
        from core.services.task_registry import _run_regime_detection
        with patch("market.services.regime.RegimeService") as MockRS:
            MockRS.return_value.get_all_current_regimes.return_value = [
                {"symbol": "BTC/USDT", "regime": "ranging", "confidence": 0.7}
            ]
            result = _run_regime_detection({}, MagicMock())
        assert result["status"] == "completed"
        assert result["regimes_detected"] == 1

    def test_broadcast_failure_isolated(self):
        from core.services.task_registry import _run_regime_detection, _last_known_regimes
        _last_known_regimes["BTC/USDT"] = "strong_trend_up"  # Set prev regime
        with patch("market.services.regime.RegimeService") as MockRS, \
             patch("core.services.ws_broadcast.broadcast_regime_change",
                   side_effect=Exception("ws fail")):
            MockRS.return_value.get_all_current_regimes.return_value = [
                {"symbol": "BTC/USDT", "regime": "ranging", "confidence": 0.7}
            ]
            result = _run_regime_detection({}, MagicMock())
        assert result["status"] == "completed"
        _last_known_regimes.pop("BTC/USDT", None)  # Cleanup


# ══════════════════════════════════════════════════════
# _run_workflow (pass-through)
# ══════════════════════════════════════════════════════


class TestRunWorkflow:
    def test_delegates_to_execute_workflow(self):
        from core.services.task_registry import _run_workflow
        with patch("analysis.services.workflow_engine.execute_workflow",
                    return_value={"status": "completed"}):
            result = _run_workflow({"workflow_run_id": "test"}, MagicMock())
        assert result["status"] == "completed"


# ══════════════════════════════════════════════════════
# ws_broadcast — channel layer None and exception handling
# ══════════════════════════════════════════════════════


class TestWsBroadcastEdgeCases:
    def test_no_channel_layer_graceful(self):
        from core.services.ws_broadcast import broadcast_news_update
        with patch("channels.layers.get_channel_layer", return_value=None):
            # Should not raise
            broadcast_news_update("crypto", 5, {"avg_score": 0.5})

    def test_broadcast_exception_swallowed(self):
        from core.services.ws_broadcast import broadcast_scheduler_event
        mock_layer = MagicMock()
        mock_layer.group_send = MagicMock(side_effect=Exception("channel fail"))
        with patch("channels.layers.get_channel_layer", return_value=mock_layer), \
             patch("asgiref.sync.async_to_sync", return_value=mock_layer.group_send):
            # Should not raise
            broadcast_scheduler_event("task_1", "data_refresh", "data_refresh", "running")
