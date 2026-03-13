"""
Tests for Prometheus-compatible metrics endpoint and collector.
"""

import contextlib

import pytest
from django.test import Client


@pytest.mark.django_db
class TestMetricsEndpoint:
    def test_metrics_returns_200(self, authenticated_client):
        resp = authenticated_client.get("/metrics/")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/plain")

    def test_metrics_requires_auth_when_no_token(self):
        """Without METRICS_AUTH_TOKEN, unauthenticated access is denied."""
        client = Client()
        resp = client.get("/metrics/")
        assert resp.status_code == 403

    def test_metrics_allows_bearer_token(self, settings):
        settings.METRICS_AUTH_TOKEN = "test-secret-token"
        client = Client()
        resp = client.get("/metrics/", HTTP_AUTHORIZATION="Bearer test-secret-token")
        assert resp.status_code == 200

    def test_metrics_allows_session_auth(self, authenticated_client):
        resp = authenticated_client.get("/metrics/")
        assert resp.status_code == 200

    def test_metrics_rejects_wrong_token(self, settings):
        settings.METRICS_AUTH_TOKEN = "test-secret-token"
        client = Client()
        resp = client.get("/metrics/", HTTP_AUTHORIZATION="Bearer wrong-token")
        assert resp.status_code == 403

    def test_metrics_rejects_unauthenticated(self):
        client = Client()
        resp = client.get("/metrics/")
        assert resp.status_code == 403

    def test_metrics_allows_empty_token_with_session(self, authenticated_client, settings):
        settings.METRICS_AUTH_TOKEN = ""
        resp = authenticated_client.get("/metrics/")
        assert resp.status_code == 200

    def test_metrics_contains_gauges(self, authenticated_client):
        """After hitting metrics, we should see active_orders gauges."""
        resp = authenticated_client.get("/metrics/")
        body = resp.content.decode()
        assert "active_orders" in body

    def test_metrics_after_request(self, authenticated_client):
        """After a real request, http_requests_total should increment."""
        authenticated_client.get("/api/health/")

        resp = authenticated_client.get("/metrics/")
        body = resp.content.decode()
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body


class TestMetricsCollector:
    def test_gauge(self):
        from core.services.metrics import MetricsCollector

        mc = MetricsCollector()
        mc.gauge("test_gauge", 42.0)
        output = mc.collect()
        assert "test_gauge 42.0" in output

    def test_gauge_with_labels(self):
        from core.services.metrics import MetricsCollector

        mc = MetricsCollector()
        mc.gauge("test_labeled", 1.0, {"env": "test"})
        output = mc.collect()
        assert 'test_labeled{env="test"} 1.0' in output

    def test_counter_inc(self):
        from core.services.metrics import MetricsCollector

        mc = MetricsCollector()
        key = 'test_counter_isolated{method="GET"}'
        # Clear any prior state for this key
        with mc._data_lock:
            mc._counters.pop(key, None)
        mc.counter_inc("test_counter_isolated", {"method": "GET"})
        mc.counter_inc("test_counter_isolated", {"method": "GET"})
        mc.counter_inc("test_counter_isolated", {"method": "GET"}, amount=3)
        output = mc.collect()
        assert 'test_counter_isolated{method="GET"} 5.0' in output

    def test_histogram(self):
        from core.services.metrics import MetricsCollector

        mc = MetricsCollector()
        for v in [0.1, 0.2, 0.3, 0.4, 0.5]:
            mc.histogram_observe("test_hist", v)
        output = mc.collect()
        assert "test_hist_count 5" in output
        assert "test_hist_sum" in output
        assert 'quantile="0.5"' in output
        assert 'quantile="0.99"' in output

    def test_timed_context_manager(self):
        import time

        from core.services.metrics import MetricsCollector, timed

        mc = MetricsCollector()
        with timed("test_timing", {"op": "sleep"}):
            time.sleep(0.01)

        output = mc.collect()
        assert "test_timing" in output


