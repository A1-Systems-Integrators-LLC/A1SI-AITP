"""
HFT Strategy Base Class
========================
Shared functionality for all hftbacktest strategies:
- Inventory tracking (position, avg cost)
- Order management (submit/cancel helpers)
- PnL + drawdown tracking
- Tick-by-tick processing loop
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import pandas as pd

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


class HFTBaseStrategy:
    """Base class for HFT strategies.

    Strategies override ``on_tick()`` which receives each tick as a dict:
    ``{timestamp, price, volume, side}`` where side is 'buy' or 'sell'.

    The base class manages inventory, fills, and PnL.
    """

    name: str = "base"
    max_position: float = 1.0  # Max absolute position size
    initial_balance: float = 10000.0

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.initial_balance = self.config.get("initial_balance", 10000.0)
        self.max_position = self.config.get("max_position", self.max_position)
        self.fee_rate: float = self.config.get("fee_rate", 0.0002)  # 0.02% maker fee

        # State
        self.position: float = 0.0  # Signed position (+ long, - short)
        self.avg_cost: float = 0.0
        self.gross_pnl: float = 0.0
        self.total_fees: float = 0.0
        self.balance: float = self.initial_balance
        self.peak_balance: float = self.initial_balance
        self.fills: list[dict] = []
        self.halted: bool = False

        # Latency simulation
        self.latency_ns: int = self.config.get("latency_ns", 1_000_000)  # 1ms default

    def run(self, ticks: np.ndarray) -> list[dict]:
        """Process all ticks through the strategy. Returns list of fills."""
        for i in range(len(ticks)):
            if self.halted:
                break
            tick = {
                "timestamp": ticks[i, 0],
                "price": ticks[i, 1],
                "volume": ticks[i, 2],
                "side": "buy" if ticks[i, 3] > 0 else "sell",
            }
            self.on_tick(tick)
        return self.fills

    def on_tick(self, tick: dict) -> None:
        """Override in subclass: process a single tick."""
        raise NotImplementedError

    def submit_order(self, side: str, price: float, size: float, tick: dict) -> Optional[dict]:
        """Submit a simulated order. Returns fill dict or None if rejected."""
        if self.halted:
            return None

        # Position limit check
        new_position = self.position + (size if side == "buy" else -size)
        if abs(new_position) > self.max_position:
            return None

        # Simulate fill at the given price
        fee = price * size * self.fee_rate
        fill = {
            "timestamp": tick["timestamp"],
            "side": side,
            "price": price,
            "size": size,
            "fee": fee,
            "position_after": new_position,
        }

        # Deduct fee from balance and accumulate
        self.balance -= fee
        self.total_fees += fee

        # Update position and PnL
        if side == "buy":
            if self.position < 0:
                # Closing short
                close_size = min(size, abs(self.position))
                pnl = close_size * (self.avg_cost - price)
                self.gross_pnl += pnl
                self.balance += pnl
                fill["pnl"] = pnl
            else:
                fill["pnl"] = 0.0

            # Update average cost
            if new_position > 0:
                if self.position > 0:
                    total_cost = self.avg_cost * self.position + price * size
                    self.avg_cost = total_cost / new_position
                else:
                    self.avg_cost = price
        else:  # sell
            if self.position > 0:
                # Closing long
                close_size = min(size, self.position)
                pnl = close_size * (price - self.avg_cost)
                self.gross_pnl += pnl
                self.balance += pnl
                fill["pnl"] = pnl
            else:
                fill["pnl"] = 0.0

            # Update average cost
            if new_position < 0:
                if self.position < 0:
                    total_cost = self.avg_cost * abs(self.position) + price * size
                    self.avg_cost = total_cost / abs(new_position)
                else:
                    self.avg_cost = price

        self.position = new_position

        # Track peak balance for drawdown
        self.peak_balance = max(self.peak_balance, self.balance)

        self.fills.append(fill)
        return fill

    def check_drawdown_halt(self, max_drawdown_pct: float = 0.05) -> bool:
        """Halt trading if drawdown exceeds threshold."""
        if self.peak_balance > 0:
            drawdown = (self.peak_balance - self.balance) / self.peak_balance
            if drawdown >= max_drawdown_pct:
                logger.warning(f"Drawdown halt: {drawdown:.2%} >= {max_drawdown_pct:.2%}")
                self.halted = True
                return True
        return False

    def get_trades_df(self) -> pd.DataFrame:
        """Convert fills to round-trip trades using FIFO position tracking.

        Handles consecutive same-side fills (accumulation) and partial closes
        correctly for market-maker workloads.
        """
        if not self.fills:
            return pd.DataFrame()

        trades = []
        # FIFO queue of open entries: [(timestamp, price, remaining_size, side)]
        open_entries: list[list] = []

        for fill in self.fills:
            fill_side = fill["side"]
            remaining = fill["size"]

            # Determine if this fill closes existing entries
            if open_entries and open_entries[0][3] != fill_side:
                # Opposite side — close FIFO entries
                while remaining > 0 and open_entries:
                    entry = open_entries[0]
                    close_size = min(remaining, entry[2])

                    if entry[3] == "buy":
                        pnl = (fill["price"] - entry[1]) * close_size
                        pnl_pct = (fill["price"] / entry[1]) - 1
                    else:
                        pnl = (entry[1] - fill["price"]) * close_size
                        pnl_pct = (entry[1] / fill["price"]) - 1

                    entry_fee = entry[1] * close_size * self.fee_rate
                    exit_fee = fill["price"] * close_size * self.fee_rate
                    total_fee = entry_fee + exit_fee

                    trades.append({
                        "entry_time": pd.Timestamp(entry[0], unit="ns", tz="UTC"),
                        "exit_time": pd.Timestamp(fill["timestamp"], unit="ns", tz="UTC"),
                        "side": entry[3],
                        "entry_price": entry[1],
                        "exit_price": fill["price"],
                        "size": close_size,
                        "pnl": pnl - total_fee,
                        "pnl_pct": pnl_pct - (2 * self.fee_rate),
                        "fee": total_fee,
                    })

                    entry[2] -= close_size
                    remaining -= close_size
                    if entry[2] <= 1e-12:
                        open_entries.pop(0)

            # Any remaining size becomes a new open entry
            if remaining > 1e-12:
                open_entries.append([fill["timestamp"], fill["price"], remaining, fill_side])

        if not trades:
            return pd.DataFrame()
        return pd.DataFrame(trades)
