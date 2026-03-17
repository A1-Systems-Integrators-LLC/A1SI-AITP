"""Aggregate sentiment signal engine — temporal decay, volume weighting, asset-class terms.

Produces actionable trading signals from per-article sentiment scores.
DB-agnostic: takes list[dict] article data, not ORM querysets.

Scorer cascade: FinBERT (best) → VADER (good) → keyword (fallback).
"""

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Half-life per asset class (hours) ─────────────────────
HALF_LIVES: dict[str, float] = {
    "crypto": 6.0,
    "equity": 12.0,
    "forex": 8.0,
}

# ── Volume conviction thresholds (article count for full conviction) ──
CONVICTION_THRESHOLDS: dict[str, int] = {
    "crypto": 20,
    "equity": 10,
    "forex": 8,
}

# ── Signal thresholds ─────────────────────────────────────
BULLISH_THRESHOLD = 0.15
BEARISH_THRESHOLD = -0.15

# ── Asset-class term relevance multipliers ────────────────
# Extra weight on an article's contribution if title/summary matches domain terms
ASSET_CLASS_TERMS: dict[str, dict[str, float]] = {
    "crypto": {
        "halving": 1.5,
        "defi": 1.3,
        "nft": 1.2,
        "staking": 1.3,
        "hack": 2.0,
        "exploit": 1.8,
        "whale": 1.3,
        "mining": 1.2,
        "blockchain": 1.1,
        "token": 1.1,
        "airdrop": 1.2,
        "regulation": 1.5,
        "sec": 1.4,
        "etf": 1.5,
    },
    "equity": {
        "earnings": 1.5,
        "dividend": 1.3,
        "fed": 1.3,
        "fomc": 1.4,
        "ipo": 1.3,
        "buyback": 1.3,
        "guidance": 1.4,
        "revenue": 1.2,
        "eps": 1.3,
        "margin": 1.2,
        "valuation": 1.2,
        "antitrust": 1.4,
    },
    "forex": {
        "rate": 1.3,
        "central bank": 1.5,
        "inflation": 1.4,
        "gdp": 1.3,
        "employment": 1.3,
        "nonfarm": 1.4,
        "boe": 1.3,
        "ecb": 1.4,
        "boj": 1.3,
        "intervention": 1.5,
        "carry trade": 1.3,
        "parity": 1.4,
    },
}


@dataclass
class SentimentSignal:
    """Aggregate sentiment signal for an asset class."""

    signal: float  # Weighted average score, [-1, 1]
    conviction: float  # 0-1, based on article volume
    signal_label: str  # "bullish", "bearish", "neutral"
    position_modifier: float  # 1.0 ± (signal * conviction * 0.2)
    article_count: int
    avg_age_hours: float
    asset_class: str


def _compute_decay_weight(age_hours: float, half_life: float) -> float:
    """Exponential decay weight: w = exp(-λ * age) where λ = ln(2) / half_life."""
    if half_life <= 0:
        return 1.0
    lam = math.log(2) / half_life
    return math.exp(-lam * age_hours)


def _compute_term_multiplier(text: str, asset_class: str) -> float:
    """Check text for domain-relevant terms, return highest multiplier found."""
    terms = ASSET_CLASS_TERMS.get(asset_class, {})
    if not terms or not text:
        return 1.0

    text_lower = text.lower()
    best = 1.0
    for term, mult in terms.items():
        if term in text_lower:
            best = max(best, mult)
    return best