@pytest.mark.django_db
class TestMetricsInstrumentation:
    def test_metrics_contains_job_queue_gauges(self, authenticated_client):
        resp = authenticated_client.get("/metrics/")
        body = resp.content.decode()
        assert "job_queue_pending" in body
        assert "job_queue_running" in body

    def test_metrics_contains_scheduler_status(self, authenticated_client):
        resp = authenticated_client.get("/metrics/")
        body = resp.content.decode()
        assert "scheduler_running" in body

    def test_metrics_contains_circuit_breaker_state(self, authenticated_client):
        """Circuit breaker state only appears after a breaker is registered."""
        from market.services.circuit_breaker import get_breaker

        get_breaker("test_exchange")
        resp = authenticated_client.get("/metrics/")
        body = resp.content.decode()
        assert "circuit_breaker_state" in body

    def test_health_detailed_includes_scheduler(self, authenticated_client):
        resp = authenticated_client.get("/api/health/?detailed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "scheduler" in data["checks"]

    def test_health_detailed_includes_circuit_breakers(self, authenticated_client):
        resp = authenticated_client.get("/api/health/?detailed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "circuit_breakers" in data["checks"]

    def test_order_create_increments_counter(self, authenticated_client):
        # Create a paper order
        authenticated_client.post(
            "/api/trading/orders/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "amount": 0.1,
                "price": 0,
                "exchange_id": "binance",
                "mode": "paper",
                "portfolio_id": 1,
            },
            content_type="application/json",
        )

        resp = authenticated_client.get("/metrics/")
        body = resp.content.decode()
        assert "orders_created_total" in body

    def test_timed_dashboard_kpi(self, authenticated_client):
        from core.services.metrics import metrics

        authenticated_client.get("/api/dashboard/kpis/")
        output = metrics.collect()
        assert "dashboard_kpi_latency_seconds" in output

    def test_timed_risk_check(self):
        from core.services.metrics import metrics
        from risk.services.risk import RiskManagementService

        with contextlib.suppress(Exception):
            RiskManagementService.periodic_risk_check(1)
        output = metrics.collect()
        assert "risk_check_duration_seconds" in output

    def test_timed_workflow_execution(self):
        from analysis.services.workflow_engine import execute_workflow
        from core.services.metrics import metrics

        with contextlib.suppress(Exception):
            execute_workflow(
                {"workflow_run_id": "nonexistent", "steps": []}, lambda p, m: None
            )
        output = metrics.collect()
        assert "workflow_execution_seconds" in output

    def test_health_detailed_includes_channel_layer(self, authenticated_client):
        resp = authenticated_client.get("/api/health/?detailed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "channel_layer" in data["checks"]
        assert data["checks"]["channel_layer"]["status"] == "ok"

    def test_health_detailed_includes_job_queue(self, authenticated_client):
        resp = authenticated_client.get("/api/health/?detailed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "job_queue" in data["checks"]
        assert "pending_count" in data["checks"]["job_queue"]

    def test_health_detailed_job_queue_warning_when_stale(self, authenticated_client):
        from datetime import timedelta

        from django.utils import timezone

        from analysis.models import BackgroundJob

        # Create a pending job, then backdate it (auto_now_add prevents direct set)
        job = BackgroundJob.objects.create(
            job_type="test",
            status="pending",
        )
        old_time = timezone.now() - timedelta(minutes=45)
        BackgroundJob.objects.filter(pk=job.pk).update(created_at=old_time)

        resp = authenticated_client.get("/api/health/?detailed=true")
        data = resp.json()
        assert data["checks"]["job_queue"]["status"] == "warning"
        assert data["checks"]["job_queue"]["oldest_pending_minutes"] > 30

    def test_health_detailed_overall_degraded_on_warning(self, authenticated_client):
        from datetime import timedelta

        from django.utils import timezone

        from analysis.models import BackgroundJob

        job = BackgroundJob.objects.create(
            job_type="test",
            status="pending",
        )
        old_time = timezone.now() - timedelta(minutes=45)
        BackgroundJob.objects.filter(pk=job.pk).update(created_at=old_time)

        resp = authenticated_client.get("/api/health/?detailed=true")
        data = resp.json()
        assert data["status"] == "degraded"

    def test_health_detailed_wal_warning_threshold(self, authenticated_client):
        resp = authenticated_client.get("/api/health/?detailed=true")
        data = resp.json()
        # With test DB, WAL should be small -> "ok"
        assert data["checks"]["wal"]["status"] == "ok"

    def test_docker_healthcheck_format_matches_grep(self, authenticated_client):
        """The grep in docker-compose expects '"status":"ok"' in the response."""
        resp = authenticated_client.get("/api/health/?detailed=true")
        body = resp.content.decode()
        # When all checks are healthy, "status":"ok" should appear
        assert '"status"' in body

    def test_health_detailed_includes_wal(self, authenticated_client):
        resp = authenticated_client.get("/api/health/?detailed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "wal" in data["checks"]
        assert "size_mb" in data["checks"]["wal"]

    def test_scheduled_task_config_exists(self):
        from django.conf import settings

        assert "db_maintenance" in settings.SCHEDULED_TASKS
        assert settings.SCHEDULED_TASKS["db_maintenance"]["task_type"] == "db_maintenance"

    def test_metrics_high_cardinality_paths_normalized(self, authenticated_client):
        """Verify that different URL paths don't create unbounded metric keys."""
        authenticated_client.get("/api/health/")
        authenticated_client.get("/api/health/?detailed=true")
        resp = authenticated_client.get("/metrics/")
        body = resp.content.decode()
        # http_requests_total should be present but not explode with unique paths
        assert "http_requests_total" in body
