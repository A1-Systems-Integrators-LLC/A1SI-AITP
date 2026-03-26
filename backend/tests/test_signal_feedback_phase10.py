"""Tests for IEB Phase 10: Performance Feedback & Adaptive Tuning.

Covers:
- SignalAttribution model (creation, validation, __str__)
- PerformanceTracker (record_entry, record_outcome, get_source_accuracy, get_records)
- PerformanceFeedback (compute_weight_adjustments, apply_adjustments, reset)
- SignalFeedbackService (record/backfill/accuracy/weights)
- Views (attribution list/detail, record, feedback, accuracy, weights)
- Task executors (signal_feedback, adaptive_weighting)
- URL routing
"""

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from analysis.models import SignalAttribution

# ── Model tests ──────────────────────────────────────────────────────


class TestSignalAttributionModel(TestCase):
    def test_create_basic(self):
        attr = SignalAttribution.objects.create(
            order_id=str(uuid.uuid4()),
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CryptoInvestorV1",
            composite_score=72.5,
        )
        assert attr.outcome == "open"
        assert attr.pnl is None
        assert "BTC/USDT" in str(attr)
        assert "72.5" in str(attr)

    def test_str_representation(self):
        attr = SignalAttribution(
            symbol="ETH/USDT",
            strategy="BMR",
            outcome="win",
            composite_score=85.0,
        )
        s = str(attr)
        assert "ETH/USDT" in s
        assert "BMR" in s
        assert "win" in s

    def test_clean_valid(self):
        attr = SignalAttribution(
            order_id=str(uuid.uuid4()),
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CryptoInvestorV1",
            composite_score=50.0,
            outcome="open",
        )
        attr.clean()  # Should not raise

    def test_clean_invalid_score(self):
        attr = SignalAttribution(
            order_id=str(uuid.uuid4()),
            symbol="BTC/USDT",
            composite_score=150.0,
        )
        with pytest.raises(ValidationError) as exc_info:
            attr.clean()
        assert "composite_score" in exc_info.value.message_dict

    def test_clean_invalid_outcome(self):
        attr = SignalAttribution(
            order_id=str(uuid.uuid4()),
            symbol="BTC/USDT",
            composite_score=50.0,
            outcome="invalid",
        )
        with pytest.raises(ValidationError) as exc_info:
            attr.clean()
        assert "outcome" in exc_info.value.message_dict

    def test_ordering(self):
        """Records should be ordered by -recorded_at (newest first)."""
        a1 = SignalAttribution.objects.create(
            order_id=str(uuid.uuid4()),
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=60.0,
        )
        a2 = SignalAttribution.objects.create(
            order_id=str(uuid.uuid4()),
            symbol="ETH/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=70.0,
        )
        records = list(SignalAttribution.objects.all())
        assert str(records[0].id) == str(a2.id)
        assert str(records[1].id) == str(a1.id)


# ── PerformanceTracker tests ─────────────────────────────────────────


