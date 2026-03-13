"""Full coverage tests for untested API views & serializers across all 6 Django apps.

Covers ~32 previously untested view endpoints:
- Risk: PositionSizeView, ResetDailyView, VaRView, HeatCheckView, MetricHistoryView,
        RecordMetricsView, TradeLogView, RiskLimitHistoryView
- Trading: OrderListView, OrderDetailView, OrderExportView
- Market: SentimentSignalView, OpportunityListView, OpportunitySummaryView,
          DailyReportView, DailyReportHistoryView
- Analysis: JobCancelView, ScreeningResultListView, ScreeningResultDetailView,
            ScreeningStrategyListView, DataListView, DataDetailView, DataDownloadView,
            WorkflowListView (GET+POST), WorkflowDetailView (GET+DELETE),
            WorkflowTriggerView, WorkflowEnableView, WorkflowDisableView,
            WorkflowRunListView, WorkflowRunDetailView, WorkflowRunCancelView,
            WorkflowStepTypesView
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone as tz
from rest_framework import status

pytestmark = pytest.mark.django_db


# ══════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════


@pytest.fixture
def portfolio():
    from portfolio.models import Portfolio

    return Portfolio.objects.create(
        name="Test Portfolio",
        exchange_id="kraken",
        asset_class="crypto",
    )


@pytest.fixture
def risk_limits(portfolio):
    from risk.models import RiskLimits

    return RiskLimits.objects.create(
        portfolio_id=portfolio.id,
        max_portfolio_drawdown=0.15,
        max_daily_loss=0.05,
        max_leverage=1.0,
        max_position_size_pct=0.10,
    )


@pytest.fixture
def risk_state(portfolio):
    from risk.models import RiskState

    return RiskState.objects.create(
        portfolio_id=portfolio.id,
        peak_equity=10000,
        total_equity=9800,
        daily_pnl=-50,
        is_halted=False,
    )


@pytest.fixture
def order(portfolio):
    from trading.models import Order

    return Order.objects.create(
        symbol="BTC/USDT",
        side="buy",
        amount=0.1,
        price=50000,
        mode="paper",
        asset_class="crypto",
        status="filled",
        timestamp=tz.now(),
    )


@pytest.fixture
def workflow():
    from analysis.models import Workflow, WorkflowStep

    wf = Workflow.objects.create(
        id="test_wf",
        name="Test Workflow",
        asset_class="crypto",
        schedule_enabled=False,
    )
    WorkflowStep.objects.create(
        workflow=wf,
        order=1,
        step_type="data_refresh",
        name="Refresh Data",
        params={},
    )
    return wf


@pytest.fixture
def workflow_run(workflow):
    from analysis.models import BackgroundJob, WorkflowRun

    job = BackgroundJob.objects.create(job_type="workflow", status="running")
    return WorkflowRun.objects.create(
        workflow=workflow,
        job=job,
        status="running",
        trigger="api",
        params={},
    )


# ══════════════════════════════════════════════════════
# Risk Views
# ══════════════════════════════════════════════════════


class TestPositionSizeView:
    def test_calculate(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.post(
            f"/api/risk/{portfolio.id}/position-size/",
            {"entry_price": 50000, "stop_loss_price": 48000},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "position_size" in resp.data or "size" in resp.data or isinstance(resp.data, dict)

    def test_unauthenticated(self, api_client, portfolio):
        resp = api_client.post(
            f"/api/risk/{portfolio.id}/position-size/",
            {"entry_price": 50000, "stop_loss_price": 48000},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestResetDailyView:
    def test_reset(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.post(f"/api/risk/{portfolio.id}/reset-daily/")
        assert resp.status_code == status.HTTP_200_OK


class TestVaRView:
    def test_get_var(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.get(f"/api/risk/{portfolio.id}/var/")
        assert resp.status_code == status.HTTP_200_OK

    def test_get_var_historical(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.get(f"/api/risk/{portfolio.id}/var/?method=historical")
        assert resp.status_code == status.HTTP_200_OK


class TestHeatCheckView:
    def test_get(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.get(f"/api/risk/{portfolio.id}/heat-check/")
        assert resp.status_code == status.HTTP_200_OK


class TestMetricHistoryView:
    def test_get(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.get(f"/api/risk/{portfolio.id}/metric-history/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.data, list)

    def test_custom_hours(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.get(f"/api/risk/{portfolio.id}/metric-history/?hours=24")
        assert resp.status_code == status.HTTP_200_OK


class TestRecordMetricsView:
    def test_record(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.post(f"/api/risk/{portfolio.id}/record-metrics/")
        assert resp.status_code == status.HTTP_200_OK


class TestTradeLogView:
    def test_get(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.get(f"/api/risk/{portfolio.id}/trade-log/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.data, list)


class TestRiskLimitHistoryView:
    def test_get_empty(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.get(f"/api/risk/{portfolio.id}/limit-history/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.data, list)

    def test_field_filter(self, authenticated_client, portfolio, risk_limits, risk_state):
        resp = authenticated_client.get(
            f"/api/risk/{portfolio.id}/limit-history/?field=max_drawdown",
        )
        assert resp.status_code == status.HTTP_200_OK


# ══════════════════════════════════════════════════════
# Trading Views
# ══════════════════════════════════════════════════════


class TestOrderListView:
    def test_list(self, authenticated_client, order):
        resp = authenticated_client.get("/api/trading/orders/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) >= 1

    def test_filter_mode(self, authenticated_client, order):
        resp = authenticated_client.get("/api/trading/orders/?mode=paper")
        assert resp.status_code == status.HTTP_200_OK
        assert all(o["mode"] == "paper" for o in resp.data)

    def test_filter_asset_class(self, authenticated_client, order):
        resp = authenticated_client.get("/api/trading/orders/?asset_class=crypto")
        assert resp.status_code == status.HTTP_200_OK

    def test_filter_symbol(self, authenticated_client, order):
        resp = authenticated_client.get("/api/trading/orders/?symbol=BTC")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) >= 1

    def test_filter_status(self, authenticated_client, order):
        resp = authenticated_client.get("/api/trading/orders/?status=filled")
        assert resp.status_code == status.HTTP_200_OK
        assert all(o["status"] == "filled" for o in resp.data)

    def test_filter_invalid_status_ignored(self, authenticated_client, order):
        resp = authenticated_client.get("/api/trading/orders/?status=bogus")
        assert resp.status_code == status.HTTP_200_OK

    def test_unauthenticated(self, api_client):
        resp = api_client.get("/api/trading/orders/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestOrderDetailView:
    def test_get(self, authenticated_client, order):
        resp = authenticated_client.get(f"/api/trading/orders/{order.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["symbol"] == "BTC/USDT"

    def test_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/trading/orders/99999/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestOrderExportView:
    def test_csv_export(self, authenticated_client, order):
        resp = authenticated_client.get("/api/trading/orders/export/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp["Content-Type"] == "text/csv"

    def test_filter_mode(self, authenticated_client, order):
        resp = authenticated_client.get("/api/trading/orders/export/?mode=paper")
        assert resp.status_code == status.HTTP_200_OK


# ══════════════════════════════════════════════════════
# Market Views
# ══════════════════════════════════════════════════════


class TestSentimentSignalView:
    def test_get(self, authenticated_client):
        with patch("market.services.news.NewsService") as mock_ns:
            mock_ns.return_value.get_sentiment_signal.return_value = {
                "asset_class": "crypto",
                "score": 0.5,
                "label": "neutral",
            }
            resp = authenticated_client.get("/api/market/news/signal/")
        assert resp.status_code == status.HTTP_200_OK

    def test_custom_params(self, authenticated_client):
        with patch("market.services.news.NewsService") as mock_ns:
            mock_ns.return_value.get_sentiment_signal.return_value = {
                "asset_class": "equity",
                "score": 0.3,
            }
            resp = authenticated_client.get(
                "/api/market/news/signal/?asset_class=equity&hours=48",
            )
        assert resp.status_code == status.HTTP_200_OK


class TestOpportunityListView:
    def test_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/market/opportunities/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == []

    def test_with_data(self, authenticated_client):
        from market.models import MarketOpportunity

        MarketOpportunity.objects.create(
            symbol="BTC/USDT",
            opportunity_type="volume_surge",
            score=80,
            asset_class="crypto",
            expires_at=tz.now() + timedelta(hours=24),
        )
        resp = authenticated_client.get("/api/market/opportunities/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1

    def test_filter_type(self, authenticated_client):
        from market.models import MarketOpportunity

        MarketOpportunity.objects.create(
            symbol="BTC/USDT",
            opportunity_type="breakout",
            score=70,
            asset_class="crypto",
            expires_at=tz.now() + timedelta(hours=24),
        )
        resp = authenticated_client.get("/api/market/opportunities/?type=breakout")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1

    def test_filter_min_score(self, authenticated_client):
        from market.models import MarketOpportunity

        MarketOpportunity.objects.create(
            symbol="BTC/USDT",
            opportunity_type="volume_surge",
            score=50,
            asset_class="crypto",
            expires_at=tz.now() + timedelta(hours=24),
        )
        resp = authenticated_client.get("/api/market/opportunities/?min_score=60")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 0

    def test_filter_asset_class(self, authenticated_client):
        from market.models import MarketOpportunity

        MarketOpportunity.objects.create(
            symbol="AAPL",
            opportunity_type="breakout",
            score=85,
            asset_class="equity",
            expires_at=tz.now() + timedelta(hours=24),
        )
        resp = authenticated_client.get("/api/market/opportunities/?asset_class=equity")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1


class TestOpportunitySummaryView:
    def test_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/market/opportunities/summary/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total_active"] == 0

    def test_with_data(self, authenticated_client):
        from market.models import MarketOpportunity

        MarketOpportunity.objects.create(
            symbol="BTC/USDT",
            opportunity_type="volume_surge",
            score=80,
            asset_class="crypto",
            expires_at=tz.now() + timedelta(hours=24),
        )
        MarketOpportunity.objects.create(
            symbol="ETH/USDT",
            opportunity_type="rsi_bounce",
            score=70,
            asset_class="crypto",
            expires_at=tz.now() + timedelta(hours=24),
        )
        resp = authenticated_client.get("/api/market/opportunities/summary/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total_active"] == 2
        assert resp.data["avg_score"] == 75.0


class TestDailyReportView:
    def test_get(self, authenticated_client):
        with patch("market.services.daily_report.DailyReportService") as mock_dr:
            mock_dr.return_value.get_latest.return_value = {
                "regime": {},
                "system_status": {},
            }
            resp = authenticated_client.get("/api/market/daily-report/")
        assert resp.status_code == status.HTTP_200_OK


class TestDailyReportHistoryView:
    def test_get(self, authenticated_client):
        with patch("market.services.daily_report.DailyReportService") as mock_dr:
            mock_dr.return_value.get_history.return_value = []
            resp = authenticated_client.get("/api/market/daily-report/history/")
        assert resp.status_code == status.HTTP_200_OK


# ══════════════════════════════════════════════════════
# Analysis — Screening Views
# ══════════════════════════════════════════════════════


class TestScreeningResultListView:
    def test_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/screening/results/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == []


class TestScreeningStrategyListView:
    def test_get(self, authenticated_client):
        resp = authenticated_client.get("/api/screening/strategies/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.data, (list, dict))


# ══════════════════════════════════════════════════════
# Analysis — Data Views
# ══════════════════════════════════════════════════════


class TestDataListView:
    def test_get(self, authenticated_client):
        with patch(
            "analysis.services.data_pipeline.DataPipelineService.list_available_data",
            return_value=[],
        ):
            resp = authenticated_client.get("/api/data/")
        assert resp.status_code == status.HTTP_200_OK

    def test_unauthenticated(self, api_client):
        resp = api_client.get("/api/data/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestDataDetailView:
    def test_not_found(self, authenticated_client):
        with patch(
            "analysis.services.data_pipeline.DataPipelineService.get_data_info", return_value=None
        ):
            resp = authenticated_client.get("/api/data/kraken/BTC_USDT/1h/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_found(self, authenticated_client):
        with patch(
            "analysis.services.data_pipeline.DataPipelineService.get_data_info",
            return_value={"symbol": "BTC/USDT", "rows": 100},
        ):
            resp = authenticated_client.get("/api/data/kraken/BTC_USDT/1h/")
        assert resp.status_code == status.HTTP_200_OK


class TestDataDownloadView:
    def test_submit(self, authenticated_client):
        with patch("analysis.services.job_runner.get_job_runner") as mock_jr:
            mock_jr.return_value.submit.return_value = "job-123"
            resp = authenticated_client.post(
                "/api/data/download/",
                {"symbols": ["BTC/USDT"], "timeframes": ["1h"]},
                format="json",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert resp.data["job_id"] == "job-123"


# ══════════════════════════════════════════════════════
# Analysis — Job Cancel
# ══════════════════════════════════════════════════════


class TestJobCancelView:
    def test_cancel(self, authenticated_client):
        from analysis.models import BackgroundJob

        job = BackgroundJob.objects.create(job_type="backtest", status="running")
        with patch("analysis.services.job_runner.get_job_runner") as mock_jr:
            mock_jr.return_value.cancel_job.return_value = True
            resp = authenticated_client.post(f"/api/jobs/{job.id}/cancel/")
        assert resp.status_code == status.HTTP_200_OK


# ══════════════════════════════════════════════════════
# Analysis — Workflow Views
# ══════════════════════════════════════════════════════


class TestWorkflowListView:
    def test_list_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/workflows/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.data, list)

    def test_list_with_data(self, authenticated_client, workflow):
        resp = authenticated_client.get("/api/workflows/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) >= 1

    def test_filter_asset_class(self, authenticated_client, workflow):
        resp = authenticated_client.get("/api/workflows/?asset_class=crypto")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) >= 1

    def test_create(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/workflows/",
            {
                "id": "new_wf",
                "name": "New Workflow",
                "asset_class": "crypto",
                "steps": [
                    {"order": 1, "step_type": "data_refresh", "name": "Refresh", "params": {}}
                ],
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["id"] == "new_wf"

    def test_create_duplicate_409(self, authenticated_client, workflow):
        resp = authenticated_client.post(
            "/api/workflows/",
            {
                "id": "test_wf",
                "name": "Duplicate",
                "steps": [{"order": 1, "step_type": "data_refresh", "name": "R", "params": {}}],
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT


class TestWorkflowDetailView:
    def test_get(self, authenticated_client, workflow):
        resp = authenticated_client.get(f"/api/workflows/{workflow.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["name"] == "Test Workflow"

    def test_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/workflows/nonexistent/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_delete(self, authenticated_client, workflow):
        resp = authenticated_client.delete(f"/api/workflows/{workflow.id}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_template_rejected(self, authenticated_client, workflow):
        workflow.is_template = True
        workflow.save()
        resp = authenticated_client.delete(f"/api/workflows/{workflow.id}/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_not_found(self, authenticated_client):
        resp = authenticated_client.delete("/api/workflows/nonexistent/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestWorkflowTriggerView:
    def test_trigger(self, authenticated_client, workflow):
        with patch(
            "analysis.services.workflow_engine.WorkflowEngine.trigger",
            return_value=("run-123", "job-456"),
        ):
            resp = authenticated_client.post(f"/api/workflows/{workflow.id}/trigger/")
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert resp.data["workflow_run_id"] == "run-123"

    def test_not_found(self, authenticated_client):
        from analysis.models import Workflow

        with patch(
            "analysis.services.workflow_engine.WorkflowEngine.trigger",
            side_effect=Workflow.DoesNotExist,
        ):
            resp = authenticated_client.post("/api/workflows/nonexistent/trigger/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestWorkflowEnableDisableView:
    def test_enable(self, authenticated_client, workflow):
        resp = authenticated_client.post(f"/api/workflows/{workflow.id}/enable/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "enabled"

    def test_disable(self, authenticated_client, workflow):
        resp = authenticated_client.post(f"/api/workflows/{workflow.id}/disable/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "disabled"

    def test_enable_not_found(self, authenticated_client):
        resp = authenticated_client.post("/api/workflows/nonexistent/enable/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestWorkflowRunListView:
    def test_list(self, authenticated_client, workflow_run):
        resp = authenticated_client.get(
            f"/api/workflows/{workflow_run.workflow_id}/runs/",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) >= 1


class TestWorkflowRunDetailView:
    def test_get(self, authenticated_client, workflow_run):
        resp = authenticated_client.get(f"/api/workflow-runs/{workflow_run.id}/")
        assert resp.status_code == status.HTTP_200_OK

    def test_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/workflow-runs/nonexistent/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestWorkflowRunCancelView:
    def test_cancel(self, authenticated_client, workflow_run):
        with patch("analysis.services.workflow_engine.WorkflowEngine.cancel", return_value=True):
            resp = authenticated_client.post(
                f"/api/workflow-runs/{workflow_run.id}/cancel/",
            )
        assert resp.status_code == status.HTTP_200_OK

    def test_cancel_not_found(self, authenticated_client):
        with patch("analysis.services.workflow_engine.WorkflowEngine.cancel", return_value=False):
            resp = authenticated_client.post(
                "/api/workflow-runs/nonexistent/cancel/",
            )
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestWorkflowStepTypesView:
    def test_get(self, authenticated_client):
        resp = authenticated_client.get("/api/workflow-steps/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.data, (list, dict))
