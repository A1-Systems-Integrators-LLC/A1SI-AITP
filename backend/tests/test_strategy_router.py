"""Tests for Regime-Adaptive Strategy Router — Sprint 2, Item 2.4
==============================================================
Covers: StrategyWeight, RoutingDecision, StrategyRouter routing for
all 6 regimes, low confidence handling, strategy switch suggestions,
routing table, and custom routing config.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.regime.regime_detector import Regime, RegimeState
from common.regime.strategy_router import (
    BMR,
    CIV1,
    VB,
    RoutingDecision,
    StrategyRouter,
    StrategyWeight,
)

# ── Helpers ──────────────────────────────────────────────────


def _make_state(regime: Regime, confidence: float = 0.8, adx: float = 30.0) -> RegimeState:
    return RegimeState(
        regime=regime,
        confidence=confidence,
        adx_value=adx,
        bb_width_percentile=50.0,
        ema_slope=0.01,
        trend_alignment=0.5,
        price_structure_score=0.3,
    )


# ── StrategyWeight Tests ─────────────────────────────────────


class TestStrategyWeight:
    def test_creation(self):
        w = StrategyWeight("CryptoInvestorV1", 0.7, 0.8)
        assert w.strategy_name == "CryptoInvestorV1"
        assert w.weight == 0.7
        assert w.position_size_factor == 0.8


# ── RoutingDecision Tests ────────────────────────────────────


class TestRoutingDecision:
    def test_creation(self):
        decision = RoutingDecision(
            regime=Regime.RANGING,
            confidence=0.8,
            primary_strategy=BMR,
            weights=[StrategyWeight(BMR, 1.0, 1.0)],
            position_size_modifier=1.0,
            reasoning="test",
        )
        assert decision.regime == Regime.RANGING
        assert decision.primary_strategy == BMR
        assert len(decision.weights) == 1


# ── Regime → Strategy Routing Tests ──────────────────────────


class TestRouterRegimeMapping:
    def test_strong_trend_up_routes_to_civ1(self):
        router = StrategyRouter()
        state = _make_state(Regime.STRONG_TREND_UP)
        decision = router.route(state)
        assert decision.primary_strategy == CIV1
        assert len(decision.weights) == 1
        assert decision.weights[0].strategy_name == CIV1
        assert decision.weights[0].weight == 1.0
        assert decision.position_size_modifier == 1.0

    def test_ranging_routes_to_bmr(self):
        router = StrategyRouter()
        state = _make_state(Regime.RANGING)
        decision = router.route(state)
        assert decision.primary_strategy == BMR
        assert decision.position_size_modifier == 1.0

    def test_high_volatility_routes_to_vb(self):
        router = StrategyRouter()
        state = _make_state(Regime.HIGH_VOLATILITY)
        decision = router.route(state)
        assert decision.primary_strategy == VB
        assert decision.weights[0].strategy_name == VB
        assert decision.position_size_modifier == 0.8

    def test_weak_trend_up_blended(self):
        router = StrategyRouter()
        state = _make_state(Regime.WEAK_TREND_UP)
        decision = router.route(state)
        assert decision.primary_strategy == CIV1
        assert len(decision.weights) == 2
        names = {w.strategy_name for w in decision.weights}
        assert CIV1 in names
        assert VB in names

    def test_weak_trend_down_blended(self):
        router = StrategyRouter()
        state = _make_state(Regime.WEAK_TREND_DOWN)
        decision = router.route(state)
        assert decision.primary_strategy == BMR
        assert len(decision.weights) == 2
        assert decision.position_size_modifier == 0.5

    def test_strong_trend_down_defensive(self):
        router = StrategyRouter()
        state = _make_state(Regime.STRONG_TREND_DOWN)
        decision = router.route(state)
        assert decision.primary_strategy == BMR
        assert decision.position_size_modifier == 0.3

    def test_all_regimes_return_valid_decision(self):
        router = StrategyRouter()
        for regime in Regime:
            state = _make_state(regime)
            decision = router.route(state)
            assert isinstance(decision, RoutingDecision)
            assert decision.regime == regime
            assert 0 < decision.position_size_modifier <= 1.0
            assert len(decision.weights) > 0
            total_weight = sum(w.weight for w in decision.weights)
            assert abs(total_weight - 1.0) < 0.01


# ── Low Confidence Tests ─────────────────────────────────────


class TestLowConfidence:
    def test_low_confidence_reduces_position_size(self):
        router = StrategyRouter()
        high_conf = _make_state(Regime.STRONG_TREND_UP, confidence=0.9)
        low_conf = _make_state(Regime.STRONG_TREND_UP, confidence=0.2)

        high_decision = router.route(high_conf)
        low_decision = router.route(low_conf)

        assert low_decision.position_size_modifier < high_decision.position_size_modifier

    def test_low_confidence_penalty_applied(self):
        router = StrategyRouter(low_confidence_threshold=0.5, low_confidence_penalty=0.5)
        state = _make_state(Regime.STRONG_TREND_UP, confidence=0.3)
        decision = router.route(state)
        # Full modifier is 1.0, with penalty should be 0.5
        assert decision.position_size_modifier == 0.5

    def test_high_confidence_no_penalty(self):
        router = StrategyRouter(low_confidence_threshold=0.5, low_confidence_penalty=0.5)
        state = _make_state(Regime.STRONG_TREND_UP, confidence=0.8)
        decision = router.route(state)
        assert decision.position_size_modifier == 1.0


# ── Strategy Switch Suggestion Tests ─────────────────────────


class TestStrategySwitchSuggestion:
    def test_no_switch_when_matching(self):
        router = StrategyRouter()
        state = _make_state(Regime.STRONG_TREND_UP)
        result = router.suggest_strategy_switch(CIV1, state)
        assert result is None

    def test_suggests_switch_when_mismatched(self):
        router = StrategyRouter()
        state = _make_state(Regime.RANGING)
        result = router.suggest_strategy_switch(CIV1, state)
        assert result is not None
        assert result.primary_strategy == BMR

    def test_no_switch_when_strategy_in_blend(self):
        router = StrategyRouter()
        state = _make_state(Regime.WEAK_TREND_UP)
        # CIV1 is primary with weight 0.7 (>= 0.5), so no switch
        result = router.suggest_strategy_switch(CIV1, state)
        assert result is None

    def test_switch_suggested_for_minor_weight(self):
        router = StrategyRouter()
        state = _make_state(Regime.WEAK_TREND_UP)
        # VB is in blend but only at 0.3 weight (< 0.5)
        result = router.suggest_strategy_switch(VB, state)
        assert result is not None
        assert result.primary_strategy == CIV1


# ── Utility Method Tests ─────────────────────────────────────


class TestRouterUtilities:
    def test_get_all_strategies(self):
        router = StrategyRouter()
        strategies = router.get_all_strategies()
        assert CIV1 in strategies
        assert BMR in strategies
        assert VB in strategies
        assert len(strategies) == 3

    def test_get_routing_table(self):
        router = StrategyRouter()
        table = router.get_routing_table()
        assert len(table) == 7  # One entry per regime (including UNKNOWN)
        for _regime_val, entry in table.items():
            assert "primary" in entry
            assert "weights" in entry
            assert "position_modifier" in entry
            assert "reasoning" in entry

    def test_unknown_regime_routes_defensively(self):
        router = StrategyRouter()
        state = _make_state(Regime.UNKNOWN)
        decision = router.route(state)
        assert decision.primary_strategy == BMR
        assert decision.position_size_modifier <= 0.3

    def test_unknown_regime_in_all_regimes_check(self):
        """Ensure UNKNOWN is covered in the routing table and route() works."""
        router = StrategyRouter()
        table = router.get_routing_table()
        assert "unknown" in table

    def test_high_vol_bullish_routes_to_vb(self):
        """HIGH_VOLATILITY with positive alignment → VB (unchanged)."""
        router = StrategyRouter()
        state = RegimeState(
            regime=Regime.HIGH_VOLATILITY,
            confidence=0.8,
            adx_value=20.0,
            bb_width_percentile=90.0,
            ema_slope=0.001,
            trend_alignment=0.3,
            price_structure_score=0.1,
        )
        decision = router.route(state)
        assert decision.primary_strategy == VB

    def test_high_vol_bearish_routes_to_bmr(self):
        """HIGH_VOLATILITY with negative alignment → BMR defensive."""
        router = StrategyRouter()
        state = RegimeState(
            regime=Regime.HIGH_VOLATILITY,
            confidence=0.8,
            adx_value=20.0,
            bb_width_percentile=90.0,
            ema_slope=-0.005,
            trend_alignment=-0.5,
            price_structure_score=-0.3,
        )
        decision = router.route(state)
        assert decision.primary_strategy == BMR

    def test_high_vol_bearish_reduced_modifier(self):
        """Bearish HIGH_VOLATILITY should have modifier = 0.5."""
        router = StrategyRouter()
        state = RegimeState(
            regime=Regime.HIGH_VOLATILITY,
            confidence=0.8,
            adx_value=20.0,
            bb_width_percentile=90.0,
            ema_slope=-0.005,
            trend_alignment=-0.5,
            price_structure_score=-0.3,
        )
        decision = router.route(state)
        assert decision.position_size_modifier == 0.5

    def test_high_vol_neutral_routes_to_vb(self):
        """HIGH_VOLATILITY with zero alignment → VB (unchanged)."""
        router = StrategyRouter()
        state = RegimeState(
            regime=Regime.HIGH_VOLATILITY,
            confidence=0.8,
            adx_value=20.0,
            bb_width_percentile=90.0,
            ema_slope=0.0,
            trend_alignment=0.0,
            price_structure_score=0.0,
        )
        decision = router.route(state)
        assert decision.primary_strategy == VB

    def test_custom_routing_config(self):
        custom = {
            Regime.RANGING: {
                "primary": CIV1,
                "weights": [StrategyWeight(CIV1, 1.0, 1.0)],
                "position_modifier": 0.5,
                "reasoning": "Custom test routing",
            },
        }
        router = StrategyRouter(routing=custom)
        state = _make_state(Regime.RANGING)
        decision = router.route(state)
        assert decision.primary_strategy == CIV1
        assert decision.position_size_modifier == 0.5
