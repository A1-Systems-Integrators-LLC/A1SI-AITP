"""
HFTMeanReversionScalper — VWAP reversion
==========================================
Tracks rolling VWAP over recent ticks and trades mean-reversion
when price deviates beyond a threshold.

Logic:
    - Maintain rolling VWAP over ``lookback`` ticks
    - Buy when price < VWAP * (1 - ``deviation_threshold``)
    - Sell when price > VWAP * (1 + ``deviation_threshold``)
    - Exit: price crosses back through VWAP OR ``max_hold_ticks`` exceeded

Parameters:
    - lookback: number of ticks for rolling VWAP (default 50)
    - deviation_threshold: min deviation from VWAP to trigger entry (10 bps, 0.001)
    - order_size: size per order (default 0.01)
    - max_hold_ticks: forced exit after N ticks (default 40)
    - drawdown_halt_pct: halt at this drawdown level (default 0.04)
"""

from collections import deque
from typing import Optional

from hftbacktest.strategies.base import HFTBaseStrategy


class HFTMeanReversionScalper(HFTBaseStrategy):

    name = "MeanReversionScalper"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.lookback: int = self.config.get("lookback", 50)
        self.deviation_threshold: float = self.config.get("deviation_threshold", 0.001)
        self.order_size: float = self.config.get("order_size", 0.01)
        self.max_hold_ticks: int = self.config.get("max_hold_ticks", 40)
        self.drawdown_halt_pct: float = self.config.get("drawdown_halt_pct", 0.04)

        # Rolling VWAP state
        self._price_volume_window: deque[tuple[float, float]] = deque(maxlen=self.lookback)
        self._vwap: float = 0.0
        self._hold_counter: int = 0

    def _update_vwap(self, price: float, volume: float) -> None:
        """Update rolling VWAP with new tick."""
        self._price_volume_window.append((price, volume))
        total_pv = sum(p * v for p, v in self._price_volume_window)
        total_v = sum(v for _, v in self._price_volume_window)
        self._vwap = total_pv / total_v if total_v > 0 else price

    def on_tick(self, tick: dict) -> None:
        if self.check_drawdown_halt(self.drawdown_halt_pct):
            return

        price = tick["price"]
        volume = tick["volume"]

        self._update_vwap(price, volume)

        # Need enough data before trading
        if len(self._price_volume_window) < self.lookback:
            return

        # Track hold duration
        if self.position != 0:
            self._hold_counter += 1

        # Forced exit on max hold
        if self.position != 0 and self._hold_counter >= self.max_hold_ticks:
            side = "sell" if self.position > 0 else "buy"
            self.submit_order(side, price, abs(self.position), tick)
            self._hold_counter = 0
            return

        # VWAP crossover exit
        if self.position > 0 and price >= self._vwap:
            # Long position — price reverted to VWAP, exit
            self.submit_order("sell", price, self.position, tick)
            self._hold_counter = 0
            return
        elif self.position < 0 and price <= self._vwap:
            # Short position — price reverted to VWAP, exit
            self.submit_order("buy", price, abs(self.position), tick)
            self._hold_counter = 0
            return

        # Entry logic (only if flat)
        if self.position == 0:
            lower_band = self._vwap * (1 - self.deviation_threshold)
            upper_band = self._vwap * (1 + self.deviation_threshold)
            if price < lower_band:
                self.submit_order("buy", price, self.order_size, tick)
                self._hold_counter = 0
            elif price > upper_band:
                self.submit_order("sell", price, self.order_size, tick)
                self._hold_counter = 0
