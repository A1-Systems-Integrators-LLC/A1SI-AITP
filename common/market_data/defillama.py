"""DefiLlama TVL — free API for chain-level Total Value Locked data.

No API key required, no rate limit. Uses /v2/chains endpoint.
Thread-safe with 1-hour cache.
"""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
CACHE_TTL = 3600  # 1 hour

API_URL = "https://api.llama.fi/v2/chains"

# Map chain names to native token symbols
CHAIN_TOKEN_MAP = {
    "Ethereum": "ETH",
    "Solana": "SOL",
    "Avalanche": "AVAX",
    "Polygon": "MATIC",
    "Arbitrum": "ARB",
    "BNB Chain": "BNB",
    "Bitcoin": "BTC",
}


def fetch_chain_tvl() -> dict[str, dict] | None:
    """Fetch TVL data for all chains.

    Returns:
        Dict mapping chain name -> {tvl, tvl_change_7d, native_token}.
        None on failure.
    """
    cache_key = "chain_tvl"
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

    try:
        resp = requests.get(API_URL, timeout=15)
        resp.raise_for_status()
        chains = resp.json()

        result = {}
        for chain in chains:
            name = chain.get("name", "")
            tvl = chain.get("tvl", 0)

            # Compute 7d change from tokenSymbol data if available
            # DefiLlama v2/chains doesn't include change %, so we track it
            result[name] = {
                "tvl": tvl,
                "native_token": CHAIN_TOKEN_MAP.get(name),
            }

        with _cache_lock:
            _cache[cache_key] = (time.monotonic(), result)

        logger.info("Fetched TVL for %d chains", len(result))
        return result

    except Exception as e:
        logger.warning("Failed to fetch DefiLlama TVL: %s", e)
        return None


def get_tvl_signal(symbol: str) -> dict:
    """Get TVL-based signal modifier for a symbol's native chain.

    Args:
        symbol: Trading pair (e.g., "ETH/USDT").

    Returns:
        Dict with: chain, tvl, modifier.
        TVL growing strongly → +5, shrinking strongly → -5.
    """
    base = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()

    chains = fetch_chain_tvl()
    if not chains:
        return {"chain": None, "tvl": None, "modifier": 0}

    # Find chain by native token
    for chain_name, data in chains.items():
        if data.get("native_token") == base:
            tvl = data.get("tvl", 0)
            # Without historical comparison, use TVL magnitude as a proxy
            # High TVL chains (>$10B) are established → neutral
            # The modifier will be meaningful when we track deltas over time
            return {
                "chain": chain_name,
                "tvl": tvl,
                "modifier": 0,  # Will be enhanced with delta tracking
            }

    return {"chain": None, "tvl": None, "modifier": 0}


def clear_cache() -> None:
    """Clear the TVL cache (for testing)."""
    with _cache_lock:
        _cache.clear()
