"""Tests for operational reliability fixes:
- Scheduler resilience (atexit, verify retry)
- ScreenResult persistence from VBT screen jobs
- Freqtrade equity sync to RiskState
- ML bootstrap on startup
- Health check scheduler warning
"""

from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings as settings_mod

from analysis.models import BackgroundJob, ScreenResult
from analysis.services.job_runner import JobRunner

# ── Fix 2: Scheduler resilience ──────────────────────────────


class TestSchedulerAtexit:
    """Test atexit resilience in TaskScheduler.start()."""

    def _noop_timer(self):
        """Timer mock that does nothing (prevents bootstrap DB access in unit tests)."""
        mock = MagicMock()
        mock.return_value.start = MagicMock()
        return mock

    def test_atexit_failure_does_not_prevent_start(self):
        """Scheduler should start even if atexit.register raises RuntimeError."""
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        with (
            patch.object(scheduler, "_sync_tasks_to_db"),
            patch.object(scheduler, "_sync_workflows_to_db"),
            patch.object(scheduler, "_schedule_active_tasks"),
            patch.object(scheduler, "_active_task_count", return_value=0),
            patch.object(scheduler, "_validate_watchlist"),
            patch.object(scheduler, "trigger_task"),
            patch("apscheduler.schedulers.background.BackgroundScheduler") as mock_bs,
            patch("threading.Thread"),
            patch("core.services.scheduler.threading.Timer", self._noop_timer()),
            patch("core.services.scheduler.atexit") as mock_atexit,
        ):
            mock_atexit.register.side_effect = RuntimeError("can't register atexit")
            mock_bs.return_value = MagicMock()
            scheduler.start()

        assert scheduler.running is True

    def test_atexit_success(self):
        """Normal atexit registration should work."""
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        with (
            patch.object(scheduler, "_sync_tasks_to_db"),
            patch.object(scheduler, "_sync_workflows_to_db"),
            patch.object(scheduler, "_schedule_active_tasks"),
            patch.object(scheduler, "_active_task_count", return_value=0),
            patch.object(scheduler, "_validate_watchlist"),
            patch.object(scheduler, "trigger_task"),
            patch("apscheduler.schedulers.background.BackgroundScheduler") as mock_bs,
            patch("threading.Thread"),
            patch("core.services.scheduler.threading.Timer", self._noop_timer()),
            patch("core.services.scheduler.atexit") as mock_atexit,
        ):
            mock_bs.return_value = MagicMock()
            scheduler.start()

        assert scheduler.running is True
        mock_atexit.register.assert_called_once_with(scheduler.shutdown)


class TestSchedulerVerify:
    """Test _verify_scheduler retry logic."""

    def test_verify_retries_on_failure(self):
        from core.apps import _verify_scheduler

        mock_sched = MagicMock()
        mock_sched.running = False
        mock_sched.start.return_value = None
        # After start(), still not running
        type(mock_sched).running = property(lambda self: False)

        with patch("core.services.scheduler.get_scheduler", return_value=mock_sched):
            _verify_scheduler()

        mock_sched.start.assert_called_once()

    def test_verify_succeeds_on_retry(self):
        from core.apps import _verify_scheduler

        mock_sched = MagicMock()
        # First check: not running; after start(): running
        running_vals = iter([False, True])
        type(mock_sched).running = property(lambda self: next(running_vals))

        with patch("core.services.scheduler.get_scheduler", return_value=mock_sched):
            _verify_scheduler()

        mock_sched.start.assert_called_once()

    def test_verify_skips_when_running(self):
        from core.apps import _verify_scheduler

        mock_sched = MagicMock()
        mock_sched.running = True

        with patch("core.services.scheduler.get_scheduler", return_value=mock_sched):
            _verify_scheduler()

        mock_sched.start.assert_not_called()

    def test_verify_handles_start_exception(self):
        """Start exception should not propagate — verify catches it."""
        from core.apps import _verify_scheduler

        mock_sched = MagicMock()
        mock_sched.running = False
        mock_sched.start.side_effect = RuntimeError("boom")

        with patch("core.services.scheduler.get_scheduler", return_value=mock_sched):
            # Should not raise
            _verify_scheduler()

        mock_sched.start.assert_called_once()


