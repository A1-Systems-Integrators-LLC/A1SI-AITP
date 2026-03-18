"""Tests for the sentiment signal aggregation engine (common/sentiment/signal.py)."""

import sys
from pathlib import Path

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.sentiment.signal import (
    BULLISH_THRESHOLD,
    SentimentSignal,
    _compute_decay_weight,
    _compute_term_multiplier,
    compute_signal,
)


class TestDecayWeight:
    def test_zero_age_gives_weight_one(self):
        assert _compute_decay_weight(0.0, 6.0) == pytest.approx(1.0)

    def test_one_half_life_gives_half_weight(self):
        assert _compute_decay_weight(6.0, 6.0) == pytest.approx(0.5, abs=0.001)

    def test_two_half_lives_gives_quarter_weight(self):
        assert _compute_decay_weight(12.0, 6.0) == pytest.approx(0.25, abs=0.001)

    def test_zero_half_life_returns_one(self):
        assert _compute_decay_weight(10.0, 0.0) == 1.0


class TestTermMultiplier:
    def test_crypto_halving_term(self):
        mult = _compute_term_multiplier("Bitcoin halving event", "crypto")
        assert mult == 1.5

    def test_equity_earnings_term(self):
        mult = _compute_term_multiplier("Apple earnings beat expectations", "equity")
        assert mult == 1.5

    def test_forex_central_bank_term(self):
        mult = _compute_term_multiplier("Central bank rate decision", "forex")
        assert mult == 1.5

    def test_no_matching_terms(self):
        mult = _compute_term_multiplier("Regular news headline", "crypto")
        assert mult == 1.0

    def test_empty_text(self):
        assert _compute_term_multiplier("", "crypto") == 1.0

    def test_unknown_asset_class(self):
        assert _compute_term_multiplier("Bitcoin halving", "commodities") == 1.0


