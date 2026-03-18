# Profitability Overhaul Plan

**Created**: 2026-03-17
**Status**: ALL 6 PHASES COMPLETE (2026-03-18)
**Team**: 6-specialist review (Quant Dev, ML Engineer, Strategy Engineer, Risk Specialist, Data Engineer, Crypto Analyst)

---

## Executive Summary

The trading system has **multiple critical bugs and misconfigurations** that make profitability impossible in the current state. The most damaging finding: **~40% of signal weight (technical + regime) is completely non-functional** due to API signature bugs where `RegimeDetector.detect()` receives a string symbol instead of a DataFrame. Additionally, all three Freqtrade strategies run in **futures mode with 3x leverage on $300 wallets**, creating catastrophic drawdown risk.

This plan has **6 phases**, ordered by impact. Phases 1-2 are bug fixes that restore broken functionality. Phases 3-6 are parameter tuning and architectural improvements.

---

## Phase 1: Critical Bug Fixes (Restore Broken Systems)

These bugs mean ~40% of signal weight and the entire orchestrator/risk regime system are silently failing.

### 1.1 Fix RegimeDetector API calls (4 callsites)

**Bug**: `RegimeDetector.detect()` accepts `(self, df: pd.DataFrame)` but is called with `(symbol_string, asset_class=...)` in 4 places. All calls crash silently, caught by try/except, returning None/fallback.

**Files & fixes**:

| File | Line | Current (broken) | Fix |
|------|------|-------------------|-----|
| `backend/analysis/services/signal_service.py` | ~92 | `detector.detect(symbol, asset_class=asset_class)` | Load OHLCV via `load_ohlcv(symbol, "1h", exchange_id)`, pass DataFrame to `detector.detect(df)` |
| `backend/analysis/views.py` (StrategyStatusView) | ~919 | `detector.detect(sym, asset_class=asset_class)` | Same pattern |
| `backend/risk/services/risk.py` | ~280 | `detector.detect("BTC/USDT")` then `.get("regime")` on RegimeState | Load OHLCV, pass DataFrame, use `state.regime.value` |
| `backend/trading/services/strategy_orchestrator.py` | ~183 | `detector.detect(sym, asset_class=asset_class)` | Load OHLCV via new `_load_regime_data()` helper, pass DataFrame |

**Impact**: Re-enables regime alignment (18% signal weight), strategy orchestrator pause/reduce, and adaptive risk tightening. This is the single highest-impact fix.

### 1.2 Fix `_get_technical_score()` passing asset_class as exchange_id

**Bug**: `signal_service.py` line ~212 calls `load_ohlcv(symbol, "1h", asset_class=asset_class)` but `load_ohlcv` has no `asset_class` kwarg — it binds to `exchange_id`, looking for files like `crypto_BTC_USDT_1h.parquet` instead of `kraken_BTC_USDT_1h.parquet`.

**Fix**: Replace with:
```python
source = "yfinance" if asset_class in ("equity", "forex") else "kraken"
df = load_ohlcv(symbol, "1h", source)
```

**Impact**: Re-enables technical scoring (22% signal weight). Combined with 1.1, restores 40% of signal that was dead.

### 1.3 Fix SignalAggregator recreated per call (regime cooldown broken)

**Bug**: `signal_service.py` line ~82 creates a new `SignalAggregator()` on every `get_signal()` call. The cooldown tracking (`_last_regimes`, `_regime_bar_counts`) resets each call, so regime change cooldown penalty never fires.

**Fix**: Use a module-level singleton for the aggregator instance.

### 1.4 Fix profit conversion bug in _conviction_helpers.py

**Bug**: Line ~305 passes `current_profit * 100` to `advise_exit()` as `current_profit_pct`. Freqtrade's `current_profit` is already a ratio (0.06 = 6%). Multiplying by 100 gives 6.0, compared against thresholds like 0.06 — exits fire on essentially every profitable trade.

**Fix**: Change `current_profit_pct=current_profit * 100` to `current_profit_pct=current_profit`.

### 1.5 Fix equity data: only 1d exists but signal service uses 1h

**Bug**: Equity downloads only daily bars, but `signal_service` hardcodes `"1h"` timeframe for technical scores and ML. All equity signals return None.

**Fix**: Add `"1h"` to equity timeframes in `pipeline.py` line ~519 (yfinance supports 730 days of 1h data). Or make signal service timeframe-aware per asset class.

### 1.6 Fix RSI calculation inconsistency

**Bug**: `pipeline.py` `add_indicators()` uses SMA-based RSI; `technical.py` `rsi()` uses Wilder's smoothing (industry standard). Different RSI values from same data (5-10 point divergence).

**Fix**: `pipeline.py` `add_indicators()` should call `technical.rsi()` instead of reimplementing.

