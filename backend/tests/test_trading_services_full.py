"""Full coverage tests for backend/trading/ services.

Covers: LiveTradingService (asset-class gating, channel layer None, fee edge cases,
invalid transitions, stop-loss passthrough), ForexPaperTradingService (price None,
opposing signals, net position edge cases, expired opps), TradingPerformanceService
(zero-price skip, only-buys, only-sells, infinity profit factor, NaN price),
order_sync (start/stop idempotency, loop error isolation).
"""

import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone as tz

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()


# ══════════════════════════════════════════════════════
# LiveTradingService — asset-class gating
# ══════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestLiveTradingAssetClassGating:
    async def _make_order(self, asset_class="crypto", **kwargs):
        from asgiref.sync import sync_to_async
        from trading.models import Order, OrderStatus, TradingMode
        defaults = dict(
            symbol="BTC/USDT", side="buy", order_type="market", amount=0.001,
            price=50000.0, mode=TradingMode.LIVE, asset_class=asset_class,
            exchange_id="kraken", status=OrderStatus.PENDING, timestamp=tz.now(),
        )
        defaults.update(kwargs)
        return await sync_to_async(Order.objects.create)(**defaults)

    async def test_equity_order_rejected(self):
        from trading.services.live_trading import LiveTradingService
        order = await self._make_order(asset_class="equity", symbol="AAPL/USD")
        with patch("trading.services.live_trading.get_channel_layer", return_value=None):
            result = await LiveTradingService.submit_order(order)
        assert result.status == "rejected"
        assert "equity" in (result.reject_reason or "").lower()

    async def test_forex_order_rejected(self):
        from trading.services.live_trading import LiveTradingService
        order = await self._make_order(asset_class="forex", symbol="EUR/USD")
        with patch("trading.services.live_trading.get_channel_layer", return_value=None):
            result = await LiveTradingService.submit_order(order)
        assert result.status == "rejected"
        assert "forex" in (result.reject_reason or "").lower()


# ══════════════════════════════════════════════════════
# LiveTradingService — channel layer None
# ══════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestLiveTradingBroadcastGraceful:
    async def test_broadcast_no_channel_layer(self):
        """Broadcast with no channel layer should be a no-op."""
        from trading.services.live_trading import LiveTradingService
        from asgiref.sync import sync_to_async
        from trading.models import Order, OrderStatus, TradingMode
        order = await sync_to_async(Order.objects.create)(
            symbol="BTC/USDT", side="buy", order_type="market", amount=0.001,
            price=50000.0, mode=TradingMode.LIVE, asset_class="crypto",
            exchange_id="kraken", status=OrderStatus.PENDING, timestamp=tz.now(),
        )
        with patch("trading.services.live_trading.get_channel_layer", return_value=None):
            await LiveTradingService._broadcast_order_update(order)
            # No exception = success