def _rescore_articles(articles: list[dict]) -> list[dict]:
    """Re-score articles using best available NLP model.

    Cascade: FinBERT → VADER → original keyword score.
    Only re-scores if a better scorer is available.
    """
    if not articles:
        return articles

    # Try FinBERT first
    try:
        from common.sentiment.finbert import is_available, score_batch

        if is_available():
            texts = [
                f"{a.get('title', '')} {a.get('summary', '')}"
                for a in articles
            ]
            results = score_batch(texts)
            rescored = []
            for art, result in zip(articles, results, strict=True):
                art_copy = dict(art)
                if result is not None:
                    art_copy["sentiment_score"] = result.sentiment
                    art_copy["scorer"] = "finbert"
                rescored.append(art_copy)
            logger.debug("Re-scored %d articles with FinBERT", len(rescored))
            return rescored
    except Exception:
        pass

    # Try VADER
    try:
        from common.sentiment.scorer import has_vader, score_text

        if has_vader():
            rescored = []
            for art in articles:
                art_copy = dict(art)
                text = f"{art.get('title', '')} {art.get('summary', '')}"
                score, _ = score_text(text)
                art_copy["sentiment_score"] = score
                art_copy["scorer"] = "vader"
                rescored.append(art_copy)
            logger.debug("Re-scored %d articles with VADER", len(rescored))
            return rescored
    except Exception:
        pass

    # Fallback: use existing scores
    return articles


def compute_signal(
    articles: list[dict],
    asset_class: str = "crypto",
    half_life: float | None = None,
    conviction_threshold: int | None = None,
    rescore: bool = True,
) -> SentimentSignal:
    """Compute aggregate sentiment signal from article data.

    Each article dict should have:
        - sentiment_score: float [-1, 1]
        - age_hours: float (hours since publication)
        - title: str
        - summary: str (optional)

    Args:
        rescore: If True, re-score articles with best available NLP model.

    Returns a SentimentSignal with trading-relevant metrics.
    """
    if rescore:
        articles = _rescore_articles(articles)

    hl = half_life if half_life is not None else HALF_LIVES.get(asset_class, 6.0)
    ct = (
        conviction_threshold
        if conviction_threshold is not None
        else CONVICTION_THRESHOLDS.get(
            asset_class,
            20,
        )
    )

    if not articles:
        return SentimentSignal(
            signal=0.0,
            conviction=0.0,
            signal_label="neutral",
            position_modifier=1.0,
            article_count=0,
            avg_age_hours=0.0,
            asset_class=asset_class,
        )

    weighted_sum = 0.0
    weight_total = 0.0
    total_age = 0.0

    for art in articles:
        score = art.get("sentiment_score", 0.0)
        age = max(0.0, art.get("age_hours", 0.0))
        title = art.get("title", "")
        summary = art.get("summary", "")

        # Temporal decay
        decay_w = _compute_decay_weight(age, hl)

        # Asset-class term relevance (check both title and summary)
        term_mult = max(
            _compute_term_multiplier(title, asset_class),
            _compute_term_multiplier(summary, asset_class),
        )

        # Combined weight
        w = decay_w * term_mult
        weighted_sum += score * w
        weight_total += w
        total_age += age

    # Weighted average signal
    signal = weighted_sum / weight_total if weight_total > 0 else 0.0
    signal = max(-1.0, min(1.0, signal))

    # Volume conviction
    article_count = len(articles)
    conviction = min(1.0, article_count / ct) if ct > 0 else 1.0

    # Signal label
    if signal > BULLISH_THRESHOLD:
        signal_label = "bullish"
    elif signal < BEARISH_THRESHOLD:
        signal_label = "bearish"
    else:
        signal_label = "neutral"

    # Position modifier: 1.0 + (signal * conviction * 0.2) → [0.8, 1.2] at full conviction
    position_modifier = 1.0 + (signal * conviction * 0.2)
    position_modifier = max(0.8, min(1.2, position_modifier))

    avg_age = total_age / article_count if article_count > 0 else 0.0

    return SentimentSignal(
        signal=round(signal, 4),
        conviction=round(conviction, 4),
        signal_label=signal_label,
        position_modifier=round(position_modifier, 4),
        article_count=article_count,
        avg_age_hours=round(avg_age, 2),
        asset_class=asset_class,
    )