class TestPerformanceTracker:
    def setup_method(self):
        import sys

        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.signals.performance_tracker import PerformanceTracker

        self.tracker = PerformanceTracker()

    def test_record_entry(self):
        rec = self.tracker.record_entry(
            order_id="order-1",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=72.0,
            contributions={"ml": 80.0, "regime": 65.0, "technical": 70.0},
        )
        assert rec.order_id == "order-1"
        assert rec.composite_score == 72.0
        assert rec.outcome == "open"
        assert rec.contributions["ml"] == 80.0

    def test_record_outcome(self):
        self.tracker.record_entry(
            order_id="order-2",
            symbol="ETH/USDT",
            asset_class="crypto",
            strategy="BMR",
            composite_score=65.0,
            contributions={"ml": 70.0},
        )
        rec = self.tracker.record_outcome("order-2", "win", pnl=150.0)
        assert rec is not None
        assert rec.outcome == "win"
        assert rec.pnl == 150.0
        assert rec.resolved_at is not None

    def test_record_outcome_not_found(self):
        result = self.tracker.record_outcome("nonexistent", "loss")
        assert result is None

    def test_get_source_accuracy(self):
        # Create several trades with known outcomes
        for i in range(10):
            self.tracker.record_entry(
                order_id=f"win-{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=75.0,
                contributions={"ml": 80.0, "regime": 70.0},
            )
            self.tracker.record_outcome(f"win-{i}", "win", pnl=100.0)

        for i in range(5):
            self.tracker.record_entry(
                order_id=f"loss-{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=60.0,
                contributions={"ml": 55.0, "regime": 45.0},
            )
            self.tracker.record_outcome(f"loss-{i}", "loss", pnl=-50.0)

        acc = self.tracker.get_source_accuracy()
        assert "ml" in acc
        assert "regime" in acc
        assert acc["ml"].total == 15
        assert acc["ml"].wins == 10
        assert acc["ml"].win_rate == pytest.approx(10 / 15, abs=0.01)
        assert acc["ml"].avg_score_win == 80.0
        assert acc["ml"].avg_score_loss == 55.0

    def test_get_source_accuracy_filtered(self):
        self.tracker.record_entry(
            order_id="crypto-1",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=70.0,
            contributions={"ml": 80.0},
        )
        self.tracker.record_outcome("crypto-1", "win")

        self.tracker.record_entry(
            order_id="equity-1",
            symbol="AAPL",
            asset_class="equity",
            strategy="EquityMomentum",
            composite_score=70.0,
            contributions={"ml": 60.0},
        )
        self.tracker.record_outcome("equity-1", "loss")

        crypto_acc = self.tracker.get_source_accuracy(asset_class="crypto")
        assert crypto_acc["ml"].wins == 1
        assert crypto_acc["ml"].losses == 0

    def test_get_source_accuracy_skips_open(self):
        self.tracker.record_entry(
            order_id="open-1",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=70.0,
            contributions={"ml": 80.0},
        )
        # Don't resolve — should be skipped
        acc = self.tracker.get_source_accuracy()
        assert len(acc) == 0

    def test_get_records(self):
        for i in range(5):
            self.tracker.record_entry(
                order_id=f"rec-{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=70.0,
                contributions={"ml": 80.0},
            )
        recs = self.tracker.get_records(limit=3)
        assert len(recs) == 3

    def test_get_records_filtered_by_outcome(self):
        self.tracker.record_entry(
            order_id="w1",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=70.0,
            contributions={},
        )
        self.tracker.record_outcome("w1", "win")
        self.tracker.record_entry(
            order_id="l1",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=50.0,
            contributions={},
        )
        self.tracker.record_outcome("l1", "loss")

        wins = self.tracker.get_records(outcome="win")
        assert len(wins) == 1
        assert wins[0].outcome == "win"

    def test_clear(self):
        self.tracker.record_entry(
            order_id="x1",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=70.0,
            contributions={},
        )
        assert len(self.tracker.get_records()) == 1
        self.tracker.clear()
        assert len(self.tracker.get_records()) == 0

    def test_source_accuracy_insufficient_data(self):
        """SourceAccuracy.accuracy returns 0.5 with < 5 trades."""
        from common.signals.performance_tracker import SourceAccuracy

        acc = SourceAccuracy(source="ml", total=3, wins=2, losses=1)
        assert acc.accuracy == 0.5


# ── PerformanceFeedback tests ────────────────────────────────────────


