"""ForexPaperTradingService — signal-to-order service for forex paper trading.

Runs as a scheduled task every 15 minutes. Reads high-score MarketOpportunity
records for forex, creates paper orders via GenericPaperTradingService, and
manages exits based on time limits, score decay, and opposing signals.
"""

import logging
from datetime import timedelta
from typing import Any

from asgiref.sync import async_to_sync
from django.utils import timezone

logger = logging.getLogger("forex_paper_trading")

# Configuration
MIN_ENTRY_SCORE = 70
MAX_OPEN_POSITIONS = 3
POSITION_SIZE_USD = 100.0  # Fallback only — prefer dynamic sizing from RiskLimits
MAX_HOLD_HOURS = 24
EXIT_SCORE_THRESHOLD = 40


class ForexPaperTradingService:
    """Convert forex scanner signals into simulated paper trades."""

    def run_cycle(self) -> dict[str, Any]:
        """Main entry point — called by scheduler every 15 min."""
        entries = self._check_entries()
        exits = self._check_exits()
        return {
            "status": "completed",
            "entries_created": entries,
            "exits_created": exits,
        }

    def _check_entries(self) -> int:
        """Create paper buy orders from high-score forex opportunities."""
        from market.models import MarketOpportunity
        from trading.models import Order, OrderStatus, TradingMode

        now = timezone.now()
        # Count current open positions (net buys > sells per symbol)
        open_symbols = self._get_open_symbols()
        if len(open_symbols) >= MAX_OPEN_POSITIONS:
            logger.debug("Max forex positions (%d) reached, skipping entries", MAX_OPEN_POSITIONS)
            return 0

        # Find actionable opportunities
        opps = MarketOpportunity.objects.filter(
            asset_class="forex",
            score__gte=MIN_ENTRY_SCORE,
            acted_on=False,
            expires_at__gt=now,
        ).order_by("-score")

        entries = 0
        for opp in opps:
            if len(open_symbols) + entries >= MAX_OPEN_POSITIONS:
                break
            if opp.symbol in open_symbols:
                continue

            # Get current price for amount computation
            price = self._get_price(opp.symbol)
            if not price or price <= 0:
                logger.warning("No price for %s, skipping entry", opp.symbol)
                continue

            position_value = self._get_position_size_usd()
            amount = position_value / price
            direction = (
                opp.details.get("direction", "bullish")
                if isinstance(opp.details, dict)
                else "bullish"
            )
            side = "buy" if direction == "bullish" else "sell"

            order = Order.objects.create(
                symbol=opp.symbol,
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

            # Submit via GenericPaperTradingService
            try:
                from trading.services.generic_paper_trading import GenericPaperTradingService

                async_to_sync(GenericPaperTradingService.submit_order)(order)
            except Exception:
                logger.warning(
                    "Failed to submit forex paper order for %s", opp.symbol, exc_info=True,
                )

            opp.acted_on = True
            opp.save(update_fields=["acted_on"])
            entries += 1
            open_symbols.add(opp.symbol)
            logger.info("Forex paper entry: %s %s %s @ %.5f", side, amount, opp.symbol, price)

        return entries

    def _check_exits(self) -> int:
        """Exit forex paper positions on time limit, score decay, or opposing signal."""
        from market.models import MarketOpportunity
        from trading.models import Order, OrderStatus, TradingMode

        now = timezone.now()
        open_symbols = self._get_open_symbols()
        if not open_symbols:
            return 0

        exits = 0
        for symbol in list(open_symbols):
            # Get the latest buy order for entry time
            entry_order = (
                Order.objects.filter(
                    symbol=symbol,
                    asset_class="forex",
                    mode=TradingMode.PAPER,
                    side="buy",
                    status=OrderStatus.FILLED,
                )
                .order_by("-filled_at")
                .first()
            )
            if not entry_order:
                # Try sell side
                entry_order = (
                    Order.objects.filter(
                        symbol=symbol,
                        asset_class="forex",
                        mode=TradingMode.PAPER,
                        side="sell",
                        status=OrderStatus.FILLED,
                    )
                    .order_by("-filled_at")
                    .first()
                )
            if not entry_order:
                continue

            should_exit = False
            reason = ""

            # Time limit
            entry_time = entry_order.filled_at or entry_order.timestamp
            if entry_time and (now - entry_time) > timedelta(hours=MAX_HOLD_HOURS):
                should_exit = True
                reason = "time_limit"

            # Score decay — check latest opportunity for this symbol
            if not should_exit:
                latest_opp = (
                    MarketOpportunity.objects.filter(
                        symbol=symbol,
                        asset_class="forex",
                    )
                    .order_by("-detected_at")
                    .first()
                )
                if latest_opp and latest_opp.score < EXIT_SCORE_THRESHOLD:
                    should_exit = True
                    reason = "score_decay"

            # Opposing signal direction
            if not should_exit and entry_order:
                latest_opp = (
                    MarketOpportunity.objects.filter(
                        symbol=symbol,
                        asset_class="forex",
                    )
                    .order_by("-detected_at")
                    .first()
                )
                if latest_opp and isinstance(latest_opp.details, dict):
                    opp_direction = latest_opp.details.get("direction", "")
                    if (
                        (entry_order.side == "buy"
                        and opp_direction == "bearish")
                        or (entry_order.side == "sell"
                        and opp_direction == "bullish")
                    ):
                        should_exit = True
                        reason = "opposing_signal"

            if should_exit:
                exit_side = "sell" if entry_order.side == "buy" else "buy"
                price = self._get_price(symbol)
                if not price or price <= 0:
                    continue

                exit_order = Order.objects.create(
                    symbol=symbol,
                    side=exit_side,
                    order_type="market",
                    amount=entry_order.amount,
                    price=price,
                    mode=TradingMode.PAPER,
                    asset_class="forex",
                    exchange_id="yfinance",
                    status=OrderStatus.PENDING,
                    timestamp=now,
                )

                try:
                    from trading.services.generic_paper_trading import GenericPaperTradingService

                    async_to_sync(GenericPaperTradingService.submit_order)(exit_order)
                except Exception:
                    logger.warning("Failed to submit forex exit for %s", symbol, exc_info=True)

                exits += 1
                logger.info("Forex paper exit: %s %s (%s)", exit_side, symbol, reason)

        return exits

    def get_profit(self) -> dict[str, Any]:
        """Compute P&L from filled forex paper trades.

        Realized P&L from matched buy/sell pairs (weighted average cost).
        Unrealized P&L from open positions marked to current market prices.
        """
        from django.db.models import F, Sum

        from trading.models import Order, OrderStatus, TradingMode

        filled = Order.objects.filter(
            asset_class="forex",
            mode=TradingMode.PAPER,
            status=OrderStatus.FILLED,
        )

        buys = filled.filter(side="buy")
        sells = filled.filter(side="sell")

        buy_count = buys.count()
        sell_count = sells.count()
        closed_count = min(buy_count, sell_count)

        # Per-symbol realized + unrealized P&L
        symbols = set(filled.values_list("symbol", flat=True))
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        winning = 0
        losing = 0

        for sym in symbols:
            sym_buys = buys.filter(symbol=sym)
            sym_sells = sells.filter(symbol=sym)

            buy_val = float(
                sym_buys.aggregate(total=Sum(F("price") * F("amount")))["total"] or 0
            )
            sell_val = float(
                sym_sells.aggregate(total=Sum(F("price") * F("amount")))["total"] or 0
            )
            buy_qty = float(sym_buys.aggregate(total=Sum("amount"))["total"] or 0)
            sell_qty = float(sym_sells.aggregate(total=Sum("amount"))["total"] or 0)

            avg_buy = buy_val / buy_qty if buy_qty > 0 else 0
            avg_sell = sell_val / sell_qty if sell_qty > 0 else 0

            # Realized P&L from matched (closed) quantities
            matched = min(buy_qty, sell_qty)
            if matched > 0:
                sym_realized = matched * (avg_sell - avg_buy)
                realized_pnl += sym_realized
                if sym_realized > 0:
                    winning += 1
                elif sym_realized < 0:
                    losing += 1

            # Unrealized P&L from open positions at current price
            net_qty = buy_qty - sell_qty
            if abs(net_qty) > 1e-10:
                current_price = self._get_price(sym)
                if current_price and current_price > 0:
                    if net_qty > 0:  # long position
                        unrealized_pnl += (current_price - avg_buy) * net_qty
                    else:  # short position
                        unrealized_pnl += (avg_sell - current_price) * abs(net_qty)

        total_pnl = realized_pnl + unrealized_pnl

        # Percentage based on total invested
        buy_value = float(
            buys.aggregate(total=Sum(F("price") * F("amount")))["total"] or 0
        )
        profit_pct = (total_pnl / buy_value * 100) if buy_value else 0.0

        # Actual open position count from net buy/sell balance per symbol
        open_symbols = self._get_open_symbols()

        return {
            "profit_all_coin": round(total_pnl, 4),
            "profit_all_percent": round(profit_pct, 2),
            "trade_count": buy_count + sell_count,
            "closed_trade_count": closed_count,
            "open_trade_count": len(open_symbols),
            "winning_trades": winning,
            "losing_trades": losing,
            "realized_pnl": round(realized_pnl, 4),
            "unrealized_pnl": round(unrealized_pnl, 4),
        }

    def get_status(self) -> dict[str, Any]:
        """Return status dict matching PaperTradingStatus interface."""
        open_symbols = self._get_open_symbols()
        from trading.models import Order, OrderStatus, TradingMode

        total_trades = Order.objects.filter(
            asset_class="forex",
            mode=TradingMode.PAPER,
            status=OrderStatus.FILLED,
        ).count()

        return {
            "running": True,
            "strategy": "ForexSignals",
            "pid": None,
            "started_at": None,
            "uptime_seconds": 0,
            "exit_code": None,
            "asset_class": "forex",
            "engine": "signal_based",
            "open_positions": len(open_symbols),
            "total_trades": total_trades,
        }

    @staticmethod
    def _get_open_symbols() -> set[str]:
        """Return set of symbols with net open positions (buys > sells or sells > buys)."""
        from django.db.models import Count

        from trading.models import Order, OrderStatus, TradingMode

        filled_forex = Order.objects.filter(
            asset_class="forex",
            mode=TradingMode.PAPER,
            status=OrderStatus.FILLED,
        )

        buy_counts = dict(
            filled_forex.filter(side="buy")
            .values_list("symbol")
            .annotate(cnt=Count("id"))
            .values_list("symbol", "cnt"),
        )
        sell_counts = dict(
            filled_forex.filter(side="sell")
            .values_list("symbol")
            .annotate(cnt=Count("id"))
            .values_list("symbol", "cnt"),
        )

        open_syms = set()
        for symbol in set(buy_counts) | set(sell_counts):
            net = buy_counts.get(symbol, 0) - sell_counts.get(symbol, 0)
            if net != 0:
                open_syms.add(symbol)
        return open_syms

    @staticmethod
    def _get_position_size_usd() -> float:
        """Compute position size from portfolio equity and risk limits.

        Uses max_position_size_pct from RiskLimits applied to current equity
        from RiskState. Falls back to POSITION_SIZE_USD constant.
        """
        try:
            from portfolio.models import Portfolio
            from risk.models import RiskLimits, RiskState

            portfolio = Portfolio.objects.order_by("id").first()
            if not portfolio:
                return POSITION_SIZE_USD

            state = RiskState.objects.get(portfolio_id=portfolio.id)
            limits = RiskLimits.objects.get(portfolio_id=portfolio.id)
            equity = state.total_equity or 500.0
            max_pct = limits.max_position_size_pct or 0.20
            size = equity * max_pct
            logger.debug(
                "Forex position size: $%.2f (equity=$%.2f × max_pct=%.0f%%)",
                size, equity, max_pct * 100,
            )
            return size
        except Exception as e:
            logger.warning("Using fallback position size: %s", e)
            return POSITION_SIZE_USD

    @staticmethod
    def _get_price(symbol: str) -> float:
        """Fetch current price for a forex symbol."""
        try:
            from market.services.data_router import DataServiceRouter

            router = DataServiceRouter()
            ticker = async_to_sync(router.fetch_ticker)(symbol, "forex")
            return ticker.get("last") or ticker.get("close") or ticker.get("price", 0)
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", symbol, e)
            return 0.0
