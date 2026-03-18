"""Tests for Alpha Phase 3 — NLP Upgrade.

Covers: VADER scorer, FinBERT mock pipeline, sentiment signal rescoring,
weight rebalance, watchlist adjuster.
"""

import importlib.util
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")

_skip_no_vader = pytest.mark.skipif(
    importlib.util.find_spec("vaderSentiment") is None,
    reason="vaderSentiment not installed (CI)",
)

# ── VADER Scorer ────────────────────────────────────────────────────────────


@_skip_no_vader
class TestVADERScorer:
    """Tests for VADER-enhanced scorer.py."""

    def test_vader_available(self):
        from common.sentiment.scorer import has_vader
        assert has_vader() is True

    def test_score_text_positive(self):
        from common.sentiment.scorer import score_text
        score, label = score_text("Bitcoin surges to all-time high, great news!")
        assert score > 0
        assert label == "positive"

    def test_score_text_negative(self):
        from common.sentiment.scorer import score_text
        score, label = score_text("Crypto crash devastates market, terrible losses")
        assert score < 0
        assert label == "negative"

    def test_score_text_neutral(self):
        from common.sentiment.scorer import score_text
        score, label = score_text("The meeting was held yesterday")
        assert label == "neutral"

    def test_score_text_empty(self):
        from common.sentiment.scorer import score_text
        score, label = score_text("")
        assert score == 0.0
        assert label == "neutral"

    def test_score_article_weighted(self):
        from common.sentiment.scorer import score_article
        score, label = score_article(
            title="Amazing rally continues!",
            summary="Markets are looking strong with gains",
        )
        assert score > 0
        assert label == "positive"

    def test_score_article_title_only(self):
        from common.sentiment.scorer import score_article
        score, label = score_article(title="Market crashes hard")
        assert score < 0

    def test_score_batch(self):
        from common.sentiment.scorer import score_batch
        results = score_batch([
            "Great bullish news!",
            "Terrible crash incoming",
            "Regular update today",
        ])
        assert len(results) == 3
        assert results[0][0] > 0  # positive
        assert results[1][0] < 0  # negative

    def test_keyword_fallback_works(self):
        """Keyword scorer still produces valid output."""
        from common.sentiment.scorer import _score_text_keyword
        score, label = _score_text_keyword("bullish surge rally breakout")
        assert score > 0
        assert label == "positive"

    def test_keyword_negation(self):
        from common.sentiment.scorer import _score_text_keyword
        score, _ = _score_text_keyword("not bullish")
        assert score < 0  # Negated positive = negative

    def test_keyword_intensifier(self):
        from common.sentiment.scorer import _score_text_keyword
        s1, _ = _score_text_keyword(
            "the market saw a surge today in a normal trading session"
        )
        s2, _ = _score_text_keyword(
            "the market saw a massive surge today in a normal trading session"
        )
        assert s2 > s1  # Intensifier boosts score


# ── FinBERT ─────────────────────────────────────────────────────────────────


class TestFinBERT:
    """Tests for FinBERT integration (mocked pipeline)."""

    def test_is_available_checks_imports(self):
        from common.sentiment.finbert import is_available
        # Will be True if transformers+torch are installed, False otherwise
        result = is_available()
        assert isinstance(result, bool)

    def test_is_loaded_initially_false(self):
        from common.sentiment.finbert import is_loaded, reset
        reset()
        assert is_loaded() is False

    def test_map_label_to_score(self):
        from common.sentiment.finbert import _map_label_to_score
        assert _map_label_to_score("positive", 0.9) == 0.9
        assert _map_label_to_score("negative", 0.8) == -0.8
        assert _map_label_to_score("neutral", 0.7) == 0.0

    @patch("common.sentiment.finbert._load_pipeline")
    def test_score_text_with_mock_pipeline(self, mock_load):
        from common.sentiment.finbert import reset, score_text
        reset()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [{"label": "positive", "score": 0.95}]
        mock_load.return_value = mock_pipe
        result = score_text("Bitcoin rally")
        assert result is not None
        assert result.label == "positive"
        assert result.sentiment == 0.95

    @patch("common.sentiment.finbert._load_pipeline")
    def test_score_text_pipeline_unavailable(self, mock_load):
        from common.sentiment.finbert import reset, score_text
        reset()
        mock_load.return_value = None
        result = score_text("test text")
        assert result is None

    @patch("common.sentiment.finbert._load_pipeline")
    def test_score_batch_with_mock(self, mock_load):
        from common.sentiment.finbert import reset, score_batch
        reset()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [
            {"label": "positive", "score": 0.9},
            {"label": "negative", "score": 0.85},
        ]
        mock_load.return_value = mock_pipe
        results = score_batch(["good news", "bad news"])
        assert len(results) == 2
        assert results[0].sentiment > 0
        assert results[1].sentiment < 0

    @patch("common.sentiment.finbert._load_pipeline")
    def test_score_article_interface(self, mock_load):
        from common.sentiment.finbert import reset, score_article
        reset()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [{"label": "positive", "score": 0.8}]
        mock_load.return_value = mock_pipe
        score, label = score_article("Market rallies!", "Gains everywhere")
        assert score > 0
        assert label == "positive"

    def test_finbert_result_dataclass(self):
        from common.sentiment.finbert import FinBERTResult
        r = FinBERTResult(
            text="test", label="positive", score=0.9, sentiment=0.9,
        )
        assert r.text == "test"
        assert r.sentiment == 0.9

    def test_reset(self):
        from common.sentiment.finbert import is_loaded, reset
        reset()
        assert is_loaded() is False


