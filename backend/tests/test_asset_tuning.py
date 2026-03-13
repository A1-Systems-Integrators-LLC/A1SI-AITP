"""Tests for IEB Phase 9: Asset-Class Specific Tuning (common/signals/asset_tuning.py)."""

from datetime import datetime, timedelta, timezone

from common.regime.regime_detector import Regime, RegimeState
from common.signals.aggregator import SignalAggregator
from common.signals.asset_tuning import (
    ASSET_CONFIGS,
    AssetClassConfig,
    get_config,
    get_conviction_threshold,
    get_session_adjustment,
)
from common.signals.constants import (
    REGIME_COOLDOWN_PENALTY,
)
from common.signals.exit_manager import advise_exit

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


# ═══════════════════════════════════════════════════════════════════════════════
# AssetClassConfig tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAssetClassConfig:
    def test_dataclass_creation(self):
        cfg = AssetClassConfig(
            conviction_threshold=55,
            regime_cooldown_bars=6,
            max_hold_multiplier=1.0,
            volume_weight_bonus=1.0,
            spread_max_pct=0.5,
        )
        assert cfg.conviction_threshold == 55
        assert cfg.session_bonus == {}

    def test_session_bonus_default(self):
        cfg = AssetClassConfig(
            conviction_threshold=55,
            regime_cooldown_bars=6,
            max_hold_multiplier=1.0,
            volume_weight_bonus=1.0,
            spread_max_pct=0.5,
        )
        assert cfg.session_bonus == {}

    def test_all_asset_configs_defined(self):
        assert "crypto" in ASSET_CONFIGS
        assert "equity" in ASSET_CONFIGS
        assert "forex" in ASSET_CONFIGS


# ═══════════════════════════════════════════════════════════════════════════════
# get_config tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetConfig:
    def test_crypto_config(self):
        cfg = get_config("crypto")
        assert cfg.conviction_threshold == 55
        assert cfg.regime_cooldown_bars == 6
        assert cfg.max_hold_multiplier == 1.0
        assert cfg.volume_weight_bonus == 1.0

    def test_equity_config(self):
        cfg = get_config("equity")
        assert cfg.conviction_threshold == 65
        assert cfg.regime_cooldown_bars == 3
        assert cfg.max_hold_multiplier == 2.0
        assert cfg.volume_weight_bonus == 1.3

    def test_forex_config(self):
        cfg = get_config("forex")
        assert cfg.conviction_threshold == 60
        assert cfg.regime_cooldown_bars == 4
        assert cfg.max_hold_multiplier == 0.7
        assert cfg.volume_weight_bonus == 0.5

    def test_unknown_asset_class_defaults_to_crypto(self):
        cfg = get_config("commodities")
        assert cfg.conviction_threshold == 55
        assert cfg is get_config("crypto")


# ═══════════════════════════════════════════════════════════════════════════════
# get_conviction_threshold tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetConvictionThreshold:
    def test_crypto_threshold(self):
        assert get_conviction_threshold("crypto") == 55

    def test_equity_threshold(self):
        assert get_conviction_threshold("equity") == 65

    def test_forex_threshold(self):
        assert get_conviction_threshold("forex") == 60

    def test_unknown_falls_back_to_crypto(self):
        assert get_conviction_threshold("bonds") == 55


# ═══════════════════════════════════════════════════════════════════════════════
# get_session_adjustment tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetSessionAdjustment:
    def test_crypto_always_zero(self):
        # Crypto is 24/7, no session adjustments
        for hour in [0, 8, 14, 20]:
            now = datetime(2026, 3, 10, hour, 0, tzinfo=timezone.utc)  # Tuesday
            assert get_session_adjustment("crypto", now) == 0

    def test_equity_always_zero(self):
        for hour in [0, 8, 14, 20]:
            now = datetime(2026, 3, 10, hour, 0, tzinfo=timezone.utc)
            assert get_session_adjustment("equity", now) == 0

    def test_forex_london_ny_overlap(self):
        # 13-16 UTC on a weekday
        now = datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc)  # Tuesday 14:00 UTC
        assert get_session_adjustment("forex", now) == -10

    def test_forex_london_ny_overlap_boundary_start(self):
        now = datetime(2026, 3, 10, 13, 0, tzinfo=timezone.utc)
        assert get_session_adjustment("forex", now) == -10

    def test_forex_london_ny_overlap_boundary_end(self):
        # 16:00 is NOT in overlap (< 16 check)
        now = datetime(2026, 3, 10, 16, 0, tzinfo=timezone.utc)
        assert get_session_adjustment("forex", now) == 0

    def test_forex_asian_session(self):
        # 0-8 UTC on a weekday
        now = datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc)  # Tuesday 03:00 UTC
        assert get_session_adjustment("forex", now) == 5

    def test_forex_asian_session_boundary_start(self):
        now = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        assert get_session_adjustment("forex", now) == 5

    def test_forex_asian_session_boundary_end(self):
        # 8:00 is NOT in Asian session (< 8 check)
        now = datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)
        assert get_session_adjustment("forex", now) == 0

    def test_forex_dead_zone_friday_evening(self):
        # Friday 22:00 UTC
        now = datetime(2026, 3, 13, 22, 0, tzinfo=timezone.utc)  # Friday
        assert get_session_adjustment("forex", now) == 15

    def test_forex_dead_zone_saturday(self):
        now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)  # Saturday
        assert get_session_adjustment("forex", now) == 15

    def test_forex_dead_zone_sunday_morning(self):
        now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)  # Sunday 10:00
        assert get_session_adjustment("forex", now) == 15

    def test_forex_dead_zone_ends_sunday_evening(self):
        # Sunday 22:00 UTC — session reopens
        now = datetime(2026, 3, 15, 22, 0, tzinfo=timezone.utc)  # Sunday 22:00
        assert get_session_adjustment("forex", now) == 0

    def test_forex_friday_before_close_no_dead_zone(self):
        # Friday 20:00 UTC — before dead zone starts at 21:00
        now = datetime(2026, 3, 13, 20, 0, tzinfo=timezone.utc)
        assert get_session_adjustment("forex", now) == 0

    def test_forex_regular_session_no_adjustment(self):
        # Tuesday 10:00 UTC — not overlap, not Asian, not dead zone
        now = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
        assert get_session_adjustment("forex", now) == 0

    def test_unknown_asset_no_adjustment(self):
        now = datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc)
        assert get_session_adjustment("bonds", now) == 0

    def test_defaults_to_utcnow(self):
        # Just verify it doesn't crash without a time argument
        result = get_session_adjustment("forex")
        assert isinstance(result, int)


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregator integration tests — per-asset-class thresholds
# ═══════════════════════════════════════════════════════════════════════════════


