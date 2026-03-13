"""Tests for Phase 2: Conviction-Aware Exit Management (common/signals/exit_manager.py)."""

from datetime import datetime, timedelta, timezone

import pytest
from common.regime.regime_detector import Regime, RegimeState
from common.signals.constants import (
    DEFAULT_MAX_HOLD_HOURS,
    MAX_HOLD_HOURS,
    PARTIAL_PROFIT_TARGETS,
    REGIME_DETERIORATION_THRESHOLD,
    STOP_TIGHTENING_MULTIPLIER,
    TIME_EXIT_REGIME_MULTIPLIER,
    URGENCY_IMMEDIATE,
    URGENCY_MONITOR,
    URGENCY_NEXT_CANDLE,
)
from common.signals.exit_manager import (
    ExitAdvice,
    advise_exit,
    get_stop_multiplier,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _regime_state(regime: Regime, confidence: float = 0.8) -> RegimeState:
    return RegimeState(
        regime=regime,
        confidence=confidence,
        adx_value=30.0,
        bb_width_percentile=50.0,
        ema_slope=0.0,
        trend_alignment=0.0,
        price_structure_score=0.0,
        transition_probabilities={},
    )


NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)


# ─── ExitAdvice Dataclass ─────────────────────────────────────────────────────


class TestExitAdviceDataclass:
    def test_create_exit_advice(self):
        advice = ExitAdvice(
            should_exit=True,
            reason="test reason",
            urgency=URGENCY_IMMEDIATE,
            partial_pct=0.5,
        )
        assert advice.should_exit is True
        assert advice.reason == "test reason"
        assert advice.urgency == URGENCY_IMMEDIATE
        assert advice.partial_pct == 0.5

    def test_no_exit_advice(self):
        advice = ExitAdvice(
            should_exit=False,
            reason="all good",
            urgency=URGENCY_MONITOR,
            partial_pct=0.0,
        )
        assert advice.should_exit is False
        assert advice.urgency == URGENCY_MONITOR


# ─── No Exit Conditions ──────────────────────────────────────────────────────


class TestNoExit:
    def test_no_exit_conditions_met(self):
        """Position with no triggers returns should_exit=False."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=1),
            current_time=NOW,
            current_profit_pct=0.01,  # +1% — below partial targets
        )
        assert advice.should_exit is False
        assert advice.urgency == URGENCY_MONITOR
        assert "No exit conditions met" in advice.reason

    def test_same_regime_no_profit_targets(self):
        """Unknown strategy with no partial targets and fresh position."""
        advice = advise_exit(
            symbol="ETH/USDT",
            strategy_name="UnknownStrategy",
            asset_class="crypto",
            entry_regime=Regime.RANGING,
            current_regime_state=_regime_state(Regime.RANGING),
            entry_time=NOW - timedelta(hours=1),
            current_time=NOW,
            current_profit_pct=0.0,
        )
        assert advice.should_exit is False


# ─── Regime Deterioration ─────────────────────────────────────────────────────


class TestRegimeDeterioration:
    def test_civ1_strong_up_to_strong_down_profitable(self):
        """CIV1 entered in STRONG_TREND_UP, now STRONG_TREND_DOWN, profitable → exit."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_DOWN),
            entry_time=NOW - timedelta(hours=24),
            current_time=NOW,
            current_profit_pct=0.03,
        )
        assert advice.should_exit is True
        assert advice.urgency == URGENCY_IMMEDIATE
        assert "Regime deterioration" in advice.reason
        assert advice.partial_pct == 0.0  # Full exit

    def test_civ1_strong_up_to_strong_down_at_loss(self):
        """CIV1 in bad regime but at loss → don't exit, monitor."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_DOWN),
            entry_time=NOW - timedelta(hours=24),
            current_time=NOW,
            current_profit_pct=-0.02,
        )
        assert advice.should_exit is False
        assert "at loss" in advice.reason
        assert advice.urgency == URGENCY_MONITOR

    def test_small_regime_change_no_exit(self):
        """CIV1 STRONG_TREND_UP → WEAK_TREND_UP: alignment drop < threshold."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.WEAK_TREND_UP),
            entry_time=NOW - timedelta(hours=1),
            current_time=NOW,
            current_profit_pct=0.05,
        )
        # CIV1: STRONG_TREND_UP=95, WEAK_TREND_UP=75 → drop=20 < 30 threshold
        assert advice.should_exit is False

    def test_same_regime_no_deterioration(self):
        """Same regime → no deterioration check."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=1),
            current_time=NOW,
            current_profit_pct=0.05,
        )
        # Should only hit partial profit, not regime deterioration
        assert "deterioration" not in advice.reason.lower() or advice.should_exit is False

    def test_bmr_regime_improvement(self):
        """BMR entered in RANGING, now RANGING → no exit (same regime)."""
        advice = advise_exit(
            symbol="ETH/USDT",
            strategy_name="BollingerMeanReversion",
            asset_class="crypto",
            entry_regime=Regime.RANGING,
            current_regime_state=_regime_state(Regime.RANGING),
            entry_time=NOW - timedelta(hours=1),
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert advice.should_exit is False

    def test_vb_entered_high_vol_to_ranging(self):
        """VB: HIGH_VOLATILITY=90 → RANGING=40 → drop=50 ≥ 30, profitable → exit."""
        advice = advise_exit(
            symbol="SOL/USDT",
            strategy_name="VolatilityBreakout",
            asset_class="crypto",
            entry_regime=Regime.HIGH_VOLATILITY,
            current_regime_state=_regime_state(Regime.RANGING),
            entry_time=NOW - timedelta(hours=10),
            current_time=NOW,
            current_profit_pct=0.04,
        )
        assert advice.should_exit is True
        assert advice.urgency == URGENCY_IMMEDIATE

    def test_equity_strategy_deterioration(self):
        """EquityMomentum: STRONG_TREND_UP=95 → STRONG_TREND_DOWN=0 → drop=95 → exit."""
        advice = advise_exit(
            symbol="AAPL",
            strategy_name="EquityMomentum",
            asset_class="equity",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_DOWN),
            entry_time=NOW - timedelta(hours=48),
            current_time=NOW,
            current_profit_pct=0.02,
        )
        assert advice.should_exit is True

    def test_forex_strategy_no_deterioration(self):
        """ForexTrend: STRONG_TREND_UP=95 → STRONG_TREND_DOWN=90 → drop=5 < 30."""
        advice = advise_exit(
            symbol="EUR/USD",
            strategy_name="ForexTrend",
            asset_class="forex",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_DOWN),
            entry_time=NOW - timedelta(hours=1),
            current_time=NOW,
            current_profit_pct=0.01,
        )
        # ForexTrend: STU=95, STD=90 → drop=5 < 30 → no exit from deterioration
        assert advice.should_exit is False

    def test_zero_profit_boundary(self):
        """At exactly breakeven (0.0), regime deterioration should NOT exit."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_DOWN),
            entry_time=NOW - timedelta(hours=24),
            current_time=NOW,
            current_profit_pct=0.0,
        )
        assert advice.should_exit is False


