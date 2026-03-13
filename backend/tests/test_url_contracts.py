"""
Cross-service URL contract tests.

Validates that every URL constructed by Python HTTP clients (Freqtrade strategies,
NautilusTrader strategies, frontend API modules) resolves to a valid Django URL pattern.

These tests prevent the class of bugs where a client constructs a URL like
``/api/analysis/signals/...`` but the actual Django route is ``/api/signals/...``.
Every cross-service URL must be tested here.

If a new endpoint is added, add a contract test. If a URL changes, update BOTH
the client code AND these tests.
"""

import re

from django.test import SimpleTestCase
from django.urls import resolve, reverse


class FreqtradeStrategyURLContractTest(SimpleTestCase):
    """Validate URLs that Freqtrade strategies construct when calling Django."""

    def test_risk_check_trade_url(self):
        """Freqtrade strategies POST /api/risk/{id}/check-trade/ for risk gating."""
        resolved = resolve("/api/risk/1/check-trade/")
        self.assertEqual(resolved.url_name, "risk-check-trade")
        self.assertEqual(resolved.kwargs, {"portfolio_id": 1})

    def test_signal_entry_check_url(self):
        """_conviction_helpers.py POST /api/signals/{symbol}/entry-check/."""
        resolved = resolve("/api/signals/BTC-USDT/entry-check/")
        self.assertEqual(resolved.url_name, "signal-entry-check")
        self.assertEqual(resolved.kwargs, {"symbol": "BTC-USDT"})

    def test_signal_entry_check_encodes_slash(self):
        """Symbols like BTC/USDT are encoded as BTC-USDT in URLs."""
        symbol = "ETH/USDT".replace("/", "-")
        resolved = resolve(f"/api/signals/{symbol}/entry-check/")
        self.assertEqual(resolved.url_name, "signal-entry-check")
        self.assertEqual(resolved.kwargs["symbol"], "ETH-USDT")

    def test_strategy_status_url(self):
        """_conviction_helpers.check_strategy_paused GET /api/signals/strategy-status/."""
        resolved = resolve("/api/signals/strategy-status/")
        self.assertEqual(resolved.url_name, "signal-strategy-status")


class NautilusStrategyURLContractTest(SimpleTestCase):
    """Validate URLs that NautilusTrader strategies construct when calling Django."""

    def test_risk_check_trade_url(self):
        """nautilus/strategies/base.py POST /api/risk/{id}/check-trade/."""
        resolved = resolve("/api/risk/1/check-trade/")
        self.assertEqual(resolved.url_name, "risk-check-trade")

    def test_risk_check_trade_trailing_slash(self):
        """Ensure /check-trade/ has trailing slash (Django APPEND_SLASH may not
        apply to POST requests, causing 500 errors)."""
        url = "/api/risk/1/check-trade/"
        self.assertTrue(url.endswith("/"))
        resolved = resolve(url)
        self.assertEqual(resolved.url_name, "risk-check-trade")

    def test_signal_entry_check_url(self):
        """nautilus/strategies/base.py POST /api/signals/{symbol}/entry-check/."""
        resolved = resolve("/api/signals/BTC-USDT/entry-check/")
        self.assertEqual(resolved.url_name, "signal-entry-check")


