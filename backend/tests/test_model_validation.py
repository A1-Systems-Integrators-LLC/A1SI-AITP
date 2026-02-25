"""P6-2 / P14-1: Tests for model clean() validation."""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from analysis.models import BackgroundJob, Workflow, WorkflowStep
from core.models import ScheduledTask
from market.models import DataSourceConfig, MarketData, NewsArticle
from portfolio.models import Holding, Portfolio
from risk.models import RiskLimits
from trading.models import Order, OrderFillEvent


@pytest.mark.django_db
class TestOrderClean:
    def _make_order(self, **overrides):
        defaults = {
            "exchange_id": "binance",
            "symbol": "BTC/USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 1.0,
            "price": 0.0,
            "timestamp": timezone.now(),
        }
        defaults.update(overrides)
        return Order(**defaults)

    def test_negative_amount(self):
        order = self._make_order(amount=-1.0)
        with pytest.raises(ValidationError) as exc_info:
            order.clean()
        assert "amount" in exc_info.value.message_dict

    def test_negative_price(self):
        order = self._make_order(price=-10.0)
        with pytest.raises(ValidationError) as exc_info:
            order.clean()
        assert "price" in exc_info.value.message_dict

    def test_limit_order_no_price(self):
        order = self._make_order(order_type="limit", price=0.0)
        with pytest.raises(ValidationError) as exc_info:
            order.clean()
        assert "price" in exc_info.value.message_dict

    def test_invalid_side(self):
        order = self._make_order(side="hold")
        with pytest.raises(ValidationError) as exc_info:
            order.clean()
        assert "side" in exc_info.value.message_dict

    def test_valid_order_passes(self):
        order = self._make_order(
            side="buy", order_type="limit", amount=0.5, price=50000.0
        )
        order.clean()  # Should not raise


@pytest.mark.django_db
class TestRiskLimitsClean:
    def test_drawdown_above_1(self):
        limits = RiskLimits(portfolio_id=100, max_portfolio_drawdown=1.5)
        with pytest.raises(ValidationError) as exc_info:
            limits.clean()
        assert "max_portfolio_drawdown" in exc_info.value.message_dict

    def test_negative_drawdown(self):
        limits = RiskLimits(portfolio_id=101, max_portfolio_drawdown=-0.1)
        with pytest.raises(ValidationError) as exc_info:
            limits.clean()
        assert "max_portfolio_drawdown" in exc_info.value.message_dict

    def test_negative_positions(self):
        limits = RiskLimits(portfolio_id=102, max_open_positions=-1)
        with pytest.raises(ValidationError) as exc_info:
            limits.clean()
        assert "max_open_positions" in exc_info.value.message_dict

    def test_valid_passes(self):
        limits = RiskLimits(
            portfolio_id=103,
            max_portfolio_drawdown=0.15,
            max_single_trade_risk=0.03,
            max_daily_loss=0.05,
            max_open_positions=10,
            max_position_size_pct=0.20,
            max_correlation=0.70,
            min_risk_reward=1.5,
            max_leverage=1.0,
        )
        limits.clean()  # Should not raise


@pytest.mark.django_db
class TestHoldingClean:
    def test_negative_amount(self):
        portfolio = Portfolio.objects.create(name="Test")
        holding = Holding(portfolio=portfolio, symbol="BTC/USDT", amount=-1.0)
        with pytest.raises(ValidationError) as exc_info:
            holding.clean()
        assert "amount" in exc_info.value.message_dict

    def test_negative_price(self):
        portfolio = Portfolio.objects.create(name="Test")
        holding = Holding(
            portfolio=portfolio, symbol="BTC/USDT", amount=1.0, avg_buy_price=-50.0
        )
        with pytest.raises(ValidationError) as exc_info:
            holding.clean()
        assert "avg_buy_price" in exc_info.value.message_dict

    def test_valid_passes(self):
        portfolio = Portfolio.objects.create(name="Test")
        holding = Holding(
            portfolio=portfolio, symbol="BTC/USDT", amount=1.0, avg_buy_price=50000.0
        )
        holding.clean()  # Should not raise


