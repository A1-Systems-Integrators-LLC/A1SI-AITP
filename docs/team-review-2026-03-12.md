# Team Review: Consolidated Findings (2026-03-12)

## The Big Picture

Six independent specialist reviews converged on a clear diagnosis: **the platform's architecture is impressive, but the intelligence layer is operating at a fraction of its designed capacity.** Multiple critical systems are silently broken or misconfigured, meaning the sophisticated conviction/signal/ML pipeline is largely decorative right now.

---

## CRITICAL Issues (Fix Immediately)

### 1. ML Predictions Silently Dead
**Flagged by**: Quant Dev, ML Engineer
**File**: `backend/analysis/services/signal_service.py:56-58`
`build_feature_matrix()` returns a tuple `(X, y, feature_names)` but it's passed whole to `ensemble.predict()`. The broad `except Exception` swallows the TypeError. **ML (20% signal weight) contributes nothing.**

### 2. Technical Score Never Populated
**Flagged by**: Quant Dev
**File**: `backend/analysis/services/signal_service.py:135-165`
`get_signal()` never calls the technical scorer functions. **The largest signal source (30% weight) is always None.** Combined with #1, the conviction system runs on only 50% of its intended intelligence — regime, sentiment, scanner, and win_rate.

### 3. Risk System Monitoring Phantom $10K Portfolio
**Flagged by**: Strategy Engineer
**File**: `backend/core/services/task_registry.py:280`
`_sync_freqtrade_equity` uses `initial_capital = 10000` from platform config. Actual capital is $500. Drawdown limits trigger at $1,500 loss instead of $75. **The risk system is effectively decorative.**

### 4. Regime Detector Freezing 60% of Capital
**Flagged by**: Crypto Analyst
**File**: `common/regime/regime_detector.py`
ADX 11-16 is barely directional, yet scored as WEAK_TREND_DOWN. CIV1 (alignment=10) and VB (alignment=5) are paused. **Only BMR's $200 can trade.** BMR was also broken until Mar 6, so we've had near-zero active trading capacity for most of the pilot.

### 5. 89% of Watchlist Has No Data
**Flagged by**: Data Engineer
36 crypto configured, 3 have data. 106 equity configured, 10 have data. 44 forex configured, 8 have data. **The market scanner, ML, VBT screener, and regime detector are blind to 165 of 186 symbols.**

### 6. Risk Tasks Starved by Compute Jobs
**Flagged by**: Tech Lead
**File**: `backend/analysis/services/job_runner.py`
`ThreadPoolExecutor(max_workers=2)` with no priority. A 30-minute VBT screen blocks risk_monitoring. **Critical safety checks can be delayed indefinitely.**

### 7. Task Failures Silently Recorded as "Completed"
**Flagged by**: Tech Lead
**File**: `backend/core/services/task_registry.py`
Executors return `{"status": "error"}` instead of raising. JobRunner marks them "completed." **risk_monitoring could fail for hours with no alert.**

### 8. Freqtrade Equity Sync Resets on Failure
**Flagged by**: Tech Lead, Strategy Engineer
If all 3 Freqtrade instances are unreachable, `total_pnl` resets to 0 and equity to `initial_capital`. **A drawdown can be silently masked.**

---

## HIGH Priority (Fix Before Live Trading)

### 9. No Exchange-Side Stop Losses
**Flagged by**: Strategy Engineer
`stoploss_on_exchange: false` in all 3 configs. If Freqtrade crashes, no downside protection. **Unbounded loss risk in live.**

### 10. Partial Exits Close Entire Positions
**Flagged by**: Quant Dev
`custom_exit()` returns a string tag (full close), but `ExitAdvice.partial_pct` suggests fractional exits. A CIV1 trade at 6% profit closes 100% instead of 1/3. **Winning trades are cut short.**

### 11. All-In Position Sizing
**Flagged by**: Quant Dev, Strategy Engineer, Crypto Analyst
`stake_amount: "unlimited"` with `tradable_balance_ratio: 0.90` = each trade is 90% of wallet. No Kelly criterion. No cross-strategy correlation check — all 3 could enter BTC simultaneously.

### 12. Orchestrator State Lost on Restart
**Flagged by**: Strategy Engineer
`_states` dict is in-memory. Docker restart un-pauses all strategies. **In a bearish regime, restart = immediate bad trades.**

### 13. RegimeDetector Hysteresis Never Accumulates
**Flagged by**: Quant Dev
New `RegimeDetector()` created per call. Hysteresis state (`_regime_hold_count`) always starts at 0. **Regime transitions are noisy, triggering false exits.**

### 14. Walk-Forward Validation Flawed
**Flagged by**: Quant Dev
OOS gets its own parameter sweep instead of using IS-best params. **Robustness checks overstate strategy quality.**

