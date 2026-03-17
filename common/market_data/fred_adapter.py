"""FRED Economic Data — Federal Reserve Economic Data API.

Free API key from https://fred.stlouisfed.org/docs/api/api_key.html.
Tracks: Fed Funds Rate (DFF), Yield Curve (T10Y2Y), VIX (VIXCLS), DXY (DTWEXBGS).
Thread-safe with 4-hour cache.
"""

import logging
import os
import threading
import time

import requests

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, float | None]] = {}
_cache_lock = threading.Lock()
CACHE_TTL = 14400  # 4 hours

API_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Series we track
SERIES_CONFIG = {
    "DFF": {"name": "Fed Funds Rate", "category": "rates"},
    "T10Y2Y": {"name": "10Y-2Y Yield Curve", "category": "rates"},
    "VIXCLS": {"name": "VIX", "category": "volatility"},
    "DTWEXBGS": {"name": "Trade Weighted USD Index (DXY proxy)", "category": "currency"},
}


def _get_api_key() -> str | None:
    """Get FRED API key from environment."""
    return os.environ.get("FRED_API_KEY")


def fetch_series_latest(series_id: str) -> float | None:
    """Fetch the latest observation for a FRED series.

    Args:
        series_id: FRED series ID (e.g., "DFF").

    Returns:
        Latest value as float, or None on failure.
    """
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(series_id)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

    api_key = _get_api_key()
    if not api_key:
        logger.debug("FRED_API_KEY not set, skipping %s", series_id)
        return None

    try:
        resp = requests.get(
            API_BASE,
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        observations = data.get("observations", [])
        if not observations:
            return None

        value_str = observations[0].get("value", ".")
        if value_str == ".":
            return None  # FRED uses "." for missing data

        value = float(value_str)

        with _cache_lock:
            _cache[series_id] = (time.monotonic(), value)

        return value

    except Exception as e:
        logger.warning("Failed to fetch FRED %s: %s", series_id, e)
        return None


def fetch_macro_snapshot() -> dict:
    """Fetch all tracked macro indicators.

    Returns:
        Dict with: fed_funds, yield_curve, vix, dxy, macro_score (0-100).
    """
    fed_funds = fetch_series_latest("DFF")
    yield_curve = fetch_series_latest("T10Y2Y")
    vix = fetch_series_latest("VIXCLS")
    dxy = fetch_series_latest("DTWEXBGS")

    score = _compute_macro_score(fed_funds, yield_curve, vix, dxy)

    return {
        "fed_funds": fed_funds,
        "yield_curve": yield_curve,
        "vix": vix,
        "dxy": dxy,
        "macro_score": score,
    }


def _compute_macro_score(
    fed_funds: float | None,
    yield_curve: float | None,
    vix: float | None,
    dxy: float | None,
) -> float:
    """Compute composite macro score (0-100).

    Bullish factors (raise score): low VIX, positive yield curve, weak DXY
    Bearish factors (lower score): high VIX, inverted yield curve, strong DXY

    Returns:
        Score 0-100 where 50 = neutral.
    """
    components: list[float] = []

    # VIX: low = bullish, high = bearish
    if vix is not None:
        if vix < 15:
            components.append(75)  # Low fear
        elif vix < 20:
            components.append(60)
        elif vix < 30:
            components.append(40)
        else:
            components.append(20)  # High fear

    # Yield curve: positive = healthy, inverted = recession risk
    if yield_curve is not None:
        if yield_curve > 0.5:
            components.append(70)  # Healthy spread
        elif yield_curve > 0:
            components.append(55)
        elif yield_curve > -0.5:
            components.append(35)
        else:
            components.append(20)  # Deep inversion

    # Fed Funds: lower rates = more accommodative = bullish for risk assets
    if fed_funds is not None:
        if fed_funds < 2.0:
            components.append(70)
        elif fed_funds < 4.0:
            components.append(55)
        elif fed_funds < 5.5:
            components.append(40)
        else:
            components.append(25)

    # DXY: weaker dollar = bullish for crypto/commodities
    if dxy is not None:
        if dxy < 95:
            components.append(65)
        elif dxy < 100:
            components.append(55)
        elif dxy < 105:
            components.append(45)
        else:
            components.append(30)

    if not components:
        return 50.0  # Neutral fallback

    return round(sum(components) / len(components), 1)


def clear_cache() -> None:
    """Clear the FRED cache (for testing)."""
    with _cache_lock:
        _cache.clear()
