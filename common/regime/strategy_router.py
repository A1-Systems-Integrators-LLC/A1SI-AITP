"""Regime-Adaptive Strategy Router
================================
Maps detected market regimes to optimal trading strategies with
weighted allocations and position-sizing adjustments.

Routes between:
    - CryptoInvestorV1 (trend-following)
    - BollingerMeanReversion (range-bound)
    - VolatilityBreakout (volatility expansion)
"""

import logging
from dataclasses import dataclass

from common.regime.regime_detector import Regime, RegimeState

logger = logging.getLogger("strategy_router")


@dataclass
class StrategyWeight:
    """Weight for a single strategy in the routing decision."""

    strategy_name: str
    weight: float  # 0-1, weights across strategies sum to 1
    position_size_factor: float  # Multiplier on base position size


@dataclass
class RoutingDecision:
    """Complete routing decision for a given regime."""

    regime: Regime
    confidence: float
    primary_strategy: str
    weights: list[StrategyWeight]
    position_size_modifier: float  # Overall position sizing modifier (0-1)
    reasoning: str
    sentiment_modifier: float | None = None  # Sentiment-based position adjustment


# Strategy name constants — crypto
CIV1 = "CryptoInvestorV1"
BMR = "BollingerMeanReversion"
VB = "VolatilityBreakout"

# Strategy name constants — equity
EQ_MOM = "EquityMomentum"
EQ_MR = "EquityMeanReversion"

# Strategy name constants — forex
FX_TREND = "ForexTrend"
FX_RANGE = "ForexRange"

# Default regime → strategy mappings
DEFAULT_ROUTING: dict[Regime, dict] = {
    Regime.STRONG_TREND_UP: {
        "primary": CIV1,
        "weights": [StrategyWeight(CIV1, 1.0, 1.0)],
        "position_modifier": 1.0,
        "reasoning": "Strong uptrend favors trend-following with full position sizing",
    },
    Regime.WEAK_TREND_UP: {
        "primary": CIV1,
        "weights": [
            StrategyWeight(CIV1, 0.7, 0.8),
            StrategyWeight(VB, 0.3, 0.6),
        ],
        "position_modifier": 0.8,
        "reasoning": "Weak uptrend: primary trend-following, secondary breakout at reduced size",
    },
    Regime.RANGING: {
        "primary": BMR,
        "weights": [StrategyWeight(BMR, 1.0, 1.0)],
        "position_modifier": 1.0,
        "reasoning": "Ranging market is ideal for mean-reversion with full sizing",
    },
    Regime.WEAK_TREND_DOWN: {
        "primary": BMR,
        "weights": [
            StrategyWeight(BMR, 0.5, 0.5),
            StrategyWeight(VB, 0.5, 0.5),
        ],
        "position_modifier": 0.5,
        "reasoning": "Weak downtrend: split between mean-reversion and breakout at half size",
    },
    Regime.STRONG_TREND_DOWN: {
        "primary": BMR,
        "weights": [StrategyWeight(BMR, 1.0, 0.3)],
        "position_modifier": 0.3,
        "reasoning": "Strong downtrend: defensive, mean-reversion only at 30% size",
    },
    Regime.HIGH_VOLATILITY: {
        "primary": VB,
        "weights": [StrategyWeight(VB, 1.0, 0.8)],
        "position_modifier": 0.8,
        "reasoning": "High volatility: breakout strategy at 80% size to manage risk",
    },
    Regime.UNKNOWN: {
        "primary": BMR,
        "weights": [StrategyWeight(BMR, 1.0, 0.3)],
        "position_modifier": 0.3,
        "reasoning": "Unknown regime (warmup/insufficient data): conservative at 30% size",
    },
}