class TestAggregatorAssetClassThresholds:
    def test_equity_threshold_rejects_score_60(self):
        """Equity threshold is 65; score of 60 should be rejected (would pass crypto at 55)."""
        agg = SignalAggregator()
        sig = agg.compute(
            "AAPL", "equity", "EquityMomentum",
            technical_score=60,
        )
        assert not sig.entry_approved
        assert sig.conviction_threshold == 65

    def test_crypto_threshold_approves_score_60(self):
        """Crypto threshold is 55; score of 60 should be approved."""
        agg = SignalAggregator()
        sig = agg.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            technical_score=60,
        )
        assert sig.entry_approved
        assert sig.conviction_threshold == 55

    def test_forex_threshold_between_crypto_and_equity(self):
        """Forex threshold is 60 (minus session adjustment).
        Score of 62 approved; score well below effective threshold rejected.
        """
        agg = SignalAggregator()
        sig_pass = agg.compute(
            "EUR/USD", "forex", "ForexTrend",
            technical_score=62,
        )
        assert sig_pass.entry_approved

        # Use score clearly below any possible effective threshold
        # (base 60, session adj can lower to 50, so 45 is always rejected)
        sig_fail = agg.compute(
            "EUR/USD", "forex", "ForexTrend",
            technical_score=45,
        )
        assert not sig_fail.entry_approved

    def test_composite_signal_stores_threshold_and_adjustment(self):
        agg = SignalAggregator()
        sig = agg.compute(
            "AAPL", "equity", "EquityMomentum",
            technical_score=80,
        )
        assert sig.conviction_threshold == 65
        assert sig.session_adjustment == 0

    def test_volume_weight_bonus_equity(self):
        """Equity volume_weight_bonus=1.3 scales scanner score up."""
        agg = SignalAggregator()
        sig = agg.compute(
            "AAPL", "equity", "EquityMomentum",
            scanner_score=50,
        )
        # 50 * 1.3 = 65
        assert sig.scanner_score == 65.0

    def test_volume_weight_bonus_forex(self):
        """Forex volume_weight_bonus=0.5 scales scanner score down."""
        agg = SignalAggregator()
        sig = agg.compute(
            "EUR/USD", "forex", "ForexTrend",
            scanner_score=80,
        )
        # 80 * 0.5 = 40
        assert sig.scanner_score == 40.0

    def test_volume_weight_bonus_crypto_no_change(self):
        """Crypto volume_weight_bonus=1.0 leaves scanner score unchanged."""
        agg = SignalAggregator()
        sig = agg.compute(
            "BTC/USDT", "crypto", "CryptoInvestorV1",
            scanner_score=70,
        )
        assert sig.scanner_score == 70.0

    def test_volume_weight_bonus_clamped_at_100(self):
        """Scanner score * bonus should not exceed 100."""
        agg = SignalAggregator()
        sig = agg.compute(
            "AAPL", "equity", "EquityMomentum",
            scanner_score=90,  # 90 * 1.3 = 117, clamped to 100
        )
        assert sig.scanner_score == 100.0


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregator cooldown uses per-asset-class bars
# ═══════════════════════════════════════════════════════════════════════════════


