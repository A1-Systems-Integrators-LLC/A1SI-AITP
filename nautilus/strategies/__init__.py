"""NautilusTrader Strategy Registry
=================================
Maps strategy names to classes for dynamic lookup by the runner and backend.
"""

from nautilus.strategies.equity_mean_reversion import EquityMeanReversion
from nautilus.strategies.equity_momentum import EquityMomentum
from nautilus.strategies.forex_range import ForexRange
from nautilus.strategies.forex_trend import ForexTrend
from nautilus.strategies.mean_reversion import NautilusMeanReversion
from nautilus.strategies.trend_following import NautilusTrendFollowing
from nautilus.strategies.volatility_breakout import NautilusVolatilityBreakout

STRATEGY_REGISTRY: dict[str, type] = {
    "NautilusTrendFollowing": NautilusTrendFollowing,
    "NautilusMeanReversion": NautilusMeanReversion,
    "NautilusVolatilityBreakout": NautilusVolatilityBreakout,
    "EquityMomentum": EquityMomentum,
    "EquityMeanReversion": EquityMeanReversion,
    "ForexTrend": ForexTrend,
    "ForexRange": ForexRange,
}
