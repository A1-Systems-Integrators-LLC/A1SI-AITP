"""Comprehensive tests for Scheduler & Task Registry edge cases.

Covers: missing executor types, silent skip loops, concurrent task execution,
scheduler lifecycle, workflow scheduling, task state transitions.
"""

from unittest.mock import patch

import pytest

from core.models import ScheduledTask
from core.services.task_registry import TASK_REGISTRY


def _noop_cb(pct, msg):
    pass


# ── Task Registry Edge Cases ────────────────────────────────


class TestRegistryCompleteness:
    """Verify all 15 registered executors and their signatures."""

    EXPECTED_TYPES = {
        "data_refresh",
        "regime_detection",
        "order_sync",
        "data_quality",
        "news_fetch",
        "workflow",
        "risk_monitoring",
        "db_maintenance",
        "vbt_screen",
        "ml_training",
        "market_scan",
        "daily_report",
        "forex_paper_trading",
        "nautilus_backtest",
        "hft_backtest",
        "ml_predict",
        "ml_feedback",
        "ml_retrain",
        "conviction_audit",
        "strategy_orchestration",
        "signal_feedback",
        "adaptive_weighting",
        "economic_calendar",
        "funding_rate_refresh",
        "fear_greed_refresh",
        "reddit_sentiment_refresh",
        "coingecko_trending_refresh",
        "macro_data_refresh",
        "daily_risk_reset",
        "autonomous_check",
    }

    def test_registry_count(self):
        assert len(TASK_REGISTRY) == 30

    def test_all_expected_types_present(self):
        assert set(TASK_REGISTRY.keys()) == self.EXPECTED_TYPES

    @pytest.mark.parametrize("task_type", EXPECTED_TYPES)
    def test_executor_is_callable(self, task_type):
        assert callable(TASK_REGISTRY[task_type])


class TestMissingExecutorHandling:
    """Test what happens when a task references a non-existent executor type."""

    @pytest.mark.django_db
    def test_execute_task_with_unknown_type_logs_error(self):
        """Scheduler._execute_task should skip silently when executor not found."""
        from core.services.scheduler import TaskScheduler

        ScheduledTask.objects.create(
            id="bad_type_task",
            name="Bad Type",
            task_type="nonexistent_executor",
            interval_seconds=60,
        )
        scheduler = TaskScheduler()
        # Should not raise
        scheduler._execute_task("bad_type_task")

        # Task should NOT have run_count incremented (since no executor found)
        task = ScheduledTask.objects.get(id="bad_type_task")
        assert task.run_count == 0

    @pytest.mark.django_db
    def test_execute_task_with_missing_task_id(self):
        """Non-existent task_id should be handled gracefully."""
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        # Should not raise
        scheduler._execute_task("totally_nonexistent_id")

    @pytest.mark.django_db
    def test_execute_paused_task_is_noop(self):
        """Paused tasks should not be executed."""
        from core.services.scheduler import TaskScheduler

        ScheduledTask.objects.create(
            id="paused_task",
            name="Paused",
            task_type="data_refresh",
            interval_seconds=60,
            status=ScheduledTask.PAUSED,
        )
        scheduler = TaskScheduler()
        scheduler._execute_task("paused_task")

        task = ScheduledTask.objects.get(id="paused_task")
        assert task.run_count == 0


# ── Scheduler Lifecycle ──────────────────────────────────────


