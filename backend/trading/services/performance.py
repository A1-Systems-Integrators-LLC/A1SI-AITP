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
        """Compute realized P&L from matched buy/sell order pairs.

        Uses weighted average cost method.  Only matched (closed) quantities
        contribute to realized P&L — unmatched quantities are tracked as open
        positions so callers can compute mark-to-market separately.
        """
        buys: dict[str, list] = defaultdict(list)
        sells: dict[str, list] = defaultdict(list)

        for order in orders:
            price = order.avg_fill_price or order.price
            if not price:
                logger.warning("Skipping order %s with zero/null price", order.id)
                continue
            entry = {
                "amount": float(order.filled or order.amount),
                "price": float(price),
                "asset_class": getattr(order, "asset_class", "crypto"),
            }
            if order.side == "buy":
                buys[order.symbol].append(entry)
            else:
                sells[order.symbol].append(entry)

        realized_pnl: dict[str, float] = {}
        open_positions: dict[str, dict] = {}

        for symbol in set(list(buys.keys()) + list(sells.keys())):
            buy_entries = buys.get(symbol, [])
            sell_entries = sells.get(symbol, [])

            total_buy_qty = sum(b["amount"] for b in buy_entries)
            total_sell_qty = sum(s["amount"] for s in sell_entries)
            total_buy_cost = sum(b["amount"] * b["price"] for b in buy_entries)
            total_sell_revenue = sum(s["amount"] * s["price"] for s in sell_entries)

            avg_buy = total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0
            avg_sell = total_sell_revenue / total_sell_qty if total_sell_qty > 0 else 0

            # Realized P&L: only from matched (closed) quantity
            matched_qty = min(total_buy_qty, total_sell_qty)
            if matched_qty > 0:
                realized_pnl[symbol] = matched_qty * (avg_sell - avg_buy)

            # Track unmatched (open) positions
            net_qty = total_buy_qty - total_sell_qty
            if abs(net_qty) > 1e-10:
                ac = (
                    buy_entries[0]["asset_class"]
                    if buy_entries
                    else sell_entries[0]["asset_class"]
                )
                open_positions[symbol] = {
                    "qty": abs(net_qty),
                    "side": "long" if net_qty > 0 else "short",
                    "avg_price": avg_buy if net_qty > 0 else avg_sell,
                    "asset_class": ac,
                }

        total_trades = len(orders)
        total_pnl = sum(realized_pnl.values()) if realized_pnl else 0.0
        wins = {s: pnl for s, pnl in realized_pnl.items() if pnl > 0}
        losses = {s: pnl for s, pnl in realized_pnl.items() if pnl < 0}

        win_count = len(wins)
        loss_count = len(losses)
        decided = win_count + loss_count
        win_rate = (win_count / decided) * 100 if decided > 0 else 0.0

        win_values = list(wins.values())
        loss_values = [abs(v) for v in losses.values()]
        avg_win = sum(win_values) / len(win_values) if win_values else 0.0
        avg_loss = sum(loss_values) / len(loss_values) if loss_values else 0.0

        total_loss = sum(loss_values)
        if total_loss > 0:
            profit_factor = sum(win_values) / total_loss
        else:
            profit_factor = float("inf") if win_values else 0.0

        all_pnls = list(realized_pnl.values())
        best_trade = max(all_pnls) if all_pnls else 0.0
        worst_trade = min(all_pnls) if all_pnls else 0.0

        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "unrealized_pnl": 0.0,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else None,
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "open_positions": open_positions,
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