# ─── Partial Profit Taking ────────────────────────────────────────────────────


class TestPartialProfit:
    def test_civ1_first_target_6pct(self):
        """CIV1 at 7% profit, nothing exited → close 1/3."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=12),
            current_time=NOW,
            current_profit_pct=0.07,
            already_exited_pct=0.0,
        )
        assert advice.should_exit is True
        assert advice.urgency == URGENCY_NEXT_CANDLE
        assert advice.partial_pct == pytest.approx(1 / 3)
        assert "CIV1 1/3 at 6%" in advice.reason

    def test_civ1_second_target_10pct(self):
        """CIV1 at 12% profit, already exited 1/3 → close 1/2."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=24),
            current_time=NOW,
            current_profit_pct=0.12,
            already_exited_pct=1 / 3,
        )
        assert advice.should_exit is True
        assert advice.partial_pct == pytest.approx(1 / 2)
        assert "CIV1 1/2 at 10%" in advice.reason

    def test_civ1_already_exited_half(self):
        """CIV1 at 12% profit, already exited 1/2 → no more partial targets."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=24),
            current_time=NOW,
            current_profit_pct=0.12,
            already_exited_pct=0.5,
        )
        # Both targets exceeded but already_exited_pct >= close_fraction for both
        assert advice.should_exit is False

    def test_bmr_first_target_2pct(self):
        """BMR at 2.5% → close 1/2."""
        advice = advise_exit(
            symbol="ETH/USDT",
            strategy_name="BollingerMeanReversion",
            asset_class="crypto",
            entry_regime=Regime.RANGING,
            current_regime_state=_regime_state(Regime.RANGING),
            entry_time=NOW - timedelta(hours=6),
            current_time=NOW,
            current_profit_pct=0.025,
            already_exited_pct=0.0,
        )
        assert advice.should_exit is True
        assert advice.partial_pct == pytest.approx(1 / 2)

    def test_bmr_second_target_4pct(self):
        """BMR at 5% profit, already exited 1/2 → close 3/4."""
        advice = advise_exit(
            symbol="ETH/USDT",
            strategy_name="BollingerMeanReversion",
            asset_class="crypto",
            entry_regime=Regime.RANGING,
            current_regime_state=_regime_state(Regime.RANGING),
            entry_time=NOW - timedelta(hours=12),
            current_time=NOW,
            current_profit_pct=0.05,
            already_exited_pct=0.5,
        )
        assert advice.should_exit is True
        assert advice.partial_pct == pytest.approx(3 / 4)
        assert "BMR 3/4 at 4%" in advice.reason

    def test_vb_target_5pct(self):
        """VB at 6% → close 1/3."""
        advice = advise_exit(
            symbol="SOL/USDT",
            strategy_name="VolatilityBreakout",
            asset_class="crypto",
            entry_regime=Regime.HIGH_VOLATILITY,
            current_regime_state=_regime_state(Regime.HIGH_VOLATILITY),
            entry_time=NOW - timedelta(hours=12),
            current_time=NOW,
            current_profit_pct=0.06,
            already_exited_pct=0.0,
        )
        assert advice.should_exit is True
        assert advice.partial_pct == pytest.approx(1 / 3)

    def test_unknown_strategy_no_targets(self):
        """Strategy without partial profit targets → skip."""
        advice = advise_exit(
            symbol="AAPL",
            strategy_name="SomeUnknownStrategy",
            asset_class="equity",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=1),
            current_time=NOW,
            current_profit_pct=0.20,
            already_exited_pct=0.0,
        )
        # Unknown strategy not in PARTIAL_PROFIT_TARGETS, so no partial exit
        assert advice.should_exit is False

    def test_below_first_target(self):
        """Profit below any target → no partial exit."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=1),
            current_time=NOW,
            current_profit_pct=0.04,  # Below 6% target
        )
        assert advice.should_exit is False

    def test_highest_target_selected_first(self):
        """When profit exceeds multiple targets, highest applicable is picked."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=24),
            current_time=NOW,
            current_profit_pct=0.15,  # Above both 6% and 10%
            already_exited_pct=0.0,
        )
        assert advice.should_exit is True
        # Should get the 10% target (1/2) since it's checked first (reversed)
        assert advice.partial_pct == pytest.approx(1 / 2)
        assert "10%" in advice.reason


# ─── Time-Based Exit ──────────────────────────────────────────────────────────


class TestTimeBasedExit:
    def test_civ1_exceeded_max_hold(self):
        """CIV1 held 170h in STRONG_TREND_UP (max=168h) → exit."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=170),
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert advice.should_exit is True
        assert advice.urgency == URGENCY_NEXT_CANDLE
        assert advice.partial_pct == 0.0  # Full exit
        assert "Time limit" in advice.reason

    def test_bmr_exceeded_48h(self):
        """BMR held 50h (max=48h) → exit."""
        advice = advise_exit(
            symbol="ETH/USDT",
            strategy_name="BollingerMeanReversion",
            asset_class="crypto",
            entry_regime=Regime.RANGING,
            current_regime_state=_regime_state(Regime.RANGING),
            entry_time=NOW - timedelta(hours=50),
            current_time=NOW,
            current_profit_pct=0.005,
        )
        assert advice.should_exit is True
        assert "48" in advice.reason

    def test_vb_within_limit(self):
        """VB held 40h in HIGH_VOLATILITY (max=72h×0.6=43.2h) → no exit."""
        advice = advise_exit(
            symbol="SOL/USDT",
            strategy_name="VolatilityBreakout",
            asset_class="crypto",
            entry_regime=Regime.HIGH_VOLATILITY,
            current_regime_state=_regime_state(Regime.HIGH_VOLATILITY),
            entry_time=NOW - timedelta(hours=40),
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert advice.should_exit is False

    def test_time_halved_in_strong_trend_down(self):
        """BMR in STRONG_TREND_DOWN: 48h × 0.5 = 24h. Held 25h → exit."""
        advice = advise_exit(
            symbol="ETH/USDT",
            strategy_name="BollingerMeanReversion",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_DOWN,  # Same regime → no deterioration
            current_regime_state=_regime_state(Regime.STRONG_TREND_DOWN),
            entry_time=NOW - timedelta(hours=25),
            current_time=NOW,
            current_profit_pct=0.005,
        )
        assert advice.should_exit is True
        assert "24.0h" in advice.reason

    def test_unknown_strategy_default_max_hours(self):
        """Unknown strategy uses DEFAULT_MAX_HOLD_HOURS (96h).
        Equity multiplier is 2.0, so effective max = 96 * 2.0 = 192h.
        """
        advice = advise_exit(
            symbol="AAPL",
            strategy_name="SomeUnknownStrategy",
            asset_class="equity",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=200),
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert advice.should_exit is True
        assert "96" in advice.reason

    def test_exact_boundary_triggers_exit(self):
        """Exactly at max hours → exit."""
        advice = advise_exit(
            symbol="ETH/USDT",
            strategy_name="BollingerMeanReversion",
            asset_class="crypto",
            entry_regime=Regime.RANGING,
            current_regime_state=_regime_state(Regime.RANGING),
            entry_time=NOW - timedelta(hours=39),  # 48h × 0.8 (RANGING multiplier) = 38.4h
            current_time=NOW,
            current_profit_pct=0.0,
        )
        assert advice.should_exit is True

    def test_high_volatility_reduces_hold_time(self):
        """HIGH_VOLATILITY regime multiplier = 0.6."""
        # BMR: 48h × 0.6 = 28.8h
        advice = advise_exit(
            symbol="ETH/USDT",
            strategy_name="BollingerMeanReversion",
            asset_class="crypto",
            entry_regime=Regime.RANGING,
            current_regime_state=_regime_state(Regime.HIGH_VOLATILITY),
            entry_time=NOW - timedelta(hours=30),
            current_time=NOW,
            current_profit_pct=0.005,
        )
        assert advice.should_exit is True


# ─── Stop Tightening Multiplier ───────────────────────────────────────────────


class TestStopMultiplier:
    def test_strong_trend_up(self):
        assert get_stop_multiplier(Regime.STRONG_TREND_UP) == 1.0

    def test_strong_trend_down(self):
        assert get_stop_multiplier(Regime.STRONG_TREND_DOWN) == 0.55

    def test_ranging(self):
        assert get_stop_multiplier(Regime.RANGING) == 0.85

    def test_all_regimes_have_multipliers(self):
        for regime in Regime:
            mult = get_stop_multiplier(regime)
            assert 0.0 < mult <= 1.0, f"Invalid multiplier for {regime}: {mult}"


# ─── Priority Order ──────────────────────────────────────────────────────────


class TestPriorityOrder:
    def test_regime_deterioration_trumps_partial_profit(self):
        """If both regime deterioration and partial profit trigger, regime wins (checked first)."""
        # CIV1: STRONG_TREND_UP(95) → STRONG_TREND_DOWN(0) = drop 95 > 30
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_DOWN),
            entry_time=NOW - timedelta(hours=12),
            current_time=NOW,
            current_profit_pct=0.10,  # Would trigger 10% partial profit too
        )
        assert advice.should_exit is True
        assert advice.urgency == URGENCY_IMMEDIATE
        assert advice.partial_pct == 0.0  # Full exit (regime deterioration)
        assert "deterioration" in advice.reason.lower()

    def test_partial_profit_trumps_time(self):
        """Partial profit is checked before time-based exit."""
        # CIV1: 170h (>168h limit), but at 7% profit (partial target)
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=NOW - timedelta(hours=170),
            current_time=NOW,
            current_profit_pct=0.07,
            already_exited_pct=0.0,
        )
        assert advice.should_exit is True
        # Partial profit target checked first
        assert advice.partial_pct == pytest.approx(1 / 3)


