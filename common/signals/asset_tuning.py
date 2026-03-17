"""Per-asset-class parameter overrides for the conviction system.

Crypto, equity, and forex have different volatility profiles, session hours,
spread characteristics, and volume reliability.  This module centralises
per-class tuning so the aggregator and exit manager adapt automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AssetClassConfig:
    """Tuning parameters for one asset class."""

    conviction_threshold: int  # Min composite score to approve entry
    regime_cooldown_bars: int  # Bars after regime change to apply penalty
    max_hold_multiplier: float  # Multiplier on strategy's base max_hold_hours
    volume_weight_bonus: float  # Multiplier on scanner/volume-related sub-scores
    spread_max_pct: float  # Max acceptable spread (future gating)
    session_bonus: dict[str, int] = field(
        default_factory=dict
    )  # Session-time conviction adjustments


ASSET_CONFIGS: dict[str, AssetClassConfig] = {
    "crypto": AssetClassConfig(
        conviction_threshold=40,  # Aggressive: lower bar for more entries
        regime_cooldown_bars=6,
        max_hold_multiplier=1.0,
        volume_weight_bonus=1.0,
        spread_max_pct=0.5,
        session_bonus={},  # 24/7, no session bonuses
    ),
    "equity": AssetClassConfig(
        conviction_threshold=50,  # Lowered from 65 for more entries
        regime_cooldown_bars=3,  # Faster adaptation (less volatile)
        max_hold_multiplier=2.0,  # Hold longer (daily bars, slower moves)
        volume_weight_bonus=1.3,  # Volume is more reliable signal
        spread_max_pct=0.2,
        session_bonus={},  # Only trades during NYSE hours (already enforced)
    ),
    "forex": AssetClassConfig(
        conviction_threshold=45,  # Lowered from 60 for more entries
        regime_cooldown_bars=4,
        max_hold_multiplier=0.7,  # Shorter holds (faster-moving)
        volume_weight_bonus=0.5,  # Tick volume less reliable
        spread_max_pct=0.1,
        session_bonus={
            "london_ny_overlap": -10,  # Lower threshold during best liquidity
            "asian": 5,  # Raise threshold (lower liquidity)
            "dead_zone": 15,  # Raise threshold significantly
        },
    ),
}


def get_config(asset_class: str) -> AssetClassConfig:
    """Return tuning config for an asset class, defaulting to crypto."""
    return ASSET_CONFIGS.get(asset_class, ASSET_CONFIGS["crypto"])


def get_conviction_threshold(asset_class: str) -> int:
    """Return the conviction threshold for an asset class."""
    return get_config(asset_class).conviction_threshold


def get_session_adjustment(asset_class: str, now: datetime | None = None) -> int:
    """Return the session-based threshold adjustment for an asset class.

    For forex, detects the current trading session and returns the
    corresponding conviction threshold adjustment:
    - London-NY overlap (13-16 UTC): -10 (lower threshold = easier entry)
    - Asian session (0-8 UTC): +5 (raise threshold)
    - Dead zone (Fri after NY close ~21 UTC through Sun ~22 UTC): +15

    Non-forex asset classes always return 0.
    """
    config = get_config(asset_class)
    if not config.session_bonus:
        return 0

    if now is None:
        now = datetime.now(timezone.utc)

    # Dead zone: Friday after 21:00 UTC through Sunday 22:00 UTC
    weekday = now.weekday()  # Mon=0 .. Sun=6
    hour = now.hour

    # Friday after NY close (21 UTC) or Saturday or Sunday before ~22 UTC
    if (weekday == 4 and hour >= 21) or weekday == 5 or (weekday == 6 and hour < 22):
        return config.session_bonus.get("dead_zone", 0)

    # London-NY overlap: 13-16 UTC (Mon-Fri)
    if 13 <= hour < 16:
        return config.session_bonus.get("london_ny_overlap", 0)

    # Asian session: 0-8 UTC (Mon-Fri)
    if 0 <= hour < 8:
        return config.session_bonus.get("asian", 0)

    # Regular session (no adjustment)
    return 0
