"""CoinGecko BTC Dominance -- free API for BTC market cap dominance.

Uses the /api/v3/global endpoint (no API key required, rate limited).
Thread-safe with 5-minute cache.
"""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

_dominance_cache: dict[str, tuple[float, float]] = {}  # key -> (timestamp, value)
_cache_lock = threading.Lock()
CACHE_TTL = 300  # 5 minutes


def fetch_btc_dominance() -> float | None:
    """Fetch current BTC market cap dominance percentage.

    Returns:
        BTC dominance as a percentage (e.g., 52.3), or None on failure.
    """
    cache_key = "btc_dominance"
    now = time.monotonic()

    with _cache_lock:
        cached = _dominance_cache.get(cache_key)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/global",
            timeout=10,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        dominance = data.get("data", {}).get("market_cap_percentage", {}).get("btc")

        if dominance is not None:
            dominance = float(dominance)
            with _cache_lock:
                _dominance_cache[cache_key] = (time.monotonic(), dominance)
            logger.info("BTC dominance: %.1f%%", dominance)
            return dominance

        logger.warning("BTC dominance not found in API response")
        return None

    except Exception as e:
        logger.warning("Failed to fetch BTC dominance: %s", e)
        return None


def get_dominance_signal(dominance: float | None = None) -> dict:
    """Convert BTC dominance to a regime modifier signal.

    Returns:
        dict with: dominance, regime_label, modifier (applied to composite score).
        - dominance > 55%: "btc_dominant" -- BTC-favored, alt exposure reduced (modifier -5)
        - dominance 40-55%: "neutral" -- balanced market (modifier 0)
        - dominance < 40%: "alt_season" -- alt-favored, broader exposure (modifier +5)
    """
    if dominance is None:
        dominance = fetch_btc_dominance()

    if dominance is None:
        return {"dominance": None, "regime_label": "unknown", "modifier": 0}

    if dominance > 55:
        return {"dominance": dominance, "regime_label": "btc_dominant", "modifier": -5}
    elif dominance < 40:
        return {"dominance": dominance, "regime_label": "alt_season", "modifier": 5}
    else:
        return {"dominance": dominance, "regime_label": "neutral", "modifier": 0}


def clear_cache() -> None:
    """Clear the dominance cache (for testing)."""
    with _cache_lock:
        _dominance_cache.clear()