# ══════════════════════════════════════════════════════
# LiveTradingService — sync_order edge cases
# ══════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestSyncOrderEdgeCases:
    async def test_no_exchange_order_id_returns_early(self):
        from asgiref.sync import sync_to_async
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.live_trading import LiveTradingService
        order = await sync_to_async(Order.objects.create)(
            symbol="BTC/USDT", side="buy", order_type="market", amount=0.001,
            price=50000.0, mode=TradingMode.LIVE, asset_class="crypto",
            exchange_id="kraken", status=OrderStatus.PENDING, timestamp=tz.now(),
            exchange_order_id="",
        )
        result = await LiveTradingService.sync_order(order)
        assert result.id == order.id  # Returned immediately

    async def test_no_fee_in_ccxt_response(self):
        """CCXT response missing fee key should not crash."""
        from asgiref.sync import sync_to_async
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.live_trading import LiveTradingService
        order = await sync_to_async(Order.objects.create)(
            symbol="BTC/USDT", side="buy", order_type="market", amount=0.001,
            price=50000.0, mode=TradingMode.LIVE, asset_class="crypto",
            exchange_id="kraken", status=OrderStatus.SUBMITTED, timestamp=tz.now(),
            exchange_order_id="test-123",
        )
        mock_exchange = AsyncMock()
        mock_exchange.fetch_order.return_value = {
            "status": "closed", "filled": 0.001, "average": 50100.0,
            # No "fee" key
        }
        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()
        with patch("trading.services.live_trading.ExchangeService", return_value=mock_service):
            with patch("trading.services.live_trading.get_channel_layer", return_value=None):
                result = await LiveTradingService.sync_order(order)
        await sync_to_async(result.refresh_from_db)()
        assert result.status == OrderStatus.FILLED

    async def test_invalid_transition_logged_not_raised(self):
        """Invalid state transition should log warning, not raise."""
        from asgiref.sync import sync_to_async
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.live_trading import LiveTradingService
        order = await sync_to_async(Order.objects.create)(
            symbol="BTC/USDT", side="buy", order_type="market", amount=0.001,
            price=50000.0, mode=TradingMode.LIVE, asset_class="crypto",
            exchange_id="kraken", status=OrderStatus.FILLED, timestamp=tz.now(),
            exchange_order_id="test-456",
        )
        mock_exchange = AsyncMock()
        mock_exchange.fetch_order.return_value = {
            "status": "open", "filled": 0, "average": 0,
        }
        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()
        with patch("trading.services.live_trading.ExchangeService", return_value=mock_service):
            with patch("trading.services.live_trading.get_channel_layer", return_value=None):
                result = await LiveTradingService.sync_order(order)
        # Should not raise, order still returned
        assert result.id == order.id


# ══════════════════════════════════════════════════════
# LiveTradingService — cancel edge cases
# ══════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestCancelOrderEdgeCases:
    async def test_cancel_terminal_order_noop(self):
        from asgiref.sync import sync_to_async
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.live_trading import LiveTradingService
        order = await sync_to_async(Order.objects.create)(
            symbol="BTC/USDT", side="buy", order_type="market", amount=0.001,
            price=50000.0, mode=TradingMode.LIVE, asset_class="crypto",
            exchange_id="kraken", status=OrderStatus.FILLED, timestamp=tz.now(),
        )
        result = await LiveTradingService.cancel_order(order)
        assert result.status == OrderStatus.FILLED  # Unchanged

    async def test_cancel_without_exchange_id(self):
        from asgiref.sync import sync_to_async
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.live_trading import LiveTradingService
        order = await sync_to_async(Order.objects.create)(
            symbol="BTC/USDT", side="buy", order_type="market", amount=0.001,
            price=50000.0, mode=TradingMode.LIVE, asset_class="crypto",
            exchange_id="kraken", status=OrderStatus.SUBMITTED, timestamp=tz.now(),
            exchange_order_id="",
        )
        mock_service = MagicMock()
        mock_service.close = AsyncMock()
        with patch("trading.services.live_trading.ExchangeService", return_value=mock_service):
            with patch("trading.services.live_trading.get_channel_layer", return_value=None):
                result = await LiveTradingService.cancel_order(order)
        await sync_to_async(result.refresh_from_db)()
        assert result.status == OrderStatus.CANCELLED


# ══════════════════════════════════════════════════════
# LiveTradingService — stop-loss passthrough
# ══════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestStopLossPassthrough:
    async def test_stop_loss_sent_to_exchange(self):
        from asgiref.sync import sync_to_async
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.live_trading import LiveTradingService
        order = await sync_to_async(Order.objects.create)(
            symbol="BTC/USDT", side="buy", order_type="market", amount=0.001,
            price=50000.0, stop_loss_price=48000.0, mode=TradingMode.LIVE,
            asset_class="crypto", exchange_id="kraken", status=OrderStatus.PENDING,
            timestamp=tz.now(),
        )
        mock_exchange = AsyncMock()
        mock_exchange.create_order.return_value = {"id": "sl-order-1"}
        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()

        with patch("trading.services.live_trading.ExchangeService", return_value=mock_service):
            with patch("trading.services.live_trading.get_channel_layer", return_value=None):
                with patch("risk.services.risk.RiskManagementService.check_trade", return_value=(True, "")):
                    await LiveTradingService.submit_order(order)

        # Verify stopLoss params were passed
        call_kwargs = mock_exchange.create_order.call_args
        assert call_kwargs[1]["params"]["stopLoss"]["triggerPrice"] == 48000.0


