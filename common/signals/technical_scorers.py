"""Per-strategy technical sub-scores (0-100).

Each scorer takes indicator values and returns a composite technical
conviction score reflecting how strongly the indicators support entry
for that specific strategy.
"""

from __future__ import annotations


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ── CryptoInvestorV1 ─────────────────────────────────────────────────────────
# Trend-following: wants RSI in bullish zone, EMA alignment, MACD confirmation,
# volume presence, and reasonable ADX showing a trend.


def civ1_technical_score(
    rsi: float,
    ema_short: float,
    ema_long: float,
    close: float,
    macd_hist: float,
    volume_ratio: float,
    adx_value: float,
) -> float:
    """CryptoInvestorV1 technical score (0-100).

    Args:
        rsi: RSI(14) value.
        ema_short: EMA(21) current value.
        ema_long: EMA(100) current value.
        close: Current close price.
        macd_hist: MACD histogram value.
        volume_ratio: Current volume / 20-period average volume.
        adx_value: ADX(14) value.
    """
    score = 0.0

    # RSI depth (0-25): sweet spot 40-60 for entry, avoid overbought
    if 40 <= rsi <= 60:
        score += 25.0
    elif 30 <= rsi < 40:
        score += 20.0
    elif 60 < rsi <= 70:
        score += 15.0
    elif rsi > 70:
        score += 5.0  # Overbought, weaker signal
    else:
        score += 10.0  # Oversold, might catch falling knife

    # EMA alignment (0-25): price > short > long is ideal
    if close > ema_short > ema_long:
        score += 25.0
    elif close > ema_short:
        score += 15.0
    elif ema_short > ema_long:
        score += 10.0
    # else: bearish alignment, 0

    # MACD confirmation (0-20)
    if macd_hist > 0:
        score += min(20.0, 10.0 + macd_hist * 100)
    # Negative histogram = 0

    # Volume presence (0-15)
    score += _clamp(volume_ratio * 10, 0, 15)

    # ADX strength (0-15): want trending market 20-50
    if 20 <= adx_value <= 50:
        score += 15.0
    elif adx_value > 50:
        score += 10.0  # Very strong but might be exhausted
    elif adx_value > 15:
        score += 8.0
    # else: no trend, 0

    return _clamp(score)


# ── BollingerMeanReversion ───────────────────────────────────────────────────
# Mean-reversion: wants price near lower BB, oversold conditions, ranging market.


def bmr_technical_score(
    close: float,
    bb_lower: float,
    bb_mid: float,
    bb_width: float,
    rsi: float,
    stoch_k: float,
    mfi: float,
    volume_ratio: float,
) -> float:
    """BollingerMeanReversion technical score (0-100).

    Args:
        close: Current close price.
        bb_lower: Bollinger Band lower value.
        bb_mid: Bollinger Band middle (SMA).
        bb_width: Bollinger Band width (upper - lower) / mid.
        rsi: RSI(14) value.
        stoch_k: Stochastic %K value.
        mfi: Money Flow Index value.
        volume_ratio: Current volume / 20-period average volume.
    """
    score = 0.0

    # BB distance from lower band (0-30): closer to or below lower = better
    if bb_mid > 0:
        pct_from_lower = (close - bb_lower) / bb_mid * 100
        if pct_from_lower <= 0:
            score += 30.0  # At or below lower band
        elif pct_from_lower <= 2:
            score += 25.0
        elif pct_from_lower <= 5:
            score += 15.0
        elif pct_from_lower <= 10:
            score += 8.0

    # RSI oversold (0-20)
    if rsi <= 30:
        score += 20.0
    elif rsi <= 40:
        score += 15.0
    elif rsi <= 50:
        score += 8.0

    # Stochastic oversold (0-15)
    if stoch_k <= 20:
        score += 15.0
    elif stoch_k <= 30:
        score += 10.0
    elif stoch_k <= 40:
        score += 5.0

    # MFI oversold (0-15)
    if mfi <= 20:
        score += 15.0
    elif mfi <= 30:
        score += 10.0
    elif mfi <= 40:
        score += 5.0

    # Volume confirmation (0-10)
    score += _clamp(volume_ratio * 5, 0, 10)

    # BB width bonus for squeeze/expanding (0-10)
    if bb_width < 0.02:
        score += 10.0  # Squeeze — potential expansion
    elif bb_width < 0.05:
        score += 6.0

    return _clamp(score)


