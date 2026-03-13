"""Signal aggregation thresholds, weights, and regime-strategy alignment matrices."""

from common.regime.regime_detector import Regime

# ── Signal source weights ────────────────────────────────────────────────────
# Must sum to 1.0.  When a source is unavailable its weight is
# redistributed proportionally to the remaining sources.
DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 0.30,
    "regime": 0.25,
    "ml": 0.20,
    "sentiment": 0.10,
    "scanner": 0.10,
    "win_rate": 0.05,
}

# ── Entry thresholds ─────────────────────────────────────────────────────────
# (offset_above_threshold, position_modifier, label)
# Actual threshold is conviction_threshold from asset_tuning + session adjustment.
ENTRY_TIER_OFFSETS: list[tuple[int, float, str]] = [
    (20, 1.0, "strong_buy"),   # threshold + 20
    (10, 0.7, "buy"),          # threshold + 10
    (0, 0.4, "cautious_buy"),  # threshold + 0
]

# ── Signal labels ────────────────────────────────────────────────────────────
LABEL_STRONG_BUY = "strong_buy"
LABEL_BUY = "buy"
LABEL_CAUTIOUS_BUY = "cautious_buy"
LABEL_NEUTRAL = "neutral"
LABEL_AVOID = "avoid"

# ── Regime-Strategy Alignment Matrices (0-100) ──────────────────────────────
# Higher = better alignment.  0 = hard-disable (instant reject).

CRYPTO_ALIGNMENT: dict[Regime, dict[str, int]] = {
    Regime.STRONG_TREND_UP:   {"CryptoInvestorV1": 95, "BollingerMeanReversion": 25, "VolatilityBreakout": 85},
    Regime.WEAK_TREND_UP:     {"CryptoInvestorV1": 70, "BollingerMeanReversion": 55, "VolatilityBreakout": 15},
    Regime.RANGING:           {"CryptoInvestorV1": 15, "BollingerMeanReversion": 95, "VolatilityBreakout":  5},
    Regime.WEAK_TREND_DOWN:   {"CryptoInvestorV1": 10, "BollingerMeanReversion": 75, "VolatilityBreakout":  5},
    Regime.STRONG_TREND_DOWN: {"CryptoInvestorV1":  0, "BollingerMeanReversion": 45, "VolatilityBreakout":  0},
    Regime.HIGH_VOLATILITY:   {"CryptoInvestorV1": 25, "BollingerMeanReversion": 65, "VolatilityBreakout": 70},
    Regime.UNKNOWN:           {"CryptoInvestorV1": 20, "BollingerMeanReversion": 45, "VolatilityBreakout": 10},
}

EQUITY_ALIGNMENT: dict[Regime, dict[str, int]] = {
    Regime.STRONG_TREND_UP:   {"EquityMomentum": 95, "EquityMeanReversion": 25},
    Regime.WEAK_TREND_UP:     {"EquityMomentum": 75, "EquityMeanReversion": 45},
    Regime.RANGING:           {"EquityMomentum": 20, "EquityMeanReversion": 90},
    Regime.WEAK_TREND_DOWN:   {"EquityMomentum": 10, "EquityMeanReversion": 65},
    Regime.STRONG_TREND_DOWN: {"EquityMomentum":  0, "EquityMeanReversion": 35},
    Regime.HIGH_VOLATILITY:   {"EquityMomentum": 25, "EquityMeanReversion": 55},
    Regime.UNKNOWN:           {"EquityMomentum": 20, "EquityMeanReversion": 35},
}

FOREX_ALIGNMENT: dict[Regime, dict[str, int]] = {
    Regime.STRONG_TREND_UP:   {"ForexTrend": 95, "ForexRange": 20},
    Regime.WEAK_TREND_UP:     {"ForexTrend": 70, "ForexRange": 40},
    Regime.RANGING:           {"ForexTrend": 15, "ForexRange": 95},
    Regime.WEAK_TREND_DOWN:   {"ForexTrend": 70, "ForexRange": 40},
    Regime.STRONG_TREND_DOWN: {"ForexTrend": 90, "ForexRange": 15},
    Regime.HIGH_VOLATILITY:   {"ForexTrend": 50, "ForexRange": 50},
    Regime.UNKNOWN:           {"ForexTrend": 30, "ForexRange": 30},
}

# Map asset_class -> alignment table
ALIGNMENT_TABLES: dict[str, dict[Regime, dict[str, int]]] = {
    "crypto": CRYPTO_ALIGNMENT,
    "equity": EQUITY_ALIGNMENT,
    "forex": FOREX_ALIGNMENT,
}

