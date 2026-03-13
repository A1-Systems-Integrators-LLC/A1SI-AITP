"""Tests for GenericPaperTradingService — equity/forex paper trading engine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from trading.models import Order, OrderStatus, TradingMode
from trading.services.generic_paper_trading import GenericPaperTradingService

# Patch target for market hours (lazy import inside submit_order)
_MARKET_OPEN = "common.market_hours.sessions.MarketHoursService.is_market_open"
_ROUTER = "market.services.data_router.DataServiceRouter"
_RISK = "risk.services.risk.RiskManagementService.check_trade"


@pytest.fixture
def portfolio(db):
    from portfolio.models import Portfolio

    return Portfolio.objects.create(name="Test", exchange_id="binance")


def _make_order(portfolio, **kwargs):
    """Create a pending paper order with sensible defaults."""
    from django.utils import timezone

    defaults = {
        "exchange_id": "binance",
        "symbol": "AAPL/USD",
        "asset_class": "equity",
        "side": "buy",
        "order_type": "market",
        "amount": 10.0,
        "price": 0.0,
        "status": OrderStatus.PENDING,
        "mode": TradingMode.PAPER,
        "portfolio_id": portfolio.id,
        "timestamp": timezone.now(),
    }
    defaults.update(kwargs)
    return Order.objects.create(**defaults)


_async_make_order = sync_to_async(_make_order)
_refresh = sync_to_async(lambda obj: (obj.refresh_from_db(), obj)[-1])


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_returns_engine_generic(self):
        status = await GenericPaperTradingService.get_status()
        assert status["engine"] == "generic"

    @pytest.mark.asyncio
    async def test_returns_supported_asset_classes(self):
        status = await GenericPaperTradingService.get_status()
        assert "equity" in status["supported_asset_classes"]
        assert "forex" in status["supported_asset_classes"]


@pytest.mark.django_db(transaction=True)
class TestSubmitOrder:
    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_market_order_fills_with_last_key(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"last": 150.0})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(portfolio, asset_class="equity")
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.FILLED
        assert result.avg_fill_price == 150.0

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_market_order_fills_with_price_key(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        """Bug fix: yfinance returns 'price' key, not 'last' or 'close'."""
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"price": 150.0})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(portfolio, asset_class="equity")
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.FILLED
        assert result.avg_fill_price == 150.0

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(False, "Drawdown limit"))
    async def test_rejected_when_risk_check_fails(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        order = await _async_make_order(portfolio, asset_class="equity")
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.REJECTED
        assert "Drawdown limit" in result.reject_reason

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=False)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_equity_rejected_when_market_closed(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        order = await _async_make_order(portfolio, asset_class="equity")
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.REJECTED
        assert "closed" in result.reject_reason.lower()

    @pytest.mark.asyncio
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_forex_skips_market_hours_check(self, mock_risk, mock_router, portfolio):
        """Forex orders should not check equity market hours."""
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"last": 1.08})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(portfolio, asset_class="forex", symbol="EUR/USD")
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_error_when_price_fetch_fails(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(side_effect=RuntimeError("Network error"))
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(portfolio, asset_class="equity")
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.ERROR

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_error_when_fill_price_is_zero(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"last": 0})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(portfolio, asset_class="equity")
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.ERROR

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_limit_buy_not_filled_above_limit(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"last": 150.0})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(
            portfolio,
            order_type="limit",
            price=140.0,
            asset_class="equity",
        )
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_limit_sell_not_filled_below_limit(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"last": 150.0})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(
            portfolio,
            side="sell",
            order_type="limit",
            price=160.0,
            asset_class="equity",
        )
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_equity_fee_rate_is_zero(self, mock_risk, mock_router, mock_hours, portfolio):
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"last": 100.0})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(portfolio, asset_class="equity", amount=5.0)
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.fee == 0.0

    @pytest.mark.asyncio
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_forex_fee_rate_applied(self, mock_risk, mock_router, portfolio):
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"last": 1.08})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(
            portfolio,
            asset_class="forex",
            symbol="EUR/USD",
            amount=10000.0,
        )
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        expected_fee = 10000.0 * 1.08 * 0.0001
        assert abs(result.fee - expected_fee) < 0.01

    @pytest.mark.asyncio
    @patch(_MARKET_OPEN, return_value=True)
    @patch(_ROUTER)
    @patch(_RISK, return_value=(True, ""))
    async def test_equity_fill_uses_usd_currency(
        self, mock_risk, mock_router, mock_hours, portfolio,
    ):
        mock_router_inst = MagicMock()
        mock_router_inst.fetch_ticker = AsyncMock(return_value={"last": 150.0})
        mock_router.return_value = mock_router_inst

        order = await _async_make_order(portfolio, asset_class="equity")
        result = await GenericPaperTradingService.submit_order(order)

        result = await _refresh(result)
        assert result.fee_currency == "USD"
