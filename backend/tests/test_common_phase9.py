"""Phase 9: common/ module — 100% coverage tests.

Covers all 91 uncovered lines across 11 files in the common/ package.
"""

import asyncio
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ── pipeline.py ──────────────────────────────────────────────


class TestPipelineDownloadWatchlistCryptoDefaults:
    """Cover line 380: crypto timeframe default branch."""

    @patch("common.data_pipeline.pipeline.fetch_ohlcv")
    @patch("common.data_pipeline.pipeline.get_last_timestamp", return_value=None)
    def test_crypto_default_timeframes(self, mock_last_ts, mock_fetch):
        """When asset_class='crypto' and timeframes=None, defaults to ['1h','4h','1d']."""
        from common.data_pipeline.pipeline import download_watchlist

        mock_fetch.return_value = pd.DataFrame()

        download_watchlist(
            symbols=["BTC/USDT"],
            timeframes=None,
            exchange_id="kraken",
            since_days=10,
            asset_class="crypto",
        )
        # Should call fetch_ohlcv for each of 3 timeframes
        assert mock_fetch.call_count == 3
        called_tfs = [call.args[1] for call in mock_fetch.call_args_list]
        assert called_tfs == ["1h", "4h", "1d"]


class TestPipelineValidateDataIssues:
    """Cover lines 653, 655, 657: NaN, outlier, OHLC violation issues."""

    @patch("common.data_pipeline.pipeline.load_ohlcv")
    @patch("common.data_pipeline.pipeline.detect_gaps", return_value=[])
    @patch("common.data_pipeline.pipeline.detect_stale_data", return_value=(False, 0.0))
    def test_nan_columns_issue(self, mock_stale, mock_gaps, mock_load):
        """Line 653: NaN columns trigger issue."""
        from common.data_pipeline.pipeline import validate_data

        df = pd.DataFrame(
            {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
            index=pd.DatetimeIndex([datetime(2025, 1, 1, tzinfo=timezone.utc)]),
        )
        df.loc[df.index[0], "volume"] = np.nan
        mock_load.return_value = df

        with (
            patch("common.data_pipeline.pipeline.audit_nans", return_value={"volume": 1}),
            patch("common.data_pipeline.pipeline.detect_outliers", return_value=[]),
            patch("common.data_pipeline.pipeline.check_ohlc_integrity", return_value=[]),
        ):
            report = validate_data("BTC/USDT", "1h")

        assert not report.passed
        assert any("NaN" in issue for issue in report.issues_summary)

    @patch("common.data_pipeline.pipeline.load_ohlcv")
    @patch("common.data_pipeline.pipeline.detect_gaps", return_value=[])
    @patch("common.data_pipeline.pipeline.detect_stale_data", return_value=(False, 0.0))
    @patch("common.data_pipeline.pipeline.audit_nans", return_value={})
    def test_outlier_issue(self, mock_nans, mock_stale, mock_gaps, mock_load):
        """Line 655: outliers trigger issue."""
        from common.data_pipeline.pipeline import validate_data

        df = pd.DataFrame(
            {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
            index=pd.DatetimeIndex([datetime(2025, 1, 1, tzinfo=timezone.utc)]),
        )
        mock_load.return_value = df

        with (
            patch(
                "common.data_pipeline.pipeline.detect_outliers",
                return_value=[{"idx": 0, "change": 0.50}],
            ),
            patch("common.data_pipeline.pipeline.check_ohlc_integrity", return_value=[]),
        ):
            report = validate_data("BTC/USDT", "1h")

        assert not report.passed
        assert any("outlier" in issue.lower() for issue in report.issues_summary)

    @patch("common.data_pipeline.pipeline.load_ohlcv")
    @patch("common.data_pipeline.pipeline.detect_gaps", return_value=[])
    @patch("common.data_pipeline.pipeline.detect_stale_data", return_value=(False, 0.0))
    @patch("common.data_pipeline.pipeline.audit_nans", return_value={})
    @patch("common.data_pipeline.pipeline.detect_outliers", return_value=[])
    def test_ohlc_violation_issue(self, mock_outliers, mock_nans, mock_stale, mock_gaps, mock_load):
        """Line 657: OHLC violations trigger issue."""
        from common.data_pipeline.pipeline import validate_data

        df = pd.DataFrame(
            {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
            index=pd.DatetimeIndex([datetime(2025, 1, 1, tzinfo=timezone.utc)]),
        )
        mock_load.return_value = df

        with patch(
            "common.data_pipeline.pipeline.check_ohlc_integrity",
            return_value=[{"row": 0, "issue": "high < open"}],
        ):
            report = validate_data("BTC/USDT", "1h")

        assert not report.passed
        assert any("OHLC" in issue for issue in report.issues_summary)


# ── ml/registry.py ───────────────────────────────────────────


class TestModelRegistryNoLightGBM:
    """Cover lines 19-21, 66, 111: ImportError paths when lightgbm missing."""

    def test_save_model_no_lightgbm(self, tmp_path):
        """Line 66: save_model raises ImportError."""
        from common.ml.registry import ModelRegistry

        registry = ModelRegistry(models_dir=tmp_path)
        with (
            patch("common.ml.registry.HAS_LIGHTGBM", False),
            pytest.raises(ImportError, match="lightgbm required"),
        ):
            registry.save_model(
                model=MagicMock(),
                metrics={"accuracy": 0.9},
                metadata={},
                feature_importance={},
            )

    def test_load_model_no_lightgbm(self, tmp_path):
        """Line 111: load_model raises ImportError."""
        from common.ml.registry import ModelRegistry

        registry = ModelRegistry(models_dir=tmp_path)
        with (
            patch("common.ml.registry.HAS_LIGHTGBM", False),
            pytest.raises(ImportError, match="lightgbm required"),
        ):
            registry.load_model("some_model_id")


class TestModelRegistryListModels:
    """Cover lines 133, 137, 140: list_models edge cases."""

    def test_list_models_skips_non_dir(self, tmp_path):
        """Line 137: skip non-directory entries."""
        from common.ml.registry import ModelRegistry

        registry = ModelRegistry(models_dir=tmp_path)
        # Create a regular file in models dir
        (tmp_path / "not_a_dir.txt").write_text("hello")
        # Create a valid model dir
        model_dir = tmp_path / "valid_model"
        model_dir.mkdir()
        (model_dir / "manifest.json").write_text(json.dumps({"model_id": "valid_model"}))

        models = registry.list_models()
        assert len(models) == 1
        assert models[0]["model_id"] == "valid_model"

    def test_list_models_skips_no_manifest(self, tmp_path):
        """Line 140: skip dirs without manifest.json."""
        from common.ml.registry import ModelRegistry

        registry = ModelRegistry(models_dir=tmp_path)
        # Dir without manifest
        (tmp_path / "no_manifest").mkdir()
        models = registry.list_models()
        assert len(models) == 0

    def test_list_models_skips_corrupt_json(self, tmp_path):
        """Except branch: skip corrupt manifest JSON."""
        from common.ml.registry import ModelRegistry

        registry = ModelRegistry(models_dir=tmp_path)
        model_dir = tmp_path / "corrupt_model"
        model_dir.mkdir()
        (model_dir / "manifest.json").write_text("{invalid json")

        models = registry.list_models()
        assert len(models) == 0

    def test_list_models_dir_not_exists(self, tmp_path):
        """Line 133: models_dir doesn't exist → return empty list."""
        from common.ml.registry import ModelRegistry

        nonexistent = tmp_path / "nonexistent_dir"
        registry = ModelRegistry.__new__(ModelRegistry)
        registry.models_dir = nonexistent

        models = registry.list_models()
        assert models == []


class TestModelRegistryGetModelDetail:
    """Cover lines 168-169: get_model_detail corrupt JSON."""

    def test_get_model_detail_corrupt_json(self, tmp_path):
        """Lines 168-169: returns None for corrupt JSON."""
        from common.ml.registry import ModelRegistry

        registry = ModelRegistry(models_dir=tmp_path)
        model_dir = tmp_path / "bad_model"
        model_dir.mkdir()
        (model_dir / "manifest.json").write_text("not json")

        result = registry.get_model_detail("bad_model")
        assert result is None


# ── ml/trainer.py ────────────────────────────────────────────


class TestTrainerNoLightGBM:
    """Cover lines 20-22, 83, 162: ImportError paths."""

    def test_train_model_no_lightgbm(self):
        """Line 83: train_model raises ImportError."""
        from common.ml.trainer import train_model

        x = pd.DataFrame({"a": [1, 2, 3]})
        y = pd.Series([0, 1, 0])
        with (
            patch("common.ml.trainer.HAS_LIGHTGBM", False),
            pytest.raises(ImportError, match="lightgbm is required"),
        ):
            train_model(x, y, ["a"])

    def test_predict_no_lightgbm(self):
        """Line 162: predict raises ImportError."""
        from common.ml.trainer import predict

        x = pd.DataFrame({"a": [1, 2]})
        with (
            patch("common.ml.trainer.HAS_LIGHTGBM", False),
            pytest.raises(ImportError, match="lightgbm is required"),
        ):
            predict(MagicMock(), x)


# ── data_pipeline/news_adapter.py ────────────────────────────


class TestNewsAdapterAtomFeed:
    """Cover lines 73, 195, 213-215: Atom feed parsing."""

    def test_atom_feed_fallback(self):
        """Line 73: fallback to Atom entries when RSS items empty."""
        from common.data_pipeline.news_adapter import fetch_rss_feed

        atom_xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Atom Title</title>
                <link href="https://example.com/atom1"/>
                <published>2025-01-01T00:00:00Z</published>
                <summary>Atom summary</summary>
            </entry>
        </feed>"""

        with patch("common.data_pipeline.news_adapter.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = atom_xml.encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            articles = fetch_rss_feed("https://example.com/feed", "TestFeed")
            assert len(articles) >= 1
            assert articles[0]["title"] == "Atom Title"

    def test_get_text_atom_namespace(self):
        """Line 195: _get_text falls back to Atom namespace."""
        from common.data_pipeline.news_adapter import _get_text

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        xml_str = (
            '<entry xmlns:atom="http://www.w3.org/2005/Atom">'
            "<atom:summary>Atom text</atom:summary></entry>"
        )
        element = ET.fromstring(xml_str)
        result = _get_text(element, "summary", ns)
        assert result == "Atom text"

    def test_get_link_atom_href(self):
        """Lines 213-215: _get_link Atom namespace link with href."""
        from common.data_pipeline.news_adapter import _get_link

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        xml_str = '<entry xmlns:atom="http://www.w3.org/2005/Atom"><atom:link href="https://example.com/atom"/></entry>'
        element = ET.fromstring(xml_str)
        result = _get_link(element, ns)
        assert result == "https://example.com/atom"


class TestNewsAdapterFetchAllDedup:
    """Cover lines 179-180: NewsAPI article dedup."""

    @patch("common.data_pipeline.news_adapter.fetch_rss_feed")
    @patch("common.data_pipeline.news_adapter.fetch_newsapi")
    def test_newsapi_dedup(self, mock_newsapi, mock_rss):
        """Lines 179-180: NewsAPI articles with same ID are deduped."""
        from common.data_pipeline.news_adapter import fetch_all_news

        rss_article = {"article_id": "abc123", "title": "RSS Article", "source": "RSS"}
        newsapi_article = {
            "article_id": "abc123",
            "title": "NewsAPI Duplicate",
            "source": "NewsAPI",
        }
        newsapi_unique = {"article_id": "def456", "title": "NewsAPI Unique", "source": "NewsAPI"}

        mock_rss.return_value = [rss_article]
        mock_newsapi.return_value = [newsapi_article, newsapi_unique]

        articles = fetch_all_news("crypto", api_key="test_key")
        # abc123 should appear only once (from RSS), def456 should appear
        ids = [a["article_id"] for a in articles]
        assert ids.count("abc123") == 1
        assert "def456" in ids


# ── market_hours/sessions.py ─────────────────────────────────


class TestMarketHoursSessionsUncovered:
    """Cover lines 110, 128, 144, 154, 186."""

    def test_forex_friday_before_close(self):
        """Line 110: Friday before 5PM ET → forex market open."""
        from common.market_hours.sessions import MarketHoursService

        # Friday 2PM ET = 7PM UTC
        friday_2pm = datetime(2025, 3, 7, 19, 0, tzinfo=timezone.utc)  # Friday
        assert MarketHoursService.is_market_open("forex", friday_2pm) is True

    def test_next_open_unknown_asset_class(self):
        """Line 128: unknown asset class returns None."""
        from common.market_hours.sessions import MarketHoursService

        result = MarketHoursService.next_open("commodities")
        assert result is None

    def test_next_equity_open_loops_past_weekend(self):
        """Line 144: next_equity_open falls through to last candidate after loop."""
        from common.market_hours.sessions import MarketHoursService

        # Saturday — should find next Monday
        saturday = datetime(2025, 3, 8, 20, 0, tzinfo=timezone.utc)
        result = MarketHoursService.next_open("equity", saturday)
        assert result is not None
        # Should be a weekday
        result_et = result.astimezone(timezone(timedelta(hours=-5)))
        assert result_et.weekday() < 5

    def test_next_forex_open_sunday_after_open_time(self):
        """Line 154: Sunday after 5PM ET → next_open returns next week."""
        from common.market_hours.sessions import MarketHoursService

        # Sunday 6PM ET = 11PM UTC → forex is already open, should return None
        sunday_6pm = datetime(2025, 3, 9, 23, 0, tzinfo=timezone.utc)
        result = MarketHoursService.next_open("forex", sunday_6pm)
        # Forex opens Sunday 5PM ET; if it's Sunday 6PM ET, market IS open → None
        assert result is None

    def test_next_close_unknown_asset_class(self):
        """Line 186: unknown asset class returns None."""
        from common.market_hours.sessions import MarketHoursService

        result = MarketHoursService.next_close("commodities")
        assert result is None


# ── data_pipeline/yfinance_adapter.py ────────────────────────


class TestYfinanceAdapterUncovered:
    """Cover lines 184, 215, 246, 262: tz_convert and async wrappers."""

    @patch("yfinance.Ticker")
    def test_tz_localize_naive_data(self, mock_ticker_cls):
        """Line 184: timezone-naive data triggers tz_localize('UTC') path."""
        from common.data_pipeline.yfinance_adapter import _fetch_ohlcv_sync

        # Create mock with timezone-NAIVE index (no tzinfo)
        mock_df = pd.DataFrame(
            {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [100]},
            index=pd.DatetimeIndex(
                [datetime(2025, 1, 1)],  # No timezone → tzinfo is None
                name="Date",
            ),
        )

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_df
        mock_ticker_cls.return_value = mock_ticker

        result = _fetch_ohlcv_sync("AAPL/USD", "1d", 30, "equity")
        assert not result.empty
        assert str(result.index.tz) == "UTC"

    def test_fetch_ohlcv_yfinance_async(self):
        """Line 215: async wrapper delegates to sync."""
        from common.data_pipeline.yfinance_adapter import fetch_ohlcv_yfinance

        with patch("common.data_pipeline.yfinance_adapter._fetch_ohlcv_sync") as mock_sync:
            mock_sync.return_value = pd.DataFrame({"close": [1.0]})
            result = asyncio.get_event_loop().run_until_complete(
                fetch_ohlcv_yfinance("AAPL/USD", "1d", 30, "equity"),
            )
            mock_sync.assert_called_once()
            assert not result.empty

    def test_fetch_ticker_yfinance_async(self):
        """Line 246: async ticker wrapper."""
        from common.data_pipeline.yfinance_adapter import fetch_ticker_yfinance

        with patch("common.data_pipeline.yfinance_adapter._fetch_ticker_sync") as mock_sync:
            mock_sync.return_value = {"symbol": "AAPL", "price": 150.0}
            result = asyncio.get_event_loop().run_until_complete(
                fetch_ticker_yfinance("AAPL/USD", "equity"),
            )
            assert result["price"] == 150.0

    def test_fetch_tickers_yfinance_async(self):
        """Line 262: async multi-ticker wrapper."""
        from common.data_pipeline.yfinance_adapter import fetch_tickers_yfinance

        with patch("common.data_pipeline.yfinance_adapter._fetch_tickers_sync") as mock_sync:
            mock_sync.return_value = [{"symbol": "AAPL", "price": 150.0}]
            result = asyncio.get_event_loop().run_until_complete(
                fetch_tickers_yfinance(["AAPL/USD"], "equity"),
            )
            assert len(result) == 1


# ── indicators/technical.py ──────────────────────────────────


class TestSupertrendDirectionChanges:
    """Cover lines 54, 56, 61: supertrend direction transitions."""

    def test_direction_changes_up_and_down(self):
        """Lines 54, 56, 61: close crosses above upper → direction=1,
        close crosses below lower → direction=-1, then direction=1 path for st.
        """
        from common.indicators.technical import supertrend

        # Use small multiplier and tight data, then extreme jumps
        # Start flat, then massive jump up (cross above upper), then crash (cross below lower)
        n = 25

        # Flat period to establish ATR
        flat = [100.0] * 10
        # Massive jump up to cross above upper band
        jump_up = [100, 110, 130, 160, 200]
        # Stay high briefly
        high_flat = [200, 200, 200]
        # Massive crash to cross below lower band
        crash = [200, 150, 80, 50, 30, 20, 20]

        close = np.array(flat + jump_up + high_flat + crash, dtype=float)

        # Tight high/low to keep ATR small so crossing is easier
        df = pd.DataFrame(
            {
                "open": close,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": np.ones(n) * 1000,
            }
        )

        result = supertrend(df, period=5, multiplier=1.0)
        assert "supertrend" in result.columns
        assert "supertrend_direction" in result.columns

        directions = set(int(d) for d in result["supertrend_direction"].dropna().unique())
        assert 1 in directions, f"Expected direction=1, got {directions}"
        assert -1 in directions, f"Expected direction=-1, got {directions}"


# ── sentiment/scorer.py ──────────────────────────────────────


class TestSentimentScorerNegative:
    """Cover lines 123-126: negative sentiment label."""

    def test_negative_sentiment(self):
        """Line 123-124: score below negative threshold → 'negative' label."""
        from common.sentiment.scorer import score_article

        # Use strongly negative title
        score, label = score_article(
            title="Massive crash collapse catastrophe fear panic",
            summary="Markets plunging amid devastating losses",
        )
        assert label == "negative"
        assert score < 0

    def test_neutral_sentiment_article(self):
        """Line 126: neutral combined score in score_article."""
        from common.sentiment.scorer import score_article

        # Use neutral/ambiguous text
        score, label = score_article(
            title="Market update for today",
            summary="",
        )
        assert label == "neutral"


# ── risk/risk_manager.py ─────────────────────────────────────


class TestRiskManagerMarketHoursImportError:
    """Cover lines 335-336: market hours ImportError fallback."""

    def test_check_new_trade_market_hours_import_error(self):
        """Lines 335-336: ImportError in market hours import → skip check."""
        from common.risk.risk_manager import RiskManager

        rm = RiskManager()

        original_import = __import__

        def selective_import(name, *args, **kwargs):
            if name == "common.market_hours.sessions":
                raise ImportError("not available")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=selective_import):
            approved, reason = rm.check_new_trade(
                symbol="EUR/USD",
                side="buy",
                size=1.0,
                entry_price=1.10,
                asset_class="forex",
            )
            assert approved is True


class TestRiskManagerCorrelationNotInMatrix:
    """Cover line 396: symbol not in correlation matrix columns."""

    def test_symbol_not_in_corr_matrix(self):
        """Line 396: symbol missing from correlation matrix → allow trade."""
        from common.risk.risk_manager import RiskManager

        rm = RiskManager()
        # Add two existing positions with enough return data
        rm.state.open_positions["BTC/USDT"] = {
            "side": "buy",
            "size": 0.1,
            "entry_price": 50000,
            "value": 1000,
            "timestamp": datetime.now(timezone.utc),
        }
        rm.state.open_positions["SOL/USDT"] = {
            "side": "buy",
            "size": 10,
            "entry_price": 100,
            "value": 1000,
            "timestamp": datetime.now(timezone.utc),
        }
        # Record enough prices for BTC and SOL (so corr matrix is non-empty)
        for i in range(25):
            rm.return_tracker.record_price("BTC/USDT", 50000 + i * 10)
            rm.return_tracker.record_price("SOL/USDT", 100 + i * 0.5)

        # ETH has no return data → won't be in corr_matrix columns
        # So line 396 fires: symbol not in corr_matrix.columns → return True
        approved, reason = rm.check_new_trade(
            symbol="ETH/USDT",
            side="buy",
            size=0.1,
            entry_price=3000.0,
        )
        assert approved is True


class TestRiskManagerPortfolioHeatCheck:
    """Cover lines 482-487, 505, 509: heat check correlation and VaR issues."""

    def test_heat_check_with_correlated_positions(self):
        """Lines 482-487, 505: high correlation pairs trigger issue."""
        from common.risk.risk_manager import RiskManager

        rm = RiskManager()
        rm.state.open_positions = {
            "BTC/USDT": {"side": "buy", "size": 1, "entry_price": 50000, "value": 2000},
            "ETH/USDT": {"side": "buy", "size": 10, "entry_price": 3000, "value": 2000},
        }

        # Record correlated prices (both go up together)
        for i in range(25):
            rm.return_tracker.record_price("BTC/USDT", 50000 + i * 100)
            rm.return_tracker.record_price("ETH/USDT", 3000 + i * 6)

        result = rm.portfolio_heat_check()
        # Should have correlation data
        assert "max_correlation" in result
        assert "high_corr_pairs" in result

    def test_heat_check_var_warning(self):
        """Line 509: VaR warning when var_99 > 10% of equity."""
        from common.risk.risk_manager import RiskManager, VaRResult

        rm = RiskManager()
        rm.state.total_equity = 10000.0
        rm.state.peak_equity = 10000.0
        rm.state.open_positions = {
            "BTC/USDT": {"side": "buy", "size": 1, "entry_price": 50000, "value": 5000},
        }

        # Mock get_var to return high VaR
        with patch.object(rm, "get_var", return_value=VaRResult(var_99=1500.0)):
            result = rm.portfolio_heat_check()
            assert any("VaR warning" in issue for issue in result["issues"])

    def test_heat_check_halted_issue(self):
        """Line 500-501: halted state triggers issue."""
        from common.risk.risk_manager import RiskManager

        rm = RiskManager()
        rm.state.is_halted = True
        rm.state.halt_reason = "Max drawdown exceeded"

        result = rm.portfolio_heat_check()
        assert not result["healthy"]
        assert any("HALTED" in issue for issue in result["issues"])


# ── regime/regime_detector.py ────────────────────────────────


class TestRegimeTransitionProbabilities:
    """Cover lines 404, 418: edge cases in transition probability computation."""

    def test_transition_probabilities_too_few_data_points(self):
        """Line 404: fewer than 2 data points → empty dict."""
        from common.regime.regime_detector import Regime, RegimeDetector

        detector = RegimeDetector()
        regimes = pd.Series([Regime.RANGING])
        result = detector._compute_transition_probabilities(regimes)
        assert result == {}

    def test_transition_probabilities_no_matching_transitions(self):
        """Line 418: current regime never appears earlier → empty dict."""
        from common.regime.regime_detector import Regime, RegimeDetector

        detector = RegimeDetector()
        # Current is last element. If it never appears before the last position,
        # there are no transitions from it → total == 0 → empty dict
        regimes = pd.Series(
            [
                Regime.STRONG_TREND_UP,
                Regime.WEAK_TREND_UP,
                Regime.RANGING,  # current — never appears earlier
            ]
        )
        result = detector._compute_transition_probabilities(regimes)
        assert result == {}


# ── regime/strategy_router.py ────────────────────────────────


class TestStrategyRouterUncovered:
    """Cover lines 244, 296: unknown regime fallback and weight check."""

    def test_route_unknown_regime_fallback(self):
        """Line 244: regime not in routing dict falls back to RANGING."""
        from common.regime.regime_detector import Regime, RegimeState
        from common.regime.strategy_router import BMR, StrategyRouter, StrategyWeight

        # Create a custom routing dict that's MISSING UNKNOWN
        custom_routing = {
            Regime.RANGING: {
                "primary": BMR,
                "weights": [StrategyWeight(BMR, 1.0, 1.0)],
                "position_modifier": 1.0,
                "reasoning": "Ranging routing",
            },
        }
        router = StrategyRouter(routing=custom_routing)

        state = RegimeState(
            regime=Regime.UNKNOWN,  # Not in custom_routing → fallback
            confidence=0.5,
            adx_value=20.0,
            bb_width_percentile=50.0,
            ema_slope=0.0,
            trend_alignment=0.0,
            price_structure_score=0.0,
        )
        decision = router.route(state)
        # Should fall back to RANGING routing
        assert decision.primary_strategy == BMR

    def test_suggest_strategy_switch_weight_above_threshold(self):
        """Line 296: current strategy in weights with weight >= 0.5 → no switch."""
        from common.regime.regime_detector import Regime, RegimeState
        from common.regime.strategy_router import BMR, VB, StrategyRouter, StrategyWeight

        # Create a custom routing where VB is NOT primary but has weight >= 0.5
        custom_routing = {
            Regime.RANGING: {
                "primary": BMR,
                "weights": [
                    StrategyWeight(BMR, 0.5, 1.0),
                    StrategyWeight(VB, 0.5, 0.8),  # weight >= 0.5
                ],
                "position_modifier": 1.0,
                "reasoning": "Ranging",
            },
        }
        router = StrategyRouter(routing=custom_routing)

        state = RegimeState(
            regime=Regime.RANGING,
            confidence=0.8,
            adx_value=15.0,
            bb_width_percentile=40.0,
            ema_slope=0.0,
            trend_alignment=0.0,
            price_structure_score=0.0,
        )

        # VB is not primary (BMR is), but VB is in weights with weight=0.5 (>= 0.5)
        # → line 296: return None (no switch needed)
        result = router.suggest_strategy_switch(VB, state)
        assert result is None

    def test_suggest_strategy_switch_triggers(self):
        """Strategy not in weights → switch recommended."""
        from common.regime.regime_detector import Regime, RegimeState
        from common.regime.strategy_router import StrategyRouter

        router = StrategyRouter()
        state = RegimeState(
            regime=Regime.STRONG_TREND_UP,
            confidence=0.9,
            adx_value=50.0,
            bb_width_percentile=30.0,
            ema_slope=0.01,
            trend_alignment=0.8,
            price_structure_score=0.5,
        )
        result = router.suggest_strategy_switch("SomeOtherStrategy", state)
        assert result is not None