---

## Phase 2: Strategy Configuration Fixes (Stop Losing Money)

### 2.1 Switch all strategies to SPOT mode, remove leverage

All three configs run `"trading_mode": "futures"` with 3x base leverage on $300 wallets. A single -7% stop at 3x = -21% account loss. Three simultaneous losers = -63%.

**Changes per config file** (`config.json`, `config_bmr.json`, `config_vb.json`):
```json
"trading_mode": "spot",
// Remove "margin_mode": "isolated"
```

**Changes per strategy file** (all 3):
- Remove `leverage()` method entirely, or set to always return 1.0
- Remove `can_short = True` (spot mode cannot short; shorts are unproven anyway)

### 2.2 Fix ROI tables (positive risk:reward, let winners run)

Current ROI tables exit at 0.5% after 6-12 hours — barely covers fees.

**CryptoInvestorV1** (trend-following, hold longer):
```python
minimal_roi = {
    "0": 0.10,      # 10% — only on massive spikes
    "120": 0.06,    # 6% after 2h
    "480": 0.03,    # 3% after 8h
    "1440": 0.015,  # 1.5% after 24h
}
```

**BollingerMeanReversion** (mean-reversion, faster exits):
```python
minimal_roi = {
    "0": 0.06,      # 6%
    "60": 0.03,     # 3% after 1h
    "120": 0.015,   # 1.5% after 2h
    "240": 0.008,   # 0.8% after 4h
}
```

**VolatilityBreakout** (breakout, let runners run):
```python
minimal_roi = {
    "0": 0.12,      # 12%
    "120": 0.07,    # 7% after 2h
    "480": 0.04,    # 4% after 8h
    "1440": 0.02,   # 2% after 24h
}
```

### 2.3 Fix stop losses for positive risk:reward

| Strategy | Current Stop | New Stop | Min R:R |
|----------|-------------|----------|---------|
| CIV1 | -7% | -4% | 2.5:1 (vs 10% ROI) |
| BMR | -6% | -3% | 2:1 (vs 6% ROI) |
| VB | -5% | -3% | 4:1 (vs 12% ROI) |

### 2.4 Fix stoploss_on_exchange conflict

Strategy Python code sets `stoploss_on_exchange: False`; config JSON sets `true`. Strategy takes precedence. Fix: set `True` in strategy code, use `"market"` type (not `"limit"`).

### 2.5 Wallet sizing and trade limits

| Config | Current | Recommended |
|--------|---------|-------------|
| CIV1 wallet | $300 | $500 |
| CIV1 stake | $80 | $60 |
| CIV1 max_trades | 3 | 2 |
| BMR wallet | $300 | $400 |
| BMR stake | $80 | $50 |
| BMR max_trades | 3 | 2 |
| VB wallet | $300 | $300 |
| VB stake | $80 | $40 |
| VB max_trades | 3 | 1 |

### 2.6 Add VolumePairList min_value

All three configs have `"min_value": 0`. Set to `500000` (500K USDT daily) to exclude illiquid pairs.

### 2.7 Cancel open orders on exit

Set `"cancel_open_orders_on_exit": true` in all three configs.

---

## Phase 3: Entry Signal Tightening (Reduce Bad Trades)

### 3.1 CryptoInvestorV1 entry overhaul

**Current problems**: OR-based EMA filter (trivially true), RSI 45 (not a real pullback), no ADX requirement.

**New long entry**:
```python
uptrend = (dataframe["ema_50"] > dataframe["ema_200"]) & (dataframe["close"] > dataframe["ema_50"])
rsi_pullback = (dataframe["rsi"] < 42) & (dataframe["rsi"] > 25)
adx_trending = dataframe["adx"] > 20
volume_confirm = dataframe["volume"] > dataframe["volume"].rolling(20).mean() * 1.0
# ALL conditions required (AND, not OR)
```

Remove short entries entirely (unproven, spot mode cannot short anyway).

### 3.2 BollingerMeanReversion entry overhaul

**Current problems**: BB 1.5 std (too tight), RSI 40 (not oversold), volume 0.5x (no filter), ADX ceiling 40 (trends allowed).

**New defaults**:
- `buy_bb_std`: 1.5 -> **2.0**
- `buy_rsi_threshold`: 40 -> **33**
- `buy_volume_factor`: 0.5 -> **1.2** (require above-average volume on capitulation)
- `buy_adx_ceiling`: 40 -> **30** (mean reversion only in ranging/weak markets)

### 3.3 VolatilityBreakout entry overhaul

**Current problems**: ADX rising requirement kills entries, volume 1.2x too low, RSI 25-75 provides no filtering.

