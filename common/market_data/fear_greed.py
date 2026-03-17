"""Fear & Greed Index — free API from alternative.me.

Contrarian signal: Extreme Fear = bullish (+10), Extreme Greed = bearish (-10).
Thread-safe with 1-hour cache. No API key required.
"""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, dict]] = {}  # key -> (timestamp, data)
_cache_lock = threading.Lock()
CACHE_TTL = 3600  # 1 hour

API_URL = "https://api.alternative.me/fng/?limit=1"


def fetch_fear_greed() -> dict | None:
    """Fetch current Fear & Greed Index.

    Returns:
        Dict with: value (0-100), classification, timestamp.
        None on failure.
    """
    cache_key = "fear_greed"
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

    try:
        resp = requests.get(API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        entries = data.get("data", [])
        if not entries:
            logger.warning("Fear & Greed API returned empty data")
            return None

        entry = entries[0]
        result = {
            "value": int(entry["value"]),
            "classification": entry["value_classification"],
            "timestamp": int(entry.get("timestamp", 0)),
        }

        with _cache_lock:
            _cache[cache_key] = (time.monotonic(), result)

        logger.info("Fear & Greed: %d (%s)", result["value"], result["classification"])
        return result

    except Exception as e:
        logger.warning("Failed to fetch Fear & Greed: %s", e)
        return None


def get_fear_greed_signal(data: dict | None = None) -> dict:
    """Convert Fear & Greed Index to a contrarian score modifier.

    Returns:
        dict with: value, classification, modifier, score.
        - Extreme Fear (0-25): modifier +10, score 75
        - Fear (25-40): modifier +5, score 62
        - Neutral (40-60): modifier 0, score 50
        - Greed (60-75): modifier -5, score 38
        - Extreme Greed (75-100): modifier -10, score 25
    """
    if data is None:
        data = fetch_fear_greed()

    if data is None:
        return {"value": None, "classification": "unknown", "modifier": 0, "score": 50}

    value = data["value"]
    classification = data["classification"]

    if value <= 25:
        modifier = 10
        score = 75
    elif value <= 40:
        modifier = 5
        score = 62
    elif value <= 60:
        modifier = 0
        score = 50
    elif value <= 75:
        modifier = -5
        score = 38
    else:
        modifier = -10
        score = 25

    return {
        "value": value,
        "classification": classification,
        "modifier": modifier,
        "score": score,
    }


def clear_cache() -> None:
    """Clear the Fear & Greed cache (for testing)."""
    with _cache_lock:
        _cache.clear()