# ── VolatilityBreakout ───────────────────────────────────────────────────────
# Breakout: wants price near highs, expanding volatility, strong momentum.


def vb_technical_score(
    close: float,
    high_n: float,
    volume_ratio: float,
    bb_width: float,
    bb_width_prev: float,
    adx_value: float,
    rsi: float,
) -> float:
    """VolatilityBreakout technical score (0-100).

    Args:
        close: Current close price.
        high_n: N-period high (e.g. 20-day).
        volume_ratio: Current volume / 20-period average volume.
        bb_width: Current Bollinger Band width.
        bb_width_prev: Previous period Bollinger Band width.
        adx_value: ADX(14) value.
        rsi: RSI(14) value.
    """
    score = 0.0

    # Breakout margin (0-25): how close to / above N-period high
    if high_n > 0:
        pct_from_high = (close - high_n) / high_n * 100
        if pct_from_high >= 0:
            score += 25.0  # At or above high
        elif pct_from_high >= -1:
            score += 20.0
        elif pct_from_high >= -3:
            score += 12.0
        elif pct_from_high >= -5:
            score += 6.0

    # Volume surge (0-20)
    if volume_ratio >= 2.0:
        score += 20.0
    elif volume_ratio >= 1.5:
        score += 15.0
    elif volume_ratio >= 1.0:
        score += 8.0

    # BB expansion (0-15): widening bands = increasing volatility
    if bb_width_prev > 0:
        expansion = (bb_width - bb_width_prev) / bb_width_prev
        if expansion > 0.1:
            score += 15.0
        elif expansion > 0.05:
            score += 10.0
        elif expansion > 0:
            score += 5.0

    # ADX rising / strong trend (0-20)
    if adx_value >= 30:
        score += 20.0
    elif adx_value >= 20:
        score += 12.0
    elif adx_value >= 15:
        score += 6.0

    # RSI room (0-20): want room to run (40-70 ideal)
    if 40 <= rsi <= 70:
        score += 20.0
    elif 35 <= rsi < 40 or 70 < rsi <= 75:
        score += 12.0
    elif rsi > 75:
        score += 4.0  # Overbought — limited upside

    return _clamp(score)


# ── Generic equity/forex scorers ─────────────────────────────────────────────


def momentum_technical_score(
    rsi: float,
    ema_short: float,
    ema_long: float,
    close: float,
    macd_hist: float,
    adx_value: float,
    volume_ratio: float,
) -> float:
    """EquityMomentum / ForexTrend technical score (0-100)."""
    # Similar to CIV1 — trend-following is transferable
    return civ1_technical_score(
        rsi=rsi,
        ema_short=ema_short,
        ema_long=ema_long,
        close=close,
        macd_hist=macd_hist,
        volume_ratio=volume_ratio,
        adx_value=adx_value,
    )


def mean_reversion_technical_score(
    close: float,
    bb_lower: float,
    bb_mid: float,
    bb_width: float,
    rsi: float,
    stoch_k: float,
    mfi: float,
    volume_ratio: float,
) -> float:
    """EquityMeanReversion / ForexRange technical score (0-100)."""
    # Same mechanics as BMR — mean reversion is transferable
    return bmr_technical_score(
        close=close,
        bb_lower=bb_lower,
        bb_mid=bb_mid,
        bb_width=bb_width,
        rsi=rsi,
        stoch_k=stoch_k,
        mfi=mfi,
        volume_ratio=volume_ratio,
    )


# ── Dispatcher ───────────────────────────────────────────────────────────────

SCORER_MAP: dict[str, str] = {
    "CryptoInvestorV1": "civ1",
    "BollingerMeanReversion": "bmr",
    "VolatilityBreakout": "vb",
    "EquityMomentum": "momentum",
    "EquityMeanReversion": "mean_reversion",
    "ForexTrend": "momentum",
    "ForexRange": "mean_reversion",
}