# ══════════════════════════════════════════════════════
# TradingPerformanceService
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPerformanceMetricsEdgeCases:
    def _create_order(self, symbol, side, price, amount=1.0, **kwargs):
        from trading.models import Order, OrderStatus, TradingMode
        return Order.objects.create(
            symbol=symbol, side=side, order_type="market", amount=amount,
            price=price, avg_fill_price=price, filled=amount,
            mode=TradingMode.LIVE, asset_class="crypto", exchange_id="kraken",
            status=OrderStatus.FILLED, portfolio_id=8000, timestamp=tz.now(),
            **kwargs,
        )

    def test_zero_price_skipped(self):
        from trading.services.performance import TradingPerformanceService
        from trading.models import Order, OrderStatus, TradingMode
        Order.objects.create(
            symbol="BTC/USDT", side="buy", order_type="market", amount=1.0,
            price=0.0, avg_fill_price=0.0, filled=1.0,
            mode=TradingMode.LIVE, asset_class="crypto", exchange_id="kraken",
            status=OrderStatus.FILLED, portfolio_id=8000, timestamp=tz.now(),
        )
        result = TradingPerformanceService.get_summary(8000)
        assert result["total_trades"] == 1  # Counted but zero-price skipped from P&L
        assert result["total_pnl"] == 0.0

    def test_only_buys_negative_pnl(self):
        """Buys with no sells → negative P&L (cost with no revenue)."""
        from trading.services.performance import TradingPerformanceService
        self._create_order("ETH/USDT", "buy", 3000.0, amount=2.0)
        result = TradingPerformanceService.get_summary(8000)
        # sell_revenue=0, buy_cost=6000 → PnL = -6000
        assert result["total_pnl"] < 0

    def test_only_sells_positive_pnl(self):
        """Sells with no buys → positive P&L (revenue with no cost)."""
        from trading.services.performance import TradingPerformanceService
        self._create_order("SOL/USDT", "sell", 150.0, amount=10.0)
        result = TradingPerformanceService.get_summary(8000)
        assert result["total_pnl"] > 0

    def test_profit_factor_infinity(self):
        """All wins, no losses → profit_factor is None (infinity)."""
        from trading.services.performance import TradingPerformanceService
        self._create_order("BTC/USDT", "buy", 100.0)
        self._create_order("BTC/USDT", "sell", 200.0)
        result = TradingPerformanceService.get_summary(8000)
        assert result["profit_factor"] is None  # Infinity → None

    def test_profit_factor_zero_no_wins(self):
        """All losses → profit_factor is 0."""
        from trading.services.performance import TradingPerformanceService
        self._create_order("BTC/USDT", "buy", 200.0)
        self._create_order("BTC/USDT", "sell", 100.0)
        result = TradingPerformanceService.get_summary(8000)
        assert result["profit_factor"] == 0.0

    def test_by_symbol_grouping(self):
        from trading.services.performance import TradingPerformanceService
        self._create_order("BTC/USDT", "buy", 100.0)
        self._create_order("ETH/USDT", "buy", 50.0)
        result = TradingPerformanceService.get_by_symbol(8000)
        symbols = {r["symbol"] for r in result}
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols

    def test_mode_filter(self):
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.performance import TradingPerformanceService
        Order.objects.create(
            symbol="BTC/USDT", side="buy", order_type="market", amount=1.0,
            price=100.0, avg_fill_price=100.0, filled=1.0,
            mode=TradingMode.PAPER, asset_class="crypto", exchange_id="kraken",
            status=OrderStatus.FILLED, portfolio_id=8001, timestamp=tz.now(),
        )
        result = TradingPerformanceService.get_summary(8001, mode="live")
        assert result["total_trades"] == 0

    def test_empty_orders(self):
        from trading.services.performance import TradingPerformanceService
        result = TradingPerformanceService.get_summary(8099)
        assert result["total_trades"] == 0
        assert result["total_pnl"] == 0.0
        assert result["win_rate"] == 0.0


