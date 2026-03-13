"""
Market Hours & Session Awareness
=================================
Tracks market open/close times for equities and forex.
Crypto is 24/7 and always returns open.
"""

import logging
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo

logger = logging.getLogger("market_hours")

ET = ZoneInfo("America/New_York")

# US market holidays for 2025-2026 (NYSE/NASDAQ)
# New Year's, MLK Day, Presidents' Day, Good Friday, Memorial Day,
# Juneteenth, Independence Day, Labor Day, Thanksgiving, Christmas
_US_HOLIDAYS_2025 = {
    (1, 1), (1, 20), (2, 17), (4, 18), (5, 26),
    (6, 19), (7, 4), (9, 1), (11, 27), (12, 25),
}
_US_HOLIDAYS_2026 = {
    (1, 1), (1, 19), (2, 16), (4, 3), (5, 25),
    (6, 19), (7, 3), (9, 7), (11, 26), (12, 25),
}
_US_HOLIDAYS = {
    2025: _US_HOLIDAYS_2025,
    2026: _US_HOLIDAYS_2026,
}


class TradingSession(str, Enum):
    CRYPTO = "crypto_24_7"
    US_EQUITY = "us_equity"
    FOREX = "forex"


# NYSE regular trading hours: 9:30 AM - 4:00 PM ET, Mon-Fri
_EQUITY_OPEN = time(9, 30)
_EQUITY_CLOSE = time(16, 0)

# Forex: Sun 5:00 PM ET - Fri 5:00 PM ET (continuous)
_FOREX_OPEN_DOW = 6   # Sunday
_FOREX_OPEN_TIME = time(17, 0)
_FOREX_CLOSE_DOW = 4  # Friday
_FOREX_CLOSE_TIME = time(17, 0)


def _is_us_holiday(dt: datetime) -> bool:
    """Check if a date is a US market holiday."""
    year_holidays = _US_HOLIDAYS.get(dt.year, set())
    return (dt.month, dt.day) in year_holidays


def _session_for_asset_class(asset_class: str) -> TradingSession:
    if asset_class == "equity":
        return TradingSession.US_EQUITY
    if asset_class == "forex":
        return TradingSession.FOREX
    return TradingSession.CRYPTO


class MarketHoursService:
    """Determine if markets are open and when they next open/close."""

    @staticmethod
    def is_market_open(asset_class: str, now: datetime | None = None) -> bool:
        """Check if the market for a given asset class is currently open."""
        if asset_class == "crypto":
            return True

        if now is None:
            now = datetime.now(timezone.utc)
        now_et = now.astimezone(ET)

        if asset_class == "equity":
            return MarketHoursService._is_equity_open(now_et)
        if asset_class == "forex":
            return MarketHoursService._is_forex_open(now_et)
        return True

    @staticmethod
    def _is_equity_open(now_et: datetime) -> bool:
        """Check if NYSE is currently open."""
        # Weekend
        if now_et.weekday() >= 5:
            return False
        # Holiday
        if _is_us_holiday(now_et):
            return False
        # Regular hours
        return _EQUITY_OPEN <= now_et.time() < _EQUITY_CLOSE

    @staticmethod
    def _is_forex_open(now_et: datetime) -> bool:
        """Check if forex market is open (Sun 5PM - Fri 5PM ET)."""
        dow = now_et.weekday()  # 0=Mon, 6=Sun
        t = now_et.time()

        # Saturday: always closed
        if dow == 5:
            return False
        # Sunday: open after 5PM ET
        if dow == 6:
            return t >= _FOREX_OPEN_TIME
        # Friday: close at 5PM ET
        if dow == 4:
            return t < _FOREX_CLOSE_TIME
        # Mon-Thu: always open
        return True

    @staticmethod
    def next_open(asset_class: str, now: datetime | None = None) -> datetime | None:
        """Get the next market open time. Returns None if already open or crypto."""
        if asset_class == "crypto":
            return None

        if now is None:
            now = datetime.now(timezone.utc)
        now_et = now.astimezone(ET)

        if asset_class == "equity":
            return MarketHoursService._next_equity_open(now_et)
        if asset_class == "forex":
            return MarketHoursService._next_forex_open(now_et)
        return None

    @staticmethod
    def _next_equity_open(now_et: datetime) -> datetime | None:
        if MarketHoursService._is_equity_open(now_et):
            return None

        # Find next weekday that's not a holiday
        candidate = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        if now_et.time() >= _EQUITY_OPEN:
            candidate += timedelta(days=1)

        for _ in range(10):
            if candidate.weekday() < 5 and not _is_us_holiday(candidate):
                return candidate.astimezone(timezone.utc)
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)  # pragma: no cover

    @staticmethod
    def _next_forex_open(now_et: datetime) -> datetime | None:
        if MarketHoursService._is_forex_open(now_et):
            return None

        # Forex opens Sunday 5PM ET
        days_until_sunday = (6 - now_et.weekday()) % 7
        if days_until_sunday == 0 and now_et.time() >= _FOREX_OPEN_TIME:  # pragma: no cover
            days_until_sunday = 7
        candidate = now_et.replace(
            hour=17, minute=0, second=0, microsecond=0,
        ) + timedelta(days=days_until_sunday)
        return candidate.astimezone(timezone.utc)

    @staticmethod
    def next_close(asset_class: str, now: datetime | None = None) -> datetime | None:
        """Get the next market close time. Returns None if closed or crypto."""
        if asset_class == "crypto":
            return None

        if now is None:
            now = datetime.now(timezone.utc)
        now_et = now.astimezone(ET)

        if asset_class == "equity":
            if not MarketHoursService._is_equity_open(now_et):
                return None
            close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            return close.astimezone(timezone.utc)

        if asset_class == "forex":
            if not MarketHoursService._is_forex_open(now_et):
                return None
            # Forex closes Friday 5PM ET
            days_until_friday = (4 - now_et.weekday()) % 7
            close = now_et.replace(
                hour=17, minute=0, second=0, microsecond=0,
            ) + timedelta(days=days_until_friday)
            return close.astimezone(timezone.utc)

        return None

    @staticmethod
    def get_session_info(asset_class: str, now: datetime | None = None) -> dict:
        """Get comprehensive session information for an asset class."""
        is_open = MarketHoursService.is_market_open(asset_class, now)
        session = _session_for_asset_class(asset_class)

        tz_map = {
            "crypto": "UTC",
            "equity": "America/New_York",
            "forex": "America/New_York",
        }

        result = {
            "is_open": is_open,
            "session": session.value,
            "timezone": tz_map.get(asset_class, "UTC"),
            "next_open": None,
            "next_close": None,
        }

        next_open = MarketHoursService.next_open(asset_class, now)
        if next_open:
            result["next_open"] = next_open.isoformat()

        next_close = MarketHoursService.next_close(asset_class, now)
        if next_close:
            result["next_close"] = next_close.isoformat()

        return result