EQUITY_ROUTING: dict[Regime, dict] = {
    Regime.STRONG_TREND_UP: {
        "primary": EQ_MOM,
        "weights": [StrategyWeight(EQ_MOM, 1.0, 1.0)],
        "position_modifier": 1.0,
        "reasoning": "Strong uptrend favors equity momentum with full sizing",
    },
    Regime.WEAK_TREND_UP: {
        "primary": EQ_MOM,
        "weights": [
            StrategyWeight(EQ_MOM, 0.7, 0.8),
            StrategyWeight(EQ_MR, 0.3, 0.5),
        ],
        "position_modifier": 0.8,
        "reasoning": "Weak uptrend: primary momentum, secondary mean-reversion",
    },
    Regime.RANGING: {
        "primary": EQ_MR,
        "weights": [StrategyWeight(EQ_MR, 1.0, 1.0)],
        "position_modifier": 1.0,
        "reasoning": "Ranging equity market ideal for mean-reversion",
    },
    Regime.WEAK_TREND_DOWN: {
        "primary": EQ_MR,
        "weights": [StrategyWeight(EQ_MR, 1.0, 0.5)],
        "position_modifier": 0.5,
        "reasoning": "Weak downtrend: defensive mean-reversion at 50% size",
    },
    Regime.STRONG_TREND_DOWN: {
        "primary": EQ_MR,
        "weights": [StrategyWeight(EQ_MR, 1.0, 0.2)],
        "position_modifier": 0.2,
        "reasoning": "Strong downtrend: minimal equity exposure at 20% size",
    },
    Regime.HIGH_VOLATILITY: {
        "primary": EQ_MR,
        "weights": [StrategyWeight(EQ_MR, 1.0, 0.5)],
        "position_modifier": 0.5,
        "reasoning": "High volatility: equity mean-reversion at 50%",
    },
    Regime.UNKNOWN: {
        "primary": EQ_MR,
        "weights": [StrategyWeight(EQ_MR, 1.0, 0.2)],
        "position_modifier": 0.2,
        "reasoning": "Unknown regime: conservative equity exposure at 20%",
    },
}

FOREX_ROUTING: dict[Regime, dict] = {
    Regime.STRONG_TREND_UP: {
        "primary": FX_TREND,
        "weights": [StrategyWeight(FX_TREND, 1.0, 1.0)],
        "position_modifier": 1.0,
        "reasoning": "Strong uptrend favors forex trend following",
    },
    Regime.WEAK_TREND_UP: {
        "primary": FX_TREND,
        "weights": [
            StrategyWeight(FX_TREND, 0.6, 0.8),
            StrategyWeight(FX_RANGE, 0.4, 0.6),
        ],
        "position_modifier": 0.8,
        "reasoning": "Weak uptrend: primary trend, secondary range at reduced size",
    },
    Regime.RANGING: {
        "primary": FX_RANGE,
        "weights": [StrategyWeight(FX_RANGE, 1.0, 1.0)],
        "position_modifier": 1.0,
        "reasoning": "Ranging market is ideal for forex range trading",
    },
    Regime.WEAK_TREND_DOWN: {
        "primary": FX_TREND,
        "weights": [
            StrategyWeight(FX_TREND, 0.5, 0.6),
            StrategyWeight(FX_RANGE, 0.5, 0.5),
        ],
        "position_modifier": 0.6,
        "reasoning": "Weak downtrend: split trend/range at reduced size",
    },
    Regime.STRONG_TREND_DOWN: {
        "primary": FX_TREND,
        "weights": [StrategyWeight(FX_TREND, 1.0, 0.4)],
        "position_modifier": 0.4,
        "reasoning": "Strong downtrend: trend following at 40% size (can short FX)",
    },
    Regime.HIGH_VOLATILITY: {
        "primary": FX_RANGE,
        "weights": [StrategyWeight(FX_RANGE, 1.0, 0.5)],
        "position_modifier": 0.5,
        "reasoning": "High volatility: range trading at 50% size",
    },
    Regime.UNKNOWN: {
        "primary": FX_RANGE,
        "weights": [StrategyWeight(FX_RANGE, 1.0, 0.3)],
        "position_modifier": 0.3,
        "reasoning": "Unknown regime: conservative range trading at 30%",
    },
}

