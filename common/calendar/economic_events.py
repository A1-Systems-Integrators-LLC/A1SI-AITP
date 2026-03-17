"""Economic Calendar — dynamic + static event schedule for forex position sizing.

Primary: ForexFactory JSON feed (https://nfs.faireconomy.media/ff_calendar_thisweek.json).
Fallback: static FOMC/ECB/NFP dates when feed unavailable.
Thread-safe with 4-hour cache.
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

_ff_cache: dict[str, tuple[float, list]] = {}
_ff_cache_lock = threading.Lock()
FF_CACHE_TTL = 14400  # 4 hours
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Impact levels
HIGH_IMPACT = "high"
MEDIUM_IMPACT = "medium"

# Static recurring events with their typical schedule
# Format: (name, impact, day_of_week, week_of_month, currency_pairs)
# For specific dates, we use a pre-computed list for 2025-2026
RECURRING_EVENTS = [
    {
        "name": "US Non-Farm Payrolls (NFP)",
        "impact": HIGH_IMPACT,
        "affected_currencies": ["USD"],
        "schedule": "first_friday",  # First Friday of each month
    },
    {
        "name": "US CPI Release",
        "impact": HIGH_IMPACT,
        "affected_currencies": ["USD"],
        "schedule": "second_tuesday",  # ~10th-14th of each month
    },
]

# Pre-computed FOMC meeting dates (2025-2026)
FOMC_DATES = [
    # 2025
    datetime(2025, 1, 29, tzinfo=timezone.utc),
    datetime(2025, 3, 19, tzinfo=timezone.utc),
    datetime(2025, 5, 7, tzinfo=timezone.utc),
    datetime(2025, 6, 18, tzinfo=timezone.utc),
    datetime(2025, 7, 30, tzinfo=timezone.utc),
    datetime(2025, 9, 17, tzinfo=timezone.utc),
    datetime(2025, 11, 5, tzinfo=timezone.utc),
    datetime(2025, 12, 17, tzinfo=timezone.utc),
    # 2026
    datetime(2026, 1, 28, tzinfo=timezone.utc),
    datetime(2026, 3, 18, tzinfo=timezone.utc),
    datetime(2026, 4, 29, tzinfo=timezone.utc),
    datetime(2026, 6, 17, tzinfo=timezone.utc),
    datetime(2026, 7, 29, tzinfo=timezone.utc),
    datetime(2026, 9, 16, tzinfo=timezone.utc),
    datetime(2026, 11, 4, tzinfo=timezone.utc),
    datetime(2026, 12, 16, tzinfo=timezone.utc),
]

# ECB meeting dates (2025-2026)
ECB_DATES = [
    datetime(2025, 1, 30, tzinfo=timezone.utc),
    datetime(2025, 3, 6, tzinfo=timezone.utc),
    datetime(2025, 4, 17, tzinfo=timezone.utc),
    datetime(2025, 6, 5, tzinfo=timezone.utc),
    datetime(2025, 7, 17, tzinfo=timezone.utc),
    datetime(2025, 9, 11, tzinfo=timezone.utc),
    datetime(2025, 10, 30, tzinfo=timezone.utc),
    datetime(2025, 12, 18, tzinfo=timezone.utc),
    datetime(2026, 1, 22, tzinfo=timezone.utc),
    datetime(2026, 3, 5, tzinfo=timezone.utc),
    datetime(2026, 4, 16, tzinfo=timezone.utc),
    datetime(2026, 6, 4, tzinfo=timezone.utc),
    datetime(2026, 7, 16, tzinfo=timezone.utc),
    datetime(2026, 9, 10, tzinfo=timezone.utc),
    datetime(2026, 10, 29, tzinfo=timezone.utc),
    datetime(2026, 12, 17, tzinfo=timezone.utc),
]


def _get_first_friday(year: int, month: int) -> datetime:
    """Get the first Friday of a given month."""
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    # Monday is 0, Friday is 4
    days_until_friday = (4 - d.weekday()) % 7
    return d + timedelta(days=days_until_friday)


def _get_nfp_dates(year: int) -> list[datetime]:
    """Generate NFP dates (first Friday) for a year."""
    return [_get_first_friday(year, m) for m in range(1, 13)]


def fetch_forexfactory_events() -> list[dict]:
    """Fetch this week's events from ForexFactory JSON feed.

    Returns:
        List of event dicts with: title, country, date, impact, forecast, previous.
        Empty list on failure.
    """
    cache_key = "ff_events"
    now_mono = time.monotonic()

    with _ff_cache_lock:
        cached = _ff_cache.get(cache_key)
        if cached and (now_mono - cached[0]) < FF_CACHE_TTL:
            return cached[1]

    try:
        resp = requests.get(FF_URL, timeout=10)
        resp.raise_for_status()
        events = resp.json()

        # Normalize events
        result = []
        for ev in events:
            impact = ev.get("impact", "").lower()
            if impact not in ("high", "medium"):
                continue  # Skip low-impact events

            result.append({
                "name": ev.get("title", "Unknown"),
                "impact": HIGH_IMPACT if impact == "high" else MEDIUM_IMPACT,
                "country": ev.get("country", ""),
                "date_str": ev.get("date", ""),
                "affected_currencies": [ev.get("country", "").upper()],
            })

        with _ff_cache_lock:
            _ff_cache[cache_key] = (time.monotonic(), result)

        logger.info("Fetched %d high/medium-impact ForexFactory events", len(result))
        return result

    except Exception as e:
        logger.warning("ForexFactory feed failed, using static calendar: %s", e)
        return []


def clear_ff_cache() -> None:
    """Clear the ForexFactory cache (for testing)."""
    with _ff_cache_lock:
        _ff_cache.clear()


def _parse_ff_date(date_str: str) -> datetime | None:
    """Parse ForexFactory date string to datetime."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%b %d, %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            continue
    return None