**New defaults**:
- Remove single-bar ADX rising requirement; use `adx > adx.shift(3)` (3-bar trend)
- `adx_low`: 15 -> **20**
- `volume_factor`: 1.2 -> **1.5**
- Narrow RSI range to 35-65

### 3.4 Populate HARD_DISABLE for regime-strategy conflicts

```python
HARD_DISABLE = {
    (Regime.RANGING, "CryptoInvestorV1"),
    (Regime.STRONG_TREND_DOWN, "CryptoInvestorV1"),
    (Regime.STRONG_TREND_UP, "BollingerMeanReversion"),
    (Regime.WEAK_TREND_UP, "BollingerMeanReversion"),
}
```

---

## Phase 4: Signal & Conviction System Tuning

### 4.1 Rebalance signal weights

```python
DEFAULT_WEIGHTS = {
    "technical": 0.30,    # Was 0.22 — primary driver
    "regime": 0.25,       # Was 0.18 — critical for strategy selection
    "ml": 0.00,           # Was 0.20 — DISABLED until pipeline fixed (see Phase 6)
    "sentiment": 0.10,    # Was 0.22 — too noisy on RSS-only
    "scanner": 0.05,
    "win_rate": 0.05,     # Was 0.03
    "funding": 0.08,      # Was 0.05
    "macro": 0.07,        # Was 0.05
}
```

ML is disabled (weight 0) until the training pipeline issues from Phase 6 are resolved. Its weight redistributes to technical and regime which are the most reliable sources.

### 4.2 Raise conviction thresholds

| Asset Class | Current | New |
|-------------|---------|-----|
| Crypto | 40 | **55** |
| Equity | 50 | **60** |
| Forex | 45 | **55** |

### 4.3 Fix entry tier offsets

```python
ENTRY_TIER_OFFSETS = [
    (25, 1.2, "very_strong_buy"),  # NEW tier
    (15, 1.0, "strong_buy"),       # Was +20
    (5, 0.7, "buy"),               # Was +10
    (0, 0.5, "cautious_buy"),      # Was 0.4, raised to 0.5
]
```

### 4.4 Require minimum 2 signal sources for entry

If fewer than 2 sources provide non-None scores, reject the entry regardless of composite score. Prevents rubber-stamping on a single source.

### 4.5 Fix exit manager: exit losers in deteriorated regimes

Current: `if current_profit_pct <= 0: return ExitAdvice(should_exit=False)`. A losing position in a deteriorating regime should exit MORE urgently.

Fix: If regime alignment dropped >40 points AND position is losing, advise exit.

### 4.6 Remove partial profit targets for Freqtrade strategies

The partial profit system (1/3 at 6%, 1/2 at 10% for CIV1) never fires because ROI exits the full position first. Freqtrade doesn't support partial exits from `custom_exit`. Remove these targets for Freqtrade strategies; keep for NautilusTrader.

---

## Phase 5: Risk & Regime Calibration

### 5.1 Lower crypto ADX regime thresholds

```python
"crypto": {"adx_strong": 32.0, "adx_weak": 20.0, "bb_high_vol_pct": 80.0}
```
Was: adx_strong 40, adx_weak 25. Crypto spends <15% of time above ADX 40. Lowering captures more genuine trends.

### 5.2 Relax regime-based risk tightening

| Regime | Current Multiplier | New Multiplier |
|--------|-------------------|----------------|
| STRONG_TREND_DOWN | 0.5x | **0.75x** |
| HIGH_VOLATILITY | 0.7x | **0.80x** |
| WEAK_TREND_DOWN | 0.85x | 0.85x (unchanged) |

Current 0.5x in STD with 15% DD limit = 7.5% effective halt. On a $500 account that's $37.50 — one bad trade halts everything.

### 5.3 Raise orchestrator thresholds

| Threshold | Current | New |
|-----------|---------|-----|
| PAUSE | 5 | **15** |
| REDUCE | 20 | **35** |

Current PAUSE=5 only catches VB in RANGING/WTD. CIV1 in RANGING (alignment=15) runs unpaused. With PAUSE=15, trend-following gets paused in ranging markets (correct behavior).

### 5.4 Add drawdown auto-recovery

When halted for drawdown, check if equity has recovered to 50% of halt threshold. If so, auto-resume with 0.5x position modifier for the first hour.

### 5.5 Raise crypto drawdown limits (pilot portfolio)

For the $500 crypto pilot: max_portfolio_drawdown 0.15 -> **0.25**, max_daily_loss 0.05 -> **0.08**. Current limits are too tight for crypto volatility.

### 5.6 Fix BTC dominance thresholds

`btc_dominant`: 55% -> **60%**, `alt_season`: 40% -> **45%**. Current thresholds permanently classify the market as BTC-dominant (BTC dominance ~58-62% in 2026).

### 5.7 Raise crypto scanner volume_surge threshold

