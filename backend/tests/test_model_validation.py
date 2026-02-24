"""P6-2: Tests for model clean() validation."""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from portfolio.models import Holding, Portfolio
from risk.models import RiskLimits
from trading.models import Order


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