class FrontendAPIURLContractTest(SimpleTestCase):
    """Validate every URL the frontend API modules construct.

    These map to the paths in frontend/src/api/*.ts, which prepend /api/
    via the api client. Each test validates the full path resolves correctly.
    """

    # ── Auth & Core ──

    def test_auth_login(self):
        resolved = resolve("/api/auth/login/")
        self.assertEqual(resolved.url_name, "auth-login")

    def test_auth_logout(self):
        resolved = resolve("/api/auth/logout/")
        self.assertEqual(resolved.url_name, "auth-logout")

    def test_auth_status(self):
        resolved = resolve("/api/auth/status/")
        self.assertEqual(resolved.url_name, "auth-status")

    def test_health(self):
        resolved = resolve("/api/health/")
        self.assertEqual(resolved.url_name, "health")

    def test_platform_status(self):
        resolved = resolve("/api/platform/status/")
        self.assertEqual(resolved.url_name, "platform-status")

    def test_platform_config(self):
        resolved = resolve("/api/platform/config/")
        self.assertEqual(resolved.url_name, "platform-config")

    def test_dashboard_kpis(self):
        resolved = resolve("/api/dashboard/kpis/")
        self.assertEqual(resolved.url_name, "dashboard-kpis")

    def test_audit_log(self):
        resolved = resolve("/api/audit-log/")
        self.assertEqual(resolved.url_name, "audit-log-list")

    # ── Exchanges ──

    def test_exchanges(self):
        resolved = resolve("/api/exchanges/")
        self.assertEqual(resolved.url_name, "exchange-list")

    def test_exchange_configs_list(self):
        resolved = resolve("/api/exchange-configs/")
        self.assertEqual(resolved.url_name, "exchange-config-list")

    def test_exchange_configs_detail(self):
        resolved = resolve("/api/exchange-configs/1/")
        self.assertEqual(resolved.url_name, "exchange-config-detail")

    def test_exchange_configs_test(self):
        resolved = resolve("/api/exchange-configs/1/test/")
        self.assertEqual(resolved.url_name, "exchange-config-test")

    def test_exchange_configs_rotate(self):
        resolved = resolve("/api/exchange-configs/1/rotate/")
        self.assertEqual(resolved.url_name, "exchange-config-rotate")

    # ── Data Sources ──

    def test_data_sources_list(self):
        resolved = resolve("/api/data-sources/")
        self.assertEqual(resolved.url_name, "data-source-list")

    def test_data_sources_detail(self):
        resolved = resolve("/api/data-sources/1/")
        self.assertEqual(resolved.url_name, "data-source-detail")

    # ── Trading ──

    def test_trading_orders(self):
        resolved = resolve("/api/trading/orders/")
        self.assertEqual(resolved.url_name, "order-list")

    def test_trading_order_detail(self):
        resolved = resolve("/api/trading/orders/1/")
        self.assertEqual(resolved.url_name, "order-detail")

    def test_trading_order_cancel(self):
        resolved = resolve("/api/trading/orders/1/cancel/")
        self.assertEqual(resolved.url_name, "order-cancel")

    def test_trading_cancel_all(self):
        resolved = resolve("/api/trading/cancel-all/")
        self.assertEqual(resolved.url_name, "cancel-all-orders")

    def test_trading_exchange_health(self):
        resolved = resolve("/api/trading/exchange-health/")
        self.assertEqual(resolved.url_name, "exchange-health")

    def test_trading_performance_summary(self):
        resolved = resolve("/api/trading/performance/summary/")
        self.assertEqual(resolved.url_name, "trading-performance-summary")

    def test_trading_performance_by_symbol(self):
        resolved = resolve("/api/trading/performance/by-symbol/")
        self.assertEqual(resolved.url_name, "trading-performance-by-symbol")

    def test_live_trading_status(self):
        resolved = resolve("/api/live-trading/status/")
        self.assertEqual(resolved.url_name, "live-trading-status")

    # ── Paper Trading ──

    def test_paper_trading_status(self):
        resolved = resolve("/api/paper-trading/status/")
        self.assertEqual(resolved.url_name, "paper-trading-status")

    def test_paper_trading_start(self):
        resolved = resolve("/api/paper-trading/start/")
        self.assertEqual(resolved.url_name, "paper-trading-start")

    def test_paper_trading_stop(self):
        resolved = resolve("/api/paper-trading/stop/")
        self.assertEqual(resolved.url_name, "paper-trading-stop")

    def test_paper_trading_trades(self):
        resolved = resolve("/api/paper-trading/trades/")
        self.assertEqual(resolved.url_name, "paper-trading-trades")

    def test_paper_trading_history(self):
        resolved = resolve("/api/paper-trading/history/")
        self.assertEqual(resolved.url_name, "paper-trading-history")

    def test_paper_trading_profit(self):
        resolved = resolve("/api/paper-trading/profit/")
        self.assertEqual(resolved.url_name, "paper-trading-profit")

    def test_paper_trading_performance(self):
        resolved = resolve("/api/paper-trading/performance/")
        self.assertEqual(resolved.url_name, "paper-trading-performance")

    def test_paper_trading_balance(self):
        resolved = resolve("/api/paper-trading/balance/")
        self.assertEqual(resolved.url_name, "paper-trading-balance")

    def test_paper_trading_log(self):
        resolved = resolve("/api/paper-trading/log/")
        self.assertEqual(resolved.url_name, "paper-trading-log")

    # ── Risk ──

    def test_risk_status(self):
        resolved = resolve("/api/risk/1/status/")
        self.assertEqual(resolved.url_name, "risk-status")

    def test_risk_limits(self):
        resolved = resolve("/api/risk/1/limits/")
        self.assertEqual(resolved.url_name, "risk-limits")

    def test_risk_equity(self):
        resolved = resolve("/api/risk/1/equity/")
        self.assertEqual(resolved.url_name, "risk-equity")

    def test_risk_check_trade(self):
        resolved = resolve("/api/risk/1/check-trade/")
        self.assertEqual(resolved.url_name, "risk-check-trade")

    def test_risk_position_size(self):
        resolved = resolve("/api/risk/1/position-size/")
        self.assertEqual(resolved.url_name, "risk-position-size")

    def test_risk_reset_daily(self):
        resolved = resolve("/api/risk/1/reset-daily/")
        self.assertEqual(resolved.url_name, "risk-reset-daily")

    def test_risk_var(self):
        resolved = resolve("/api/risk/1/var/")
        self.assertEqual(resolved.url_name, "risk-var")

    def test_risk_heat_check(self):
        resolved = resolve("/api/risk/1/heat-check/")
        self.assertEqual(resolved.url_name, "risk-heat-check")

    def test_risk_metric_history(self):
        resolved = resolve("/api/risk/1/metric-history/")
        self.assertEqual(resolved.url_name, "risk-metric-history")

    def test_risk_trade_log(self):
        resolved = resolve("/api/risk/1/trade-log/")
        self.assertEqual(resolved.url_name, "risk-trade-log")

    def test_risk_halt(self):
        resolved = resolve("/api/risk/1/halt/")
        self.assertEqual(resolved.url_name, "risk-halt")

    def test_risk_resume(self):
        resolved = resolve("/api/risk/1/resume/")
        self.assertEqual(resolved.url_name, "risk-resume")

    def test_risk_alerts(self):
        resolved = resolve("/api/risk/1/alerts/")
        self.assertEqual(resolved.url_name, "risk-alerts")

    def test_risk_record_metrics(self):
        resolved = resolve("/api/risk/1/record-metrics/")
        self.assertEqual(resolved.url_name, "risk-record-metrics")

    # ── Portfolio ──

    def test_portfolios_list(self):
        resolved = resolve("/api/portfolios/")
        self.assertEqual(resolved.url_name, "portfolio-list")

    def test_portfolios_detail(self):
        resolved = resolve("/api/portfolios/1/")
        self.assertEqual(resolved.url_name, "portfolio-detail")

    def test_holdings_list(self):
        resolved = resolve("/api/portfolios/1/holdings/")
        self.assertEqual(resolved.url_name, "holding-create")

    def test_holdings_detail(self):
        resolved = resolve("/api/portfolios/1/holdings/1/")
        self.assertEqual(resolved.url_name, "holding-detail")

    def test_portfolio_summary(self):
        resolved = resolve("/api/portfolios/1/summary/")
        self.assertEqual(resolved.url_name, "portfolio-summary")

    def test_portfolio_allocation(self):
        resolved = resolve("/api/portfolios/1/allocation/")
        self.assertEqual(resolved.url_name, "portfolio-allocation")

    # ── Market ──

    def test_market_ticker(self):
        resolved = resolve("/api/market/ticker/BTC/USDT/")
        self.assertEqual(resolved.url_name, "market-ticker")

    def test_market_tickers(self):
        resolved = resolve("/api/market/tickers/")
        self.assertEqual(resolved.url_name, "market-tickers")

    def test_market_ohlcv(self):
        resolved = resolve("/api/market/ohlcv/BTC/USDT/")
        self.assertEqual(resolved.url_name, "market-ohlcv")

    def test_market_status(self):
        resolved = resolve("/api/market/status/")
        self.assertEqual(resolved.url_name, "market-status")

    def test_market_news(self):
        resolved = resolve("/api/market/news/")
        self.assertEqual(resolved.url_name, "news-list")

    def test_market_news_sentiment(self):
        resolved = resolve("/api/market/news/sentiment/")
        self.assertEqual(resolved.url_name, "news-sentiment")

    def test_market_news_signal(self):
        resolved = resolve("/api/market/news/signal/")
        self.assertEqual(resolved.url_name, "news-signal")

    def test_market_news_fetch(self):
        resolved = resolve("/api/market/news/fetch/")
        self.assertEqual(resolved.url_name, "news-fetch")

    def test_market_opportunities(self):
        resolved = resolve("/api/market/opportunities/")
        self.assertEqual(resolved.url_name, "opportunity-list")

    def test_market_opportunities_summary(self):
        resolved = resolve("/api/market/opportunities/summary/")
        self.assertEqual(resolved.url_name, "opportunity-summary")

    def test_market_daily_report(self):
        resolved = resolve("/api/market/daily-report/")
        self.assertEqual(resolved.url_name, "daily-report")

    def test_market_daily_report_history(self):
        resolved = resolve("/api/market/daily-report/history/")
        self.assertEqual(resolved.url_name, "daily-report-history")

    def test_market_circuit_breaker(self):
        resolved = resolve("/api/market/circuit-breaker/")
        self.assertEqual(resolved.url_name, "circuit-breaker-status")

    # ── Data Pipeline ──

    def test_data_list(self):
        resolved = resolve("/api/data/")
        self.assertEqual(resolved.url_name, "data-list")

    def test_data_download(self):
        resolved = resolve("/api/data/download/")
        self.assertEqual(resolved.url_name, "data-download")

    def test_data_generate_sample(self):
        resolved = resolve("/api/data/generate-sample/")
        self.assertEqual(resolved.url_name, "data-generate-sample")

    def test_data_quality_list(self):
        resolved = resolve("/api/data/quality/")
        self.assertEqual(resolved.url_name, "data-quality-list")

    def test_data_quality_detail(self):
        resolved = resolve("/api/data/quality/BTC-USDT/1h/")
        self.assertEqual(resolved.url_name, "data-quality-detail")

    def test_data_detail(self):
        resolved = resolve("/api/data/kraken/BTC-USDT/1h/")
        self.assertEqual(resolved.url_name, "data-detail")

    # ── Indicators ──

    def test_indicators_list(self):
        resolved = resolve("/api/indicators/")
        self.assertEqual(resolved.url_name, "indicator-list")

    def test_indicators_compute(self):
        resolved = resolve("/api/indicators/kraken/BTC-USDT/1h/")
        self.assertEqual(resolved.url_name, "indicator-compute")

    # ── Regime ──

    def test_regime_current_all(self):
        resolved = resolve("/api/regime/current/")
        self.assertEqual(resolved.url_name, "regime-current-all")

    def test_regime_current_symbol(self):
        resolved = resolve("/api/regime/current/BTC/USDT/")
        self.assertEqual(resolved.url_name, "regime-current")

    def test_regime_history(self):
        resolved = resolve("/api/regime/history/BTC/USDT/")
        self.assertEqual(resolved.url_name, "regime-history")

    def test_regime_recommendation(self):
        resolved = resolve("/api/regime/recommendation/BTC/USDT/")
        self.assertEqual(resolved.url_name, "regime-recommendation")

    def test_regime_recommendations(self):
        resolved = resolve("/api/regime/recommendations/")
        self.assertEqual(resolved.url_name, "regime-recommendations")

    def test_regime_position_size(self):
        resolved = resolve("/api/regime/position-size/")
        self.assertEqual(resolved.url_name, "regime-position-size")

    # ── Signals (Conviction) ──

    def test_signal_detail(self):
        resolved = resolve("/api/signals/BTC-USDT/")
        self.assertEqual(resolved.url_name, "signal-detail")

    def test_signal_batch(self):
        resolved = resolve("/api/signals/batch/")
        self.assertEqual(resolved.url_name, "signal-batch")

    def test_signal_entry_check(self):
        resolved = resolve("/api/signals/BTC-USDT/entry-check/")
        self.assertEqual(resolved.url_name, "signal-entry-check")

    def test_signal_strategy_status(self):
        resolved = resolve("/api/signals/strategy-status/")
        self.assertEqual(resolved.url_name, "signal-strategy-status")

    def test_signal_attribution_list(self):
        resolved = resolve("/api/signals/attribution/")
        self.assertEqual(resolved.url_name, "signal-attribution-list")

    def test_signal_attribution_detail(self):
        resolved = resolve("/api/signals/attribution/ORD-123/")
        self.assertEqual(resolved.url_name, "signal-attribution-detail")

    def test_signal_record(self):
        resolved = resolve("/api/signals/record/")
        self.assertEqual(resolved.url_name, "signal-record")

    def test_signal_feedback(self):
        resolved = resolve("/api/signals/feedback/")
        self.assertEqual(resolved.url_name, "signal-feedback")

    def test_signal_accuracy(self):
        resolved = resolve("/api/signals/accuracy/")
        self.assertEqual(resolved.url_name, "signal-accuracy")

    def test_signal_weights(self):
        resolved = resolve("/api/signals/weights/")
        self.assertEqual(resolved.url_name, "signal-weights")

    # ── ML ──

    def test_ml_train(self):
        resolved = resolve("/api/ml/train/")
        self.assertEqual(resolved.url_name, "ml-train")

    def test_ml_models_list(self):
        resolved = resolve("/api/ml/models/")
        self.assertEqual(resolved.url_name, "ml-model-list")

    def test_ml_model_detail(self):
        resolved = resolve("/api/ml/models/model_123/")
        self.assertEqual(resolved.url_name, "ml-model-detail")

    def test_ml_predict(self):
        resolved = resolve("/api/ml/predict/")
        self.assertEqual(resolved.url_name, "ml-predict")

    def test_ml_predictions(self):
        resolved = resolve("/api/ml/predictions/BTC-USDT/")
        self.assertEqual(resolved.url_name, "ml-prediction-list")

    def test_ml_model_performance(self):
        resolved = resolve("/api/ml/models/model_123/performance/")
        self.assertEqual(resolved.url_name, "ml-model-performance")

    # ── Screening ──

    def test_screening_run(self):
        resolved = resolve("/api/screening/run/")
        self.assertEqual(resolved.url_name, "screening-run")

    def test_screening_results(self):
        resolved = resolve("/api/screening/results/")
        self.assertEqual(resolved.url_name, "screening-results")

    def test_screening_result_detail(self):
        resolved = resolve("/api/screening/results/1/")
        self.assertEqual(resolved.url_name, "screening-result-detail")

    def test_screening_strategies(self):
        resolved = resolve("/api/screening/strategies/")
        self.assertEqual(resolved.url_name, "screening-strategies")

    # ── Backtest ──

    def test_backtest_run(self):
        resolved = resolve("/api/backtest/run/")
        self.assertEqual(resolved.url_name, "backtest-run")

    def test_backtest_results(self):
        resolved = resolve("/api/backtest/results/")
        self.assertEqual(resolved.url_name, "backtest-results")

    def test_backtest_result_detail(self):
        resolved = resolve("/api/backtest/results/1/")
        self.assertEqual(resolved.url_name, "backtest-result-detail")

    def test_backtest_strategies(self):
        resolved = resolve("/api/backtest/strategies/")
        self.assertEqual(resolved.url_name, "backtest-strategies")

    def test_backtest_compare(self):
        resolved = resolve("/api/backtest/compare/")
        self.assertEqual(resolved.url_name, "backtest-compare")

    def test_backtest_export(self):
        resolved = resolve("/api/backtest/export/")
        self.assertEqual(resolved.url_name, "backtest-export")

    # ── Jobs ──

    def test_jobs_list(self):
        resolved = resolve("/api/jobs/")
        self.assertEqual(resolved.url_name, "job-list")

    def test_job_detail(self):
        resolved = resolve("/api/jobs/abc123/")
        self.assertEqual(resolved.url_name, "job-detail")

    def test_job_cancel(self):
        resolved = resolve("/api/jobs/abc123/cancel/")
        self.assertEqual(resolved.url_name, "job-cancel")

    # ── Scheduler ──

    def test_scheduler_status(self):
        resolved = resolve("/api/scheduler/status/")
        self.assertEqual(resolved.url_name, "scheduler-status")

    def test_scheduler_tasks(self):
        resolved = resolve("/api/scheduler/tasks/")
        self.assertEqual(resolved.url_name, "scheduler-task-list")

    def test_scheduler_task_detail(self):
        resolved = resolve("/api/scheduler/tasks/data_refresh/")
        self.assertEqual(resolved.url_name, "scheduler-task-detail")

    def test_scheduler_task_pause(self):
        resolved = resolve("/api/scheduler/tasks/data_refresh/pause/")
        self.assertEqual(resolved.url_name, "scheduler-task-pause")

    def test_scheduler_task_resume(self):
        resolved = resolve("/api/scheduler/tasks/data_refresh/resume/")
        self.assertEqual(resolved.url_name, "scheduler-task-resume")

    def test_scheduler_task_trigger(self):
        resolved = resolve("/api/scheduler/tasks/data_refresh/trigger/")
        self.assertEqual(resolved.url_name, "scheduler-task-trigger")

    # ── Workflows ──

    def test_workflows_list(self):
        resolved = resolve("/api/workflows/")
        self.assertEqual(resolved.url_name, "workflow-list")

    def test_workflow_detail(self):
        resolved = resolve("/api/workflows/wf-123/")
        self.assertEqual(resolved.url_name, "workflow-detail")

    def test_workflow_trigger(self):
        resolved = resolve("/api/workflows/wf-123/trigger/")
        self.assertEqual(resolved.url_name, "workflow-trigger")

    def test_workflow_enable(self):
        resolved = resolve("/api/workflows/wf-123/enable/")
        self.assertEqual(resolved.url_name, "workflow-enable")

    def test_workflow_disable(self):
        resolved = resolve("/api/workflows/wf-123/disable/")
        self.assertEqual(resolved.url_name, "workflow-disable")

    def test_workflow_runs(self):
        resolved = resolve("/api/workflows/wf-123/runs/")
        self.assertEqual(resolved.url_name, "workflow-runs")

    def test_workflow_run_detail(self):
        resolved = resolve("/api/workflow-runs/run-456/")
        self.assertEqual(resolved.url_name, "workflow-run-detail")

    def test_workflow_run_cancel(self):
        resolved = resolve("/api/workflow-runs/run-456/cancel/")
        self.assertEqual(resolved.url_name, "workflow-run-cancel")

    def test_workflow_step_types(self):
        resolved = resolve("/api/workflow-steps/")
        self.assertEqual(resolved.url_name, "workflow-step-types")

    # ── Notifications ──

    def test_notification_preferences(self):
        resolved = resolve("/api/notifications/1/preferences/")
        self.assertEqual(resolved.url_name, "notification-prefs")

    # ── Metrics (non-API prefix) ──

    def test_metrics(self):
        resolved = resolve("/metrics/")
        self.assertEqual(resolved.url_name, "metrics")

    # ── OpenAPI ──

    def test_schema(self):
        resolved = resolve("/api/schema/")
        self.assertEqual(resolved.url_name, "schema")

    def test_swagger_ui(self):
        resolved = resolve("/api/docs/")
        self.assertEqual(resolved.url_name, "swagger-ui")


