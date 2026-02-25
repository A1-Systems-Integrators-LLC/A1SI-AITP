"""
HFTGridTrader — Fixed-level grid trading
==========================================
Places buy and sell orders at fixed grid levels around a reference price.

Logic:
    - Compute grid levels from initial price: ``reference +/- k * grid_spacing``
      for k = 1..``num_levels``
    - Buy at unfilled lower levels, sell at unfilled upper levels
    - Reset grid when all levels are filled or price escapes the grid range

Parameters:
    - grid_spacing: distance between grid levels as fraction (default 0.002 = 20 bps)
    - num_levels: number of grid levels on each side (default 3)
    - order_size: size per grid order (default 0.01)
    - max_position: max absolute position (default 1.0)
    - drawdown_halt_pct: halt at this drawdown level (default 0.05)
"""

from typing import Optional

from hftbacktest.strategies.base import HFTBaseStrategy


class HFTGridTrader(HFTBaseStrategy):

    name = "GridTrader"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.grid_spacing: float = self.config.get("grid_spacing", 0.002)
        self.num_levels: int = self.config.get("num_levels", 3)
        self.order_size: float = self.config.get("order_size", 0.01)
        self.drawdown_halt_pct: float = self.config.get("drawdown_halt_pct", 0.05)

        # Grid state
        self._reference_price: Optional[float] = None
        self._buy_levels_filled: set[int] = set()   # filled level indices (1..num_levels)
        self._sell_levels_filled: set[int] = set()

    def _reset_grid(self, reference: float) -> None:
        """Reset grid around a new reference price."""
        self._reference_price = reference
        self._buy_levels_filled = set()
        self._sell_levels_filled = set()

    def _grid_level_price(self, level: int, side: str) -> float:
        """Compute price for a grid level. Negative offset for buy, positive for sell."""
        assert self._reference_price is not None
        if side == "buy":
            return self._reference_price * (1 - level * self.grid_spacing)
        return self._reference_price * (1 + level * self.grid_spacing)

    def on_tick(self, tick: dict) -> None:
        if self.check_drawdown_halt(self.drawdown_halt_pct):
            return

        price = tick["price"]

        # Initialize grid on first tick
        if self._reference_price is None:
            self._reset_grid(price)
            return

        # Check if price has escaped the grid range — reset
        upper_bound = self._reference_price * (1 + (self.num_levels + 1) * self.grid_spacing)
        lower_bound = self._reference_price * (1 - (self.num_levels + 1) * self.grid_spacing)
        if price > upper_bound or price < lower_bound:
            self._reset_grid(price)
            return

        # Check if all levels filled — reset
        if (
            len(self._buy_levels_filled) >= self.num_levels
            and len(self._sell_levels_filled) >= self.num_levels
        ):
            self._reset_grid(price)
            return

        # Check buy levels (price touching or crossing below a grid buy level)
        for k in range(1, self.num_levels + 1):
            if k not in self._buy_levels_filled:
                level_price = self._grid_level_price(k, "buy")
                if price <= level_price:
                    fill = self.submit_order("buy", price, self.order_size, tick)
                    if fill is not None:
                        self._buy_levels_filled.add(k)

        # Check sell levels (price touching or crossing above a grid sell level)
        for k in range(1, self.num_levels + 1):
            if k not in self._sell_levels_filled:
                level_price = self._grid_level_price(k, "sell")
                if price >= level_price:
                    fill = self.submit_order("sell", price, self.order_size, tick)
                    if fill is not None:
                        self._sell_levels_filled.add(k)
