# Intelligence-to-Execution Bridge: Complete Implementation Plan

## Context

The A1SI-AITP platform has a fully operational intelligence layer (ML predictions, sentiment signals, regime detection, market scanner, VBT screening) and a fully operational execution layer (3 Freqtrade strategies, 7 NautilusTrader strategies, paper/live trading, risk management). **These two layers are completely disconnected.** Intelligence outputs feed dashboards and reports but never influence trade entry, exit, position sizing, or strategy selection. The result is low-quality entries in unfavorable conditions — the system takes too many trades with no conviction filtering.

This plan bridges the gap by creating a **Conviction Scoring System** that aggregates all intelligence into a composite score, gates entries, adapts position sizing, manages exits, and creates feedback loops for continuous improvement. Target: >55% win rate across asset classes, trending toward 80% as the feedback loop tunes weights.

---

## Architecture Overview

```
Intelligence Layer (existing)          NEW: Conviction Gate           Execution Layer (existing)
┌─────────────────────┐          ┌──────────────────────┐          ┌─────────────────────┐
│ ML Predictions      │──┐       │ SignalAggregator     │          │ Freqtrade (3 inst.) │
│ Sentiment Signal    │──┤       │   composite_score    │──gate──→ │ confirm_trade_entry │
│ Regime Detection    │──┼──────→│   entry_approved     │          │ custom_stake_amount  │
│ Market Scanner      │──┤       │   position_modifier  │──size──→ │ custom_stoploss      │
│ VBT Screening       │──┘       │   exit_advice        │──exit──→ │ custom_exit          │
│ Trade Performance   │──────────│   feedback_loop      │          │                     │
└─────────────────────┘          └──────────────────────┘          │ NautilusTrader (7)  │
                                          │                        │ Paper Trading       │
                                          ▼                        │ Risk Manager        │
                                 ┌──────────────────────┐          └─────────────────────┘
                                 │ Performance Feedback  │
                                 │ - Track outcomes      │
                                 │ - Tune weights        │
                                 │ - Retrain ML models   │
                                 └──────────────────────┘
```

---

## Phase 1: Signal Aggregation Core (`common/signals/`)

**New files to create:**

### 1.1 `common/signals/__init__.py`
Exports: `CompositeSignal`, `SignalAggregator`, `SignalCache`

### 1.2 `common/signals/aggregator.py` — Central signal combiner

**`CompositeSignal` dataclass:**
- `symbol`, `asset_class`, `timestamp`
- Component scores (all 0-1): `ml_score`, `sentiment_score`, `regime_score`, `scanner_score`, `screen_score`
- Component confidences: `ml_confidence`, `sentiment_conviction`, `regime_confidence`
- Outputs: `composite_score` (0-100), `signal_label` (strong_buy/buy/neutral/avoid), `entry_approved` (bool), `position_modifier` (0.2-1.5), `reasoning` (list[str])

**`SignalAggregator` class:**
- `compute(symbol, asset_class, strategy_name)` → `CompositeSignal`
- Collects from 6 sources via `_get_*_signal()` methods (each wraps try/except, fails gracefully)
- Weight scheme (configurable):

| Source | Weight | Fallback when unavailable |
|--------|--------|--------------------------|
| Technical (strategy-specific) | 0.30 | Always available |
| Regime alignment | 0.25 | Score 50, redistribute |
| ML prediction | 0.20 | Redistribute to tech + regime |
| Sentiment confirmation | 0.10 | Score 50 (neutral) |
| Scanner opportunity | 0.10 | Score 0 (no bonus) |
| Historical win rate | 0.05 | Score 50 (coin flip) |

- Missing signal weights redistributed proportionally to available signals
- Entry thresholds: `>=75` full size, `65-74` 70% size, `55-64` 40% size, `<55` reject

**Reuses:**
- `common/regime/regime_detector.py` → `RegimeDetector.detect()`
- `common/regime/strategy_router.py` → `StrategyRouter.route()`
- `common/sentiment/signal.py` → `compute_signal()`
- `common/ml/trainer.py` → `predict()`
- `common/ml/registry.py` → `load_model()`, `list_models()`

### 1.3 `common/signals/signal_cache.py` — Thread-safe TTL cache

- 5-minute default TTL (configurable)
- `threading.Lock` (consistent with `RiskManager` pattern)
- `get(symbol)`, `set(symbol, signal)`, `invalidate(symbol)`, `invalidate_all()`

### 1.4 `common/signals/constants.py` — All thresholds and alignment matrices

**Regime-Strategy Alignment Matrix (0-100):**