class SmokeTestURLContractTest(SimpleTestCase):
    """Validate URLs used in scripts/smoke_test.sh resolve correctly."""

    def test_health_detailed(self):
        resolved = resolve("/api/health/")
        self.assertEqual(resolved.url_name, "health")

    def test_auth_login(self):
        resolved = resolve("/api/auth/login/")
        self.assertEqual(resolved.url_name, "auth-login")

    def test_auth_status(self):
        """smoke_test.sh checks auth session at /api/auth/status/ (NOT /api/auth/user/)."""
        resolved = resolve("/api/auth/status/")
        self.assertEqual(resolved.url_name, "auth-status")

    def test_dashboard_kpis(self):
        resolved = resolve("/api/dashboard/kpis/")
        self.assertEqual(resolved.url_name, "dashboard-kpis")

    def test_risk_status(self):
        resolved = resolve("/api/risk/1/status/")
        self.assertEqual(resolved.url_name, "risk-status")

    def test_regime_current(self):
        """smoke_test.sh checks regime at /api/regime/current/ (NOT /api/market/regime/current/)."""
        resolved = resolve("/api/regime/current/")
        self.assertEqual(resolved.url_name, "regime-current-all")

    def test_jobs_list(self):
        """smoke_test.sh checks jobs at /api/jobs/ (NOT /api/analysis/jobs/)."""
        resolved = resolve("/api/jobs/")
        self.assertEqual(resolved.url_name, "job-list")

    def test_orders_list(self):
        resolved = resolve("/api/trading/orders/")
        self.assertEqual(resolved.url_name, "order-list")

    def test_portfolio_list(self):
        resolved = resolve("/api/portfolios/")
        self.assertEqual(resolved.url_name, "portfolio-list")

    def test_scheduler_tasks(self):
        resolved = resolve("/api/scheduler/tasks/")
        self.assertEqual(resolved.url_name, "scheduler-task-list")