### 15. Atomic Parquet Writes Missing
**Flagged by**: Data Engineer
Crash during `df.to_parquet()` corrupts the file. No temp-file + rename pattern. **Data loss risk.**

### 16. Signal Service Uncached
**Flagged by**: Tech Lead
5 sequential data-fetch calls with ML inference per signal request. Freqtrade's 5s timeout → fail-open. **Conviction gate bypassed under normal load.**

---

## MEDIUM Priority (Improve Performance)

| # | Issue | Source |
|---|-------|--------|
| 17 | ML target too noisy (1-bar binary, should be multi-bar with dead zone) | ML Eng, Quant |
| 18 | ~70 features on ~600 rows (overfitting risk, need feature reduction) | ML Engineer |
| 19 | Calibration never applied (Platt scaling built but never wired in) | ML Engineer |
| 20 | No cross-validation (single 80/20 split, unreliable accuracy) | ML Engineer |
| 21 | ML feedback loop has zero resolved outcomes (paper trades not backfilled) | ML Engineer |
| 22 | BMR computes 24 BB combos, uses 1 (memory/CPU waste) | Quant Dev |
| 23 | 5-min signal cache too slow for HV regime | Quant Dev |
| 24 | No economic calendar for forex (event-window losses) | Data Engineer |
| 25 | Missing 4h timeframe data (crypto + forex) | Data Engineer |
| 26 | No data quality auto-remediation (stale files just log warnings) | Data Engineer |
| 27 | Docker healthcheck passes on degraded state | Tech Lead |
| 28 | Scheduler startup race conditions, no failure alerting | Tech Lead |
| 29 | SQLite concurrent write tuning (CONN_MAX_AGE, WAL frequency) | Tech Lead |
| 30 | Grafana + Prometheus for unified monitoring | Tech Lead |

---

## NEW Capabilities Recommended

| Capability | Source | Expected Impact |
|-----------|--------|----------------|
| **Funding rate data** (free via CCXT) | Crypto Analyst, Data Eng | 20-30% trade timing improvement |
| **Open interest data** | Crypto Analyst | Trend confirmation |
| **BTC dominance as regime signal** | Crypto Analyst | Better altcoin filtering |
| **Cross-asset ML features** (BTC→ALT, DXY→forex) | Data Engineer | Model accuracy |
| **Order book depth snapshots** | Data Engineer | HFT + microstructure signals |
| **VADER/TextBlob sentiment** | Data Engineer | Better NLP than keywords |
| **XGBoost as ensemble diversity** | ML Engineer | 1-3% accuracy improvement |
| **Hyperparameter tuning** (random search) | ML Engineer | 2-5% accuracy improvement |
| **PostgreSQL migration** (plan for future) | Tech Lead | Eliminates SQLite bottleneck |
| **Grafana + Prometheus** | Tech Lead | Unified monitoring/alerting |

---

## Recommended Execution Order

### Phase A — "Stop the Bleeding" (restore what's broken) ✅ COMPLETE
1. ✅ Fix ML tuple bug (`signal_service.py:56`)
2. ✅ Wire in technical scorers (`signal_service.py:135`)
3. ✅ Fix equity baseline to $500 (`task_registry.py:280`)
4. ✅ Recalibrate regime detector for low-ADX (RANGING vs WTD)
5. ✅ Full data backfill for all 186 watchlist symbols (50-symbol cap removed)
6. ✅ Split job pool (critical vs batch workers)
7. ✅ Add failure alerting for critical tasks

### Phase B — "Protect the Capital" (live-trading readiness) ✅ COMPLETE
8. ✅ Enable `stoploss_on_exchange: true`
9. ✅ Persist orchestrator state to JSON (survives restarts)
10. ✅ Fix position sizing (explicit stake amounts: $60/$50/$30)
11. ✅ Add signal staleness TTL (15min max-age)
12. ✅ Atomic Parquet writes (write to .tmp then os.replace)
13. ✅ Cache signal computations (60s TTL, thread-safe)

### Phase C — "Add Alpha" (new signal sources + ML improvements) ✅ COMPLETE
14. ✅ Funding rate data collection (fetch/save/load + ML feature integration)
15. ✅ Multi-bar ML target with dead zone (horizon=3, dead_zone=0.5%)
16. ✅ Feature reduction (~70 → ~35, correlation filter + variance cap)
17. ✅ Enable calibration in training + prediction (fit_calibration=True, auto-load in PredictionService)
18. ✅ Walk-forward validation fix (OOS evaluates IS-best params, not re-optimized)
19. ✅ Prometheus metrics enhanced (HELP/TYPE annotations, ML/orchestrator/signal gauges)