_ROUTING_BY_ASSET_CLASS: dict[str, dict[Regime, dict]] = {
    "crypto": DEFAULT_ROUTING,
    "equity": EQUITY_ROUTING,
    "forex": FOREX_ROUTING,
}


class StrategyRouter:
    """Routes market regimes to optimal strategy combinations."""

    def __init__(
        self,
        routing: dict[Regime, dict] | None = None,
        low_confidence_threshold: float = 0.4,
        low_confidence_penalty: float = 0.5,
        asset_class: str = "crypto",
    ) -> None:
        self.routing = routing or _ROUTING_BY_ASSET_CLASS.get(asset_class, DEFAULT_ROUTING)
        self.low_confidence_threshold = low_confidence_threshold
        self.low_confidence_penalty = low_confidence_penalty

    def route(
        self,
        state: RegimeState,
        sentiment_modifier: float | None = None,
    ) -> RoutingDecision:
        """Get strategy routing decision for a detected regime state.

        Args:
            state: Detected regime state from RegimeDetector.
            sentiment_modifier: Optional position size multiplier from sentiment signal.
                Clamped to [0.5, 1.5]. None preserves existing behavior.

        """
        mapping = self.routing.get(state.regime)
        if mapping is None:
            # Fallback to RANGING if unknown
            mapping = self.routing[Regime.RANGING]

        # Override: bearish high volatility → defensive BMR instead of VB
        if state.regime == Regime.HIGH_VOLATILITY and state.trend_alignment < 0:
            mapping = {
                "primary": BMR,
                "weights": [StrategyWeight(BMR, 1.0, 0.5)],
                "position_modifier": 0.5,
                "reasoning": "High volatility + bearish alignment: defensive BMR at 50%",
            }

        position_modifier = mapping["position_modifier"]

        # Low confidence → further reduce position sizing
        if state.confidence < self.low_confidence_threshold:
            position_modifier *= self.low_confidence_penalty

        # Apply sentiment modifier if provided
        if sentiment_modifier is not None:
            clamped = max(0.5, min(1.5, sentiment_modifier))
            position_modifier *= clamped

        return RoutingDecision(
            regime=state.regime,
            confidence=state.confidence,
            primary_strategy=mapping["primary"],
            weights=list(mapping["weights"]),
            position_size_modifier=round(position_modifier, 3),
            reasoning=mapping["reasoning"],
            sentiment_modifier=sentiment_modifier,
        )

    def suggest_strategy_switch(
        self,
        current_strategy: str,
        state: RegimeState,
    ) -> RoutingDecision | None:
        """Return a new routing decision if current strategy mismatches the regime.

        Returns None if no switch is needed.
        """
        decision = self.route(state)

        # No switch needed if current strategy is the primary
        if decision.primary_strategy == current_strategy:
            return None

        # No switch needed if current strategy is in the active weights
        active_names = {w.strategy_name for w in decision.weights}
        if current_strategy in active_names:
            # Still active, but check if it's no longer primary
            for w in decision.weights:
                if w.strategy_name == current_strategy and w.weight >= 0.5:
                    return None

        return decision

    def get_all_strategies(self) -> list[str]:
        """Return sorted list of all strategy names used in routing."""
        names: set[str] = set()
        for mapping in self.routing.values():
            for w in mapping["weights"]:
                names.add(w.strategy_name)
        return sorted(names)

    def get_routing_table(self) -> dict[str, dict]:
        """Return human-readable routing table for display."""
        table = {}
        for regime, mapping in self.routing.items():
            table[regime.value] = {
                "primary": mapping["primary"],
                "weights": [
                    {
                        "strategy": w.strategy_name,
                        "weight": w.weight,
                        "position_size_factor": w.position_size_factor,
                    }
                    for w in mapping["weights"]
                ],
                "position_modifier": mapping["position_modifier"],
                "reasoning": mapping["reasoning"],
            }
        return table
