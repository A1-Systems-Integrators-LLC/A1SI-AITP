"""HFTMarketMaker — inventory-aware market making strategy
========================================================
Quotes both sides of the spread with inventory-aware skew.

Logic:
    - Maintain bid/ask quotes around mid price
    - Skew quotes based on current inventory (penalize adding to large positions)
    - Hard position limits
    - Drawdown halt

Parameters
----------
    - half_spread: base half-spread (e.g. 0.001 = 10 bps)
    - skew_factor: how much to skew per unit of inventory
    - order_size: size per quote
    - max_position: max absolute position
    - drawdown_halt_pct: halt at this drawdown level

"""


from hftbacktest.strategies.base import HFTBaseStrategy


class HFTMarketMaker(HFTBaseStrategy):

    name = "MarketMaker"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.half_spread: float = self.config.get("half_spread", 0.001)
        self.skew_factor: float = self.config.get("skew_factor", 0.0005)
        self.order_size: float = self.config.get("order_size", 0.01)
        self.drawdown_halt_pct: float = self.config.get("drawdown_halt_pct", 0.05)
        self._tick_count: int = 0
        self._quote_interval: int = self.config.get("quote_interval", 4)

    def on_tick(self, tick: dict) -> None:
        self._tick_count += 1

        # Check drawdown before quoting
        if self.check_drawdown_halt(self.drawdown_halt_pct):
            return

        # Only requote every N ticks to reduce fill churn
        if self._tick_count % self._quote_interval != 0:
            return

        mid_price = tick["price"]

        # Inventory skew: shift quotes away from the side we're overweight
        inventory_skew = self.position * self.skew_factor

        bid_price = mid_price * (1 - self.half_spread) - inventory_skew
        ask_price = mid_price * (1 + self.half_spread) - inventory_skew

        # Submit passive quotes if within position limits
        # Buy side (bid)
        if (
            self.position < self.max_position
            and tick["price"] <= bid_price
            and tick["side"] == "sell"
        ):
            self.submit_order("buy", bid_price, self.order_size, tick)

        # Sell side (ask)
        if (
            self.position > -self.max_position
            and tick["price"] >= ask_price
            and tick["side"] == "buy"
        ):
            self.submit_order("sell", ask_price, self.order_size, tick)
