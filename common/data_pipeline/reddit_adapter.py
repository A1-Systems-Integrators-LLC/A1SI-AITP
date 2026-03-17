"""Reddit Crypto Sentiment — public JSON feed scraper.

Fetches new posts from crypto subreddits via Reddit's public JSON API
(no API key or OAuth required). Scores posts using title + selftext.
Thread-safe with 15-minute cache.
"""

import logging
import threading
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, list]] = {}
_cache_lock = threading.Lock()
CACHE_TTL = 900  # 15 minutes

SUBREDDITS = [
    "CryptoCurrency",
    "Bitcoin",
    "ethereum",
]

USER_AGENT = "A1SI-AITP/1.0 (crypto sentiment bot)"

# Bullish/bearish keyword scoring (simple keyword scorer)
BULLISH_KEYWORDS = {
    "bullish", "moon", "pump", "surge", "rally", "breakout", "ath",
    "buy", "accumulate", "hodl", "undervalued", "adoption", "institutional",
    "upgrade", "partnership", "launch", "approval", "etf approved",
}
BEARISH_KEYWORDS = {
    "bearish", "crash", "dump", "plunge", "selloff", "sell-off", "sell off",
    "sell", "short", "overvalued", "bubble", "scam", "hack", "ban",
    "regulation", "crackdown", "liquidation", "capitulation", "rug pull",
}


@dataclass
class RedditPost:
    """Simplified Reddit post for scoring."""

    title: str
    selftext: str
    score: int
    upvote_ratio: float
    subreddit: str
    created_utc: float


def fetch_subreddit_posts(subreddit: str, limit: int = 25) -> list[RedditPost]:
    """Fetch recent posts from a subreddit's public JSON feed.

    Args:
        subreddit: Subreddit name (without r/).
        limit: Max posts to fetch (1-100).

    Returns:
        List of RedditPost objects.
    """
    try:
        url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()

        posts = []
        for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})
            posts.append(RedditPost(
                title=post_data.get("title", ""),
                selftext=post_data.get("selftext", "")[:500],  # Cap text length
                score=post_data.get("score", 0),
                upvote_ratio=post_data.get("upvote_ratio", 0.5),
                subreddit=subreddit,
                created_utc=post_data.get("created_utc", 0),
            ))
        return posts

    except Exception as e:
        logger.warning("Failed to fetch r/%s: %s", subreddit, e)
        return []


def score_post(post: RedditPost) -> float:
    """Score a single post's sentiment.

    Returns:
        Float in [-1, 1]. Positive = bullish, negative = bearish.
    """
    text = f"{post.title} {post.selftext}".lower()

    bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
    bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text)

    total = bullish_count + bearish_count
    if total == 0:
        return 0.0

    raw = (bullish_count - bearish_count) / total
    # Weight by upvote ratio (higher upvotes = more consensus)
    return raw * post.upvote_ratio


def fetch_reddit_sentiment() -> dict:
    """Fetch and aggregate sentiment from all tracked subreddits.

    Returns:
        Dict with: score (-1 to 1), post_count, subreddit_scores,
        modifier (for composite signal).
    """
    cache_key = "reddit_sentiment"
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and (now - cached[0]) < CACHE_TTL:
            return {"cached": True, **_aggregate(cached[1])}

    all_posts: list[RedditPost] = []
    for sub in SUBREDDITS:
        posts = fetch_subreddit_posts(sub, limit=25)
        all_posts.extend(posts)

    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), all_posts)

    return _aggregate(all_posts)


def _aggregate(posts: list[RedditPost]) -> dict:
    """Aggregate post scores into a single sentiment signal."""
    if not posts:
        return {
            "score": 0.0,
            "post_count": 0,
            "modifier": 0,
            "signal_score": 50,
            "subreddit_scores": {},
        }

    # Score per subreddit
    sub_scores: dict[str, list[float]] = {}
    for post in posts:
        s = score_post(post)
        sub_scores.setdefault(post.subreddit, []).append(s)

    sub_avgs = {sub: sum(scores) / len(scores) for sub, scores in sub_scores.items()}
    overall = sum(score_post(p) for p in posts) / len(posts)

    # Convert to modifier: strong sentiment = +-5 points
    if overall > 0.3:
        modifier = 5
    elif overall > 0.1:
        modifier = 3
    elif overall < -0.3:
        modifier = -5
    elif overall < -0.1:
        modifier = -3
    else:
        modifier = 0

    # Convert to 0-100 score for aggregator
    signal_score = max(0, min(100, (overall + 1) * 50))

    return {
        "score": round(overall, 3),
        "post_count": len(posts),
        "modifier": modifier,
        "signal_score": round(signal_score, 1),
        "subreddit_scores": {k: round(v, 3) for k, v in sub_avgs.items()},
    }


def clear_cache() -> None:
    """Clear the Reddit sentiment cache (for testing)."""
    with _cache_lock:
        _cache.clear()
