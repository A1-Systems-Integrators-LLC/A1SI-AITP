"""Portfolio analytics — summary, P&L, allocation calculations."""

import logging

from asgiref.sync import async_to_sync

from portfolio.models import Holding, Portfolio

logger = logging.getLogger(__name__)


class PortfolioAnalyticsService:
    @staticmethod
    def get_portfolio_summary(portfolio_id: int) -> dict:
        """Compute portfolio summary: total value, cost, P&L, holding count."""
        portfolio = Portfolio.objects.prefetch_related("holdings").get(id=portfolio_id)
        holdings = list(portfolio.holdings.all())

        if not holdings:
            return {
                "total_value": 0.0,
                "total_cost": 0.0,
                "unrealized_pnl": 0.0,
                "pnl_pct": 0.0,
                "holding_count": 0,
                "currency": "USD",
            }

        prices = _fetch_prices(holdings, portfolio.exchange_id)

        total_value = 0.0
        total_cost = 0.0
        for h in holdings:
            cost = h.amount * h.avg_buy_price
            total_cost += cost
            price = prices.get(h.symbol)
            if price is not None:
                total_value += h.amount * price
            else:
                total_value += cost  # fallback to cost basis

        unrealized_pnl = total_value - total_cost
        pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

        return {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "holding_count": len(holdings),
            "currency": "USD",
        }

    @staticmethod
    def get_allocation(portfolio_id: int) -> list[dict]:
        """Per-holding allocation with weights, P&L, current prices."""
        portfolio = Portfolio.objects.prefetch_related("holdings").get(id=portfolio_id)
        holdings = list(portfolio.holdings.all())

        if not holdings:
            return []

        prices = _fetch_prices(holdings, portfolio.exchange_id)

        items = []
        total_value = 0.0
        for h in holdings:
            price = prices.get(h.symbol)
            price_stale = price is None
            current_price = price if price is not None else h.avg_buy_price
            market_value = h.amount * current_price
            total_value += market_value
            items.append({
                "symbol": h.symbol,
                "amount": h.amount,
                "current_price": round(current_price, 8),
                "market_value": round(market_value, 2),
                "cost_basis": round(h.amount * h.avg_buy_price, 2),
                "pnl": round(market_value - h.amount * h.avg_buy_price, 2),
                "pnl_pct": round(
                    ((current_price - h.avg_buy_price) / h.avg_buy_price * 100)
                    if h.avg_buy_price > 0 else 0.0,
                    2,
                ),
                "weight": 0.0,
                "price_stale": price_stale,
            })

        # Compute weights
        for item in items:
            item["weight"] = round(
                (item["market_value"] / total_value * 100) if total_value > 0 else 0.0,
                2,
            )

        return items


def _fetch_prices(holdings: list[Holding], exchange_id: str) -> dict[str, float]:
    """Fetch current prices for holdings. Returns {symbol: price}."""
    prices: dict[str, float] = {}

    try:
        from market.services.exchange import ExchangeService

        service = ExchangeService(exchange_id=exchange_id)

        async def _fetch_all():
            results = {}
            for h in holdings:
                try:
                    ticker = await service.fetch_ticker(h.symbol)
                    if ticker and ticker.get("price"):
                        results[h.symbol] = ticker["price"]
                except Exception:
                    logger.debug("Failed to fetch price for %s", h.symbol)
            await service.close()
            return results

        prices = async_to_sync(_fetch_all)()
    except Exception:
        logger.warning("Price fetch failed, using cost basis", exc_info=True)

    return prices
