"""NewsService — orchestrates news fetching, sentiment scoring, and storage."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from django.conf import settings
from django.db.models import Avg, Count, Q

logger = logging.getLogger("market")

NEWS_ARTICLE_CAP = 1000


class NewsService:
    def fetch_and_store(self, asset_class: str) -> int:
        """Fetch news, score sentiment, store in DB. Returns count of new articles."""
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from common.data_pipeline.news_adapter import fetch_all_news
        from common.sentiment.scorer import score_article

        from market.models import NewsArticle

        api_key = getattr(settings, "NEWSAPI_KEY", "")
        raw_articles = fetch_all_news(asset_class, api_key)

        if not raw_articles:
            return 0

        # Score sentiment and build model instances
        to_create = []
        for art in raw_articles:
            score, label = score_article(art["title"], art.get("summary", ""))
            to_create.append(
                NewsArticle(
                    article_id=art["article_id"],
                    title=art["title"],
                    url=art["url"],
                    source=art["source"],
                    summary=art.get("summary", ""),
                    published_at=art["published_at"],
                    asset_class=asset_class,
                    sentiment_score=score,
                    sentiment_label=label,
                )
            )

        # Bulk create, skip duplicates
        created = NewsArticle.objects.bulk_create(to_create, ignore_conflicts=True)
        new_count = len(created)

        # Enforce article cap — delete oldest beyond 1000
        total = NewsArticle.objects.count()
        if total > NEWS_ARTICLE_CAP:
            excess = total - NEWS_ARTICLE_CAP
            oldest_ids = list(
                NewsArticle.objects.order_by("published_at")
                .values_list("id", flat=True)[:excess]
            )
            NewsArticle.objects.filter(id__in=oldest_ids).delete()
            logger.info("Pruned %d old news articles (cap=%d)", excess, NEWS_ARTICLE_CAP)

        logger.info(
            "News fetch for %s: %d fetched, %d new",
            asset_class, len(raw_articles), new_count,
        )
        return new_count

    def get_articles(
        self,
        asset_class: str | None = None,
        symbol: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent articles, optionally filtered."""
        from market.models import NewsArticle

        qs = NewsArticle.objects.all()
        if asset_class:
            qs = qs.filter(asset_class=asset_class)
        if symbol:
            qs = qs.filter(symbols__contains=[symbol])

        return list(
            qs.values(
                "article_id", "title", "url", "source", "summary",
                "published_at", "symbols", "asset_class",
                "sentiment_score", "sentiment_label", "created_at",
            )[:limit]
        )

    def get_sentiment_summary(
        self,
        asset_class: str | None = None,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Aggregate sentiment stats for recent articles."""
        from market.models import NewsArticle

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        qs = NewsArticle.objects.filter(published_at__gte=cutoff)
        if asset_class:
            qs = qs.filter(asset_class=asset_class)

        agg = qs.aggregate(
            avg_score=Avg("sentiment_score"),
            total=Count("id"),
            positive=Count("id", filter=Q(sentiment_label="positive")),
            negative=Count("id", filter=Q(sentiment_label="negative")),
            neutral=Count("id", filter=Q(sentiment_label="neutral")),
        )

        avg_score = agg["avg_score"] or 0.0
        if avg_score > 0.1:
            overall_label = "positive"
        elif avg_score < -0.1:
            overall_label = "negative"
        else:
            overall_label = "neutral"

        return {
            "asset_class": asset_class or "all",
            "hours": hours,
            "total_articles": agg["total"],
            "avg_score": round(avg_score, 4),
            "overall_label": overall_label,
            "positive_count": agg["positive"],
            "negative_count": agg["negative"],
            "neutral_count": agg["neutral"],
        }
