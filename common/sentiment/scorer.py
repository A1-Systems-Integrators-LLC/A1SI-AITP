"""Keyword-based financial sentiment scorer.

Zero dependencies (stdlib re only). Produces a score in [-1, 1] and a label.
"""

import re

# ── Positive financial terms ────────────────────────────────
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

# ── Negative financial terms ────────────────────────────────
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

# ── Intensifiers (1.5x weight) ──────────────────────────────
INTENSIFIERS: frozenset[str] = frozenset({
    "very", "massive", "sharp", "significant", "major",
    "extreme", "unprecedented", "huge", "enormous", "dramatic",
})

# ── Negators (flip polarity) ────────────────────────────────
NEGATORS: frozenset[str] = frozenset({
    "not", "no", "never", "without", "barely", "hardly",
    "neither", "nor",
})

_WORD_RE = re.compile(r"[a-z]+(?:-[a-z]+)*")

# Thresholds for label assignment
_POS_THRESHOLD = 0.1
_NEG_THRESHOLD = -0.1


def score_text(text: str) -> tuple[float, str]:
    """Score a single text string.

    Returns (score, label) where score is in [-1, 1] and
    label is 'positive', 'negative', or 'neutral'.
    """
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

        # Check intensifier for upcoming word
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
        else:
            # Reset negation after one non-sentiment word gap
            if negated and i > 0:
                # Allow negation to carry over one word
                pass
            else:
                negated = False

    # Normalize: divide by word count to get density, then clamp
    density = score / len(words)
    # Scale up so typical articles don't all cluster near 0
    normalized = max(-1.0, min(1.0, density * 10.0))

    if normalized > _POS_THRESHOLD:
        label = "positive"
    elif normalized < _NEG_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"

    return round(normalized, 4), label


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
