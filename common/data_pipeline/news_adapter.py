"""News adapter — NewsAPI.org (optional) + RSS feeds per asset class.

Rate-limited, dedup by URL hash, stdlib-only for RSS parsing.
"""

import hashlib
import json
import logging
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("scheduler")

# ── RSS feed URLs by asset class ────────────────────────────

RSS_FEEDS: dict[str, list[dict[str, str]]] = {
    "crypto": [
        {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
        {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
        {"name": "Decrypt", "url": "https://decrypt.co/feed"},
    ],
    "equity": [
        {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
        {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories/"},
    ],
    "forex": [
        {"name": "DailyFX", "url": "https://www.dailyfx.com/feeds/market-news"},
        {"name": "ForexFactory", "url": "https://www.forexfactory.com/rss.php"},
    ],
}

# ── NewsAPI search terms by asset class ─────────────────────

NEWSAPI_QUERIES: dict[str, str] = {
    "crypto": "bitcoin OR ethereum OR crypto",
    "equity": "stock market OR earnings OR S&P 500",
    "forex": "forex OR currency OR central bank",
}

# ── Rate limiting ───────────────────────────────────────────

_newsapi_last_call: float = 0.0
_newsapi_lock = threading.Lock()
_NEWSAPI_MIN_INTERVAL = 900  # 15 min between calls (96/day, under 100 free tier)


def article_id(url: str) -> str:
    """Generate a deterministic article ID from URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:64]


def fetch_rss_feed(feed_url: str, source_name: str, timeout: int = 10) -> list[dict[str, Any]]:
    """Parse a single RSS feed, returning article dicts."""
    articles = []
    try:
        req = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "A1SI-AITP/0.1 NewsAdapter"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()

        root = ET.fromstring(data)

        # Handle both RSS 2.0 and Atom feeds
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item")  # RSS 2.0
        if not items:
            items = root.findall(".//atom:entry", ns)  # Atom

        for item in items[:20]:  # Cap per feed
            title = _get_text(item, "title", ns)
            link = _get_link(item, ns)
            pub_date = _get_text(item, "pubDate", ns) or _get_text(item, "published", ns)
            description = _get_text(item, "description", ns) or _get_text(item, "summary", ns)

            if not title or not link:
                continue

            published_at = _parse_date(pub_date) if pub_date else datetime.now(tz=timezone.utc)

            articles.append({
                "article_id": article_id(link),
                "title": title[:500],
                "url": link[:1000],
                "source": source_name,
                "summary": _strip_html(description or "")[:2000],
                "published_at": published_at,
            })

    except Exception as e:
        logger.warning("RSS fetch failed for %s (%s): %s", source_name, feed_url, e)

    return articles


def fetch_newsapi(
    asset_class: str, api_key: str, timeout: int = 10
) -> list[dict[str, Any]]:
    """Fetch articles from NewsAPI.org, rate-limited to 1 call per 15 min."""
    global _newsapi_last_call

    if not api_key:
        return []

    with _newsapi_lock:
        now = time.time()
        if now - _newsapi_last_call < _NEWSAPI_MIN_INTERVAL:
            logger.debug("NewsAPI rate limit: skipping (last call %.0fs ago)", now - _newsapi_last_call)
            return []
        _newsapi_last_call = now

    query = NEWSAPI_QUERIES.get(asset_class, "")
    if not query:
        return []

    url = (
        f"https://newsapi.org/v2/everything?"
        f"q={urllib.request.quote(query)}"
        f"&sortBy=publishedAt&pageSize=20&language=en"
    )

    articles = []
    try:
        req = urllib.request.Request(
            url,
            headers={
                "X-Api-Key": api_key,
                "User-Agent": "A1SI-AITP/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

        for item in data.get("articles", []):
            art_url = item.get("url", "")
            if not art_url:
                continue

            published_at = _parse_date(item.get("publishedAt", ""))

            articles.append({
                "article_id": article_id(art_url),
                "title": (item.get("title") or "")[:500],
                "url": art_url[:1000],
                "source": (item.get("source", {}).get("name") or "NewsAPI")[:100],
                "summary": (item.get("description") or "")[:2000],
                "published_at": published_at,
            })

    except Exception as e:
        logger.warning("NewsAPI fetch failed for %s: %s", asset_class, e)

    return articles


def fetch_all_news(
    asset_class: str, api_key: str = ""
) -> list[dict[str, Any]]:
    """Fetch news from all sources for an asset class. Returns deduped articles."""
    seen_ids: set[str] = set()
    articles: list[dict[str, Any]] = []

    # RSS feeds
    feeds = RSS_FEEDS.get(asset_class, [])
    for feed in feeds:
        for art in fetch_rss_feed(feed["url"], feed["name"]):
            if art["article_id"] not in seen_ids:
                seen_ids.add(art["article_id"])
                articles.append(art)

    # NewsAPI (if key available)
    for art in fetch_newsapi(asset_class, api_key):
        if art["article_id"] not in seen_ids:
            seen_ids.add(art["article_id"])
            articles.append(art)

    return articles


# ── Helpers ─────────────────────────────────────────────────

def _get_text(element: ET.Element, tag: str, ns: dict[str, str]) -> str:
    """Get text from child element, trying both plain and namespaced."""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    # Try Atom namespace
    child = element.find(f"atom:{tag}", ns)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _get_link(item: ET.Element, ns: dict[str, str]) -> str:
    """Extract link from RSS item or Atom entry."""
    # RSS 2.0
    link_el = item.find("link")
    if link_el is not None:
        if link_el.text:
            return link_el.text.strip()
        # Atom-style href attribute
        href = link_el.get("href")
        if href:
            return href.strip()
    # Atom
    link_el = item.find("atom:link", ns)
    if link_el is not None:
        href = link_el.get("href")
        if href:
            return href.strip()
    return ""


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    import re

    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_date(date_str: str) -> datetime:
    """Parse various date formats to UTC datetime."""
    if not date_str:
        return datetime.now(tz=timezone.utc)

    # ISO 8601
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822
        "%a, %d %b %Y %H:%M:%S GMT",
    ):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return datetime.now(tz=timezone.utc)