| Regime | CryptoInvestorV1 | BollingerMeanReversion | VolatilityBreakout |
|--------|-----------------|----------------------|-------------------|
| STRONG_TREND_UP | 95 | 30 | 60 |
| WEAK_TREND_UP | 75 | 50 | 70 |
| RANGING | 20 | 95 | 40 |
| WEAK_TREND_DOWN | 10 | 70 | 50 |
| STRONG_TREND_DOWN | 0 (hard disable) | 40 | 15 |
| HIGH_VOLATILITY | 30 | 60 | 90 |
| UNKNOWN | 25 | 40 | 30 |

**Equity and forex alignment tables** for NautilusTrader strategies (EquityMomentum, EquityMeanReversion, ForexTrend, ForexRange).

**Hard-disable rules:** CIV1 in STRONG_TREND_DOWN, VB in STRONG_TREND_DOWN → instant reject regardless of other scores.

**Regime change cooldown:** 6 bars after regime transition, apply 0.6x penalty to regime sub-score.

### 1.5 `common/signals/technical_scorers.py` — Per-strategy technical sub-scores

- `civ1_technical_score(candle)` → 0-100 (RSI depth + EMA alignment + MACD + volume + ADX)
- `bmr_technical_score(candle, bb_lower, bb_mid)` → 0-100 (BB distance + RSI + stochastic + MFI + volume)
- `vb_technical_score(candle, high_n)` → 0-100 (breakout margin + volume + BB expansion + ADX rising + RSI room)

**Estimated tests:** ~80

---

## Phase 2: Conviction-Aware Exit Management (`common/signals/`)

### 2.1 `common/signals/exit_manager.py`

**`ExitAdvice` dataclass:** `should_exit`, `reason`, `urgency` (immediate/next_candle/monitor), `partial_pct` (0.0=full, 0.5=half)

**`advise_exit()` function** — called from each strategy's `custom_exit`:
- **Regime deterioration exit:** If regime shifted against strategy since entry (e.g., CIV1 entered in STRONG_TREND_UP, now in WEAK_TREND_DOWN), exit profitable positions immediately
- **Partial profit taking:** Regime-aware targets (CIV1: 1/3 at 6%, 1/2 at 10%; BMR: 1/2 at 2%, 3/4 at 4%; VB: 1/3 at 5%)
- **Time-based exit:** Max hold hours per strategy × regime multiplier (CIV1: 168h base, BMR: 48h, VB: 72h; halved in STRONG_TREND_DOWN)
- **Regime-aware stop tightening:** Multiplier on ATR-based stops (1.0 in STRONG_TREND_UP → 0.5 in STRONG_TREND_DOWN)

**Estimated tests:** ~40

---

## Phase 3: ML Prediction Service & Feedback Loop (`common/ml/`)

### 3.1 `common/ml/prediction.py` — Real-time prediction service (NEW)

**`PredictionResult` dataclass:** `symbol`, `probability` (calibrated), `raw_probability`, `confidence`, `direction`, `model_id`, `regime`, `asset_class`

**`PredictionService` class:**
- `predict_single(symbol, timeframe, asset_class)` → `PredictionResult` (cached 5min)
- `predict_batch(symbols, timeframe, asset_class)` → `list[PredictionResult]`
- `score_opportunity(symbol, opp_type, scanner_score, asset_class)` → blended score
- Model selection cascade: exact-symbol → asset-class → best-accuracy fallback
- Thread-safe cache, <2s total latency

### 3.2 `common/ml/calibration.py` — Confidence calibration (NEW)

**`PredictionCalibrator` class:**
- Platt scaling: `calibrated = 1 / (1 + exp(a * raw + b))`, fitted on test set after training
- Rolling accuracy tracking per model (window=100 predictions)
- Confidence formula: `|calibrated_prob - 0.5| * 2 * rolling_accuracy`
- `needs_recalibration()` → True if accuracy < 52% with 50+ samples
- Stored as `calibration.json` in model directory (consistent with registry pattern)

### 3.3 `common/ml/ensemble.py` — Multi-model ensemble (NEW)

**`ModelEnsemble` class:**
- 3 modes: `simple_average`, `accuracy_weighted`, `regime_gated`
- Max 5 models per ensemble (keeps prediction <10ms)
- `agreement_ratio`: fraction of models agreeing on direction (secondary confidence signal)
- `build_from_registry(asset_class)` auto-selects best recent models

### 3.4 `common/ml/feedback.py` — Outcome tracking & retrain triggers (NEW)

