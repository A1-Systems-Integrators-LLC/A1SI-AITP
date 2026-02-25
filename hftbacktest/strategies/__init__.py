"""
HFT Strategy Registry
======================
Maps strategy names to classes for dynamic lookup by the runner and backend.
"""

from hftbacktest.strategies.grid_trader import HFTGridTrader
from hftbacktest.strategies.market_maker import HFTMarketMaker
from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper
from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

STRATEGY_REGISTRY: dict[str, type] = {
    "MarketMaker": HFTMarketMaker,
    "MomentumScalper": HFTMomentumScalper,
    "GridTrader": HFTGridTrader,
    "MeanReversionScalper": HFTMeanReversionScalper,
}
