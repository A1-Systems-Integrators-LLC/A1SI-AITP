"""Live trading service — bridges order state machine to ccxt exchange execution."""

import logging

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

from market.services.exchange import ExchangeService
from trading.models import Order, OrderFillEvent, OrderStatus, TradingMode

logger = logging.getLogger(__name__)

# Map ccxt order statuses to our OrderStatus
CCXT_STATUS_MAP = {
    "open": OrderStatus.OPEN,
    "closed": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
}


class LiveTradingService:
    """Singleton-style service for live order execution via ccxt."""

    @staticmethod
    async def submit_order(order: Order) -> Order:
        """Submit an order to the exchange.

        1. Gate non-crypto live trading
        2. Check risk limits
        3. Check kill switch
        4. Submit via ccxt
        5. Transition pending -> submitted
        6. Broadcast order_update
        """
        # Gate: live trading only supported for crypto via CCXT
        asset_class = getattr(order, "asset_class", "crypto")
        if asset_class in ("equity", "forex"):
            await sync_to_async(order.transition_to)(
                OrderStatus.REJECTED,
                reject_reason=(
                    f"Live trading not yet supported for {asset_class}. "
                    "Use paper trading mode instead."
                ),
            )
            await LiveTradingService._broadcast_order_update(order)
            return order

        from risk.models import RiskState

        # Kill switch check
        state = await sync_to_async(
            lambda: RiskState.objects.filter(portfolio_id=order.portfolio_id).first(),
        )()
        if state and state.is_halted:
            await sync_to_async(order.transition_to)(
                OrderStatus.REJECTED,
                reject_reason=f"Trading halted: {state.halt_reason}",
            )
            await LiveTradingService._broadcast_order_update(order)
            return order

        # Risk check
        from risk.services.risk import RiskManagementService

        approved, reason = await sync_to_async(RiskManagementService.check_trade)(
            order.portfolio_id,
            order.symbol,
            order.side,
            order.amount,
            order.price or 0.0,
            order.stop_loss_price,
        )
        if not approved:
            await sync_to_async(order.transition_to)(
                OrderStatus.REJECTED,
                reject_reason=reason,
            )
            await LiveTradingService._broadcast_order_update(order)
            return order

        # Submit to exchange
        service = ExchangeService(exchange_id=order.exchange_id)
        try:
            exchange = await service._get_exchange()
            params = {}
            if order.stop_loss_price:
                params["stopLoss"] = {"triggerPrice": order.stop_loss_price}

            ccxt_order = await exchange.create_order(
                symbol=order.symbol,
                type=order.order_type,
                side=order.side,
                amount=order.amount,
                price=order.price if order.order_type == "limit" else None,
                params=params,
            )

            exchange_order_id = ccxt_order.get("id", "")
            await sync_to_async(order.transition_to)(
                OrderStatus.SUBMITTED,
                exchange_order_id=exchange_order_id,
            )
        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            await sync_to_async(order.transition_to)(
                OrderStatus.ERROR,
                error_message=str(e)[:500],
            )
        finally:
            await service.close()

        await LiveTradingService._broadcast_order_update(order)
        return order

    @staticmethod
    async def sync_order(order: Order) -> Order:
        """Poll exchange for order status and update local state."""
        if not order.exchange_order_id:
            return order

        service = ExchangeService(exchange_id=order.exchange_id)
        try:
            exchange = await service._get_exchange()
            ccxt_order = await exchange.fetch_order(order.exchange_order_id, order.symbol)

            new_status = CCXT_STATUS_MAP.get(ccxt_order.get("status", ""))
            if not new_status or new_status == order.status:
                return order

            kwargs = {}
            filled = ccxt_order.get("filled", 0) or 0
            if filled > order.filled:
                kwargs["filled"] = filled

            avg_price = ccxt_order.get("average") or ccxt_order.get("price") or 0
            if avg_price:
                kwargs["avg_fill_price"] = avg_price

            fee_info = ccxt_order.get("fee") or {}
            if fee_info.get("cost"):
                kwargs["fee"] = fee_info["cost"]
                kwargs["fee_currency"] = fee_info.get("currency", "")

            # Handle partial fills -> record fill events
            is_fill = new_status in (OrderStatus.FILLED, OrderStatus.PARTIAL_FILL)
            if is_fill and filled > order.filled:
                fill_amount = filled - order.filled
                await sync_to_async(OrderFillEvent.objects.create)(
                    order=order,
                    fill_price=avg_price,
                    fill_amount=fill_amount,
                    fee=fee_info.get("cost", 0),
                    fee_currency=fee_info.get("currency", ""),
                )

            # If partially filled but ccxt says "open", use partial_fill
            if ccxt_order.get("status") == "open" and filled > 0 and filled < order.amount:
                new_status = OrderStatus.PARTIAL_FILL

            try:
                await sync_to_async(order.transition_to)(new_status, **kwargs)
                await LiveTradingService._broadcast_order_update(order)
            except ValueError:
                logger.warning(
                    f"Invalid transition for order {order.id}: {order.status} -> {new_status}",
                )

        except Exception as e:
            logger.error(f"Order sync failed for {order.id}: {e}")
        finally:
            await service.close()

        return order

    @staticmethod
    async def cancel_order(order: Order) -> Order:
        """Cancel an order on the exchange."""
        terminal = {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.ERROR,
        }
        if order.status in terminal:
            return order

        service = ExchangeService(exchange_id=order.exchange_id)
        try:
            if order.exchange_order_id:
                exchange = await service._get_exchange()
                await exchange.cancel_order(order.exchange_order_id, order.symbol)

            await sync_to_async(order.transition_to)(OrderStatus.CANCELLED)
            await LiveTradingService._broadcast_order_update(order)
        except Exception as e:
            logger.error(f"Order cancel failed for {order.id}: {e}")
            await sync_to_async(order.transition_to)(
                OrderStatus.ERROR,
                error_message=f"Cancel failed: {str(e)[:400]}",
            )
        finally:
            await service.close()

        return order

    @staticmethod
    async def cancel_all_open_orders(portfolio_id: int) -> int:
        """Cancel all open/submitted/partial live orders for a portfolio.

        Returns the number of orders cancelled.
        """
        live_statuses = [OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIAL_FILL]
        orders = await sync_to_async(list)(
            Order.objects.filter(
                portfolio_id=portfolio_id,
                mode=TradingMode.LIVE,
                status__in=live_statuses,
            ),
        )

        cancelled = 0
        for order in orders:
            try:
                await LiveTradingService.cancel_order(order)
                cancelled += 1
            except Exception as e:
                logger.error(f"Failed to cancel order {order.id}: {e}")

        return cancelled

    @staticmethod
    async def _broadcast_order_update(order: Order) -> None:
        """Push order update to system_events WebSocket group."""
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        await channel_layer.group_send(
            "system_events",
            {
                "type": "order_update",
                "data": {
                    "order_id": order.id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "status": order.status,
                    "mode": order.mode,
                    "filled": order.filled,
                    "amount": order.amount,
                    "avg_fill_price": order.avg_fill_price,
                },
            },
        )
