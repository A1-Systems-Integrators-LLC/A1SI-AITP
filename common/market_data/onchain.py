"""On-Chain Data Adapter
======================
Fetches BTC on-chain metrics from free public APIs:
- Blockchain.info: hash rate, transaction count, mempool
- Blockchair: exchange flows (free tier)

No API keys required. Cached to reduce API calls.
"""

import logging
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 3600  # 1 hour


def _get_cached(key: str) -> dict | None:
    """Get cached value if not expired."""
    if key in _cache:
        ts, data = _cache[key]
        if time.monotonic() - ts < CACHE_TTL:
            return data
    return None


def _set_cached(key: str, data: dict) -> None:
    """Cache a value with TTL."""
    _cache[key] = (time.monotonic(), data)


# ── Blockchain.info ───────────────────────────────────────────────────────────

BLOCKCHAIN_INFO_BASE = "https://api.blockchain.info"


def fetch_hash_rate() -> dict | None:
    """Fetch current BTC hash rate from Blockchain.info.

    Returns:
        Dict with hash_rate (TH/s), fetched_at, or None on failure.
    """
    cached = _get_cached("hash_rate")
    if cached is not None:
        return cached

    try:
        resp = httpx.get(
            f"{BLOCKCHAIN_INFO_BASE}/charts/hash-rate",
            params={"timespan": "7days", "format": "json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        if not values:
            return None

        latest = values[-1]
        previous = values[-2] if len(values) >= 2 else latest

        result = {
            "hash_rate": latest.get("y", 0),
            "hash_rate_previous": previous.get("y", 0),
            "change_pct": (
                (latest["y"] - previous["y"]) / previous["y"] * 100
                if previous.get("y", 0) > 0
                else 0.0
            ),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _set_cached("hash_rate", result)
        return result
    except Exception as e:
        logger.warning("Failed to fetch hash rate: %s", e)
        return None


def fetch_mempool_size() -> dict | None:
    """Fetch BTC mempool transaction count.

    Returns:
        Dict with mempool_count, fetched_at, or None on failure.
    """
    cached = _get_cached("mempool")
    if cached is not None:
        return cached

    try:
        resp = httpx.get(
            f"{BLOCKCHAIN_INFO_BASE}/charts/mempool-count",
            params={"timespan": "2days", "format": "json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        if not values:
            return None

        latest = values[-1]
        result = {
            "mempool_count": latest.get("y", 0),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _set_cached("mempool", result)
        return result
    except Exception as e:
        logger.warning("Failed to fetch mempool: %s", e)
        return None


def fetch_transaction_count() -> dict | None:
    """Fetch daily BTC transaction count.

    Returns:
        Dict with tx_count, tx_count_previous, change_pct, fetched_at.
    """
    cached = _get_cached("tx_count")
    if cached is not None:
        return cached

    try:
        resp = httpx.get(
            f"{BLOCKCHAIN_INFO_BASE}/charts/n-transactions",
            params={"timespan": "7days", "format": "json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        if not values:
            return None

        latest = values[-1]
        previous = values[-2] if len(values) >= 2 else latest

        result = {
            "tx_count": latest.get("y", 0),
            "tx_count_previous": previous.get("y", 0),
            "change_pct": (
                (latest["y"] - previous["y"]) / previous["y"] * 100
                if previous.get("y", 0) > 0
                else 0.0
            ),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _set_cached("tx_count", result)
        return result
    except Exception as e:
        logger.warning("Failed to fetch transaction count: %s", e)
        return None


# ── Composite Signal ──────────────────────────────────────────────────────────


def get_onchain_signal() -> dict:
    """Compute composite on-chain signal for BTC.

    Combines hash rate trend + transaction activity into a
    directional modifier for the signal aggregator.

    Returns:
        Dict with:
        - modifier: int score modifier (-5 to +5)
        - components: dict of individual signals
        - reasoning: str
    """
    modifier = 0
    components: dict[str, float] = {}
    reasons: list[str] = []

    # Hash rate trend
    hr = fetch_hash_rate()
    if hr is not None:
        hr_change = hr.get("change_pct", 0)
        components["hash_rate_change_pct"] = hr_change
        if hr_change > 5:
            modifier += 3
            reasons.append(f"Hash rate rising {hr_change:.1f}% (bullish)")
        elif hr_change < -5:
            modifier -= 3
            reasons.append(f"Hash rate falling {hr_change:.1f}% (bearish)")

    # Transaction count trend
    tx = fetch_transaction_count()
    if tx is not None:
        tx_change = tx.get("change_pct", 0)
        components["tx_count_change_pct"] = tx_change
        if tx_change > 10:
            modifier += 2
            reasons.append(f"TX count rising {tx_change:.1f}% (active network)")
        elif tx_change < -10:
            modifier -= 2
            reasons.append(f"TX count falling {tx_change:.1f}% (declining activity)")

    return {
        "modifier": max(-5, min(5, modifier)),
        "components": components,
        "reasoning": "; ".join(reasons) if reasons else "On-chain neutral",
    }


def clear_cache() -> None:
    """Clear the on-chain data cache."""
    _cache.clear()
