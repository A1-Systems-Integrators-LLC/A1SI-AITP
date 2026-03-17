"""Central signal combiner — aggregates intelligence sources into a composite conviction score."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from common.regime.regime_detector import Regime, RegimeDetector, RegimeState
from common.signals.asset_tuning import get_config, get_session_adjustment
from common.signals.constants import (
    ALIGNMENT_TABLES,
    DEFAULT_WEIGHTS,
    ENTRY_TIER_OFFSETS,
    FALLBACK_NEUTRAL,
    HARD_DISABLE,
    LABEL_AVOID,
    LABEL_NEUTRAL,
    REGIME_COOLDOWN_PENALTY,
)

logger = logging.getLogger("signal_aggregator")


@dataclass
class CompositeSignal:
    """Output of the signal aggregation pipeline."""

    symbol: str
    asset_class: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Component scores (0-100 each)
    ml_score: float = 50.0
    sentiment_score: float = 50.0
    regime_score: float = 50.0
    scanner_score: float = 0.0
    screen_score: float = 50.0
    technical_score: float = 50.0

    # Component confidences
    ml_confidence: float = 0.0
    sentiment_conviction: float = 0.0
    regime_confidence: float = 0.0

    # Computed outputs
    composite_score: float = 0.0
    signal_label: str = LABEL_NEUTRAL
    entry_approved: bool = False
    position_modifier: float = 0.0
    reasoning: list[str] = field(default_factory=list)

    # Metadata
    sources_available: list[str] = field(default_factory=list)
    hard_disabled: bool = False
    conviction_threshold: int = 55
    session_adjustment: int = 0


class SignalAggregator:
    """Aggregates multiple intelligence sources into a single conviction score.

    Sources (all fail gracefully):
    - technical: per-strategy indicator scoring
    - regime: regime-strategy alignment matrix
    - ml: model prediction probability
    - sentiment: news-based signal
    - scanner: market opportunity score
    - win_rate: historical performance for this strategy
    - funding: funding rate contrarian signal (crypto only)
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        regime_detector: RegimeDetector | None = None,
    ):
        self._weights = dict(weights or DEFAULT_WEIGHTS)
        self._regime_detector = regime_detector
        # Track last regime per symbol for cooldown detection
        self._last_regimes: dict[str, Regime] = {}
        self._regime_bar_counts: dict[str, int] = {}

    def compute(
        self,
        symbol: str,
        asset_class: str,
        strategy_name: str,
        *,
        # Pre-computed inputs (any can be None = unavailable)
        technical_score: float | None = None,
        regime_state: RegimeState | None = None,
        ml_probability: float | None = None,
        ml_confidence: float | None = None,
        sentiment_signal: float | None = None,
        sentiment_conviction: float | None = None,
        scanner_score: float | None = None,
        win_rate: float | None = None,
        macro_score: float | None = None,
    ) -> CompositeSignal:
        """Compute composite conviction signal.

        All source inputs are optional; unavailable sources get fallback
        scores and their weights are redistributed proportionally.
        """
        config = get_config(asset_class)
        session_adj = get_session_adjustment(asset_class)
        effective_threshold = config.conviction_threshold + session_adj

        result = CompositeSignal(
            symbol=symbol,
            asset_class=asset_class,
            conviction_threshold=config.conviction_threshold,
            session_adjustment=session_adj,
        )
        sources: dict[str, float] = {}
        available: list[str] = []

        # ── 1. Check hard-disable rules ──────────────────────────────────
        regime = regime_state.regime if regime_state else Regime.UNKNOWN
        if (regime, strategy_name) in HARD_DISABLE:
            result.hard_disabled = True
            result.composite_score = 0.0
            result.signal_label = LABEL_AVOID
            result.entry_approved = False
            result.position_modifier = 0.0
            result.reasoning = [
                f"Hard-disabled: {strategy_name} blocked in {regime.value}",
            ]
            logger.info(
                "Signal HARD-DISABLED: %s %s in %s",
                symbol,
                strategy_name,
                regime.value,
            )
            return result

        # ── 2. Collect component scores ──────────────────────────────────

        # Technical (always "available" — caller should compute it)
        if technical_score is not None:
            sources["technical"] = _clamp(technical_score)
            available.append("technical")
            result.technical_score = sources["technical"]

        # Regime alignment
        if regime_state is not None:
            regime_raw = self._get_regime_alignment(
                regime_state,
                strategy_name,
                asset_class,
            )
            # Apply cooldown penalty if regime just changed
            regime_raw = self._apply_cooldown(
                symbol,
                regime_state.regime,
                regime_raw,
                config.regime_cooldown_bars,
            )
            sources["regime"] = regime_raw
            available.append("regime")
            result.regime_score = regime_raw
            result.regime_confidence = regime_state.confidence

        # ML prediction
        if ml_probability is not None:
            sources["ml"] = _clamp(ml_probability * 100)
            available.append("ml")
            result.ml_score = sources["ml"]
            result.ml_confidence = ml_confidence or 0.0

        # Sentiment
        if sentiment_signal is not None:
            # Convert [-1, 1] signal to [0, 100] score
            sources["sentiment"] = _clamp((sentiment_signal + 1) * 50)
            available.append("sentiment")
            result.sentiment_score = sources["sentiment"]
            result.sentiment_conviction = sentiment_conviction or 0.0

        # Scanner opportunity (apply volume weight bonus)
        if scanner_score is not None:
            sources["scanner"] = _clamp(scanner_score * config.volume_weight_bonus)
            available.append("scanner")
            result.scanner_score = sources["scanner"]

        # Historical win rate
        if win_rate is not None:
            sources["win_rate"] = _clamp(win_rate)
            available.append("win_rate")
            result.screen_score = sources["win_rate"]

        # Funding rate signal (crypto only)
        if asset_class == "crypto":
            try:
                funding_score = self._score_funding_rate(symbol)
                if funding_score is not None:
                    sources["funding"] = _clamp(funding_score)
                    available.append("funding")
            except Exception:
                pass

        # Macro data (FRED: VIX, yield curve, fed funds, DXY)
        if macro_score is not None:
            sources["macro"] = _clamp(macro_score)
            available.append("macro")

        result.sources_available = available

        # ── 3. Compute weighted score with redistribution ────────────────
        if not available:
            result.composite_score = FALLBACK_NEUTRAL
            result.signal_label = LABEL_NEUTRAL
            result.reasoning = ["No signal sources available — using neutral fallback"]
            return result

        composite = self._weighted_score(sources, available)

        # BTC dominance modifier (crypto only, ~+-5 points)
        _dom_reason: str | None = None
        if asset_class == "crypto":
            try:
                from common.market_data.coingecko import get_dominance_signal

                dom_signal = get_dominance_signal()
                dom_modifier = dom_signal.get("modifier", 0)
                if dom_modifier != 0:
                    composite = _clamp(composite + dom_modifier)
                    _dom_reason = (
                        f"BTC dominance: {dom_signal['regime_label']}"
                        f" ({dom_signal['dominance']:.1f}%, {dom_modifier:+d})"
                    )
            except Exception:
                pass  # Graceful fallback

        # Fear & Greed contrarian modifier (crypto only, ~+-10 points)
        _fg_reason: str | None = None
        if asset_class == "crypto":
            try:
                from common.market_data.fear_greed import get_fear_greed_signal

                fg = get_fear_greed_signal()
                fg_mod = fg.get("modifier", 0)
                if fg_mod != 0:
                    composite = _clamp(composite + fg_mod)
                    _fg_reason = (
                        f"Fear & Greed: {fg.get('classification', 'unknown')}"
                        f" (value={fg['value']}, {fg_mod:+d})"
                    )
            except Exception:
                pass

        # Reddit sentiment modifier (crypto only, ~+-5 points)
        _reddit_reason: str | None = None
        if asset_class == "crypto":
            try:
                from common.data_pipeline.reddit_adapter import fetch_reddit_sentiment

                reddit = fetch_reddit_sentiment()
                reddit_mod = reddit.get("modifier", 0)
                if reddit_mod != 0:
                    composite = _clamp(composite + reddit_mod)
                    _reddit_reason = (
                        f"Reddit sentiment: {reddit['score']:+.2f}"
                        f" ({reddit['post_count']} posts, {reddit_mod:+d})"
                    )
            except Exception:
                pass

        # Trending coin modifier (crypto only, +3 points)
        _trending_reason: str | None = None
        if asset_class == "crypto":
            try:
                from common.market_data.coingecko import get_trending_modifier

                trending_mod = get_trending_modifier(symbol)
                if trending_mod > 0:
                    composite = _clamp(composite + trending_mod)
                    _trending_reason = f"Trending on CoinGecko (+{trending_mod})"
            except Exception:
                pass

        result.composite_score = round(composite, 1)

        # ── 4. Derive outputs ────────────────────────────────────────────
        result.signal_label = self._label(composite, effective_threshold)
        result.entry_approved = composite >= effective_threshold
        result.position_modifier = self._position_modifier(composite, effective_threshold)
        result.reasoning = self._build_reasoning(
            sources,
            available,
            composite,
            strategy_name,
            regime,
            effective_threshold,
        )
        if _dom_reason:
            result.reasoning.insert(0, _dom_reason)
        if _fg_reason:
            result.reasoning.insert(0, _fg_reason)
        if _reddit_reason:
            result.reasoning.insert(0, _reddit_reason)
        if _trending_reason:
            result.reasoning.insert(0, _trending_reason)

        # Economic calendar modifier (forex only)
        if asset_class == "forex":
            try:
                from common.calendar.economic_events import get_position_modifier as cal_modifier
                cal_mod = cal_modifier(symbol=symbol, asset_class=asset_class)
                if cal_mod < 1.0:
                    result.position_modifier *= cal_mod
                    result.reasoning.insert(0, f"Economic calendar: position scaled by {cal_mod}")
            except Exception:
                pass  # Graceful fallback

        logger.info(
            "Signal %s %s %s: score=%.1f approved=%s modifier=%.2f sources=%s",
            symbol,
            strategy_name,
            asset_class,
            composite,
            result.entry_approved,
            result.position_modifier,
            available,
        )

        return result

    def _score_funding_rate(self, symbol: str) -> float | None:
        """Score funding rate as a contrarian signal (crypto only).

        High positive funding rate = market overleveraged long = bearish signal (score < 50)
        High negative funding rate = market overleveraged short = bullish signal (score > 50)
        Near zero = neutral (score ~50)

        Returns:
            Score 0-100, or None if data unavailable.
        """
        try:
            from common.data_pipeline.pipeline import load_funding_rates

            df = load_funding_rates(symbol)
            if df is None or df.empty:
                return None

            # Use latest funding rate
            latest_rate = float(df["funding_rate"].iloc[-1])

            # Normalize: funding rates typically range from -0.1% to +0.1%
            # Map to 0-100 score (contrarian: high positive = low score)
            # -0.001 -> 75 (bullish), 0 -> 50, +0.001 -> 25 (bearish)
            score = 50 - (latest_rate * 25000)  # Scale factor for typical rates
            return max(0, min(100, score))

        except Exception:
            return None

    # ── Private helpers ──────────────────────────────────────────────────

    def _get_regime_alignment(
        self,
        state: RegimeState,
        strategy_name: str,
        asset_class: str,
    ) -> float:
        """Look up alignment score from the matrix."""
        table = ALIGNMENT_TABLES.get(asset_class, ALIGNMENT_TABLES["crypto"])
        regime_row = table.get(state.regime, {})
        raw = regime_row.get(strategy_name, FALLBACK_NEUTRAL)
        # Scale by regime confidence
        return raw * state.confidence + FALLBACK_NEUTRAL * (1 - state.confidence)

    def _apply_cooldown(
        self,
        symbol: str,
        current_regime: Regime,
        score: float,
        cooldown_bars: int,
    ) -> float:
        """Penalise regime sub-score during the cooldown period after a transition."""
        prev = self._last_regimes.get(symbol)
        if prev is not None and prev != current_regime:
            # Regime just changed — reset counter
            self._regime_bar_counts[symbol] = 0
            self._last_regimes[symbol] = current_regime
        elif prev is None:
            self._last_regimes[symbol] = current_regime
            self._regime_bar_counts[symbol] = cooldown_bars  # No penalty on first

        count = self._regime_bar_counts.get(symbol, cooldown_bars)
        self._regime_bar_counts[symbol] = min(count + 1, cooldown_bars + 1)

        if count < cooldown_bars:
            return score * REGIME_COOLDOWN_PENALTY
        return score

    def _weighted_score(
        self,
        sources: dict[str, float],
        available: list[str],
    ) -> float:
        """Weighted average with proportional redistribution of missing weights."""
        # Total weight of available sources
        total_available_weight = sum(self._weights.get(k, 0) for k in available)
        if total_available_weight <= 0:
            return FALLBACK_NEUTRAL

        # Apply fallback for missing sources and redistribute
        weighted_sum = 0.0
        for name in available:
            w = self._weights.get(name, 0) / total_available_weight
            weighted_sum += w * sources[name]

        return weighted_sum

    @staticmethod
    def _label(score: float, threshold: int) -> str:
        for offset, _, label in ENTRY_TIER_OFFSETS:
            if score >= threshold + offset:
                return label
        if score >= threshold:  # pragma: no cover — offset=0 in ENTRY_TIER_OFFSETS catches this
            return LABEL_NEUTRAL
        return LABEL_AVOID

    @staticmethod
    def _position_modifier(score: float, threshold: int) -> float:
        for offset, modifier, _ in ENTRY_TIER_OFFSETS:
            if score >= threshold + offset:
                return modifier
        return 0.0

    @staticmethod
    def _build_reasoning(
        sources: dict[str, float],
        available: list[str],
        composite: float,
        strategy_name: str,
        regime: Regime,
        threshold: int,
    ) -> list[str]:
        reasons: list[str] = []
        reasons.append(f"Strategy: {strategy_name}, Regime: {regime.value}")
        for name in available:
            reasons.append(f"  {name}: {sources[name]:.1f}")
        reasons.append(f"Composite: {composite:.1f}")
        if composite < threshold:
            reasons.append("REJECTED: below conviction threshold")
        return reasons


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))