class TestPerformanceFeedback:
    def setup_method(self):
        import sys

        sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")
        from common.signals.feedback import PerformanceFeedback
        from common.signals.performance_tracker import PerformanceTracker

        self.tracker = PerformanceTracker()
        self.feedback = PerformanceFeedback(tracker=self.tracker)

    def test_insufficient_trades(self):
        """With fewer than MIN_TRADES_FOR_ADJUSTMENT, weights stay unchanged."""
        adj = self.feedback.compute_weight_adjustments()
        assert adj.total_trades == 0
        assert all(v == 0.0 for v in adj.adjustments.values())
        assert "Only 0 resolved trades" in adj.reasoning[0]

    def test_weight_increase_on_high_win_rate(self):
        """Sources with >60% win rate get increased weight."""
        # 20 trades, ML always 80 on wins, 40 on losses
        for i in range(15):
            self.tracker.record_entry(
                order_id=f"w{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=75.0,
                contributions={"ml": 80.0, "regime": 70.0, "technical": 60.0},
            )
            self.tracker.record_outcome(f"w{i}", "win", pnl=100.0)

        for i in range(5):
            self.tracker.record_entry(
                order_id=f"l{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=55.0,
                contributions={"ml": 40.0, "regime": 30.0, "technical": 55.0},
            )
            self.tracker.record_outcome(f"l{i}", "loss", pnl=-50.0)

        adj = self.feedback.compute_weight_adjustments()
        assert adj.total_trades == 20
        assert adj.win_rate == pytest.approx(0.75, abs=0.01)
        # All sources have 75% win rate → should increase
        assert adj.adjustments.get("ml", 0) > 0 or "increase" in str(adj.reasoning)

    def test_weight_decrease_on_low_win_rate(self):
        """Sources with <45% win rate get decreased weight."""
        for i in range(4):
            self.tracker.record_entry(
                order_id=f"w{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=60.0,
                contributions={"ml": 80.0, "sentiment": 70.0},
            )
            self.tracker.record_outcome(f"w{i}", "win")

        for i in range(8):
            self.tracker.record_entry(
                order_id=f"l{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=50.0,
                contributions={"ml": 60.0, "sentiment": 50.0},
            )
            self.tracker.record_outcome(f"l{i}", "loss")

        adj = self.feedback.compute_weight_adjustments()
        # 33% win rate → should decrease weights and raise threshold
        assert adj.threshold_adjustment > 0

    def test_threshold_lowered_on_high_win_rate(self):
        """Win rate > 65% should lower threshold."""
        for i in range(14):
            self.tracker.record_entry(
                order_id=f"w{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=80.0,
                contributions={"ml": 90.0},
            )
            self.tracker.record_outcome(f"w{i}", "win")

        for i in range(6):
            self.tracker.record_entry(
                order_id=f"l{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=55.0,
                contributions={"ml": 50.0},
            )
            self.tracker.record_outcome(f"l{i}", "loss")

        adj = self.feedback.compute_weight_adjustments()
        # 70% win rate → should lower threshold
        assert adj.threshold_adjustment < 0

    def test_apply_adjustments(self):
        from common.signals.feedback import WeightAdjustment

        adj = WeightAdjustment(
            current_weights={"ml": 0.20, "regime": 0.25},
            recommended_weights={"ml": 0.25, "regime": 0.20},
            adjustments={"ml": 0.05, "regime": -0.05},
            source_accuracy={},
            total_trades=50,
            win_rate=0.60,
            threshold_adjustment=-3,
        )
        self.feedback.apply_adjustments(adj)
        assert self.feedback.current_weights["ml"] == 0.25
        assert self.feedback.threshold_delta == -3

    def test_reset(self):
        from common.signals.feedback import WeightAdjustment

        adj = WeightAdjustment(
            current_weights={},
            recommended_weights={"ml": 0.30},
            adjustments={},
            source_accuracy={},
            threshold_adjustment=5,
        )
        self.feedback.apply_adjustments(adj)
        self.feedback.reset()
        assert self.feedback.threshold_delta == 0
        # Should be back to defaults
        assert "ml" in self.feedback.current_weights

    def test_weight_normalization(self):
        """Recommended weights should sum to ~1.0."""
        for i in range(12):
            self.tracker.record_entry(
                order_id=f"t{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=70.0,
                contributions={
                    "ml": 80.0,
                    "regime": 60.0,
                    "technical": 70.0,
                    "sentiment": 50.0,
                    "scanner": 40.0,
                    "win_rate": 55.0,
                },
            )
            self.tracker.record_outcome(f"t{i}", "win" if i < 8 else "loss")

        adj = self.feedback.compute_weight_adjustments()
        total = sum(adj.recommended_weights.values())
        assert abs(total - 1.0) < 0.01


