"""Generic Paper Trading Service — asset-class-agnostic paper trading engine.

Simulates fills using yfinance live prices (equities/forex) or CCXT (crypto).
Enforces market hours for equities. Used for equity/forex paper trading while
the existing PaperTradingService stays for Freqtrade crypto paper trading.
"""

import logging
from typing import Any

from asgiref.sync import sync_to_async

from trading.models import Order, OrderFillEvent, OrderStatus

logger = logging.getLogger("generic_paper_trading")


class GenericPaperTradingService:
    """Paper trading engine for equities and forex.

    Simulates market order fills at current price fetched from yfinance
    or CCXT depending on asset class. Limit orders are filled when
    the price crosses the limit price.
    """

    @staticmethod
    async def submit_order(order: Order) -> Order:
        """Submit a paper order and simulate an immediate fill for market orders."""
        from market.services.data_router import DataServiceRouter

        asset_class = getattr(order, "asset_class", "crypto")

        # Market hours check for equities
        if asset_class == "equity":
            try:
                from common.market_hours.sessions import MarketHoursService

                if not MarketHoursService.is_market_open("equity"):
                    await sync_to_async(order.transition_to)(
                        OrderStatus.REJECTED,
                        reject_reason="US equity market is closed",
                    )
                    return order
            except ImportError:
                pass

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
            return order

        # Get current price for fill simulation
        router = DataServiceRouter()
        try:
            ticker = await router.fetch_ticker(order.symbol, asset_class)
            fill_price = ticker.get("last") or ticker.get("close") or ticker.get("price", 0)
        except Exception as e:
            logger.error(f"Failed to fetch price for {order.symbol}: {e}")
            await sync_to_async(order.transition_to)(
                OrderStatus.ERROR,
                error_message=f"Price fetch failed: {str(e)[:400]}",
            )
            return order

        if not fill_price or fill_price <= 0:
            await sync_to_async(order.transition_to)(
                OrderStatus.ERROR,
                error_message=f"Invalid price for {order.symbol}",
            )
            return order

        # For limit orders, check if fill is possible
        if order.order_type == "limit" and order.price:
            if order.side == "buy" and fill_price > order.price:
                # Price above limit — submit but don't fill yet
                await sync_to_async(order.transition_to)(OrderStatus.SUBMITTED)
                return order
            if order.side == "sell" and fill_price < order.price:
                await sync_to_async(order.transition_to)(OrderStatus.SUBMITTED)
                return order

        # Simulate fill
        fee_rates = {"crypto": 0.001, "equity": 0.0, "forex": 0.0001}
        fee_rate = fee_rates.get(asset_class, 0.001)
        fee = order.amount * fill_price * fee_rate

        await sync_to_async(order.transition_to)(OrderStatus.SUBMITTED)

        await sync_to_async(OrderFillEvent.objects.create)(
            order=order,
            fill_price=fill_price,
            fill_amount=order.amount,
            fee=fee,
            fee_currency="USD" if asset_class in ("equity", "forex") else "USDT",
        )

        await sync_to_async(order.transition_to)(
            OrderStatus.FILLED,
            filled=order.amount,
            avg_fill_price=fill_price,
            fee=fee,
            fee_currency="USD" if asset_class in ("equity", "forex") else "USDT",
        )

        logger.info(
            f"Paper fill: {order.side} {order.amount} {order.symbol} "
            f"@ {fill_price} (fee={fee:.4f}, {asset_class})",
        )
        return order

    @staticmethod
    async def get_status() -> dict[str, Any]:
        """Return paper trading engine status."""
        return {
            "engine": "generic",
            "status": "ready",
            "supported_asset_classes": ["equity", "forex"],
        }