**`FeedbackTracker` class:**
- `record_prediction()` → stores prediction record
- `backfill_outcomes()` → matches unresolved predictions with actual OHLCV returns
- `get_model_accuracy(model_id, lookback_days)` → accuracy metrics by regime/asset class
- `should_retrain(model_id)` → True if accuracy dropped, regime shifted, or model stale (7+ days)
- Storage: JSONL files in `models/_feedback/YYYY-MM-DD.jsonl` (avoids SQLite write contention)

### 3.5 `common/ml/features.py` — Enhanced feature engineering (MODIFY)

Add to existing `build_feature_matrix()`:
- **Regime features:** `regime_ordinal` (0-6), `regime_confidence`, `regime_adx`, `regime_trend_alignment`
- **Sentiment features:** `sentiment_score`, `sentiment_conviction`, `sentiment_position_modifier`
- **Temporal features:** `hour_sin/cos`, `dow_sin/cos`, `month_sin/cos` (cyclical encoding)
- **Volatility regime features:** `bb_width_percentile_100`, `atr_percentile_100`, `realized_vol_20`, `vol_of_vol_20`
- Features grow from ~55 to ~70; backward-compatible (new params optional)

### 3.6 `common/ml/trainer.py` — Training enhancements (MODIFY)

- Add `fit_calibration=True` param: fits Platt scaling on test set after training
- Save calibration params to manifest

**Estimated tests:** ~150

---

## Phase 4: Django API & Service Layer

### 4.1 `backend/analysis/services/signal_service.py` (NEW)

**`SignalService` class:**
- `get_signal(symbol, asset_class, strategy_name)` → dict (wraps `SignalAggregator`)
- `get_signals_batch(symbols, asset_class)` → list[dict]
- `get_entry_recommendation(symbol, strategy, asset_class)` → `{approved, score, position_modifier, reasoning}`

### 4.2 `backend/analysis/models.py` (MODIFY) — 2 new models

**`MLPrediction`:** prediction_id, model_id, symbol, asset_class, probability, confidence, direction, regime, actual_direction (filled later), correct (filled later), predicted_at
- Indexes: (model_id, -predicted_at), (symbol, -predicted_at)

**`MLModelPerformance`:** model_id (PK), total_predictions, correct_predictions, rolling_accuracy, accuracy_by_regime (JSON), retrain_recommended, updated_at

### 4.3 New API endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/signals/<symbol>/` | GET | Session | Composite signal for dashboard |
| `/api/signals/batch/` | POST | Session | Batch signals for watchlist |
| `/api/signals/<symbol>/entry-check/` | POST | None* | Entry gate for Freqtrade |
| `/api/signals/strategy-status/` | GET | Session | Which strategies should be active |
| `/api/ml/predictions/<symbol>/` | GET | Session | Recent predictions audit |
| `/api/ml/models/<model_id>/performance/` | GET | Session | Model accuracy metrics |

*Unauthenticated like existing `TradeCheckView` (internal Freqtrade calls)

### 4.4 `backend/core/services/task_registry.py` (MODIFY) — 4 new executors

| Executor | Interval | Purpose |
|----------|----------|---------|
| `_run_ml_predict` | 1h | Batch ML predictions for watchlist, store `MLPrediction` records |
| `_run_ml_feedback` | 1h (offset 30m) | Backfill outcomes, update `MLModelPerformance`, set retrain flags |
| `_run_ml_retrain` | Weekly (or triggered) | Retrain models flagged by feedback loop |
| `_run_conviction_audit` | 1h | Log conviction scores, compute rolling accuracy, adjust thresholds |
| `_run_strategy_orchestration` | 15m | Check regime alignment for all strategies, set pause/resume flags |

### 4.5 `backend/analysis/urls.py` (MODIFY) — Wire new views

**Estimated tests:** ~80

---

## Phase 5: Freqtrade Strategy Integration

### 5.1 All 3 strategies — `confirm_trade_entry()` (MODIFY)

Add conviction gate after existing risk gate:
```
1. Check risk gate (existing, fail-open)
2. NEW: Fetch composite signal from /api/signals/<pair>/entry-check/
3. If score < threshold: return False (block entry)
4. If score >= threshold: return True (existing risk approval stands)
```
- Fail-open: if signal API unreachable, approve (consistent with risk gate pattern)
- Skip in BACKTEST/HYPEROPT mode (preserve historical fidelity)

### 5.2 All 3 strategies — `custom_stake_amount()` (NEW hook)

Scale position size by `signal.position_modifier`:
- Score >=75: 1.0x (full), 65-74: 0.7x, 55-64: 0.4x
- Further multiplied by regime modifier and sentiment modifier
- Clamped to [min_stake, max_stake]

### 5.3 All 3 strategies — `custom_exit()` (MODIFY or NEW)