class TestAggregatorCooldownPerAssetClass:
    def test_equity_cooldown_3_bars(self):
        """Equity uses 3-bar cooldown (shorter than crypto's 6)."""
        agg = SignalAggregator()
        bullish = _regime_state(Regime.STRONG_TREND_UP, 0.9)
        ranging = _regime_state(Regime.RANGING, 0.7)

        # Set initial regime
        agg.compute("AAPL", "equity", "EquityMomentum", regime_state=bullish)
        # Trigger regime change
        agg.compute("AAPL", "equity", "EquityMomentum", regime_state=ranging)

        # After 3 bars the cooldown should wear off (equity cooldown = 3)
        for _ in range(3):
            sig = agg.compute("AAPL", "equity", "EquityMomentum", regime_state=ranging)

        # Raw alignment for EquityMomentum in RANGING (0.7 confidence)
        raw = 20 * 0.7 + 50 * 0.3  # 29
        assert abs(sig.regime_score - raw) < 1.0

    def test_forex_cooldown_4_bars(self):
        """Forex uses 4-bar cooldown."""
        agg = SignalAggregator()
        bullish = _regime_state(Regime.STRONG_TREND_UP, 0.9)
        ranging = _regime_state(Regime.RANGING, 0.7)

        agg.compute("EUR/USD", "forex", "ForexTrend", regime_state=bullish)
        # Trigger change — bar 0 (penalised)
        sig = agg.compute("EUR/USD", "forex", "ForexTrend", regime_state=ranging)
        raw = 15 * 0.7 + 50 * 0.3
        expected_penalised = raw * REGIME_COOLDOWN_PENALTY
        assert abs(sig.regime_score - expected_penalised) < 1.0

        # Bars 1, 2, 3 still penalised (cooldown = 4)
        for _ in range(3):
            sig = agg.compute("EUR/USD", "forex", "ForexTrend", regime_state=ranging)
        # Bar 3 is the last penalised bar

        # Bar 4 — penalty gone
        sig = agg.compute("EUR/USD", "forex", "ForexTrend", regime_state=ranging)
        assert abs(sig.regime_score - raw) < 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Exit manager integration — max_hold_multiplier
# ═══════════════════════════════════════════════════════════════════════════════


NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)


class TestExitManagerMaxHoldMultiplier:
    def test_equity_doubles_hold_time(self):
        """Equity max_hold_multiplier=2.0 doubles the base hold hours."""
        # Equity: 168 * 2.0 = 336h. At 200h in, should not exit yet.
        entry_time = NOW - timedelta(hours=200)
        advice = advise_exit(
            symbol="AAPL",
            strategy_name="CryptoInvestorV1",
            asset_class="equity",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=entry_time,
            current_time=NOW,
            current_profit_pct=0.01,
        )
        # 200h < 336h (168 * 2.0 * 1.0 regime), so no time exit
        assert not advice.should_exit

    def test_equity_eventually_triggers_time_exit(self):
        """Equity holds longer, but still triggers after max_hold * multiplier."""
        # Equity: 168 * 2.0 = 336h + regime 1.0 = 336h. At 340h should exit.
        entry_time = NOW - timedelta(hours=340)
        advice = advise_exit(
            symbol="AAPL",
            strategy_name="CryptoInvestorV1",
            asset_class="equity",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=entry_time,
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert advice.should_exit
        assert "Time limit" in advice.reason

    def test_forex_shortens_hold_time(self):
        """Forex max_hold_multiplier=0.7 shortens hold time."""
        # Forex: 48 * 0.7 = 33.6h * 1.0 regime = 33.6h. At 35h should exit.
        entry_time = NOW - timedelta(hours=35)
        advice = advise_exit(
            symbol="EUR/USD",
            strategy_name="BollingerMeanReversion",
            asset_class="forex",
            entry_regime=Regime.RANGING,
            current_regime_state=_regime_state(Regime.RANGING),
            entry_time=entry_time,
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert advice.should_exit

    def test_forex_no_exit_within_hold_time(self):
        """Forex at 20h < 33.6h (48 * 0.7 * 1.0 in STRONG_TREND_UP) should not trigger time exit."""
        entry_time = NOW - timedelta(hours=20)
        advice = advise_exit(
            symbol="EUR/USD",
            strategy_name="BollingerMeanReversion",
            asset_class="forex",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=entry_time,
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert not advice.should_exit

    def test_crypto_multiplier_unchanged(self):
        """Crypto max_hold_multiplier=1.0 preserves original behaviour."""
        # Crypto: 168 * 1.0 * 1.0 = 168h. At 170h should exit.
        entry_time = NOW - timedelta(hours=170)
        advice = advise_exit(
            symbol="BTC/USDT",
            strategy_name="CryptoInvestorV1",
            asset_class="crypto",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=entry_time,
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert advice.should_exit

    def test_default_strategy_with_asset_multiplier(self):
        """Unknown strategy uses DEFAULT_MAX_HOLD_HOURS, still applies multiplier."""
        # Equity: 96 * 2.0 = 192h. At 100h should NOT exit.
        entry_time = NOW - timedelta(hours=100)
        advice = advise_exit(
            symbol="AAPL",
            strategy_name="UnknownStrategy",
            asset_class="equity",
            entry_regime=Regime.STRONG_TREND_UP,
            current_regime_state=_regime_state(Regime.STRONG_TREND_UP),
            entry_time=entry_time,
            current_time=NOW,
            current_profit_pct=0.01,
        )
        assert not advice.should_exit
