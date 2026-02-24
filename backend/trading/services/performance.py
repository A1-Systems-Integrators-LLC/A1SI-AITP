"""Trading performance analytics service."""

import logging
from collections import defaultdict

from django.db.models import QuerySet

from trading.models import Order, OrderStatus

logger = logging.getLogger(__name__)


class TradingPerformanceService:
    @staticmethod
    def _base_qs(
        portfolio_id: int,
        mode: str | None = None,
        asset_class: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> QuerySet:
        qs = Order.objects.filter(portfolio_id=portfolio_id, status=OrderStatus.FILLED)
        if mode:
            qs = qs.filter(mode=mode)
        if asset_class:
            qs = qs.filter(asset_class=asset_class)
        if date_from:
            qs = qs.filter(timestamp__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__lte=date_to)
        return qs

    @staticmethod
    def _compute_metrics(orders: list[Order]) -> dict:
        """Compute P&L per symbol from buy/sell order pairs."""
        buys: dict[str, list] = defaultdict(list)
        sells: dict[str, list] = defaultdict(list)

        for order in orders:
            price = order.avg_fill_price if order.avg_fill_price else order.price
            if not price:
                logger.warning("Skipping order %s with zero/null price", order.id)
                continue
            entry = {"amount": order.filled or order.amount, "price": price}
            if order.side == "buy":
                buys[order.symbol].append(entry)
            else:
                sells[order.symbol].append(entry)

        symbol_pnl: dict[str, float] = {}
        for symbol in set(list(buys.keys()) + list(sells.keys())):
            buy_cost = sum(b["amount"] * b["price"] for b in buys.get(symbol, []))
            sell_revenue = sum(s["amount"] * s["price"] for s in sells.get(symbol, []))
            symbol_pnl[symbol] = sell_revenue - buy_cost

        total_trades = len(orders)
        wins = {s: pnl for s, pnl in symbol_pnl.items() if pnl > 0}
        losses = {s: pnl for s, pnl in symbol_pnl.items() if pnl <= 0}
        total_pnl = sum(symbol_pnl.values())

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / max(len(symbol_pnl), 1)) * 100

        win_values = list(wins.values())
        loss_values = [abs(v) for v in losses.values()]
        avg_win = sum(win_values) / len(win_values) if win_values else 0.0
        avg_loss = sum(loss_values) / len(loss_values) if loss_values else 0.0

        total_loss = sum(loss_values)
        if total_loss > 0:
            profit_factor = sum(win_values) / total_loss
        else:
            profit_factor = float("inf") if win_values else 0.0

        best_trade = max(symbol_pnl.values()) if symbol_pnl else 0.0
        worst_trade = min(symbol_pnl.values()) if symbol_pnl else 0.0

        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else None,
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
        }

    @staticmethod
    def get_summary(
        portfolio_id: int,
        mode: str | None = None,
        asset_class: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        qs = TradingPerformanceService._base_qs(
            portfolio_id, mode, asset_class, date_from, date_to,
        )
        orders = list(qs)
        return TradingPerformanceService._compute_metrics(orders)

    @staticmethod
    def get_by_symbol(
        portfolio_id: int,
        mode: str | None = None,
        asset_class: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        qs = TradingPerformanceService._base_qs(
            portfolio_id, mode, asset_class, date_from, date_to,
        )
        orders = list(qs)

        # Group orders by symbol
        by_symbol: dict[str, list] = defaultdict(list)
        for order in orders:
            by_symbol[order.symbol].append(order)

        results = []
        for symbol, sym_orders in sorted(by_symbol.items()):
            metrics = TradingPerformanceService._compute_metrics(sym_orders)
            metrics["symbol"] = symbol
            results.append(metrics)
        return results
