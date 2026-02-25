"""
HFTMomentumScalper — Tick-level momentum detection
====================================================
Tracks EMA of price deltas over recent N ticks and enters when
momentum exceeds a configurable threshold.

Logic:
    - Compute price delta (current - previous tick price)
    - Maintain EMA of deltas over ``lookback`` ticks
    - Buy when momentum > ``entry_threshold`` (positive momentum)
    - Sell when momentum < -``entry_threshold`` (negative momentum)
    - Exit: opposite signal OR ``max_hold_ticks`` exceeded

Parameters:
    - lookback: EMA lookback period for momentum (default 20)
    - entry_threshold: min momentum to trigger entry (5 bps/tick, 0.0005)
    - exit_threshold: momentum magnitude to trigger exit (2 bps, 0.0002)
    - order_size: size per order (default 0.01)
    - max_hold_ticks: forced exit after N ticks (default 50)
    - drawdown_halt_pct: halt at this drawdown level (default 0.03)
"""

from typing import Optional

from hftbacktest.strategies.base import HFTBaseStrategy


class HFTMomentumScalper(HFTBaseStrategy):

    name = "MomentumScalper"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.lookback: int = self.config.get("lookback", 20)
        self.entry_threshold: float = self.config.get("entry_threshold", 0.0005)
        self.exit_threshold: float = self.config.get("exit_threshold", 0.0002)
        self.order_size: float = self.config.get("order_size", 0.01)
        self.max_hold_ticks: int = self.config.get("max_hold_ticks", 50)
        self.drawdown_halt_pct: float = self.config.get("drawdown_halt_pct", 0.03)

        # Internal state
        self._prev_price: Optional[float] = None
        self._ema_momentum: float = 0.0
        self._alpha: float = 2.0 / (self.lookback + 1)
        self._hold_counter: int = 0
        self._tick_count: int = 0

    def on_tick(self, tick: dict) -> None:
        if self.check_drawdown_halt(self.drawdown_halt_pct):
            return

        price = tick["price"]
        self._tick_count += 1

        # Need at least one previous price to compute delta
        if self._prev_price is None:
            self._prev_price = price
            return

        # Compute price delta and update EMA momentum
        delta = price - self._prev_price
        self._prev_price = price
        self._ema_momentum = self._alpha * delta + (1 - self._alpha) * self._ema_momentum

        # Track hold duration
        if self.position != 0:
            self._hold_counter += 1

        # Forced exit on max hold
        if self.position != 0 and self._hold_counter >= self.max_hold_ticks:
            side = "sell" if self.position > 0 else "buy"
            self.submit_order(side, price, abs(self.position), tick)
            self._hold_counter = 0
            return

        # Entry / exit logic
        if self.position == 0:
            # No position — look for entry
            if self._ema_momentum > self.entry_threshold:
                self.submit_order("buy", price, self.order_size, tick)
                self._hold_counter = 0
            elif self._ema_momentum < -self.entry_threshold:
                self.submit_order("sell", price, self.order_size, tick)
                self._hold_counter = 0
        elif self.position > 0:
            # Long — exit on negative momentum
            if self._ema_momentum < -self.exit_threshold:
                self.submit_order("sell", price, self.position, tick)
                self._hold_counter = 0
        else:
            # Short — exit on positive momentum
            if self._ema_momentum > self.exit_threshold:
                self.submit_order("buy", price, abs(self.position), tick)
                self._hold_counter = 0