# ── Fix 3: ScreenResult persistence ──────────────────────────


@pytest.mark.django_db
class TestScreenResultPersistence:
    """Test VBT screen results are persisted to ScreenResult table."""

    def _make_runner(self):
        runner = JobRunner.__new__(JobRunner)
        runner._executor = MagicMock()
        return runner

    def test_vbt_screen_creates_screen_results(self):
        """Successful VBT screen should create ScreenResult records."""
        job = BackgroundJob.objects.create(
            id="test-screen-1",
            job_type="scheduled_vbt_screen",
            status="running",
            params={"asset_class": "crypto", "timeframe": "1h"},
        )

        result = {
            "status": "completed",
            "symbols_screened": 1,
            "results": [
                {
                    "symbol": "BTC/USDT",
                    "status": "completed",
                    "result": {
                        "symbol": "BTC/USDT",
                        "timeframe": "1h",
                        "strategies": {
                            "sma_crossover": {
                                "total_combinations": 100,
                                "top_results": [
                                    {"params": {"fast": 10, "slow": 50}, "sharpe": 1.5}
                                ],
                                "summary": {"best_sharpe": 1.5},
                            },
                            "rsi_divergence": {
                                "total_combinations": 50,
                                "top_results": [{"params": {"period": 14}, "sharpe": 0.8}],
                                "summary": {"best_sharpe": 0.8},
                            },
                        },
                    },
                },
            ],
        }

        def fake_run(params, progress_cb):
            return result

        runner = self._make_runner()
        runner._run_job("test-screen-1", fake_run, {"asset_class": "crypto", "timeframe": "1h"})

        job.refresh_from_db()
        assert job.status == "completed"

        screens = ScreenResult.objects.filter(job=job)
        assert screens.count() == 2
        assert set(screens.values_list("strategy_name", flat=True)) == {
            "sma_crossover",
            "rsi_divergence",
        }
        assert screens.filter(symbol="BTC/USDT").count() == 2

    def test_vbt_screen_skips_error_strategies(self):
        """Strategies with errors should not create ScreenResult records."""
        job = BackgroundJob.objects.create(
            id="test-screen-2",
            job_type="scheduled_vbt_screen",
            status="running",
            params={"asset_class": "crypto"},
        )

        result = {
            "status": "completed",
            "results": [
                {
                    "symbol": "ETH/USDT",
                    "status": "completed",
                    "result": {
                        "strategies": {
                            "sma_crossover": {
                                "total_combinations": 50,
                                "top_results": [],
                                "summary": {},
                            },
                            "broken_strat": {"error": "Not enough data"},
                        },
                    },
                },
            ],
        }

        def fake_run(params, progress_cb):
            return result

        runner = self._make_runner()
        runner._run_job("test-screen-2", fake_run, {"asset_class": "crypto"})

        screens = ScreenResult.objects.filter(job=job)
        assert screens.count() == 1
        assert screens.first().strategy_name == "sma_crossover"

    def test_non_vbt_job_does_not_create_screen_results(self):
        """Non-VBT jobs should not create ScreenResult records."""
        job = BackgroundJob.objects.create(
            id="test-screen-3",
            job_type="scheduled_data_refresh",
            status="running",
            params={},
        )

        def fake_run(params, progress_cb):
            return {"status": "completed", "results": []}

        runner = self._make_runner()
        runner._run_job("test-screen-3", fake_run, {})

        assert ScreenResult.objects.filter(job=job).count() == 0

    def test_vbt_screen_skips_failed_symbols(self):
        """Symbols with status=error should not create ScreenResult records."""
        job = BackgroundJob.objects.create(
            id="test-screen-4",
            job_type="scheduled_vbt_screen",
            status="running",
            params={"asset_class": "crypto"},
        )

        result = {
            "status": "completed",
            "results": [
                {"symbol": "BAD/USDT", "status": "error", "error": "No data"},
            ],
        }

        def fake_run(params, progress_cb):
            return result

        runner = self._make_runner()
        runner._run_job("test-screen-4", fake_run, {"asset_class": "crypto"})

        assert ScreenResult.objects.filter(job=job).count() == 0