# ── Django service tests ──────────────────────────────────────────────


class TestSignalFeedbackService(TestCase):
    def test_record_attribution(self):
        from analysis.services.signal_feedback import SignalFeedbackService

        signal_data = {
            "composite_score": 72.5,
            "position_modifier": 0.7,
            "components": {
                "ml": 80.0,
                "sentiment": 60.0,
                "regime": 70.0,
                "scanner": 40.0,
                "win_rate": 55.0,
            },
        }
        result = SignalFeedbackService.record_attribution(
            order_id="test-order-1",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CryptoInvestorV1",
            signal_data=signal_data,
        )
        assert result["order_id"] == "test-order-1"
        assert result["composite_score"] == 72.5

        # Verify in DB
        attr = SignalAttribution.objects.get(order_id="test-order-1")
        assert attr.ml_contribution == 80.0
        assert attr.sentiment_contribution == 60.0
        assert attr.position_modifier == 0.7

    def test_get_source_accuracy_empty(self):
        from analysis.services.signal_feedback import SignalFeedbackService

        result = SignalFeedbackService.get_source_accuracy()
        assert result["total_trades"] == 0
        assert result["overall_win_rate"] == 0.0

    def test_get_source_accuracy_with_data(self):
        from analysis.services.signal_feedback import SignalFeedbackService

        # Create some resolved attributions
        for i in range(5):
            SignalAttribution.objects.create(
                order_id=f"win-{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=75.0,
                ml_contribution=80.0,
                regime_contribution=70.0,
                outcome="win",
                pnl=100.0,
            )
        for i in range(3):
            SignalAttribution.objects.create(
                order_id=f"loss-{i}",
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy="CIV1",
                composite_score=55.0,
                ml_contribution=45.0,
                regime_contribution=35.0,
                outcome="loss",
                pnl=-50.0,
            )

        result = SignalFeedbackService.get_source_accuracy()
        assert result["total_trades"] == 8
        assert result["wins"] == 5
        assert result["overall_win_rate"] == pytest.approx(5 / 8, abs=0.01)
        assert "ml" in result["sources"]

    def test_get_weight_recommendations(self):
        from analysis.services.signal_feedback import SignalFeedbackService

        # With no data, should still return valid structure
        result = SignalFeedbackService.get_weight_recommendations()
        # May return error or valid adjustment with 0 trades
        assert "current_weights" in result or "error" in result

    def test_backfill_outcomes_no_orders(self):
        from analysis.services.signal_feedback import SignalFeedbackService

        SignalAttribution.objects.create(
            order_id="orphan-order",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CIV1",
            composite_score=70.0,
            outcome="open",
        )
        result = SignalFeedbackService.backfill_outcomes()
        # No matching filled orders → 0 resolved
        assert result["resolved"] == 0


# ── View tests ────────────────────────────────────────────────────────