Call `advise_exit()` from exit_manager:
- Check regime deterioration, partial profit targets, time-based exits
- Return exit signal with `exit_tag` for analytics

### 5.4 All 3 strategies — `custom_stoploss()` (MODIFY or NEW)

Apply regime-aware stop tightening multiplier (1.0x in trending → 0.5x in STRONG_TREND_DOWN)

### 5.5 All 3 strategies — `bot_loop_start()` (NEW hook)

Fetch and cache composite signals for all active pairs every 5 minutes. Store in `self._signals` dict for use by other hooks.

**Files modified:**
- `freqtrade/user_data/strategies/CryptoInvestorV1.py`
- `freqtrade/user_data/strategies/BollingerMeanReversion.py`
- `freqtrade/user_data/strategies/VolatilityBreakout.py`

**Estimated tests:** ~40

---

## Phase 6: NautilusTrader Integration

### 6.1 `nautilus/strategies/base.py` (MODIFY)

In `on_bar()`, after `should_enter()` returns True:
- Fetch composite signal via `_get_composite_signal()` (API call in live mode, skip in backtest)
- If `entry_approved=False`: skip entry
- Apply `position_modifier` to computed position size
- Store entry regime in position metadata for exit advisor

In `on_bar()` exit path:
- Call exit advisor to check regime deterioration and time limits

### 6.2 `nautilus/strategies/nt_native.py` (MODIFY)

Same pattern for the native adapter's `on_bar()`.

**Estimated tests:** ~30

---

## Phase 7: Risk Manager Enhancement

### 7.1 `common/risk/risk_manager.py` (MODIFY)

- `calculate_position_size()`: add `signal_modifier` param (already has `regime_modifier`). Clamped [0.2, 1.5].
- Wire: `SignalAggregator.compute()` → `position_modifier` → `signal_modifier`

### 7.2 `backend/risk/services/risk.py` (MODIFY)

- `periodic_risk_check()`: add adaptive risk tightening based on regime
  - STRONG_TREND_DOWN / HIGH_VOLATILITY: temporarily tighten daily_loss limit by 30-50%
  - These are runtime adjustments, not permanent changes to `RiskLimits` model
  - Logged via AlertLog for audit

### 7.3 `backend/risk/views.py` — `TradeCheckView` (MODIFY)

Accept optional `composite_score` in request body. Log ML agreement/disagreement. Future: gate when ML confidence is proven (accuracy >60% over 200+ predictions).

**Estimated tests:** ~25

---

## Phase 8: Strategy Orchestrator

### 8.1 `backend/trading/services/strategy_orchestrator.py` (NEW)

**`StrategyOrchestrator` class:**
- `evaluate()` → checks regime alignment for all running Freqtrade instances
- If regime misaligned (e.g., CIV1 in STRONG_TREND_DOWN):
  - Sets "paused" flag in SignalCache (not process kill)
  - Logs to AlertLog
  - Sends Telegram notification
  - WS broadcast for dashboard
- Each strategy's `confirm_trade_entry()` checks pause flag before allowing new entries
- Existing open positions continue to manage risk via their own exit logic

### 8.2 Scheduled task: `_run_strategy_orchestration` (every 15 min)

**Estimated tests:** ~20

---

## Phase 9: Asset-Class Specific Tuning

### 9.1 `common/signals/asset_tuning.py` (NEW)

Per-asset-class parameter overrides:

| Parameter | Crypto | Equity | Forex |
|-----------|--------|--------|-------|
| Conviction threshold | 55 | 65 | 60 |
| Regime cooldown bars | 6 | 3 | 4 |
| Max hold multiplier | 1.0x | 2.0x | 0.7x |
| Volume weight bonus | 1.0x | 1.3x | 0.5x |
| Session filter | None | NYSE hours | London-NY overlap preferred |
| Spread max | 0.5% | 0.2% | 0.1% |

Forex session conviction bonuses: London-NY overlap (-10 threshold), Asian (+5), Dead zone (+15).

**Estimated tests:** ~15

---

## Phase 10: Performance Feedback & Adaptive Tuning

### 10.1 `common/signals/feedback.py` (NEW)

**`PerformanceFeedback` class:**
- `compute_weight_adjustments(window_days=30)` → analyze recent trades, attribute wins/losses to signal sources
- If ML-approved trades win >60%: increase ML weight
- If sentiment-aligned trades outperform: increase sentiment weight
- If a weight source consistently predicts wrong: decrease toward 0
- Adaptive threshold: if win rate <50%, raise conviction threshold by 5; if >65%, lower by 3 (clamp [50, 80])

### 10.2 `common/signals/performance_tracker.py` (NEW)