# ── P14-1: New model clean() tests ──────────────────────────


@pytest.mark.django_db
class TestOrderFillEventClean:
    def _make_order(self):
        return Order.objects.create(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=1.0,
            price=0.0,
            timestamp=timezone.now(),
        )

    def test_negative_fill_price(self):
        order = self._make_order()
        fill = OrderFillEvent(order=order, fill_price=-1.0, fill_amount=1.0)
        with pytest.raises(ValidationError) as exc_info:
            fill.clean()
        assert "fill_price" in exc_info.value.message_dict

    def test_zero_fill_amount(self):
        order = self._make_order()
        fill = OrderFillEvent(order=order, fill_price=100.0, fill_amount=0.0)
        with pytest.raises(ValidationError) as exc_info:
            fill.clean()
        assert "fill_amount" in exc_info.value.message_dict

    def test_negative_fee(self):
        order = self._make_order()
        fill = OrderFillEvent(order=order, fill_price=100.0, fill_amount=1.0, fee=-0.5)
        with pytest.raises(ValidationError) as exc_info:
            fill.clean()
        assert "fee" in exc_info.value.message_dict

    def test_valid_passes(self):
        order = self._make_order()
        fill = OrderFillEvent(order=order, fill_price=100.0, fill_amount=0.5, fee=0.01)
        fill.clean()  # Should not raise


@pytest.mark.django_db
class TestBackgroundJobClean:
    def test_progress_above_1(self):
        job = BackgroundJob(job_type="test", progress=1.5)
        with pytest.raises(ValidationError) as exc_info:
            job.clean()
        assert "progress" in exc_info.value.message_dict

    def test_progress_below_0(self):
        job = BackgroundJob(job_type="test", progress=-0.1)
        with pytest.raises(ValidationError) as exc_info:
            job.clean()
        assert "progress" in exc_info.value.message_dict

    def test_invalid_status(self):
        job = BackgroundJob(job_type="test", status="bogus")
        with pytest.raises(ValidationError) as exc_info:
            job.clean()
        assert "status" in exc_info.value.message_dict

    def test_valid_passes(self):
        job = BackgroundJob(job_type="test", progress=0.5, status="running")
        job.clean()  # Should not raise


@pytest.mark.django_db
class TestWorkflowClean:
    def test_negative_schedule_interval(self):
        wf = Workflow(id="test_wf", name="Test", schedule_interval_seconds=-10)
        with pytest.raises(ValidationError) as exc_info:
            wf.clean()
        assert "schedule_interval_seconds" in exc_info.value.message_dict

    def test_zero_schedule_interval(self):
        wf = Workflow(id="test_wf", name="Test", schedule_interval_seconds=0)
        with pytest.raises(ValidationError) as exc_info:
            wf.clean()
        assert "schedule_interval_seconds" in exc_info.value.message_dict

    def test_valid_passes(self):
        wf = Workflow(id="test_wf", name="Test", schedule_interval_seconds=3600)
        wf.clean()  # Should not raise


@pytest.mark.django_db
class TestWorkflowStepClean:
    def test_order_below_1(self):
        wf = Workflow.objects.create(id="step_test_wf", name="Test")
        step = WorkflowStep(workflow=wf, order=0, name="S1", step_type="data_refresh")
        with pytest.raises(ValidationError) as exc_info:
            step.clean()
        assert "order" in exc_info.value.message_dict

    def test_timeout_zero(self):
        wf = Workflow.objects.create(id="step_test_wf2", name="Test")
        step = WorkflowStep(
            workflow=wf, order=1, name="S1",
            step_type="data_refresh", timeout_seconds=0,
        )
        with pytest.raises(ValidationError) as exc_info:
            step.clean()
        assert "timeout_seconds" in exc_info.value.message_dict

    def test_valid_passes(self):
        wf = Workflow.objects.create(id="step_test_wf3", name="Test")
        step = WorkflowStep(
            workflow=wf, order=1, name="S1",
            step_type="data_refresh", timeout_seconds=60,
        )
        step.clean()  # Should not raise