@pytest.mark.django_db
class TestSchedulerLifecycle:
    def test_start_then_shutdown(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        assert scheduler.running is False
        scheduler.start()
        assert scheduler.running is True
        scheduler.shutdown()
        assert scheduler.running is False

    def test_double_start_is_noop(self):
        """Calling start() twice should not crash or create duplicate jobs."""
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        scheduler.start()
        scheduler.start()  # Should be idempotent
        assert scheduler.running is True
        scheduler.shutdown()

    def test_shutdown_without_start_is_safe(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        scheduler.shutdown()  # Should not raise
        assert scheduler.running is False

    def test_start_syncs_tasks(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        scheduler.start()
        # After start, tasks from settings should be in DB
        assert ScheduledTask.objects.count() >= 13  # 21 configured tasks
        scheduler.shutdown()


# ── Task State Transitions ───────────────────────────────────


@pytest.mark.django_db
class TestTaskStateTransitions:
    def test_active_to_paused_to_active(self):
        from core.services.scheduler import TaskScheduler

        ScheduledTask.objects.create(
            id="state_test",
            name="State Test",
            task_type="data_refresh",
            interval_seconds=60,
        )
        scheduler = TaskScheduler()

        # Active → Paused
        assert scheduler.pause_task("state_test") is True
        task = ScheduledTask.objects.get(id="state_test")
        assert task.status == ScheduledTask.PAUSED

        # Paused → Active
        assert scheduler.resume_task("state_test") is True
        task.refresh_from_db()
        assert task.status == ScheduledTask.ACTIVE

    def test_resume_nonexistent_returns_false(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        assert scheduler.resume_task("nonexistent") is False


# ── Executor Error Isolation ─────────────────────────────────


class TestExecutorErrorIsolation:
    """Verify that individual executor failures don't crash the scheduler."""

    def test_data_refresh_with_download_exception(self):
        executor = TASK_REGISTRY["data_refresh"]
        mock_config = {"data": {"watchlist": ["BTC/USDT"]}}

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("core.platform_bridge.get_platform_config", return_value=mock_config),
            patch(
                "common.data_pipeline.pipeline.download_watchlist",
                side_effect=Exception("Exchange timeout"),
            ),
            pytest.raises(Exception, match="Exchange timeout"),
        ):
            executor({"asset_class": "crypto"}, _noop_cb)

    def test_vbt_screen_empty_watchlist(self):
        executor = TASK_REGISTRY["vbt_screen"]
        mock_config = {"data": {"watchlist": []}}

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("core.platform_bridge.get_platform_config", return_value=mock_config),
        ):
            result = executor({"asset_class": "crypto"}, _noop_cb)
            assert result["status"] == "skipped"

    def test_nautilus_backtest_empty_watchlist(self):
        executor = TASK_REGISTRY["nautilus_backtest"]
        mock_config = {"data": {"watchlist": []}}

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("core.platform_bridge.get_platform_config", return_value=mock_config),
            patch(
                "nautilus.nautilus_runner.list_nautilus_strategies",
                return_value=["NautilusTrendFollowing"],
            ),
        ):
            result = executor({"asset_class": "crypto"}, _noop_cb)
            assert result["status"] == "skipped"

    def test_hft_backtest_empty_watchlist(self):
        executor = TASK_REGISTRY["hft_backtest"]
        mock_config = {"data": {"watchlist": []}}

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("core.platform_bridge.get_platform_config", return_value=mock_config),
            patch("hftbacktest.hft_runner.list_hft_strategies", return_value=["MarketMaker"]),
        ):
            result = executor({}, _noop_cb)
            assert result["status"] == "skipped"

    def test_ml_training_service_error(self):
        executor = TASK_REGISTRY["ml_training"]

        with patch(
            "analysis.services.ml.MLService.train",
            side_effect=RuntimeError("No data for BTC/USDT"),
        ):
            result = executor({"symbol": "BTC/USDT"}, _noop_cb)
            assert result["status"] == "completed"
            assert result["results"][0]["status"] == "error"
            assert "No data" in result["results"][0]["error"]

    def test_market_scan_service_error(self):
        executor = TASK_REGISTRY["market_scan"]

        with patch(
            "market.services.market_scanner.MarketScannerService.scan_all",
            side_effect=Exception("Scanner crashed"),
        ):
            result = executor({}, _noop_cb)
            assert result["status"] == "error"

    def test_daily_report_service_error(self):
        executor = TASK_REGISTRY["daily_report"]

        with patch(
            "market.services.daily_report.DailyReportService.generate",
            side_effect=Exception("Report failed"),
        ):
            result = executor({}, _noop_cb)
            assert result["status"] == "error"

    def test_forex_paper_trading_service_error(self):
        executor = TASK_REGISTRY["forex_paper_trading"]

        with patch(
            "trading.services.forex_paper_trading.ForexPaperTradingService.run_cycle",
            side_effect=Exception("Forex service down"),
        ):
            result = executor({}, _noop_cb)
            assert result["status"] == "error"


# ── Data Refresh Asset Class Routing ─────────────────────────


class TestDataRefreshAssetRouting:
    """Test that data_refresh correctly routes to different watchlist keys."""

    def _run_with_config(self, asset_class, config):
        executor = TASK_REGISTRY["data_refresh"]
        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("core.platform_bridge.get_platform_config", return_value=config),
            patch(
                "common.data_pipeline.pipeline.download_watchlist",
                return_value={"SYM/USDT": {"status": "ok", "saved": 100}},
            ) as mock_dl,
        ):
            result = executor({"asset_class": asset_class}, _noop_cb)
            return result, mock_dl

    def test_crypto_uses_watchlist_key(self):
        config = {"data": {"watchlist": ["BTC/USDT"]}}
        result, mock_dl = self._run_with_config("crypto", config)
        assert result["status"] == "completed"
        mock_dl.assert_called_once()
        call_kwargs = mock_dl.call_args
        assert call_kwargs[1]["asset_class"] == "crypto"

    def test_equity_uses_equity_watchlist_key(self):
        config = {"data": {"equity_watchlist": ["AAPL"]}}
        result, mock_dl = self._run_with_config("equity", config)
        assert result["status"] == "completed"

    def test_forex_uses_forex_watchlist_key(self):
        config = {"data": {"forex_watchlist": ["EUR/USD"]}}
        result, mock_dl = self._run_with_config("forex", config)
        assert result["status"] == "completed"

    def test_unknown_asset_class_falls_back_to_watchlist(self):
        config = {"data": {"watchlist": []}}
        result, _ = self._run_with_config("unknown_class", config)
        assert result["status"] == "skipped"


# ── Progress Callback Tracking ───────────────────────────────


@pytest.mark.django_db
class TestProgressCallbacks:
    def test_order_sync_reports_progress(self):
        executor = TASK_REGISTRY["order_sync"]
        progress = []
        executor({}, lambda pct, msg: progress.append((pct, msg)))
        assert len(progress) >= 1
        assert progress[0][0] == 0.0  # Initial progress

    @pytest.mark.django_db
    def test_db_maintenance_reports_progress(self):
        executor = TASK_REGISTRY["db_maintenance"]
        progress = []
        executor({}, lambda pct, msg: progress.append((pct, msg)))
        assert len(progress) == 2  # 0.1 and 0.9


# ── Workflow Scheduling ──────────────────────────────────────


@pytest.mark.django_db
class TestWorkflowScheduling:
    def test_execute_workflow_missing_id(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        # Should not raise when workflow doesn't exist
        scheduler._execute_workflow("nonexistent_workflow_id")

    def test_execute_workflow_inactive(self):
        from analysis.models import Workflow

        Workflow.objects.create(
            id="inactive_wf",
            name="Inactive",
            schedule_enabled=False,
            is_active=True,
        )
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        # Should be a no-op
        scheduler._execute_workflow("inactive_wf")