# ── Hard-disable rules ───────────────────────────────────────────────────────
# (regime, strategy) pairs that instantly reject regardless of other scores.
HARD_DISABLE: set[tuple[Regime, str]] = {
    (Regime.STRONG_TREND_DOWN, "CryptoInvestorV1"),
    (Regime.STRONG_TREND_DOWN, "VolatilityBreakout"),
    (Regime.STRONG_TREND_DOWN, "EquityMomentum"),
}

# ── Regime change cooldown ───────────────────────────────────────────────────
# REGIME_COOLDOWN_BARS moved to per-asset-class config in asset_tuning.py
REGIME_COOLDOWN_PENALTY = 0.6  # Multiply regime sub-score by this during cooldown

# ── Fallback scores for unavailable sources ──────────────────────────────────
FALLBACK_NEUTRAL = 50
FALLBACK_SCANNER = 0  # No bonus when scanner unavailable

# ── Exit Management Constants ────────────────────────────────────────────────

# Urgency levels for exit advice
URGENCY_IMMEDIATE = "immediate"
URGENCY_NEXT_CANDLE = "next_candle"
URGENCY_MONITOR = "monitor"

# ── Regime deterioration exit rules ──────────────────────────────────────────
# Map strategy -> set of regimes considered "favorable" at entry.
# If the current regime is *worse* than the entry regime for this strategy,
# we trigger a regime deterioration exit on profitable positions.
#
# "Worse" is defined by an alignment drop of this many points or more:
REGIME_DETERIORATION_THRESHOLD = 30  # alignment drop triggering exit

# ── Partial profit targets ───────────────────────────────────────────────────
# Per strategy: list of (profit_pct, close_fraction, label)
# Applied in order; once a tier is reached, that fraction is exited.
PARTIAL_PROFIT_TARGETS: dict[str, list[tuple[float, float, str]]] = {
    "CryptoInvestorV1": [
        (0.06, 1 / 3, "CIV1 1/3 at 6%"),
        (0.10, 1 / 2, "CIV1 1/2 at 10%"),
    ],
    "BollingerMeanReversion": [
        (0.02, 1 / 2, "BMR 1/2 at 2%"),
        (0.04, 3 / 4, "BMR 3/4 at 4%"),
    ],
    "VolatilityBreakout": [
        (0.05, 1 / 3, "VB 1/3 at 5%"),
    ],
    "EquityMomentum": [
        (0.04, 1 / 3, "EqMom 1/3 at 4%"),
        (0.08, 1 / 2, "EqMom 1/2 at 8%"),
    ],
    "EquityMeanReversion": [
        (0.03, 1 / 2, "EqMR 1/2 at 3%"),
        (0.06, 3 / 4, "EqMR 3/4 at 6%"),
    ],
    "ForexTrend": [
        (0.015, 1 / 3, "FxTrend 1/3 at 1.5%"),
        (0.03, 1 / 2, "FxTrend 1/2 at 3%"),
    ],
    "ForexRange": [
        (0.01, 1 / 2, "FxRange 1/2 at 1%"),
        (0.02, 3 / 4, "FxRange 3/4 at 2%"),
    ],
}

# ── Time-based exit ──────────────────────────────────────────────────────────
# Base max hold hours per strategy.
# Halved in STRONG_TREND_DOWN.
MAX_HOLD_HOURS: dict[str, float] = {
    "CryptoInvestorV1": 168.0,       # 7 days
    "BollingerMeanReversion": 48.0,  # 2 days
    "VolatilityBreakout": 72.0,      # 3 days
    "EquityMomentum": 240.0,         # 10 days (equity holds longer)
    "EquityMeanReversion": 120.0,    # 5 days
    "ForexTrend": 96.0,              # 4 days
    "ForexRange": 48.0,              # 2 days (range trades resolve fast)
}
DEFAULT_MAX_HOLD_HOURS = 96.0  # 4 days fallback

# Regime multiplier for max hold hours
TIME_EXIT_REGIME_MULTIPLIER: dict[Regime, float] = {
    Regime.STRONG_TREND_UP: 1.0,
    Regime.WEAK_TREND_UP: 1.0,
    Regime.RANGING: 0.8,
    Regime.WEAK_TREND_DOWN: 0.7,
    Regime.STRONG_TREND_DOWN: 0.5,
    Regime.HIGH_VOLATILITY: 0.6,
    Regime.UNKNOWN: 0.8,
}

# ── Regime-aware stop tightening ─────────────────────────────────────────────
# Multiplier on ATR-based stops; lower = tighter stop.
STOP_TIGHTENING_MULTIPLIER: dict[Regime, float] = {
    Regime.STRONG_TREND_UP: 1.0,
    Regime.WEAK_TREND_UP: 0.95,
    Regime.RANGING: 0.85,
    Regime.WEAK_TREND_DOWN: 0.80,
    Regime.STRONG_TREND_DOWN: 0.55,
    Regime.HIGH_VOLATILITY: 0.85,
    Regime.UNKNOWN: 0.85,
}