# ── Fix 4: Freqtrade equity sync ─────────────────────────────


class TestFreqtradeEquitySync:
    """Test _sync_freqtrade_equity() function."""

    @patch("requests.get")
    @pytest.mark.django_db
    def test_sync_updates_risk_state(self, mock_get):
        """Successful sync should update RiskState equity."""
        from portfolio.models import Portfolio
        from risk.models import RiskLimits, RiskState

        portfolio = Portfolio.objects.create(
            name="Test Portfolio",
            exchange_id="kraken",
            asset_class="crypto",
        )
        RiskState.objects.create(
            portfolio_id=portfolio.id,
            total_equity=10000,
            peak_equity=10000,
        )
        RiskLimits.objects.create(portfolio_id=portfolio.id)

        # Mock Freqtrade responses
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"profit_all_coin": -41.0}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        # Mock FREQTRADE_INSTANCES with dry_run_wallet (actual capital)
        mock_instances = [
            {"name": "CIV1", "url": "http://ft1:8080", "dry_run_wallet": 200.0},
            {"name": "BMR", "url": "http://ft2:8083", "dry_run_wallet": 200.0},
            {"name": "VB", "url": "http://ft3:8084", "dry_run_wallet": 100.0},
        ]
        with (
            patch.object(settings_mod, "FREQTRADE_API_URL", "http://ft1:8080"),
            patch.object(settings_mod, "FREQTRADE_BMR_API_URL", "http://ft2:8083"),
            patch.object(settings_mod, "FREQTRADE_VB_API_URL", "http://ft3:8084"),
            patch.object(settings_mod, "FREQTRADE_INSTANCES", mock_instances),
            patch("core.platform_bridge.ensure_platform_imports"),
        ):
            from core.services.task_registry import _sync_freqtrade_equity

            result = _sync_freqtrade_equity()

        assert result["equity_updated"] is True
        # 3 instances × -41 = -123 total PnL
        assert result["total_pnl"] == pytest.approx(-123.0)

        state = RiskState.objects.get(portfolio_id=portfolio.id)
        # Actual capital: $200 + $200 + $100 = $500, equity = 500 - 123 = 377
        assert state.total_equity == pytest.approx(500.0 - 123.0)
        # daily_pnl should reflect the equity change from daily_start_equity
        assert state.daily_pnl == pytest.approx(state.total_equity - state.daily_start_equity)

    @patch("requests.get")
    @pytest.mark.django_db
    def test_sync_handles_connection_error(self, mock_get):
        """Connection errors should be caught and reported per-instance."""
        from portfolio.models import Portfolio

        Portfolio.objects.create(
            name="Test",
            exchange_id="kraken",
            asset_class="crypto",
        )

        mock_get.side_effect = Exception("Connection refused")

        mock_config = {"trading": {"initial_capital": 10000.0}}
        with (
            patch.object(settings_mod, "FREQTRADE_API_URL", "http://ft1:8080"),
            patch.object(settings_mod, "FREQTRADE_BMR_API_URL", ""),
            patch.object(settings_mod, "FREQTRADE_VB_API_URL", ""),
            patch("core.platform_bridge.get_platform_config", return_value=mock_config),
            patch("core.platform_bridge.ensure_platform_imports"),
        ):
            from core.services.task_registry import _sync_freqtrade_equity

            result = _sync_freqtrade_equity()

        assert result["total_pnl"] == 0.0
        assert result["instances"][0]["status"] == "error"

    @patch("requests.get")
    @pytest.mark.django_db
    def test_sync_uses_instance_urls_as_fallback(self, mock_get):
        """When top-level settings are empty, falls back to FREQTRADE_INSTANCES."""
        from portfolio.models import Portfolio

        Portfolio.objects.create(
            name="Test",
            exchange_id="kraken",
            asset_class="crypto",
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"profit_all_coin": 5.0}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        mock_config = {"trading": {"initial_capital": 10000.0}}
        with (
            patch.object(settings_mod, "FREQTRADE_API_URL", ""),
            patch.object(settings_mod, "FREQTRADE_BMR_API_URL", ""),
            patch.object(settings_mod, "FREQTRADE_VB_API_URL", ""),
            patch("core.platform_bridge.get_platform_config", return_value=mock_config),
            patch("core.platform_bridge.ensure_platform_imports"),
        ):
            from core.services.task_registry import _sync_freqtrade_equity

            result = _sync_freqtrade_equity()

        # Should have used instance URLs (3 instances in settings)
        assert result["equity_updated"] is True
        assert len(result["instances"]) == 3


