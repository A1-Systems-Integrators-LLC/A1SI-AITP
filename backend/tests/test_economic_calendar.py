"""Tests for economic calendar and forex position modifiers."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.calendar.economic_events import (
    FOMC_DATES,
    get_position_modifier,
    get_upcoming_events,
)


class TestUpcomingEvents:
    def test_fomc_within_window(self):
        # Use a known FOMC date
        fomc = FOMC_DATES[0]
        now = fomc - timedelta(hours=2)
        events = get_upcoming_events(hours=4, now=now)
        assert len(events) >= 1
        assert any("FOMC" in e["name"] for e in events)

    def test_no_events_outside_window(self):
        # Far from any event
        now = datetime(2025, 2, 15, 12, 0, tzinfo=timezone.utc)
        events = get_upcoming_events(hours=1, now=now)
        # Might still have NFP on first Friday, but not FOMC
        assert all("FOMC" not in e["name"] for e in events) or len(events) == 0

    def test_nfp_first_friday(self):
        # First Friday of Jan 2026 is Jan 2
        now = datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc)
        events = get_upcoming_events(hours=24, now=now)
        nfp = [e for e in events if "NFP" in e["name"] or "Non-Farm" in e["name"]]
        assert len(nfp) >= 1

    def test_empty_for_distant_future(self):
        now = datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)
        events = get_upcoming_events(hours=4, now=now)
        # Only NFP (first Friday) might match, FOMC/ECB won't
        fomc = [e for e in events if "FOMC" in e["name"]]
        assert len(fomc) == 0


class TestPositionModifier:
    def test_forex_high_impact_close(self):
        fomc = FOMC_DATES[0]
        now = fomc - timedelta(hours=1)
        mod = get_position_modifier("EUR/USD", "forex", hours=4, now=now)
        assert mod == 0.5

    def test_forex_high_impact_further(self):
        fomc = FOMC_DATES[0]
        now = fomc - timedelta(hours=3)
        mod = get_position_modifier("EUR/USD", "forex", hours=4, now=now)
        assert mod == 0.75

    def test_forex_no_event(self):
        now = datetime(2025, 2, 15, 12, 0, tzinfo=timezone.utc)
        mod = get_position_modifier("EUR/USD", "forex", hours=1, now=now)
        assert mod == 1.0

    def test_crypto_always_1(self):
        fomc = FOMC_DATES[0]
        now = fomc - timedelta(hours=1)
        mod = get_position_modifier("BTC/USDT", "crypto", hours=4, now=now)
        assert mod == 1.0

    def test_unaffected_currency_pair(self):
        fomc = FOMC_DATES[0]
        now = fomc - timedelta(hours=1)
        # AUD/NZD not directly affected by USD events
        mod = get_position_modifier("AUD/NZD", "forex", hours=4, now=now)
        # Should still be 1.0 because AUD/NZD doesn't contain USD
        assert mod == 1.0

    def test_ecb_affects_eur_pairs(self):
        from common.calendar.economic_events import ECB_DATES
        ecb = ECB_DATES[0]
        now = ecb - timedelta(hours=1)
        mod = get_position_modifier("EUR/USD", "forex", hours=4, now=now)
        assert mod < 1.0


@pytest.mark.django_db
class TestScheduledTask:
    def test_economic_calendar_task_exists(self):
        from django.conf import settings
        assert "economic_calendar" in settings.SCHEDULED_TASKS

    def test_economic_calendar_executor_exists(self):
        from core.services.task_registry import TASK_REGISTRY
        assert "economic_calendar" in TASK_REGISTRY