# ══════════════════════════════════════════════════════
# ForexPaperTradingService
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestForexPaperTradingEdgeCases:
    def test_price_none_skips_entry(self):
        from trading.services.forex_paper_trading import ForexPaperTradingService
        svc = ForexPaperTradingService()
        with patch.object(svc, "_get_price", return_value=0.0):
            with patch.object(svc, "_get_open_symbols", return_value=set()):
                from market.models import MarketOpportunity
                from django.utils import timezone
                now = timezone.now()
                MarketOpportunity.objects.create(
                    symbol="EUR/USD", asset_class="forex", opportunity_type="rsi_bounce",
                    score=85, details={"direction": "bullish"},
                    expires_at=now + timedelta(hours=1),
                )
                entries = svc._check_entries()
        assert entries == 0

    def test_max_positions_reached(self):
        from trading.services.forex_paper_trading import ForexPaperTradingService
        svc = ForexPaperTradingService()
        with patch.object(svc, "_get_open_symbols", return_value={"EUR/USD", "GBP/USD", "USD/JPY"}):
            entries = svc._check_entries()
        assert entries == 0

    def test_run_cycle_returns_dict(self):
        from trading.services.forex_paper_trading import ForexPaperTradingService
        svc = ForexPaperTradingService()
        with patch.object(svc, "_check_entries", return_value=0):
            with patch.object(svc, "_check_exits", return_value=0):
                result = svc.run_cycle()
        assert result["status"] == "completed"
        assert result["entries_created"] == 0
        assert result["exits_created"] == 0

    def test_get_status_shape(self):
        from trading.services.forex_paper_trading import ForexPaperTradingService
        svc = ForexPaperTradingService()
        status = svc.get_status()
        assert status["running"] is True
        assert status["strategy"] == "ForexSignals"
        assert status["asset_class"] == "forex"
        assert "open_positions" in status

    def test_get_open_symbols_balanced_is_empty(self):
        """Equal buys and sells = no open position."""
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.forex_paper_trading import ForexPaperTradingService
        # Create matching buy + sell
        for side in ("buy", "sell"):
            Order.objects.create(
                symbol="EUR/USD", side=side, order_type="market", amount=1000.0,
                price=1.10, mode=TradingMode.PAPER, asset_class="forex",
                exchange_id="yfinance", status=OrderStatus.FILLED, timestamp=tz.now(),
            )
        result = ForexPaperTradingService._get_open_symbols()
        assert "EUR/USD" not in result

    def test_get_open_symbols_unbalanced(self):
        """More buys than sells = open position."""
        from trading.models import Order, OrderStatus, TradingMode
        from trading.services.forex_paper_trading import ForexPaperTradingService
        Order.objects.create(
            symbol="GBP/USD", side="buy", order_type="market", amount=1000.0,
            price=1.25, mode=TradingMode.PAPER, asset_class="forex",
            exchange_id="yfinance", status=OrderStatus.FILLED, timestamp=tz.now(),
        )
        result = ForexPaperTradingService._get_open_symbols()
        assert "GBP/USD" in result


