"""Tests for auto-starting order sync on startup."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

_NOW = datetime.now(timezone.utc)


def _create_order(status, mode):
    from trading.models import Order
    return Order.objects.create(
        exchange_id="kraken",
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        amount=1.0,
        price=50000.0,
        status=status,
        mode=mode,
        timestamp=_NOW,
    )


@pytest.mark.django_db
class TestMaybeStartOrderSync:
    @patch("core.apps.logger")
    @patch("trading.services.order_sync.start_order_sync")
    def test_starts_sync_when_active_orders_exist(self, mock_start, mock_logger):
        from trading.models import OrderStatus, TradingMode
        _create_order(OrderStatus.SUBMITTED, TradingMode.LIVE)

        from core.apps import _maybe_start_order_sync

        with (
            patch("asyncio.get_running_loop", side_effect=RuntimeError),
            patch("threading.Thread") as mock_thread,
        ):
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance
            _maybe_start_order_sync()
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()

    @patch("core.apps.logger")
    def test_does_not_start_sync_when_no_active_orders(self, mock_logger):
        from trading.models import OrderStatus, TradingMode
        _create_order(OrderStatus.FILLED, TradingMode.LIVE)

        from core.apps import _maybe_start_order_sync

        with patch("trading.services.order_sync.start_order_sync") as mock_start:
            _maybe_start_order_sync()
            mock_start.assert_not_called()

    @patch("core.apps.logger")
    def test_does_not_start_sync_for_paper_orders(self, mock_logger):
        from trading.models import OrderStatus, TradingMode
        _create_order(OrderStatus.SUBMITTED, TradingMode.PAPER)

        from core.apps import _maybe_start_order_sync

        with patch("trading.services.order_sync.start_order_sync") as mock_start:
            _maybe_start_order_sync()
            mock_start.assert_not_called()

    @patch("core.apps.logger")
    def test_handles_exception_gracefully(self, mock_logger):
        from core.apps import _maybe_start_order_sync

        with patch(
            "core.apps.Order.objects" if False else "trading.models.Order.objects",
        ) as mock_objects:
            mock_objects.filter.side_effect = Exception("DB unavailable")
            # Should not raise
            _maybe_start_order_sync()