class TrailingSlashContractTest(SimpleTestCase):
    """Ensure all client-constructed URLs include trailing slashes.

    Django's APPEND_SLASH does not reliably work for POST requests,
    so all URLs MUST include the trailing slash in the client code.
    """

    # These are the exact URL patterns constructed by Python HTTP clients
    PYTHON_CLIENT_URLS = [
        "/api/risk/1/check-trade/",
        "/api/signals/BTC-USDT/entry-check/",
        "/api/signals/strategy-status/",
    ]

    def test_all_python_client_urls_have_trailing_slash(self):
        for url in self.PYTHON_CLIENT_URLS:
            self.assertTrue(
                url.endswith("/"),
                f"URL {url} must have trailing slash",
            )

    def test_all_python_client_urls_resolve(self):
        for url in self.PYTHON_CLIENT_URLS:
            resolved = resolve(url)
            self.assertIsNotNone(
                resolved.url_name,
                f"URL {url} did not resolve to a named URL",
            )


class NoWrongPrefixRegressionTest(SimpleTestCase):
    """Guard against the /api/analysis/ prefix bug.

    All analysis app URLs are mounted at /api/ (not /api/analysis/).
    These tests ensure the wrong paths correctly return 404.
    """

    WRONG_PATHS = [
        "/api/analysis/signals/BTC-USDT/entry-check/",
        "/api/analysis/signals/strategy-status/",
        "/api/analysis/signals/batch/",
        "/api/analysis/signals/accuracy/",
        "/api/analysis/signals/weights/",
        "/api/analysis/jobs/",
        "/api/analysis/ml/train/",
        "/api/analysis/ml/models/",
        "/api/market/regime/current/",
    ]

    def test_wrong_prefix_does_not_resolve(self):
        from django.urls import Resolver404

        for path in self.WRONG_PATHS:
            with self.assertRaises(
                Resolver404,
                msg=f"Path {path} should NOT resolve — wrong prefix!",
            ):
                resolve(path)