2.0x -> **3.0x**. A 2x volume spike in crypto is routine and generates too many false positives.

---

## Phase 6: ML Pipeline Repair (Deferred — Enable After Phases 1-5)

ML is disabled (weight=0) until these fixes are applied and validated. This phase can run in parallel with live testing of Phases 1-5.

### 6.1 Fix feedback horizon mismatch

`_run_ml_feedback` compares `close[-1]` vs `close[-2]` (1-bar), but model trains with `target_horizon=3`. Must compare against the bar 3 periods ahead. All current accuracy metrics are meaningless.

### 6.2 Get more training data

Current: 721 1h bars (30 days) for 3 symbols. Need: 6-12 months (4,000-8,700 rows). Either increase download window or pool data across symbols.

### 6.3 Add early stopping to LightGBM

Pass `callbacks=[lgb.early_stopping(20)]` to `.fit()`. Currently all 200 estimators always train regardless of overfitting.

### 6.4 Fix model labels for asset-class filtering

Pass `label=asset_class` when saving models in `MLService.train()` so `PredictionService._select_model()` can filter properly instead of always falling through to "best accuracy" catch-all.

### 6.5 Remove redundant features

Remove raw SMA/EMA features (8 columns) — only ratio features matter. Remove duplicate return features (keep `return_N` or `log_return_N`, not both). Saves 12+ feature slots.

### 6.6 Fix ensemble model_ids alignment bug

When a middle model fails, `probabilities` list and `model_ids` list get misaligned. Track which IDs actually produced predictions.

### 6.7 Unify feedback systems

Remove JSONL `FeedbackTracker` or wire it into production. Currently two parallel feedback systems where only Django `MLPrediction` receives data.

### 6.8 Re-enable ML at weight 0.15

After fixes validated: set `"ml": 0.15` in DEFAULT_WEIGHTS, redistribute from technical (0.30 -> 0.25) and macro (0.07 -> 0.02).

---

## Implementation Order & Dependencies

```
Phase 1 (Bug Fixes)          <- Do first, all other phases depend on working signals
  |
Phase 2 (Strategy Config)    <- Do second, stops active money loss
  |
Phase 3 (Entry Tightening)   <- Requires Phase 1 (regime data flowing)
  |
Phase 4 (Signal Tuning)      <- Requires Phase 1 (weights meaningful when sources work)
  |
Phase 5 (Risk Calibration)   <- Requires Phase 1 (regime tightening needs working regime)
  |
Phase 6 (ML Repair)          <- Independent, can run in parallel with 3-5
```

## Estimated Impact

| Phase | Expected Impact |
|-------|----------------|
| Phase 1 | Restores 40% of signal weight + orchestrator + risk regime. **Foundational.** |
| Phase 2 | Eliminates catastrophic drawdown risk from leverage. Improves R:R from <1:1 to >2:1. |
| Phase 3 | Reduces false entries by ~50-60%. Fewer trades but higher quality. |
| Phase 4 | Signals become meaningful filters. Conviction gate actually gates. |
| Phase 5 | System stays active through normal crypto volatility instead of auto-halting. |
| Phase 6 | Adds a functioning ML signal at 15% weight (deferred, lower priority). |

## Files Changed (Estimated)

| Phase | Files |
|-------|-------|
| 1 | signal_service.py, views.py, risk.py, strategy_orchestrator.py, pipeline.py, technical.py |
| 2 | config.json, config_bmr.json, config_vb.json, CryptoInvestorV1.py, BollingerMeanReversion.py, VolatilityBreakout.py |
| 3 | CryptoInvestorV1.py, BollingerMeanReversion.py, VolatilityBreakout.py, constants.py |
| 4 | constants.py, asset_tuning.py, aggregator.py, exit_manager.py, _conviction_helpers.py |
| 5 | regime_detector.py, risk.py, strategy_orchestrator.py, risk_manager.py, coingecko.py, market_scanner.py |
| 6 | trainer.py, features.py, ensemble.py, feedback.py, task_registry.py, signal_service.py |

## Test Impact

All changes must pass the existing 5,954 tests. New tests needed:
- Phase 1: Update regime detector mocks in signal_service tests, orchestrator tests, risk tests
- Phase 2: Update strategy config expectations in Freqtrade tests
- Phase 3: Update entry condition tests
- Phase 4: Update signal weight / conviction threshold tests
- Phase 5: Update regime threshold / risk multiplier tests
- Phase 6: Update ML pipeline tests

---

## Validation Criteria

Before declaring any phase complete:
1. `make test` passes (0 failures)
2. `make lint` passes
3. For Phases 1-2: manually verify with `curl` that signal endpoints return non-None technical and regime scores
4. For Phase 2: verify Freqtrade configs load without error in dry-run mode
5. Document changes in memory files