class TestRiskMonitoringWithSync:
    """Test that _run_risk_monitoring calls equity sync."""

    @pytest.mark.django_db
    def test_risk_monitoring_calls_sync(self):
        """risk_monitoring should call _sync_freqtrade_equity before risk checks."""
        from portfolio.models import Portfolio
        from risk.models import RiskLimits, RiskState

        portfolio = Portfolio.objects.create(
            name="Test",
            exchange_id="kraken",
            asset_class="crypto",
        )
        RiskState.objects.create(
            portfolio_id=portfolio.id,
            total_equity=10000,
            peak_equity=10000,
        )
        RiskLimits.objects.create(portfolio_id=portfolio.id)

        sync_result = {"total_pnl": -10.0, "equity_updated": True, "instances": []}

        with patch(
            "core.services.task_registry._sync_freqtrade_equity", return_value=sync_result
        ) as mock_sync:
            from core.services.task_registry import _run_risk_monitoring

            result = _run_risk_monitoring({}, lambda p, m: None)

        mock_sync.assert_called_once()
        assert result["equity_sync"] == sync_result

    @pytest.mark.django_db
    def test_risk_monitoring_continues_on_sync_failure(self):
        """Risk monitoring should continue even if equity sync fails."""
        from portfolio.models import Portfolio
        from risk.models import RiskLimits, RiskState

        portfolio = Portfolio.objects.create(
            name="Test",
            exchange_id="kraken",
            asset_class="crypto",
        )
        RiskState.objects.create(
            portfolio_id=portfolio.id,
            total_equity=10000,
            peak_equity=10000,
        )
        RiskLimits.objects.create(portfolio_id=portfolio.id)

        with patch(
            "core.services.task_registry._sync_freqtrade_equity", side_effect=Exception("boom")
        ):
            from core.services.task_registry import _run_risk_monitoring

            result = _run_risk_monitoring({}, lambda p, m: None)

        assert result["status"] == "completed"
        assert result["portfolios_checked"] == 1


# ── Fix 5: ML bootstrap ──────────────────────────────────────


class TestMLBootstrap:
    """Test ML training is triggered on startup when no models exist."""

    def _make_immediate_timer(self):
        """Return a Timer mock that executes the callback immediately."""

        class ImmediateTimer:
            def __init__(self, delay, fn, *args, **kwargs):
                self._fn = fn
                self._args = args

            def start(self):
                self._fn(*self._args)

        return ImmediateTimer

    def test_ml_bootstrap_triggers_training_when_no_models(self):
        """Should call trigger_task('ml_training') when ModelRegistry is empty."""
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        with (
            patch.object(scheduler, "_sync_tasks_to_db"),
            patch.object(scheduler, "_sync_workflows_to_db"),
            patch.object(scheduler, "_schedule_active_tasks"),
            patch.object(scheduler, "_active_task_count", return_value=0),
            patch.object(scheduler, "_validate_watchlist"),
            patch.object(scheduler, "trigger_task") as mock_trigger,
            patch("apscheduler.schedulers.background.BackgroundScheduler") as mock_bs,
            patch("threading.Thread"),
            patch("core.services.scheduler.threading.Timer", self._make_immediate_timer()),
            patch("core.services.scheduler.atexit"),
        ):
            mock_bs.return_value = MagicMock()
            with patch("common.ml.registry.ModelRegistry") as mock_reg:
                mock_reg.return_value.list_models.return_value = []
                scheduler.start()

        mock_trigger.assert_called_once_with("ml_training")

    def test_ml_bootstrap_skips_when_models_exist(self):
        """Should NOT trigger training when models already exist."""
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        with (
            patch.object(scheduler, "_sync_tasks_to_db"),
            patch.object(scheduler, "_sync_workflows_to_db"),
            patch.object(scheduler, "_schedule_active_tasks"),
            patch.object(scheduler, "_active_task_count", return_value=0),
            patch.object(scheduler, "_validate_watchlist"),
            patch.object(scheduler, "trigger_task") as mock_trigger,
            patch("apscheduler.schedulers.background.BackgroundScheduler") as mock_bs,
            patch("threading.Thread"),
            patch("core.services.scheduler.threading.Timer", self._make_immediate_timer()),
            patch("core.services.scheduler.atexit"),
        ):
            mock_bs.return_value = MagicMock()
            with patch("common.ml.registry.ModelRegistry") as mock_reg:
                mock_reg.return_value.list_models.return_value = ["model_1"]
                scheduler.start()

        mock_trigger.assert_not_called()

    def test_ml_bootstrap_handles_import_error(self):
        """ML bootstrap should not block scheduler start on ImportError."""
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        with (
            patch.object(scheduler, "_sync_tasks_to_db"),
            patch.object(scheduler, "_sync_workflows_to_db"),
            patch.object(scheduler, "_schedule_active_tasks"),
            patch.object(scheduler, "_active_task_count", return_value=0),
            patch.object(scheduler, "_validate_watchlist"),
            patch("apscheduler.schedulers.background.BackgroundScheduler") as mock_bs,
            patch("threading.Thread"),
            patch("core.services.scheduler.threading.Timer", self._make_immediate_timer()),
            patch("core.services.scheduler.atexit"),
        ):
            mock_bs.return_value = MagicMock()
            with patch.dict("sys.modules", {"common.ml.registry": None}):
                # Should not raise, scheduler should still be running
                scheduler.start()

        assert scheduler.running is True