@pytest.mark.django_db
class TestNewsArticleClean:
    def test_sentiment_score_above_1(self):
        article = NewsArticle(
            article_id="test1", title="Test", url="https://example.com",
            source="test", published_at=timezone.now(), sentiment_score=1.5,
        )
        with pytest.raises(ValidationError) as exc_info:
            article.clean()
        assert "sentiment_score" in exc_info.value.message_dict

    def test_sentiment_score_below_neg1(self):
        article = NewsArticle(
            article_id="test2", title="Test", url="https://example.com",
            source="test", published_at=timezone.now(), sentiment_score=-1.5,
        )
        with pytest.raises(ValidationError) as exc_info:
            article.clean()
        assert "sentiment_score" in exc_info.value.message_dict

    def test_invalid_sentiment_label(self):
        article = NewsArticle(
            article_id="test3", title="Test", url="https://example.com",
            source="test", published_at=timezone.now(), sentiment_label="bogus",
        )
        with pytest.raises(ValidationError) as exc_info:
            article.clean()
        assert "sentiment_label" in exc_info.value.message_dict

    def test_valid_passes(self):
        article = NewsArticle(
            article_id="test4", title="Test", url="https://example.com",
            source="test", published_at=timezone.now(),
            sentiment_score=0.5, sentiment_label="positive",
        )
        article.clean()  # Should not raise


@pytest.mark.django_db
class TestDataSourceConfigClean:
    def test_empty_symbols(self):
        ds = DataSourceConfig(symbols=[], fetch_interval_minutes=60)
        with pytest.raises(ValidationError) as exc_info:
            ds.clean()
        assert "symbols" in exc_info.value.message_dict

    def test_negative_fetch_interval(self):
        ds = DataSourceConfig(symbols=["BTC/USDT"], fetch_interval_minutes=-1)
        with pytest.raises(ValidationError) as exc_info:
            ds.clean()
        assert "fetch_interval_minutes" in exc_info.value.message_dict

    def test_valid_passes(self):
        ds = DataSourceConfig(symbols=["BTC/USDT"], fetch_interval_minutes=60)
        ds.clean()  # Should not raise


@pytest.mark.django_db
class TestMarketDataClean:
    def test_negative_price(self):
        md = MarketData(
            symbol="BTC/USDT", exchange_id="binance",
            price=-100.0, timestamp=timezone.now(),
        )
        with pytest.raises(ValidationError) as exc_info:
            md.clean()
        assert "price" in exc_info.value.message_dict

    def test_negative_volume(self):
        md = MarketData(
            symbol="BTC/USDT", exchange_id="binance",
            price=100.0, volume_24h=-500.0, timestamp=timezone.now(),
        )
        with pytest.raises(ValidationError) as exc_info:
            md.clean()
        assert "volume_24h" in exc_info.value.message_dict

    def test_valid_passes(self):
        md = MarketData(
            symbol="BTC/USDT", exchange_id="binance",
            price=100.0, volume_24h=1000.0, timestamp=timezone.now(),
        )
        md.clean()  # Should not raise


@pytest.mark.django_db
class TestScheduledTaskClean:
    def test_negative_interval(self):
        task = ScheduledTask(id="t1", name="Test", task_type="data_refresh", interval_seconds=-10)
        with pytest.raises(ValidationError) as exc_info:
            task.clean()
        assert "interval_seconds" in exc_info.value.message_dict

    def test_negative_run_count(self):
        task = ScheduledTask(id="t2", name="Test", task_type="data_refresh", run_count=-1)
        with pytest.raises(ValidationError) as exc_info:
            task.clean()
        assert "run_count" in exc_info.value.message_dict

    def test_negative_error_count(self):
        task = ScheduledTask(id="t3", name="Test", task_type="data_refresh", error_count=-1)
        with pytest.raises(ValidationError) as exc_info:
            task.clean()
        assert "error_count" in exc_info.value.message_dict

    def test_valid_passes(self):
        task = ScheduledTask(
            id="t4", name="Test", task_type="data_refresh",
            interval_seconds=300, run_count=5, error_count=0,
        )
        task.clean()  # Should not raise