# ─── Default current_time ────────────────────────────────────────────────────


class TestDefaultCurrentTime:
    def test_defaults_to_now(self):
        """When current_time is not provided, uses utcnow."""
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            current_profit_pct=0.01,
        )
        assert advice.should_exit is False


# ─── Constants Validation ─────────────────────────────────────────────────────


class TestConstants:
    def test_all_regimes_have_time_multiplier(self):
        for regime in Regime:
            assert regime in TIME_EXIT_REGIME_MULTIPLIER

    def test_all_regimes_have_stop_multiplier(self):
        for regime in Regime:
            assert regime in STOP_TIGHTENING_MULTIPLIER

    def test_partial_targets_ordered(self):
        """Profit targets must be in ascending order per strategy."""
        for strategy, targets in PARTIAL_PROFIT_TARGETS.items():
            pcts = [t[0] for t in targets]
            assert pcts == sorted(pcts), f"{strategy} targets not sorted: {pcts}"

    def test_deterioration_threshold_positive(self):
        assert REGIME_DETERIORATION_THRESHOLD > 0

    def test_max_hold_hours_positive(self):
        for strategy, hours in MAX_HOLD_HOURS.items():
            assert hours > 0, f"{strategy} has non-positive max hold hours"
        assert DEFAULT_MAX_HOLD_HOURS > 0


# ─── Package Exports ──────────────────────────────────────────────────────────


class TestExports:
    def test_package_exports(self):
        from common.signals import ExitAdvice, advise_exit, get_stop_multiplier

        assert ExitAdvice is not None
        assert callable(advise_exit)
        assert callable(get_stop_multiplier)
