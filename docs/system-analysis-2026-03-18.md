# System Analysis Report — 2026-03-18

Full 5-specialist team analysis of bugs, silent failures, and reliability issues.

## CRITICAL (4 issues)

| # | Domain | Issue | File | Impact |
|---|--------|-------|------|--------|
| **C1** | ML/Signal | **ML weight is 0.00** — entire ML pipeline has zero influence on trading | `common/signals/constants.py:11` | All ML training/prediction/ensemble/calibration is wasted computation |
| **C2** | ML/Signal | **Feature column mismatch between training and prediction** — `_reduce_features()` is data-dependent, producing different columns at train vs predict time; LightGBM uses positional index | `common/ml/features.py:481-509` | ML predictions are silently garbage when columns misalign |
| **C3** | Risk | **`abs()` on daily P&L in periodic_risk_check** — profits trigger auto-halt | `backend/risk/services/risk.py:319-321` | A +5% profitable day auto-halts all trading |
| **C4** | Backend | **`load_ohlcv()` called with invalid `asset_class` kwarg** in ML feedback loop | `backend/core/services/task_registry.py:825` | TypeError on every call — ML feedback/outcome backfill completely dead |

## HIGH (13 issues)

| # | Domain | Issue | File |
|---|--------|-------|------|
| **H1** | ML/Signal | **`macro` source (12% weight) never populated** — weight silently redistributed, inflating technical/regime | `constants.py:16`, `signal_service.py` |
| **H2** | ML/Signal | **`technical` source missing from `SignalAttribution`** — highest-weight signal (35%) invisible to feedback loop | `signal_feedback.py:45-60` |
| **H3** | ML/Signal | **Feedback loop never applied** — `PerformanceFeedback` + `PerformanceTracker` are recreated fresh each call, adaptive weights reset to defaults | `performance_tracker.py` |
| **H4** | ML/Signal | **P&L attribution matches wrong closing orders** — first opposite-side fill used regardless of trade linkage | `signal_feedback.py:296-329` |
| **H5** | Risk | **`check_new_trade` not thread-safe** — reads state without lock; concurrent calls can bypass position limits | `risk_manager.py:323-393` |
| **H6** | Risk | **`_sync_freqtrade_equity` writes same equity to ALL portfolios** | `task_registry.py:346-355` |
| **H7** | Risk | **`open_positions` in RiskState never populated** — max_open_positions limit never enforced | `risk/services/risk.py` |
| **H8** | Risk | **Correlation/VaR always empty** — `_build_risk_manager` creates fresh ReturnTracker every call | `risk/services/risk.py:30-56` |
| **H9** | Risk | **Strategy orchestrator un-pauses all strategies on any exception** (data error → strategies resume) | `strategy_orchestrator.py:205-211` |
| **H10** | Freqtrade | **Partial profit exits are full exits** — Freqtrade can't partially close; `partial_pct` logged but never acted on | `_conviction_helpers.py:297-314` |
| **H11** | Freqtrade | **Stoploss values never updated**: CIV1=-4% (should be -7%), BMR=-3% (should be -6%), VB=-3% (should be -5%) | All 3 strategy files |
| **H12** | Data | **Momentum shift scanner completely dead** — looks for column `"histogram"` but MACD returns `"macd_hist"` | `market_scanner.py:406` |
| **H13** | Data | **Equity symbols misclassified as crypto** by `_guess_asset_class` — per-symbol equity regime always returns "unknown" | `regime.py:152-167` |

## MEDIUM (14 issues)

| # | Domain | Issue |
|---|--------|-------|
| **M1** | ML/Signal | `entry_regime` always empty string on SignalAttribution records |
| **M2** | ML/Signal | XGBoost training ignores Optuna-tuned parameters (tunes LightGBM params, discards them) |
| **M3** | ML/Signal | `inf` values from volume_ratio division by zero not caught (NaN dropped, inf not) |
| **M4** | Risk | Async halt/resume AlertLog creation in try/except — emergency halts can have no audit trail |
| **M5** | Risk | Stuck order timeout bypasses `transition_to()` state machine (skips WS broadcast) |
| **M6** | Risk | Forex/equity paper trading P&L not tracked in RiskState (no drawdown monitoring) |
| **M7** | Risk | `check_new_trade` doesn't check daily loss proactively (only checked in `update_equity`) |
| **M8** | Data | RegimeService always uses crypto thresholds for equity/forex (per-class config never applied) |
| **M9** | Data | `validate_data` doesn't pass asset_class — equity data always flagged as stale |
| **M10** | Data | `list_available_data` misparses funding rate filenames as OHLCV |
| **M11** | Data | Gap detection produces false positives for equity (overnight gaps) and forex (weekend gaps) |
| **M12** | Freqtrade | CIV1 STRONG_TREND_DOWN alignment=60 wrong for long-only strategy (delays deterioration exits) |
| **M13** | Freqtrade | BMR volume_factor=1.2, RSI=33, ADX_ceiling=30 all more restrictive than documented |
| **M14** | Backend | Health check doesn't validate journal mode value — always reports "ok" even for WAL |

## LOW (18 issues)

Order sync no backoff, RegimeDetector reinstantiated per call, triple Parquet reads per signal, screen/win_rate duplicate attribution, stale regime singleton, swallowed Prometheus exceptions, various MEMORY.md documentation mismatches, NaN not guarded in ATR stoploss, and others.

## Top Priority Fix Order

1. **C3** — `abs()` daily loss: Actively halting trading on profitable days
2. **C4** — ML feedback `TypeError`: Entire feedback loop is dead
3. **C1** — ML weight=0: All ML infrastructure produces nothing
4. **C2** — Feature mismatch: When ML is enabled, predictions will be garbage
5. **H11** — Stoploss values: Strategies stopped out 40-50% tighter than intended
6. **H12** — Dead momentum scanner: Entire detector never fires
7. **H9** — Orchestrator un-pause on error: Safety pauses defeated by transient errors
8. **H7/H8** — Risk state never populated: Position limits and VaR are decorative
9. **H10** — Partial exits as full exits: Winning positions closed entirely too early
10. **M14** — Health check WAL validation: Critical safety check is a no-op