def get_upcoming_events(
    hours: int = 4,
    now: datetime | None = None,
) -> list[dict]:
    """Get economic events within the next N hours.

    Primary: ForexFactory live feed. Fallback: static FOMC/ECB/NFP dates.

    Args:
        hours: Look-ahead window in hours.
        now: Current time (defaults to UTC now).

    Returns:
        List of event dicts with name, impact, time, and affected currencies.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    window_end = now + timedelta(hours=hours)
    events = []

    # Try ForexFactory live feed first
    ff_events = fetch_forexfactory_events()
    if ff_events:
        for ev in ff_events:
            dt = _parse_ff_date(ev.get("date_str", ""))
            if dt and now <= dt <= window_end:
                events.append({
                    "name": ev["name"],
                    "impact": ev["impact"],
                    "time": dt.isoformat(),
                    "affected_currencies": ev.get("affected_currencies", []),
                    "hours_until": (dt - now).total_seconds() / 3600,
                })
        if events:
            return events

    # Fallback: static FOMC dates
    for dt in FOMC_DATES:
        if now <= dt <= window_end:
            events.append({
                "name": "FOMC Rate Decision",
                "impact": HIGH_IMPACT,
                "time": dt.isoformat(),
                "affected_currencies": ["USD"],
                "hours_until": (dt - now).total_seconds() / 3600,
            })

    # Fallback: static ECB dates
    for dt in ECB_DATES:
        if now <= dt <= window_end:
            events.append({
                "name": "ECB Rate Decision",
                "impact": HIGH_IMPACT,
                "time": dt.isoformat(),
                "affected_currencies": ["EUR"],
                "hours_until": (dt - now).total_seconds() / 3600,
            })

    # Fallback: static NFP dates
    for year in (now.year, now.year + 1):
        for dt in _get_nfp_dates(year):
            if now <= dt <= window_end:
                events.append({
                    "name": "US Non-Farm Payrolls",
                    "impact": HIGH_IMPACT,
                    "time": dt.isoformat(),
                    "affected_currencies": ["USD"],
                    "hours_until": (dt - now).total_seconds() / 3600,
                })

    return events


def get_position_modifier(
    symbol: str = "",
    asset_class: str = "forex",
    hours: int = 4,
    now: datetime | None = None,
) -> float:
    """Get position size modifier based on upcoming economic events.

    Args:
        symbol: Trading pair (e.g., "EUR/USD").
        asset_class: Only applies to forex.
        hours: Look-ahead window.
        now: Current time.

    Returns:
        Position modifier: 0.5 (high-impact within 2h), 0.75 (medium/further),
        or 1.0 (no events).
    """
    if asset_class != "forex":
        return 1.0

    events = get_upcoming_events(hours=hours, now=now)
    if not events:
        return 1.0

    # Extract currencies from symbol
    symbol_currencies = set()
    if "/" in symbol:
        parts = symbol.split("/")
        symbol_currencies.add(parts[0].upper())
        symbol_currencies.add(parts[1].upper())

    # Find relevant events
    min_modifier = 1.0
    for event in events:
        affected = set(event.get("affected_currencies", []))
        if not symbol_currencies or affected & symbol_currencies:
            hours_until = event.get("hours_until", hours)
            if event["impact"] == HIGH_IMPACT and hours_until <= 2:
                min_modifier = min(min_modifier, 0.5)
            elif event["impact"] in (HIGH_IMPACT, MEDIUM_IMPACT):
                min_modifier = min(min_modifier, 0.75)

    return min_modifier
