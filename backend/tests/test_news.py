"""Tests for news/sentiment system — model, adapter, scorer, service, and API."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from market.models import NewsArticle

# ── Sentiment scorer tests ──────────────────────────────────


class TestSentimentScorer:
    @pytest.fixture(autouse=True)
    def _ensure_imports(self):
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()

    def test_positive_text(self):
        from common.sentiment.scorer import score_text

        score, label = score_text("Bitcoin rally continues with massive gains and bullish momentum")
        assert score > 0.1
        assert label == "positive"

    def test_negative_text(self):
        from common.sentiment.scorer import score_text

        score, label = score_text("Crypto crash leads to major losses and bearish outlook")
        assert score < -0.1
        assert label == "negative"

    def test_neutral_text(self):
        from common.sentiment.scorer import score_text

        score, label = score_text("The market traded in a range today with mixed results")
        assert label == "neutral"

    def test_empty_text(self):
        from common.sentiment.scorer import score_text

        score, label = score_text("")
        assert score == 0.0
        assert label == "neutral"

    def test_negation(self):
        from common.sentiment.scorer import score_text

        score_no_neg, _ = score_text("This is a bullish rally")
        score_negated, _ = score_text("This is not a bullish rally")
        assert score_negated < score_no_neg

    def test_intensifier(self):
        from common.sentiment.scorer import score_text

        # Use longer text so normalization doesn't clamp both to 1.0
        base = "the company reported a quiet day with some trading activity and a small rally"
        intense = "the company reported a quiet day with some trading activity and a massive rally"
        score_normal, _ = score_text(base)
        score_intense, _ = score_text(intense)
        assert score_intense > score_normal

    def test_score_article(self):
        from common.sentiment.scorer import score_article

        score, label = score_article(
            "Bitcoin surges to new record high",
            "The cryptocurrency market saw massive gains today as bulls took control",
        )
        assert score > 0
        assert label == "positive"

    def test_score_article_title_weighted_more(self):
        from common.sentiment.scorer import score_article

        # Positive title, negative summary — title should dominate (60%)
        score, _ = score_article(
            "Massive bullish breakout in crypto markets",
            "Some concerns about crash risks remain",
        )
        assert score > 0  # Title positivity should outweigh summary negativity


# ── News adapter tests ──────────────────────────────────────


class TestNewsAdapter:
    @pytest.fixture(autouse=True)
    def _ensure_imports(self):
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()

    def test_article_id_deterministic(self):
        from common.data_pipeline.news_adapter import article_id

        id1 = article_id("https://example.com/article-1")
        id2 = article_id("https://example.com/article-1")
        assert id1 == id2

    def test_article_id_different_urls(self):
        from common.data_pipeline.news_adapter import article_id

        id1 = article_id("https://example.com/article-1")
        id2 = article_id("https://example.com/article-2")
        assert id1 != id2

    def test_article_id_length(self):
        from common.data_pipeline.news_adapter import article_id

        aid = article_id("https://example.com/test")
        assert len(aid) == 64

    def test_rss_feeds_config(self):
        from common.data_pipeline.news_adapter import RSS_FEEDS

        assert "crypto" in RSS_FEEDS
        assert "equity" in RSS_FEEDS
        assert "forex" in RSS_FEEDS
        assert len(RSS_FEEDS["crypto"]) > 0

    def test_newsapi_queries_config(self):
        from common.data_pipeline.news_adapter import NEWSAPI_QUERIES

        assert "crypto" in NEWSAPI_QUERIES
        assert "equity" in NEWSAPI_QUERIES
        assert "forex" in NEWSAPI_QUERIES


# ── NewsArticle model tests ─────────────────────────────────


@pytest.mark.django_db
class TestNewsArticleModel:
    def test_create_article(self):
        article = NewsArticle.objects.create(
            article_id="abc123",
            title="Test Article",
            url="https://example.com/test",
            source="TestSource",
            published_at=datetime.now(tz=timezone.utc),
            asset_class="crypto",
            sentiment_score=0.5,
            sentiment_label="positive",
        )
        assert article.article_id == "abc123"
        assert article.sentiment_label == "positive"

    def test_unique_article_id(self):
        NewsArticle.objects.create(
            article_id="unique_test",
            title="First",
            url="https://example.com/1",
            source="Test",
            published_at=datetime.now(tz=timezone.utc),
        )
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            NewsArticle.objects.create(
                article_id="unique_test",
                title="Duplicate",
                url="https://example.com/2",
                source="Test",
                published_at=datetime.now(tz=timezone.utc),
            )

    def test_ordering_by_published_at_desc(self):
        now = datetime.now(tz=timezone.utc)
        NewsArticle.objects.create(
            article_id="old",
            title="Old",
            url="https://example.com/old",
            source="Test",
            published_at=now - timedelta(hours=2),
        )
        NewsArticle.objects.create(
            article_id="new",
            title="New",
            url="https://example.com/new",
            source="Test",
            published_at=now,
        )
        articles = list(NewsArticle.objects.values_list("article_id", flat=True))
        assert articles[0] == "new"
        assert articles[1] == "old"

    def test_str_representation(self):
        article = NewsArticle(
            article_id="str_test",
            title="My Test Article Title",
            sentiment_label="positive",
        )
        assert "positive" in str(article)
        assert "My Test Article" in str(article)


# ── NewsService tests ────────────────────────────────────────


@pytest.mark.django_db
class TestNewsService:
    def test_get_articles_empty(self):
        from market.services.news import NewsService

        service = NewsService()
        articles = service.get_articles("crypto")
        assert articles == []

    def test_get_articles_filtered(self):
        now = datetime.now(tz=timezone.utc)
        NewsArticle.objects.create(
            article_id="crypto1",
            title="Crypto Article",
            url="https://example.com/crypto",
            source="Test",
            published_at=now,
            asset_class="crypto",
        )
        NewsArticle.objects.create(
            article_id="equity1",
            title="Equity Article",
            url="https://example.com/equity",
            source="Test",
            published_at=now,
            asset_class="equity",
        )

        from market.services.news import NewsService

        service = NewsService()
        crypto_articles = service.get_articles("crypto")
        assert len(crypto_articles) == 1
        assert crypto_articles[0]["article_id"] == "crypto1"

    def test_get_sentiment_summary(self):
        now = datetime.now(tz=timezone.utc)
        NewsArticle.objects.create(
            article_id="sent1",
            title="Positive",
            url="https://example.com/1",
            source="Test",
            published_at=now,
            asset_class="crypto",
            sentiment_score=0.5,
            sentiment_label="positive",
        )
        NewsArticle.objects.create(
            article_id="sent2",
            title="Negative",
            url="https://example.com/2",
            source="Test",
            published_at=now,
            asset_class="crypto",
            sentiment_score=-0.3,
            sentiment_label="negative",
        )

        from market.services.news import NewsService

        service = NewsService()
        summary = service.get_sentiment_summary("crypto", hours=24)
        assert summary["total_articles"] == 2
        assert summary["positive_count"] == 1
        assert summary["negative_count"] == 1
        assert summary["avg_score"] == pytest.approx(0.1, abs=0.01)

    def test_get_sentiment_summary_empty(self):
        from market.services.news import NewsService

        service = NewsService()
        summary = service.get_sentiment_summary("crypto", hours=24)
        assert summary["total_articles"] == 0
        assert summary["avg_score"] == 0.0

    @patch("market.services.news.NewsService.fetch_and_store")
    def test_fetch_and_store_mock(self, mock_fetch):
        mock_fetch.return_value = 5
        from market.services.news import NewsService

        service = NewsService()
        count = service.fetch_and_store("crypto")
        assert count == 5


# ── API tests ────────────────────────────────────────────────


@pytest.mark.django_db
class TestNewsAPI:
    def test_list_requires_auth(self, api_client):
        resp = api_client.get("/api/market/news/")
        assert resp.status_code == 403

    def test_list_authenticated(self, authenticated_client):
        resp = authenticated_client.get("/api/market/news/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_with_asset_class_filter(self, authenticated_client):
        now = datetime.now(tz=timezone.utc)
        NewsArticle.objects.create(
            article_id="api_crypto",
            title="Crypto News",
            url="https://example.com/c",
            source="Test",
            published_at=now,
            asset_class="crypto",
        )
        resp = authenticated_client.get("/api/market/news/?asset_class=crypto")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_sentiment_endpoint(self, authenticated_client):
        resp = authenticated_client.get("/api/market/news/sentiment/?asset_class=crypto")
        assert resp.status_code == 200
        data = resp.json()
        assert "avg_score" in data
        assert "total_articles" in data

    def test_fetch_requires_auth(self, api_client):
        resp = api_client.post("/api/market/news/fetch/", {"asset_class": "crypto"}, format="json")
        assert resp.status_code == 403

    def test_fetch_invalid_asset_class(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/market/news/fetch/",
            {"asset_class": "invalid"},
            format="json",
        )
        assert resp.status_code == 400
