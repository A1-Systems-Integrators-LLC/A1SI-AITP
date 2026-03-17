"""Financial sentiment scorer — VADER primary, keyword fallback.

VADER (Valence Aware Dictionary and sEntiment Reasoner) produces more
nuanced scores than keyword matching. Falls back to keyword scorer
when vaderSentiment is not installed.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Try VADER import ──────────────────────────────────────────
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    _vader = SentimentIntensityAnalyzer()
    _HAS_VADER = True
    logger.info("VADER sentiment analyzer loaded")
except ImportError:  # pragma: no cover
    _vader = None
    _HAS_VADER = False
    logger.info("vaderSentiment not installed, using keyword fallback")


# ── Keyword-based fallback ────────────────────────────────────

POSITIVE_WORDS: frozenset[str] = frozenset({
    "bullish", "surge", "rally", "gains", "upgrade", "breakout",
    "soar", "jump", "boom", "profit", "growth", "optimism",
    "recovery", "upside", "outperform", "beat", "exceed",
    "momentum", "accumulation", "adoption", "innovation",
    "partnership", "milestone", "record", "approval",
    "expansion", "dividend", "buyback", "confidence",
    "strength", "positive", "support", "advance", "climb",
    "rebound", "uptick", "promising", "favorable", "opportunity",
    "breakthrough", "launch",
})

NEGATIVE_WORDS: frozenset[str] = frozenset({
    "bearish", "crash", "dump", "sell-off", "downgrade", "liquidation",
    "plunge", "drop", "slump", "loss", "decline", "pessimism",
    "recession", "downside", "underperform", "miss", "fail",
    "correction", "distribution", "ban", "fraud", "hack",
    "default", "bankruptcy", "investigation", "lawsuit",
    "contraction", "inflation", "shutdown", "warning",
    "weakness", "negative", "resistance", "retreat", "fall",
    "selloff", "downtick", "concerning", "unfavorable", "risk",
    "collapse", "crisis",
})

INTENSIFIERS: frozenset[str] = frozenset({
    "very", "massive", "sharp", "significant", "major",
    "extreme", "unprecedented", "huge", "enormous", "dramatic",
})

NEGATORS: frozenset[str] = frozenset({
    "not", "no", "never", "without", "barely", "hardly",
    "neither", "nor",
})

_WORD_RE = re.compile(r"[a-z]+(?:-[a-z]+)*")

# Thresholds for label assignment
_POS_THRESHOLD = 0.1
_NEG_THRESHOLD = -0.1


def _score_text_keyword(text: str) -> tuple[float, str]:
    """Keyword-based scorer (original implementation)."""
    if not text:
        return 0.0, "neutral"

    words = _WORD_RE.findall(text.lower())
    if not words:
        return 0.0, "neutral"

    score = 0.0
    negated = False

    for i, word in enumerate(words):
        if word in NEGATORS:
            negated = True
            continue

        intensifier = 1.0
        if i > 0 and words[i - 1] in INTENSIFIERS:
            intensifier = 1.5

        if word in POSITIVE_WORDS:
            val = 1.0 * intensifier
            score += -val if negated else val
            negated = False
        elif word in NEGATIVE_WORDS:
            val = -1.0 * intensifier
            score += -val if negated else val
            negated = False
        elif negated and i > 0:
            pass
        else:
            negated = False

    density = score / len(words)
    normalized = max(-1.0, min(1.0, density * 10.0))

    if normalized > _POS_THRESHOLD:
        label = "positive"
    elif normalized < _NEG_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"

    return round(normalized, 4), label


def _score_text_vader(text: str) -> tuple[float, str]:
    """VADER-based scorer — better handling of negation, caps, punctuation."""
    if not text or _vader is None:
        return 0.0, "neutral"

    scores = _vader.polarity_scores(text)
    compound = scores["compound"]  # Already in [-1, 1]

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    return round(compound, 4), label


def score_text(text: str) -> tuple[float, str]:
    """Score a single text string.

    Uses VADER when available, keyword fallback otherwise.
    Returns (score, label) where score is in [-1, 1] and
    label is 'positive', 'negative', or 'neutral'.
    """
    if _HAS_VADER:
        return _score_text_vader(text)
    return _score_text_keyword(text)


def score_article(title: str, summary: str = "") -> tuple[float, str]:
    """Score an article with weighted title (60%) and summary (40%).

    Returns (score, label).
    """
    title_score, _ = score_text(title)
    summary_score, _ = score_text(summary) if summary else (0.0, "neutral")

    combined = title_score * 0.6 + summary_score * 0.4
    combined = max(-1.0, min(1.0, combined))

    if combined > _POS_THRESHOLD:
        label = "positive"
    elif combined < _NEG_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"

    return round(combined, 4), label


def has_vader() -> bool:
    """Check if VADER is available."""
    return _HAS_VADER


def score_batch(texts: list[str]) -> list[tuple[float, str]]:
    """Score multiple texts efficiently.

    Returns list of (score, label) tuples.
    """
    return [score_text(t) for t in texts]