class ReverseURLConsistencyTest(SimpleTestCase):
    """Verify that reverse() produces paths matching what clients construct."""

    def test_signal_entry_check_reverse(self):
        url = reverse("signal-entry-check", kwargs={"symbol": "BTC-USDT"})
        self.assertEqual(url, "/api/signals/BTC-USDT/entry-check/")

    def test_signal_strategy_status_reverse(self):
        url = reverse("signal-strategy-status")
        self.assertEqual(url, "/api/signals/strategy-status/")

    def test_risk_check_trade_reverse(self):
        url = reverse("risk-check-trade", kwargs={"portfolio_id": 1})
        self.assertEqual(url, "/api/risk/1/check-trade/")

    def test_signal_batch_reverse(self):
        url = reverse("signal-batch")
        self.assertEqual(url, "/api/signals/batch/")

    def test_signal_accuracy_reverse(self):
        url = reverse("signal-accuracy")
        self.assertEqual(url, "/api/signals/accuracy/")

    def test_signal_weights_reverse(self):
        url = reverse("signal-weights")
        self.assertEqual(url, "/api/signals/weights/")

    def test_regime_current_all_reverse(self):
        url = reverse("regime-current-all")
        self.assertEqual(url, "/api/regime/current/")

    def test_jobs_list_reverse(self):
        url = reverse("job-list")
        self.assertEqual(url, "/api/jobs/")

    def test_auth_status_reverse(self):
        url = reverse("auth-status")
        self.assertEqual(url, "/api/auth/status/")