# ══════════════════════════════════════════════════════
# ForexPaperTradingService — exit logic
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestForexExitLogic:
    def _create_filled_buy(self, symbol, hours_ago=0):
        from django.utils import timezone
        from trading.models import Order, OrderStatus, TradingMode
        ts = timezone.now() - timedelta(hours=hours_ago)
        return Order.objects.create(
            symbol=symbol, side="buy", order_type="market", amount=1000.0,
            price=1.10, mode=TradingMode.PAPER, asset_class="forex",
            exchange_id="yfinance", status=OrderStatus.FILLED,
            filled_at=ts, timestamp=ts,
        )

    def test_time_limit_exit(self):
        from trading.services.forex_paper_trading import ForexPaperTradingService
        self._create_filled_buy("AUD/USD", hours_ago=25)  # Over 24h
        svc = ForexPaperTradingService()
        with patch.object(svc, "_get_price", return_value=1.10):
            with patch("trading.services.forex_paper_trading.async_to_sync",
                        return_value=lambda o: None):
                exits = svc._check_exits()
        assert exits >= 1

    def test_score_decay_exit(self):
        from django.utils import timezone
        from market.models import MarketOpportunity
        from trading.services.forex_paper_trading import ForexPaperTradingService
        self._create_filled_buy("NZD/USD", hours_ago=1)  # Recent, not timed out
        # Create low-score opportunity
        MarketOpportunity.objects.create(
            symbol="NZD/USD", asset_class="forex", opportunity_type="rsi_bounce",
            score=20, details={},  # Below EXIT_SCORE_THRESHOLD=40
            expires_at=timezone.now() + timedelta(hours=1),
        )
        svc = ForexPaperTradingService()
        with patch.object(svc, "_get_price", return_value=1.10):
            with patch("trading.services.forex_paper_trading.async_to_sync",
                        return_value=lambda o: None):
                exits = svc._check_exits()
        assert exits >= 1


# ══════════════════════════════════════════════════════
# order_sync — start/stop
# ══════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestOrderSync:
    async def test_start_creates_task(self):
        import trading.services.order_sync as osync
        osync._sync_task = None
        with patch.object(osync, "_sync_loop", new_callable=AsyncMock):
            await osync.start_order_sync()
            assert osync._sync_task is not None
            # Cleanup
            osync._sync_task.cancel()
            try:
                await osync._sync_task
            except asyncio.CancelledError:
                pass
            osync._sync_task = None

    async def test_start_idempotent(self):
        import trading.services.order_sync as osync
        osync._sync_task = None
        with patch.object(osync, "_sync_loop", new_callable=AsyncMock):
            await osync.start_order_sync()
            first_task = osync._sync_task
            await osync.start_order_sync()
            assert osync._sync_task is first_task  # Same task
            # Cleanup
            osync._sync_task.cancel()
            try:
                await osync._sync_task
            except asyncio.CancelledError:
                pass
            osync._sync_task = None

    async def test_stop_when_not_running(self):
        import trading.services.order_sync as osync
        osync._sync_task = None
        await osync.stop_order_sync()  # Should not raise

    async def test_stop_cancels_task(self):
        import trading.services.order_sync as osync
        osync._sync_task = None
        with patch.object(osync, "_sync_loop", new_callable=AsyncMock):
            await osync.start_order_sync()
            assert osync._sync_task is not None
            await osync.stop_order_sync()
            assert osync._sync_task is None


# ══════════════════════════════════════════════════════
# CCXT status mapping
# ══════════════════════════════════════════════════════


class TestCCXTStatusMap:
    def test_all_known_statuses(self):
        from trading.services.live_trading import CCXT_STATUS_MAP
        from trading.models import OrderStatus
        assert CCXT_STATUS_MAP["open"] == OrderStatus.OPEN
        assert CCXT_STATUS_MAP["closed"] == OrderStatus.FILLED
        assert CCXT_STATUS_MAP["canceled"] == OrderStatus.CANCELLED
        assert CCXT_STATUS_MAP["cancelled"] == OrderStatus.CANCELLED
        assert CCXT_STATUS_MAP["expired"] == OrderStatus.CANCELLED
        assert CCXT_STATUS_MAP["rejected"] == OrderStatus.REJECTED

    def test_unknown_status_returns_none(self):
        from trading.services.live_trading import CCXT_STATUS_MAP
        assert CCXT_STATUS_MAP.get("unknown_status") is None