# ── Health check scheduler warning ────────────────────────────


@pytest.mark.django_db
class TestHealthCheckSchedulerWarning:
    """Test health check reports warning when scheduler not running."""

    def test_health_check_warns_scheduler_down(self, client, admin_user):
        client.force_login(admin_user)

        mock_sched = MagicMock()
        mock_sched.running = False

        with patch("core.services.scheduler.get_scheduler", return_value=mock_sched):
            resp = client.get("/api/health/?detailed=true")

        data = resp.json()
        assert data["checks"]["scheduler"]["status"] == "warning"
        assert data["checks"]["scheduler"]["running"] is False

    def test_health_check_ok_scheduler_running(self, client, admin_user):
        client.force_login(admin_user)

        mock_sched = MagicMock()
        mock_sched.running = True

        with patch("core.services.scheduler.get_scheduler", return_value=mock_sched):
            resp = client.get("/api/health/?detailed=true")

        data = resp.json()
        assert data["checks"]["scheduler"]["status"] == "ok"
        assert data["checks"]["scheduler"]["running"] is True


# ── Settings: ml_predict and ml_feedback tasks ────────────────


class TestScheduledTaskSettings:
    """Verify ml_predict and ml_feedback are in SCHEDULED_TASKS."""

    def test_ml_predict_in_scheduled_tasks(self):
        from django.conf import settings

        assert "ml_predict" in settings.SCHEDULED_TASKS
        task = settings.SCHEDULED_TASKS["ml_predict"]
        assert task["task_type"] == "ml_predict"
        assert task["interval_seconds"] == 3600

    def test_ml_feedback_in_scheduled_tasks(self):
        from django.conf import settings

        assert "ml_feedback" in settings.SCHEDULED_TASKS
        task = settings.SCHEDULED_TASKS["ml_feedback"]
        assert task["task_type"] == "ml_feedback"
        assert task["interval_seconds"] == 3600


# ── Settings: Freqtrade settings ──────────────────────────────


class TestFreqtradeSettings:
    """Verify Freqtrade settings are available."""

    def test_freqtrade_settings_exist(self):
        from django.conf import settings

        assert hasattr(settings, "FREQTRADE_API_URL")
        assert hasattr(settings, "FREQTRADE_BMR_API_URL")
        assert hasattr(settings, "FREQTRADE_VB_API_URL")
        assert hasattr(settings, "FREQTRADE_USERNAME")
        assert hasattr(settings, "FREQTRADE_PASSWORD")
