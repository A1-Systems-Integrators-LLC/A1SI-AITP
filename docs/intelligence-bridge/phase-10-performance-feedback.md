# IEB Phase 10: Performance Feedback & Adaptive Tuning

**Status**: COMPLETE
**Date**: 2026-03-10

## What Was Built

### New Files
1. **`common/signals/performance_tracker.py`** — `PerformanceTracker` class with `AttributionRecord` and `SourceAccuracy` dataclasses. Thread-safe in-memory tracking of signal attributions: record at entry, backfill outcome at exit, compute per-source accuracy (win rate, avg score win vs loss). Filters by asset_class, strategy, window_days.

2. **`common/signals/feedback.py`** — `PerformanceFeedback` class with `WeightAdjustment` dataclass. Adaptive weight tuning engine: analyzes trade outcomes per signal source, increases weight for >60% win rate sources (+0.05), decreases for <45% (-0.05), normalizes to sum=1.0. Adaptive threshold: raise +5 when win rate <50%, lower -3 when >65%. Clamped [50, 80]. Thread-safe.

3. **`backend/analysis/services/signal_feedback.py`** — `SignalFeedbackService` Django service layer. Bridges common.signals with Django ORM: record_attribution (creates SignalAttribution), backfill_outcomes (matches open attributions with filled orders), get_source_accuracy (DB aggregation), get_weight_recommendations (loads DB into PerformanceTracker→PerformanceFeedback).

### Modified Files
4. **`backend/analysis/models.py`** — Added `SignalAttribution` model with 3 indexes (symbol+date, strategy+asset+date, outcome+date). Fields: order_id, symbol, asset_class, strategy, composite_score, 6 contribution fields (ml/sentiment/regime/scanner/screen/win_rate), position_modifier, entry_regime, outcome (win/loss/open), pnl, recorded_at, resolved_at.

5. **`common/signals/__init__.py`** — Added exports: PerformanceFeedback, WeightAdjustment, AttributionRecord, PerformanceTracker, SourceAccuracy.

6. **`backend/analysis/serializers.py`** — 5 new serializers: SignalAttributionSerializer, RecordAttributionRequestSerializer, BackfillOutcomeRequestSerializer, SourceAccuracyResponseSerializer, WeightRecommendationResponseSerializer.

7. **`backend/analysis/views.py`** — 6 new views: SignalAttributionListView (GET, filtered), SignalAttributionDetailView (GET by order_id), SignalRecordView (POST), SignalFeedbackView (POST), SignalAccuracyView (GET), SignalWeightsView (GET).

8. **`backend/analysis/urls.py`** — 6 new URL patterns (static routes before parameterized to avoid `<str:symbol>` matching).

9. **`backend/core/services/task_registry.py`** — 2 new executors: `signal_feedback` (backfill outcomes + compute accuracy) and `adaptive_weighting` (compute + log weight recommendations). TASK_REGISTRY now has 22 executors.

10. **`backend/config/settings.py`** — 2 new scheduled tasks: signal_feedback (hourly), adaptive_weighting (daily). DEFAULT_SCHEDULED_TASKS now has 24 entries.

### Migration
- `backend/analysis/migrations/0006_add_signal_attribution.py`

### API Endpoints (6 new)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/signals/attribution/` | GET | List attributions (filters: asset_class, strategy, outcome, limit) |
| `/api/signals/attribution/<order_id>/` | GET | Single attribution detail |
| `/api/signals/record/` | POST | Record signal at trade entry |
| `/api/signals/feedback/` | POST | Backfill outcome for attribution |
| `/api/signals/accuracy/` | GET | Per-source accuracy stats |
| `/api/signals/weights/` | GET | Current + recommended weights |

### Tests
- **45 new tests** in `backend/tests/test_signal_feedback_phase10.py`
- Model tests: create, __str__, clean validation, ordering
- PerformanceTracker: record entry/outcome, source accuracy, filtering, clear
- PerformanceFeedback: insufficient trades, weight increase/decrease, threshold adjustment, apply/reset, normalization
- Django service: record_attribution, backfill_outcomes, source_accuracy, weight_recommendations
- Views: all 6 endpoints (list, detail, record, feedback, accuracy, weights) with filters and error cases
- Task executors: signal_feedback, adaptive_weighting, registry count
- URL routing: all 6 patterns resolve correctly