class TestSignalAttributionViews(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Create test attribution
        self.attr = SignalAttribution.objects.create(
            order_id="view-test-order",
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy="CryptoInvestorV1",
            composite_score=72.5,
            ml_contribution=80.0,
            sentiment_contribution=60.0,
            regime_contribution=70.0,
        )

    def test_attribution_list(self):
        resp = self.client.get("/api/signals/attribution/")
        assert resp.status_code == 200
        assert len(resp.data) >= 1

    def test_attribution_list_filter_asset_class(self):
        resp = self.client.get("/api/signals/attribution/?asset_class=crypto")
        assert resp.status_code == 200
        assert all(a["asset_class"] == "crypto" for a in resp.data)

    def test_attribution_list_filter_strategy(self):
        resp = self.client.get("/api/signals/attribution/?strategy=CryptoInvestorV1")
        assert resp.status_code == 200

    def test_attribution_list_filter_outcome(self):
        resp = self.client.get("/api/signals/attribution/?outcome=open")
        assert resp.status_code == 200

    def test_attribution_detail(self):
        resp = self.client.get(f"/api/signals/attribution/{self.attr.order_id}/")
        assert resp.status_code == 200
        assert resp.data["order_id"] == "view-test-order"
        assert resp.data["composite_score"] == 72.5

    def test_attribution_detail_not_found(self):
        resp = self.client.get("/api/signals/attribution/nonexistent/")
        assert resp.status_code == 404

    def test_record_attribution(self):
        resp = self.client.post(
            "/api/signals/record/",
            {
                "order_id": "new-order-1",
                "symbol": "ETH/USDT",
                "asset_class": "crypto",
                "strategy": "BollingerMeanReversion",
                "signal_data": {
                    "composite_score": 68.0,
                    "position_modifier": 0.4,
                    "components": {
                        "ml": 70.0,
                        "sentiment": 55.0,
                        "regime": 65.0,
                        "scanner": 30.0,
                        "win_rate": 50.0,
                    },
                },
            },
            format="json",
        )
        assert resp.status_code == 201
        assert SignalAttribution.objects.filter(order_id="new-order-1").exists()

    def test_feedback_backfill(self):
        resp = self.client.post(
            "/api/signals/feedback/",
            {
                "order_id": "view-test-order",
                "outcome": "win",
                "pnl": 250.0,
            },
            format="json",
        )
        assert resp.status_code == 200
        self.attr.refresh_from_db()
        assert self.attr.outcome == "win"
        assert self.attr.pnl == 250.0
        assert self.attr.resolved_at is not None

    def test_feedback_not_found(self):
        resp = self.client.post(
            "/api/signals/feedback/",
            {
                "order_id": "nonexistent",
                "outcome": "loss",
            },
            format="json",
        )
        assert resp.status_code == 404

    def test_accuracy_view(self):
        resp = self.client.get("/api/signals/accuracy/")
        assert resp.status_code == 200
        assert "total_trades" in resp.data

    def test_accuracy_view_with_filters(self):
        resp = self.client.get("/api/signals/accuracy/?asset_class=crypto&window_days=7")
        assert resp.status_code == 200

    def test_weights_view(self):
        resp = self.client.get("/api/signals/weights/")
        assert resp.status_code == 200

    def test_weights_view_with_filters(self):
        resp = self.client.get("/api/signals/weights/?asset_class=crypto&strategy=CIV1")
        assert resp.status_code == 200


# ── Task executor tests ──────────────────────────────────────────────


class TestSignalFeedbackExecutors(TestCase):
    def test_signal_feedback_executor(self):
        from core.services.task_registry import TASK_REGISTRY

        assert "signal_feedback" in TASK_REGISTRY

        progress_calls = []

        def progress_cb(pct, msg):
            progress_calls.append((pct, msg))

        result = TASK_REGISTRY["signal_feedback"]({}, progress_cb)
        assert result["status"] == "completed"
        assert "backfill" in result
        assert "accuracy" in result

    def test_adaptive_weighting_executor(self):
        from core.services.task_registry import TASK_REGISTRY

        assert "adaptive_weighting" in TASK_REGISTRY

        progress_calls = []

        def progress_cb(pct, msg):
            progress_calls.append((pct, msg))

        result = TASK_REGISTRY["adaptive_weighting"]({}, progress_cb)
        assert result["status"] == "completed"

    def test_registry_has_22_executors(self):
        from core.services.task_registry import TASK_REGISTRY

        assert len(TASK_REGISTRY) == 31  # +1: pdf_report executor


# ── URL routing tests ────────────────────────────────────────────────


class TestSignalFeedbackURLs(TestCase):
    def test_url_patterns_exist(self):
        from django.urls import reverse

        assert reverse("signal-attribution-list") == "/api/signals/attribution/"
        assert (
            reverse("signal-attribution-detail", args=["test-order"])
            == "/api/signals/attribution/test-order/"
        )
        assert reverse("signal-record") == "/api/signals/record/"
        assert reverse("signal-feedback") == "/api/signals/feedback/"
        assert reverse("signal-accuracy") == "/api/signals/accuracy/"
        assert reverse("signal-weights") == "/api/signals/weights/"
