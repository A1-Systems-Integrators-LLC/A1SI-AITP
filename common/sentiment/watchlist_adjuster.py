"""Sentiment-driven watchlist adjuster.

Promotes symbols with strong positive sentiment to active scan,
flags symbols with strong negative sentiment for short scan.
Integrates into MarketScannerService.scan_all().
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Thresholds for watchlist actions
PROMOTE_THRESHOLD = 0.6  # Sentiment > 0.6 → promote to active scan
SHORT_FLAG_THRESHOLD = -0.5  # Sentiment < -0.5 → flag for short scan
DEMOTE_THRESHOLD = -0.3  # Sentiment < -0.3 → demote from active scan


@dataclass
class WatchlistAdjustment:
    """Recommended watchlist change based on sentiment."""

    symbol: str
    action: str  # "promote", "flag_short", "demote", "hold"
    sentiment_score: float
    reason: str


@dataclass
class WatchlistState:
    """Current watchlist state with sentiment-driven adjustments."""

    promoted: list[str] = field(default_factory=list)
    short_flagged: list[str] = field(default_factory=list)
    demoted: list[str] = field(default_factory=list)
    adjustments: list[WatchlistAdjustment] = field(default_factory=list)


def evaluate_symbol(
    symbol: str,
    sentiment_score: float,
) -> WatchlistAdjustment:
    """Evaluate a single symbol's sentiment for watchlist adjustment.

    Args:
        symbol: Trading pair.
        sentiment_score: Aggregate sentiment in [-1, 1].

    Returns:
        WatchlistAdjustment with recommended action.
    """
    if sentiment_score > PROMOTE_THRESHOLD:
        return WatchlistAdjustment(
            symbol=symbol,
            action="promote",
            sentiment_score=sentiment_score,
            reason=f"Strong positive sentiment ({sentiment_score:+.2f})"
            " → promote to active scan",
        )
    elif sentiment_score < SHORT_FLAG_THRESHOLD:
        return WatchlistAdjustment(
            symbol=symbol,
            action="flag_short",
            sentiment_score=sentiment_score,
            reason=f"Strong negative sentiment ({sentiment_score:+.2f})"
            " → flag for short scan",
        )
    elif sentiment_score < DEMOTE_THRESHOLD:
        return WatchlistAdjustment(
            symbol=symbol,
            action="demote",
            sentiment_score=sentiment_score,
            reason=f"Negative sentiment ({sentiment_score:+.2f})"
            " → demote from active scan",
        )
    else:
        return WatchlistAdjustment(
            symbol=symbol,
            action="hold",
            sentiment_score=sentiment_score,
            reason="Sentiment within normal range",
        )


def evaluate_watchlist(
    sentiment_scores: dict[str, float],
) -> WatchlistState:
    """Evaluate all symbols and produce watchlist adjustments.

    Args:
        sentiment_scores: Map of symbol → aggregate sentiment [-1, 1].

    Returns:
        WatchlistState with promoted, short-flagged, and demoted lists.
    """
    state = WatchlistState()

    for symbol, score in sentiment_scores.items():
        adj = evaluate_symbol(symbol, score)
        state.adjustments.append(adj)

        if adj.action == "promote":
            state.promoted.append(symbol)
        elif adj.action == "flag_short":
            state.short_flagged.append(symbol)
        elif adj.action == "demote":
            state.demoted.append(symbol)

    if state.promoted:
        logger.info(
            "Sentiment promoted %d symbols: %s",
            len(state.promoted),
            state.promoted[:5],
        )
    if state.short_flagged:
        logger.info(
            "Sentiment short-flagged %d symbols: %s",
            len(state.short_flagged),
            state.short_flagged[:5],
        )

    return state


def filter_scan_symbols(
    symbols: list[str],
    sentiment_scores: dict[str, float],
    include_promoted: bool = True,
    exclude_demoted: bool = True,
) -> list[str]:
    """Filter symbol list based on sentiment adjustments.

    Args:
        symbols: Original watchlist symbols.
        sentiment_scores: Map of symbol → sentiment score.
        include_promoted: Add promoted symbols not already in list.
        exclude_demoted: Remove demoted symbols.

    Returns:
        Adjusted symbol list.
    """
    state = evaluate_watchlist(sentiment_scores)

    result = list(symbols)

    if exclude_demoted:
        demoted_set = set(state.demoted)
        result = [s for s in result if s not in demoted_set]

    if include_promoted:
        existing = set(result)
        for s in state.promoted:
            if s not in existing:
                result.append(s)

    return result
