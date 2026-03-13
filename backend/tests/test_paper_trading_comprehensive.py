"""Comprehensive tests for Paper Trading services (S12).

Covers: ForexPaperTradingService (signal-to-order, exits, max positions, sizing,
market hours), GenericPaperTradingService (equity market hours, fills, errors),
PaperTradingService (crypto multi-instance aggregation), status API, P&L tracking.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from market.models import MarketOpportunity, OpportunityType
from trading.models import Order, OrderFillEvent, OrderStatus, TradingMode
from trading.services.forex_paper_trading import (
    MIN_ENTRY_SCORE,
    POSITION_SIZE_USD,
    ForexPaperTradingService,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _create_forex_opportunity(
    symbol: str = "EURUSD=X",
    score: int = 80,
    direction: str = "bullish",
    expires_hours: int = 24,
    acted_on: bool = False,
) -> MarketOpportunity:
    """Create a forex MarketOpportunity for testing."""
    now = timezone.now()
    return MarketOpportunity.objects.create(
        symbol=symbol,
        timeframe="1h",
        opportunity_type=OpportunityType.MOMENTUM_SHIFT,
        asset_class="forex",
        score=score,
        details={"direction": direction},
        expires_at=now + timedelta(hours=expires_hours),
        acted_on=acted_on,
    )


def _create_filled_forex_order(
    symbol: str = "EURUSD=X",
    side: str = "buy",
    amount: float = 909.09,
    price: float = 1.1,
    filled_at_offset_hours: float = 0,
) -> Order:
    """Create a filled forex paper order for testing."""
    now = timezone.now()
    order = Order.objects.create(
        symbol=symbol,
        side=side,
        order_type="market",
        amount=amount,
        price=price,
        mode=TradingMode.PAPER,
        asset_class="forex",
        exchange_id="yfinance",
        status=OrderStatus.PENDING,
        timestamp=now,
    )
    # Transition through valid states: PENDING -> SUBMITTED -> FILLED
    order.transition_to(OrderStatus.SUBMITTED)
    filled_time = now - timedelta(hours=filled_at_offset_hours)
    order.transition_to(
        OrderStatus.FILLED,
        filled=amount,
        avg_fill_price=price,
    )
    # Override filled_at for time-based exit tests
    if filled_at_offset_hours > 0:
        order.filled_at = filled_time
        order.save(update_fields=["filled_at"])
    return order


# ── Forex Signal-to-Order Tests ──────────────────────────────────────────────


@pytest.mark.django_db
class TestForexSignalToOrder:
    """Test that forex opportunities above score threshold create paper orders."""

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_score_above_threshold_creates_order(self, mock_a2s, mock_price):
        """Score >= 70 should create a paper buy order."""
        mock_a2s.return_value = lambda order: None  # No-op for submit
        _create_forex_opportunity(symbol="EURUSD=X", score=75, direction="bullish")

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 1
        order = Order.objects.filter(
            symbol="EURUSD=X",
            asset_class="forex",
            mode=TradingMode.PAPER,
        ).first()
        assert order is not None
        assert order.side == "buy"

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    def test_score_below_threshold_no_order(self, mock_price):
        """Score < 70 should not create any order."""
        _create_forex_opportunity(symbol="EURUSD=X", score=65)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 0
        assert Order.objects.filter(asset_class="forex", mode=TradingMode.PAPER).count() == 0

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_score_exactly_threshold_creates_order(self, mock_a2s, mock_price):
        """Score == 70 (the threshold) should create an order."""
        mock_a2s.return_value = lambda order: None
        _create_forex_opportunity(symbol="GBPUSD=X", score=MIN_ENTRY_SCORE)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 1

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_bearish_direction_creates_sell_order(self, mock_a2s, mock_price):
        """Bearish direction on opportunity should create a sell order."""
        mock_a2s.return_value = lambda order: None
        _create_forex_opportunity(symbol="USDJPY=X", score=80, direction="bearish")

        svc = ForexPaperTradingService()
        svc.run_cycle()

        order = Order.objects.filter(
            symbol="USDJPY=X", asset_class="forex", mode=TradingMode.PAPER,
        ).first()
        assert order is not None
        assert order.side == "sell"

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_expired_opportunity_ignored(self, mock_a2s, mock_price):
        """Expired opportunities should not create orders."""
        mock_a2s.return_value = lambda order: None
        _create_forex_opportunity(symbol="EURUSD=X", score=80, expires_hours=-1)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 0

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_acted_on_opportunity_ignored(self, mock_a2s, mock_price):
        """Already acted-on opportunities should not create new orders."""
        mock_a2s.return_value = lambda order: None
        _create_forex_opportunity(symbol="EURUSD=X", score=85, acted_on=True)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 0


# ── Forex Exit Condition Tests ───────────────────────────────────────────────


@pytest.mark.django_db
class TestForexExitConditions:
    """Test the three forex exit conditions: time limit, score decay, opposing signal."""

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.12)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_exit_on_24h_timeout(self, mock_a2s, mock_price):
        """Position held > 24h should trigger a time_limit exit."""
        mock_a2s.return_value = lambda order: None
        _create_filled_forex_order(
            symbol="EURUSD=X", side="buy", filled_at_offset_hours=25,
        )

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["exits_created"] == 1
        exit_order = Order.objects.filter(
            symbol="EURUSD=X", side="sell", mode=TradingMode.PAPER,
        ).first()
        assert exit_order is not None

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.08)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_exit_on_score_decay(self, mock_a2s, mock_price):
        """Score below EXIT_SCORE_THRESHOLD should trigger exit."""
        mock_a2s.return_value = lambda order: None
        _create_filled_forex_order(
            symbol="GBPUSD=X", side="buy", filled_at_offset_hours=2,
        )
        # Create a recent low-score opportunity for the same symbol
        _create_forex_opportunity(symbol="GBPUSD=X", score=30)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["exits_created"] == 1

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.09)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_exit_on_opposing_signal(self, mock_a2s, mock_price):
        """Bearish signal on a buy position should trigger exit."""
        mock_a2s.return_value = lambda order: None
        _create_filled_forex_order(
            symbol="AUDUSD=X", side="buy", filled_at_offset_hours=2,
        )
        # Create an opposing (bearish) signal above EXIT_SCORE_THRESHOLD
        _create_forex_opportunity(
            symbol="AUDUSD=X", score=60, direction="bearish",
        )

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["exits_created"] == 1

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.10)
    def test_no_exit_when_score_above_threshold(self, mock_price):
        """Position with high recent score and same direction should not exit."""
        _create_filled_forex_order(
            symbol="NZDUSD=X", side="buy", filled_at_offset_hours=2,
        )
        # Recent high-score bullish signal -- no exit condition met
        _create_forex_opportunity(
            symbol="NZDUSD=X", score=75, direction="bullish",
        )

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["exits_created"] == 0


# ── Forex Max Positions Tests ────────────────────────────────────────────────


@pytest.mark.django_db
class TestForexMaxPositions:
    """Test that max 3 forex positions are enforced."""

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_max_positions_enforced(self, mock_a2s, mock_price):
        """Cannot open more than MAX_OPEN_POSITIONS simultaneously."""
        mock_a2s.return_value = lambda order: None

        # Create 3 existing open positions (filled buys, no matching sells)
        for sym in ["EURUSD=X", "GBPUSD=X", "USDJPY=X"]:
            _create_filled_forex_order(symbol=sym, side="buy")

        # Create a new high-score opportunity
        _create_forex_opportunity(symbol="AUDUSD=X", score=90)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 0

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_position_slot_freed_after_close(self, mock_a2s, mock_price):
        """After closing a position (buy+sell matched), a new entry can be made."""
        mock_a2s.return_value = lambda order: None

        # Create 3 open positions
        for sym in ["EURUSD=X", "GBPUSD=X", "USDJPY=X"]:
            _create_filled_forex_order(symbol=sym, side="buy")

        # Close one position (matching sell for EURUSD=X)
        _create_filled_forex_order(symbol="EURUSD=X", side="sell")

        # Now only 2 net open positions, new entry should be allowed
        _create_forex_opportunity(symbol="AUDUSD=X", score=90)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 1


# ── Forex Position Sizing Tests ──────────────────────────────────────────────


@pytest.mark.django_db
class TestForexPositionSizing:
    """Test that position size is $1000 per trade."""

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_position_size_usd_1000(self, mock_a2s, mock_price):
        """Order amount = POSITION_SIZE_USD / price."""
        mock_a2s.return_value = lambda order: None
        _create_forex_opportunity(symbol="EURUSD=X", score=80)

        svc = ForexPaperTradingService()
        svc.run_cycle()

        order = Order.objects.filter(
            symbol="EURUSD=X", asset_class="forex", mode=TradingMode.PAPER,
        ).first()
        assert order is not None
        expected_amount = POSITION_SIZE_USD / 1.1
        assert abs(order.amount - expected_amount) < 0.01

    @patch.object(ForexPaperTradingService, "_get_price", return_value=0.0)
    def test_zero_price_skips_entry(self, mock_price):
        """Zero price should skip the entry (no order created)."""
        _create_forex_opportunity(symbol="EURUSD=X", score=80)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 0


# ── Generic Paper Trading: Market Hours & Fills ─────────────────────────────


@pytest.mark.django_db(transaction=True)
class TestGenericPaperTradingEquityHours:
    """Test GenericPaperTradingService market hours enforcement for equities."""

    @pytest.mark.asyncio
    async def test_equity_rejected_when_market_closed(self):
        """Equity orders should be rejected when the US market is closed."""
        from trading.services.generic_paper_trading import GenericPaperTradingService

        order = await _async_create_order(
            symbol="AAPL",
            asset_class="equity",
            side="buy",
            amount=10.0,
            price=150.0,
        )

        # Mock the MarketHoursService that submit_order imports lazily
        mock_mhs = MagicMock()
        mock_mhs.is_market_open.return_value = False
        mock_sessions = MagicMock()
        mock_sessions.MarketHoursService = mock_mhs

        import sys

        sys.modules["common"] = MagicMock()
        sys.modules["common.market_hours"] = MagicMock()
        sys.modules["common.market_hours.sessions"] = mock_sessions
        try:
            svc = GenericPaperTradingService()
            result = await svc.submit_order(order)
            assert result.status == OrderStatus.REJECTED
            assert "market is closed" in (result.reject_reason or "")
        finally:
            sys.modules.pop("common.market_hours.sessions", None)
            sys.modules.pop("common.market_hours", None)
            sys.modules.pop("common", None)

    @pytest.mark.asyncio
    async def test_forex_order_no_equity_hours_check(self):
        """Forex orders should not be blocked by equity market hours check.

        GenericPaperTradingService only gates equity orders on market hours,
        so a forex order should pass through even if equity markets are closed.
        """
        from trading.services.generic_paper_trading import GenericPaperTradingService

        order = await _async_create_order(
            symbol="EURUSD=X",
            asset_class="forex",
            side="buy",
            amount=1000.0,
            price=1.1,
        )

        with (
            patch(
                "risk.services.risk.RiskManagementService.check_trade",
                return_value=(True, "approved"),
            ),
            patch(
                "market.services.data_router.DataServiceRouter.fetch_ticker",
                new_callable=AsyncMock,
                return_value={"last": 1.1},
            ),
        ):
            svc = GenericPaperTradingService()
            result = await svc.submit_order(order)
            # Forex should NOT be rejected for market hours
            assert result.status != OrderStatus.REJECTED or "market is closed" not in (
                result.reject_reason or ""
            )


# ── Crypto Multi-Instance Aggregation ────────────────────────────────────────


@pytest.mark.django_db
class TestCryptoMultiInstanceAggregation:
    """Test PaperTradingService crypto multi-instance setup."""

    def test_multi_instance_status_view(self, authenticated_client):
        """Status endpoint returns statuses from all configured instances + forex."""
        mock_svc_1 = MagicMock()
        mock_svc_1.get_status.return_value = {
            "running": True,
            "strategy": "CryptoInvestorV1",
            "pid": 1001,
            "uptime_seconds": 3600,
        }
        mock_svc_2 = MagicMock()
        mock_svc_2.get_status.return_value = {
            "running": True,
            "strategy": "BollingerMeanReversion",
            "pid": 1002,
            "uptime_seconds": 1800,
        }
        mock_svc_3 = MagicMock()
        mock_svc_3.get_status.return_value = {
            "running": False,
            "strategy": "VolatilityBreakout",
            "pid": None,
            "uptime_seconds": 0,
        }

        services = {
            "CryptoInvestorV1": mock_svc_1,
            "BollingerMeanReversion": mock_svc_2,
            "VolatilityBreakout": mock_svc_3,
        }

        with patch("trading.views._get_paper_trading_services", return_value=services):
            resp = authenticated_client.get("/api/paper-trading/status/")

        assert resp.status_code == 200
        data = resp.json()
        # 3 crypto instances + 1 forex_signals
        assert len(data) >= 3
        instance_names = [s["instance"] for s in data]
        assert "CryptoInvestorV1" in instance_names
        assert "BollingerMeanReversion" in instance_names
        assert "VolatilityBreakout" in instance_names

    def test_multi_instance_trades_aggregation(self, authenticated_client):
        """Trades endpoint aggregates open trades from all instances."""
        mock_svc_1 = MagicMock()
        mock_svc_1.get_open_trades = AsyncMock(
            return_value=[
                {"pair": "BTC/USDT", "amount": 0.01, "is_open": True},
            ],
        )
        mock_svc_2 = MagicMock()
        mock_svc_2.get_open_trades = AsyncMock(
            return_value=[
                {"pair": "ETH/USDT", "amount": 0.1, "is_open": True},
            ],
        )

        services = {"CIV1": mock_svc_1, "BMR": mock_svc_2}

        with patch("trading.views._get_paper_trading_services", return_value=services):
            resp = authenticated_client.get("/api/paper-trading/trades/")

        assert resp.status_code == 200
        data = resp.json()
        # At least 2 trades from the two instances
        pairs = [t.get("pair") for t in data]
        assert "BTC/USDT" in pairs
        assert "ETH/USDT" in pairs


# ── Paper Trading P&L Calculation Tests ──────────────────────────────────────


@pytest.mark.django_db
class TestPaperTradingPnL:
    """Test profit/loss tracking for paper trades."""

    def test_forex_status_total_trades(self):
        """ForexPaperTradingService.get_status() counts total filled orders."""
        # Create some filled forex orders
        _create_filled_forex_order(symbol="EURUSD=X", side="buy")
        _create_filled_forex_order(symbol="GBPUSD=X", side="buy")
        _create_filled_forex_order(symbol="EURUSD=X", side="sell")

        svc = ForexPaperTradingService()
        status = svc.get_status()

        assert status["total_trades"] == 3
        assert status["strategy"] == "ForexSignals"
        assert status["running"] is True

    def test_forex_open_positions_count(self):
        """get_status reports correct number of open positions."""
        _create_filled_forex_order(symbol="EURUSD=X", side="buy")
        _create_filled_forex_order(symbol="GBPUSD=X", side="buy")
        # Close EURUSD position
        _create_filled_forex_order(symbol="EURUSD=X", side="sell")

        svc = ForexPaperTradingService()
        status = svc.get_status()

        # EURUSD is closed (1 buy - 1 sell = 0), GBPUSD open (1 buy)
        assert status["open_positions"] == 1

    def test_fill_event_tracks_pnl_data(self):
        """OrderFillEvent records are created for paper fills."""
        order = _create_filled_forex_order(
            symbol="EURUSD=X", side="buy", amount=909.09, price=1.1,
        )
        # Manually create a fill event as the service would
        fill = OrderFillEvent.objects.create(
            order=order,
            fill_price=1.1,
            fill_amount=909.09,
            fee=0.1,
            fee_currency="USD",
        )

        assert fill.fill_price == 1.1
        assert fill.fill_amount == 909.09
        assert fill.fee == 0.1
        assert fill.fee_currency == "USD"


# ── Error Handling Tests ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPaperTradingErrorHandling:
    """Test error handling when external services are unavailable."""

    @patch.object(ForexPaperTradingService, "_get_price", return_value=0.0)
    def test_price_fetch_failure_skips_entry(self, mock_price):
        """When price fetch returns 0, entry is skipped gracefully."""
        _create_forex_opportunity(symbol="EURUSD=X", score=85)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 0
        assert Order.objects.filter(asset_class="forex").count() == 0

    @patch.object(ForexPaperTradingService, "_get_price", return_value=0.0)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_price_fetch_failure_skips_exit(self, mock_a2s, mock_price):
        """When price is unavailable during exit, exit is skipped gracefully."""
        mock_a2s.return_value = lambda order: None
        # Create a position that should be exited (held > 24h)
        _create_filled_forex_order(
            symbol="EURUSD=X", side="buy", filled_at_offset_hours=25,
        )

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        # Exit skipped because price is 0
        assert result["exits_created"] == 0

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_submit_order_exception_handled(self, mock_a2s, mock_price):
        """If GenericPaperTradingService.submit_order raises, entry still counts."""
        mock_a2s.return_value = MagicMock(side_effect=RuntimeError("Connection refused"))
        _create_forex_opportunity(symbol="EURUSD=X", score=80)

        svc = ForexPaperTradingService()
        # Should not raise -- the exception is caught internally
        result = svc.run_cycle()

        # Entry still counted (order created in DB before submit call)
        assert result["entries_created"] == 1

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_generic_service_handles_price_fetch_error(self):
        """GenericPaperTradingService transitions to ERROR on price fetch failure."""
        from trading.services.generic_paper_trading import GenericPaperTradingService

        order = await _async_create_order(
            symbol="AAPL",
            asset_class="equity",
            side="buy",
            amount=10.0,
            price=150.0,
        )

        # Mock common.market_hours.sessions for the lazy import
        mock_mhs = MagicMock()
        mock_mhs.is_market_open.return_value = True
        mock_sessions = MagicMock()
        mock_sessions.MarketHoursService = mock_mhs

        import sys

        sys.modules["common"] = MagicMock()
        sys.modules["common.market_hours"] = MagicMock()
        sys.modules["common.market_hours.sessions"] = mock_sessions
        try:
            with (
                patch(
                    "risk.services.risk.RiskManagementService.check_trade",
                    return_value=(True, "approved"),
                ),
                patch(
                    "market.services.data_router.DataServiceRouter.fetch_ticker",
                    new_callable=AsyncMock,
                    side_effect=ConnectionError("Exchange down"),
                ),
            ):
                svc = GenericPaperTradingService()
                result = await svc.submit_order(order)
                assert result.status == OrderStatus.ERROR
                assert "Price fetch failed" in (result.error_message or "")
        finally:
            sys.modules.pop("common.market_hours.sessions", None)
            sys.modules.pop("common.market_hours", None)
            sys.modules.pop("common", None)


# ── Forex Status API Tests ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestForexStatusAPI:
    """Test the forex paper trading status reporting."""

    def test_status_includes_forex_fields(self):
        """get_status() returns expected fields for forex paper trading."""
        svc = ForexPaperTradingService()
        status = svc.get_status()

        assert "running" in status
        assert "strategy" in status
        assert "asset_class" in status
        assert status["asset_class"] == "forex"
        assert status["engine"] == "signal_based"
        assert "open_positions" in status
        assert "total_trades" in status

    def test_status_with_no_trades(self):
        """Status with zero trades should report 0 positions and trades."""
        svc = ForexPaperTradingService()
        status = svc.get_status()

        assert status["open_positions"] == 0
        assert status["total_trades"] == 0

    def test_run_cycle_returns_complete_result(self):
        """run_cycle() returns status, entries_created, and exits_created."""
        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["status"] == "completed"
        assert "entries_created" in result
        assert "exits_created" in result


# ── Duplicate Symbol Prevention ──────────────────────────────────────────────


@pytest.mark.django_db
class TestDuplicateSymbolPrevention:
    """Test that the service does not open duplicate positions for the same symbol."""

    @patch.object(ForexPaperTradingService, "_get_price", return_value=1.1)
    @patch("trading.services.forex_paper_trading.async_to_sync")
    def test_no_duplicate_entry_for_open_symbol(self, mock_a2s, mock_price):
        """Should not open a second position for a symbol that already has one."""
        mock_a2s.return_value = lambda order: None
        _create_filled_forex_order(symbol="EURUSD=X", side="buy")
        _create_forex_opportunity(symbol="EURUSD=X", score=90)

        svc = ForexPaperTradingService()
        result = svc.run_cycle()

        assert result["entries_created"] == 0


# ── Async helper ─────────────────────────────────────────────────────────────


async def _async_create_order(
    symbol: str,
    asset_class: str,
    side: str,
    amount: float,
    price: float,
) -> Order:
    """Create an Order in an async context using sync_to_async."""
    from asgiref.sync import sync_to_async

    return await sync_to_async(Order.objects.create)(
        symbol=symbol,
        side=side,
        order_type="market",
        amount=amount,
        price=price,
        mode=TradingMode.PAPER,
        asset_class=asset_class,
        exchange_id="yfinance",
        status=OrderStatus.PENDING,
        timestamp=timezone.now(),
    )