**`SignalAttribution` dataclass:** Records which signals contributed to each trade and the outcome.
- Stored in DB for analysis (new `SignalAttribution` model)
- Queried by feedback loop and displayed on frontend

### 10.3 New Django model: `SignalAttribution` in `analysis/models.py`

Fields: order_id, symbol, composite_score, ml_contribution, sentiment_contribution, regime_contribution, scanner_contribution, outcome (win/loss/open), pnl, recorded_at

**Estimated tests:** ~30

---

## Phase 11: Frontend Conviction Dashboard

### 11.1 New page: `frontend/src/pages/ConvictionDashboard.tsx`

- Real-time conviction scores per symbol (color-coded heatmap)
- Signal component breakdown (radar chart: technical, regime, ML, sentiment, scanner)
- Strategy orchestrator status (which strategies active/paused + why)
- Performance attribution chart (which signal sources driving wins)
- Conviction score history timeline

### 11.2 Dashboard integration

- Add conviction score to existing Trading page order form
- Add "Signal Quality" indicator to Market Opportunities page
- Add ML prediction accuracy widget to ML Models page

**Estimated tests:** ~40

---

## Phase 12: Tests & Validation

- Unit tests for all new modules (~80 signal, ~40 exit, ~150 ML, ~80 API, ~40 FT, ~30 NT, ~25 risk, ~20 orchestrator, ~15 tuning, ~30 feedback, ~40 frontend)
- **Total estimated new tests: ~550**
- Integration test: end-to-end flow from signal computation → entry gate → position sizing → exit advice
- Backtest validation: run Freqtrade backtest with and without conviction gate, compare win rates

---

## Implementation Order

| Step | Phase | Dependencies | Est. New Files | Est. Modified Files |
|------|-------|-------------|----------------|-------------------|
| 1 | Phase 1 (Signal Aggregation) | None | 5 | 0 |
| 2 | Phase 2 (Exit Management) | Phase 1 | 1 | 0 |
| 3 | Phase 3 (ML Enhancement) | Phase 1 | 4 | 2 |
| 4 | Phase 4 (Django API) | Phases 1-3 | 2 | 3 |
| 5 | Phase 5 (Freqtrade) | Phase 4 | 0 | 3 |
| 6 | Phase 6 (NautilusTrader) | Phase 4 | 0 | 2 |
| 7 | Phase 7 (Risk Manager) | Phase 1 | 0 | 3 |
| 8 | Phase 8 (Orchestrator) | Phase 4 | 1 | 1 |
| 9 | Phase 9 (Asset Tuning) | Phase 1 | 1 | 0 |
| 10 | Phase 10 (Feedback Loop) | Phases 4, 5 | 2 | 1 |
| 11 | Phase 11 (Frontend) | Phase 4 | 1 | 3 |
| 12 | Phase 12 (Tests) | All | ~12 test files | 0 |

**Totals: ~17 new files, ~18 modified files, ~550 new tests**

---

## Verification Plan

1. **Unit tests:** `make test` — all 5500+ tests pass (existing 5027 + ~550 new)
2. **Lint:** `make lint` — zero ruff/eslint errors
3. **Signal computation:** `python -c "from common.signals.aggregator import SignalAggregator; s = SignalAggregator(); print(s.compute('BTC/USDT', 'crypto', 'CryptoInvestorV1'))"` — returns valid CompositeSignal
4. **API endpoint:** `curl http://localhost:8000/api/signals/BTC-USDT/entry-check/ -X POST -d '{"strategy":"CryptoInvestorV1","asset_class":"crypto"}'` — returns score + approved
5. **Freqtrade integration:** Start paper trading, observe conviction scores in logs, verify low-score entries are blocked
6. **Win rate tracking:** After 7 days of paper trading with conviction gate, compare win rate vs. previous period
7. **Feedback loop:** After 30 days, verify weight adjustments are being computed and threshold is adapting

---

## Expected Outcomes

| Metric | Before | After (Est.) |
|--------|--------|-------------|
| Entries per day (crypto) | 5-15 | 1-4 |
| Win rate | ~40-45% | 55-65% (initial), 70-80% (after feedback tuning) |
| Profit factor | ~0.8-1.0 | 1.3-1.8 |
| Max drawdown | Unconstrained | Regime-adaptive (30-50% tighter in downtrends) |
| Average conviction at entry | N/A (no filtering) | 65+ (only quality trades) |

The key insight: **filtering out bad trades contributes more to win rate than finding new good trades.** The existing strategies already identify reasonable entries — the intelligence layer's job is to say "not now" when conditions are unfavorable.