class TestComputeSignal:
    def test_empty_articles_returns_neutral(self):
        result = compute_signal([], "crypto")
        assert result.signal == 0.0
        assert result.conviction == 0.0
        assert result.signal_label == "neutral"
        assert result.position_modifier == 1.0
        assert result.article_count == 0

    def test_single_positive_article(self):
        articles = [
            {"sentiment_score": 0.5, "age_hours": 0.0, "title": "Bull market", "summary": ""},
        ]
        result = compute_signal(articles, "crypto", rescore=False)
        assert result.signal > 0
        assert result.signal_label == "bullish"
        assert result.article_count == 1

    def test_single_negative_article(self):
        articles = [
            {"sentiment_score": -0.5, "age_hours": 0.0, "title": "Market crash", "summary": ""},
        ]
        result = compute_signal(articles, "crypto")
        assert result.signal < 0
        assert result.signal_label == "bearish"

    def test_neutral_signal(self):
        articles = [
            {"sentiment_score": 0.05, "age_hours": 1.0, "title": "News", "summary": ""},
            {"sentiment_score": -0.05, "age_hours": 1.0, "title": "News", "summary": ""},
        ]
        result = compute_signal(articles, "crypto")
        assert result.signal_label == "neutral"
        assert abs(result.signal) <= BULLISH_THRESHOLD

    def test_temporal_decay_reduces_old_article_influence(self):
        """Recent article should dominate over old article."""
        articles = [
            {"sentiment_score": 0.8, "age_hours": 0.0, "title": "New", "summary": ""},
            {"sentiment_score": -0.8, "age_hours": 48.0, "title": "Old", "summary": ""},
        ]
        result = compute_signal(articles, "crypto", rescore=False)
        # Recent positive should outweigh old negative due to decay
        assert result.signal > 0

    def test_conviction_scales_with_article_count(self):
        # 5 articles with crypto threshold=20 → conviction=0.25
        articles = [
            {"sentiment_score": 0.3, "age_hours": 1.0, "title": "X", "summary": ""}
            for _ in range(5)
        ]
        result = compute_signal(articles, "crypto")
        assert result.conviction == pytest.approx(0.25, abs=0.01)

    def test_full_conviction_at_threshold(self):
        articles = [
            {"sentiment_score": 0.3, "age_hours": 1.0, "title": "X", "summary": ""}
            for _ in range(20)
        ]
        result = compute_signal(articles, "crypto")
        assert result.conviction == pytest.approx(1.0, abs=0.01)

    def test_conviction_caps_at_one(self):
        articles = [
            {"sentiment_score": 0.3, "age_hours": 1.0, "title": "X", "summary": ""}
            for _ in range(40)
        ]
        result = compute_signal(articles, "crypto")
        assert result.conviction == 1.0

    def test_position_modifier_bullish(self):
        """Full conviction + strong bullish → modifier > 1.0."""
        articles = [
            {"sentiment_score": 0.8, "age_hours": 0.5, "title": "X", "summary": ""}
            for _ in range(20)
        ]
        result = compute_signal(articles, "crypto", rescore=False)
        assert result.position_modifier > 1.0
        assert result.position_modifier <= 1.2

    def test_position_modifier_bearish(self):
        """Full conviction + strong bearish → modifier < 1.0."""
        articles = [
            {"sentiment_score": -0.8, "age_hours": 0.5, "title": "X", "summary": ""}
            for _ in range(20)
        ]
        result = compute_signal(articles, "crypto", rescore=False)
        assert result.position_modifier < 1.0
        assert result.position_modifier >= 0.8

    def test_position_modifier_clamped(self):
        """Modifier should be bounded to [0.8, 1.2]."""
        articles = [
            {"sentiment_score": 1.0, "age_hours": 0.0, "title": "X", "summary": ""}
            for _ in range(50)
        ]
        result = compute_signal(articles, "crypto")
        assert 0.8 <= result.position_modifier <= 1.2

    def test_term_relevance_boosts_signal(self):
        """Articles with domain terms should have more influence."""
        # Same scores, but one set has relevant terms
        plain_articles = [
            {"sentiment_score": 0.5, "age_hours": 1.0, "title": "Good news", "summary": ""},
            {"sentiment_score": -0.5, "age_hours": 1.0, "title": "Bad news", "summary": ""},
        ]
        term_articles = [
            {
                "sentiment_score": 0.5,
                "age_hours": 1.0,
                "title": "Bitcoin halving rally",
                "summary": "",
            },
            {"sentiment_score": -0.5, "age_hours": 1.0, "title": "Bad news", "summary": ""},
        ]
        plain_result = compute_signal(plain_articles, "crypto", rescore=False)
        term_result = compute_signal(term_articles, "crypto", rescore=False)
        # Term-boosted positive should shift signal more positive
        assert term_result.signal > plain_result.signal

    def test_different_asset_classes(self):
        """Each asset class should use its own half-life — visible with mixed-age articles."""
        articles = [
            {"sentiment_score": 0.8, "age_hours": 1.0, "title": "Recent", "summary": ""},
            {"sentiment_score": -0.3, "age_hours": 20.0, "title": "Old", "summary": ""},
        ]
        crypto_result = compute_signal(articles, "crypto", rescore=False)  # half_life=6
        equity_result = compute_signal(articles, "equity", rescore=False)  # half_life=12
        # Equity has longer half-life: old negative article decays less → lower signal
        # Both should still be positive (recent dominates), but differ
        assert crypto_result.signal != equity_result.signal

    def test_custom_half_life_override(self):
        """With mixed-age articles, half-life affects the decay weighting."""
        articles = [
            {"sentiment_score": 0.8, "age_hours": 1.0, "title": "New", "summary": ""},
            {"sentiment_score": -0.5, "age_hours": 12.0, "title": "Old", "summary": ""},
        ]
        result_short = compute_signal(articles, "crypto", half_life=3.0, rescore=False)
        result_long = compute_signal(articles, "crypto", half_life=24.0, rescore=False)
        # Shorter half-life → old negative decays more → more positive signal
        assert result_short.signal > result_long.signal

    def test_avg_age_hours(self):
        articles = [
            {"sentiment_score": 0.3, "age_hours": 2.0, "title": "X", "summary": ""},
            {"sentiment_score": 0.3, "age_hours": 6.0, "title": "Y", "summary": ""},
        ]
        result = compute_signal(articles, "crypto")
        assert result.avg_age_hours == pytest.approx(4.0, abs=0.01)

    def test_returns_dataclass(self):
        result = compute_signal([], "crypto")
        assert isinstance(result, SentimentSignal)
        assert result.asset_class == "crypto"

    def test_signal_clamped_to_bounds(self):
        """Signal should never exceed [-1, 1]."""
        articles = [
            {"sentiment_score": 1.0, "age_hours": 0.0, "title": "X", "summary": ""}
            for _ in range(100)
        ]
        result = compute_signal(articles, "crypto")
        assert -1.0 <= result.signal <= 1.0