# ── Signal Engine Rescoring ─────────────────────────────────────────────────


class TestSignalEngineRescoring:
    """Tests for _rescore_articles and compute_signal with rescore."""

    def test_rescore_empty(self):
        from common.sentiment.signal import _rescore_articles
        assert _rescore_articles([]) == []

    @patch("common.sentiment.scorer.has_vader", return_value=True)
    @patch("common.sentiment.scorer.score_text")
    def test_rescore_with_vader(self, mock_score, mock_has):
        from common.sentiment.signal import _rescore_articles
        mock_score.return_value = (0.7, "positive")
        articles = [
            {"title": "BTC surge", "summary": "", "sentiment_score": 0.1},
        ]
        result = _rescore_articles(articles)
        assert result[0]["sentiment_score"] == 0.7
        assert result[0]["scorer"] == "vader"

    def test_compute_signal_with_rescore_false(self):
        from common.sentiment.signal import compute_signal
        articles = [
            {
                "title": "Test", "summary": "",
                "sentiment_score": 0.5, "age_hours": 1.0,
            },
        ]
        sig = compute_signal(articles, rescore=False)
        assert sig.signal > 0

    def test_compute_signal_default_rescores(self):
        """Default rescore=True doesn't crash."""
        from common.sentiment.signal import compute_signal
        articles = [
            {
                "title": "Bullish news", "summary": "",
                "sentiment_score": 0.3, "age_hours": 2.0,
            },
        ]
        sig = compute_signal(articles)
        assert sig.article_count == 1


# ── Weight Rebalance ────────────────────────────────────────────────────────


class TestPhase3Weights:
    """Tests for updated weights after FinBERT upgrade."""

    def test_weights_sum_to_one(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.001

    def test_sentiment_weight(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["sentiment"] == 0.10

    def test_technical_weight(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["technical"] == 0.35

    def test_regime_weight(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["regime"] == 0.25

    def test_ml_weight_disabled(self):
        from common.signals.constants import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["ml"] == 0.08


# ── Watchlist Adjuster ──────────────────────────────────────────────────────


class TestWatchlistAdjuster:
    """Tests for sentiment-driven watchlist adjustments."""

    def test_promote_high_sentiment(self):
        from common.sentiment.watchlist_adjuster import evaluate_symbol
        adj = evaluate_symbol("BTC/USDT", 0.8)
        assert adj.action == "promote"

    def test_flag_short_low_sentiment(self):
        from common.sentiment.watchlist_adjuster import evaluate_symbol
        adj = evaluate_symbol("DOGE/USDT", -0.7)
        assert adj.action == "flag_short"

    def test_demote_negative_sentiment(self):
        from common.sentiment.watchlist_adjuster import evaluate_symbol
        adj = evaluate_symbol("XRP/USDT", -0.4)
        assert adj.action == "demote"

    def test_hold_normal_sentiment(self):
        from common.sentiment.watchlist_adjuster import evaluate_symbol
        adj = evaluate_symbol("ETH/USDT", 0.1)
        assert adj.action == "hold"

    def test_evaluate_watchlist(self):
        from common.sentiment.watchlist_adjuster import evaluate_watchlist
        scores = {
            "BTC/USDT": 0.8,
            "ETH/USDT": 0.1,
            "DOGE/USDT": -0.7,
            "XRP/USDT": -0.4,
        }
        state = evaluate_watchlist(scores)
        assert "BTC/USDT" in state.promoted
        assert "DOGE/USDT" in state.short_flagged
        assert "XRP/USDT" in state.demoted
        assert len(state.adjustments) == 4

    def test_filter_scan_symbols_promote(self):
        from common.sentiment.watchlist_adjuster import filter_scan_symbols
        symbols = ["ETH/USDT", "SOL/USDT"]
        scores = {"BTC/USDT": 0.8}  # Not in original list
        result = filter_scan_symbols(symbols, scores)
        assert "BTC/USDT" in result  # Promoted in

    def test_filter_scan_symbols_demote(self):
        from common.sentiment.watchlist_adjuster import filter_scan_symbols
        symbols = ["ETH/USDT", "DOGE/USDT", "SOL/USDT"]
        scores = {"DOGE/USDT": -0.4}
        result = filter_scan_symbols(symbols, scores)
        assert "DOGE/USDT" not in result  # Demoted out
        assert "ETH/USDT" in result

    def test_filter_no_changes(self):
        from common.sentiment.watchlist_adjuster import filter_scan_symbols
        symbols = ["ETH/USDT", "BTC/USDT"]
        scores = {"ETH/USDT": 0.2}
        result = filter_scan_symbols(symbols, scores)
        assert result == symbols

    def test_empty_scores(self):
        from common.sentiment.watchlist_adjuster import evaluate_watchlist
        state = evaluate_watchlist({})
        assert len(state.promoted) == 0
        assert len(state.short_flagged) == 0
        assert len(state.adjustments) == 0

    def test_boundary_promote(self):
        from common.sentiment.watchlist_adjuster import (
            PROMOTE_THRESHOLD,
            evaluate_symbol,
        )
        adj = evaluate_symbol("X", PROMOTE_THRESHOLD + 0.01)
        assert adj.action == "promote"

    def test_boundary_short(self):
        from common.sentiment.watchlist_adjuster import (
            SHORT_FLAG_THRESHOLD,
            evaluate_symbol,
        )
        adj = evaluate_symbol("X", SHORT_FLAG_THRESHOLD - 0.01)
        assert adj.action == "flag_short"
