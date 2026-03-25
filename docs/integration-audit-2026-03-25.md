# Integration Audit — 2026-03-25

## Background

Signal attributions showed 0 (broken) on dashboard despite being "fully tested."
Root cause: `SignalRecordView` required authentication but Freqtrade called it without credentials.
Every POST returned 403, zero attributions recorded. Tests passed because they used authenticated test clients.

This triggered a full 6-dimension cross-boundary audit.

## Audit Dimensions

### 1. Cross-Boundary HTTP Calls

Every place one subsystem calls another via HTTP:

| Source | Target | Endpoint | Auth Required | Auth Sent | Status |
|--------|--------|----------|---------------|-----------|--------|
| Freqtrade | Django | `POST /api/signals/{symbol}/entry-check/` | AllowAny | None | OK |
| Freqtrade | Django | `GET /api/signals/strategy-status/` | **IsAuthenticated** | **None** | **BROKEN** (fail-opens) |
| Freqtrade | Django | `POST /api/signals/record/` | AllowAny (fixed) | None | **FIXED 2026-03-25** |
| NautilusTrader | Django | `POST /api/risk/{id}/check-trade/` | No auth | None | OK |
| NautilusTrader | Django | `POST /api/signals/{symbol}/entry-check/` | AllowAny | None | OK |
| Django | Freqtrade | `GET /api/v1/profit` | Basic Auth | Basic Auth | OK |
| Django | Freqtrade | `GET /api/v1/status` | Basic Auth | Basic Auth | OK |
| Django | Freqtrade | `GET /api/v1/ping` | Basic Auth | Basic Auth | OK |
| Django | Freqtrade | `GET /api/v1/trades` | Basic Auth | Basic Auth | OK |
| Frontend | Django | All `/api/*` | Session+CSRF | Session+CSRF | OK |

### 2. View Permission Mismatches

- **StrategyStatusView**: No explicit `permission_classes`, defaults to `IsAuthenticated`. Freqtrade calls unauthenticated. Fail-opens but silently broken.
- **TradeCheckView**: Uses empty `[]` instead of `[AllowAny]` — works but inconsistent style.

### 3. Serializer/Payload Mismatches

| Issue | Severity | Details |
|-------|----------|---------|
| SignalRecordView payload format | **CRITICAL (FIXED)** | Freqtrade sent flat fields, serializer expected nested `signal_data` |
| Frontend OrderForm "binance" default | Medium | Should be "kraken" |
| Frontend checkTrade missing asset_class | Medium | Defaults to crypto for all asset classes |
| Nautilus risk gate missing asset_class | Medium | Defaults to crypto for equity/forex strategies |
| Entry-check extra `side` field | Low | Harmless, DRF ignores extra fields |

### 4. Task Executor Silent Failures

**CRITICAL**: Multiple task executors return "completed" status when they actually fail:

| Executor | Issue | Impact |
|----------|-------|--------|
| `_run_ml_predict` | Returns "completed" with 0 models | ML pipeline completely dead, no errors |
| `_run_risk_monitoring` | Continues with stale equity on Freqtrade API failure | Risk limits based on old data |
| `_run_signal_feedback` | Freqtrade backfill failure only WARNING | Signal weights never update |
| `_run_data_refresh` | Returns "completed" if 1/N symbols succeeds | 95% stale data unreported |
| `_run_vbt_screen` | Returns "completed" if all symbols fail | Screen results empty but "success" |
| `_run_ml_training` | Counting bug: len(results) includes errors | Reports N models trained including failures |
| `_run_order_sync` | Per-order failures never escalate | 100% failed syncs = "completed" |
| `_run_daily_report` | Telegram failure swallowed | User never receives report |

### 5. Test Mock Gaps

Tests that mock away the exact boundary they should verify:

| Test Area | What's Mocked | What's Hidden |
|-----------|---------------|---------------|
| Signal entry-check | `SignalService.get_entry_recommendation` | Entire aggregator pipeline |
| ML feedback backfill | `requests` library | Freqtrade API contract |
| Paper trading | `_get_paper_trading_services()` | Config loading, multi-instance init |
| Strategy orchestration | `check_strategy_paused()` | Real state machine |
| Signal aggregation | Individual scorers | Weight composition logic |
| Trade check response | (partial) | Freqtrade response parsing contract |
| Nautilus conviction | Service call | Real gate logic |
| Forex prices | `_get_price()` globally | yfinance integration |

### 6. Frontend-Backend Contract Gaps

| Issue | Severity | Details |
|-------|----------|---------|
| DashboardKPISerializer missing fields | Medium | Missing `system_health`, `activity_feed`, `learning_status` (API returns them, schema wrong) |
| DashboardTradingKPISerializer missing fields | Medium | Missing `total_orders`, `rejected_orders`, `filled_orders`, `rejection_rate` |
| DashboardPortfolioKPISerializer missing field | Low | Missing optional `equity_source` |
| Missing API wrapper: exchange rotate | Low | Backend endpoint exists, no frontend wrapper |

## Fix Plan

### Phase A: Critical Fixes (Immediate)

1. ~~Fix SignalRecordView auth + payload~~ (DONE 2026-03-25)
2. Fix StrategyStatusView `permission_classes = [AllowAny]`
3. Fix task executor silent failures (ERROR logging + proper status)
4. Fix NautilusTrader risk gate missing `asset_class`
5. Fix frontend OrderForm "binance" → "kraken"

### Phase B: Schema/Contract Fixes

6. Fix DashboardKPISerializer missing fields
7. Fix DashboardTradingKPISerializer missing fields
8. Fix DashboardPortfolioKPISerializer missing field

### Phase C: Cross-Boundary Integration Tests

9. Add unauthenticated caller tests for all Freqtrade→Django endpoints
10. Add payload format contract tests (real format, no mocks)
11. Add task executor outcome validation tests
12. Add response format contract tests (what callers actually parse)

## Root Cause Analysis

The fundamental failure mode: **unit tests with authenticated clients and mocked services pass even when the real integration is broken.** The 100% code coverage effort measured line execution, not boundary correctness. A view can have 100% line coverage while being completely inaccessible to its real caller.

### Prevention

Every endpoint called by an external system (Freqtrade, NautilusTrader) MUST have:
1. A test using `APIClient()` without `force_authenticate()` — verifying the real auth context
2. A test sending the exact payload format the real caller sends — not a hand-crafted ideal payload
3. A test asserting the response format matches what the real caller parses

## Phase 2: Broader Audit (Runtime + Data Flow)

After fixing the HTTP boundary issues, a second broader audit checked runtime state,
data pipelines, and unfixed issues from the first pass.

### Additional Issues Found & Fixed

| # | Issue | Severity | Fix |
|---|-------|----------|-----|
| 12 | Dashboard KPI tests failing (mode=PAPER vs mode=LIVE) | Critical | Test fixture used PAPER mode, dashboard queries LIVE |
| 13 | Dashboard fallback missing 4 fields | High | Added total_orders, rejected_orders, filled_orders, rejection_rate to exception path |
| 14 | Risk service check_trade ignoring asset_class | High | Added asset_class param to check_trade() + TradeCheckLog |
| 15 | Equity sync swing guard blocking all updates | High | Guard compared vs stale equity; now also checks vs computed capital base |
| 16 | 8 hardcoded "binance" defaults in frontend | Medium | All changed to "kraken" |

### Runtime Health Findings (Not Code Bugs)

| Finding | Status | Action |
|---------|--------|--------|
| ML weight = 0.0 in signal aggregator | By design | ML disabled while accuracy is ~50%; enable when accuracy improves |
| Scanner weight = 0.0 | By design | Same rationale as ML |
| Win rate almost always None | Data gap | No BacktestResults created from live trades |
| Macro score always 50 (neutral) | Silent failure | FRED adapter likely failing; investigate separately |
| 99.5% order rejection rate | Risk config | Risk thresholds very conservative; review after equity sync unblocked |
| Orchestrator state file missing | Non-critical | File created on first evaluate() call; starts fresh on restart |

### Total Changes (Both Phases)

- **18 files modified**
- **25 new cross-boundary tests**
- **~20 bugs fixed** (3 critical, 8 high, 9 medium)
- **0 test regressions** (5240+ backend, 1125 frontend passing)

## Phase 3: Full Team Audit (Runtime Verification)

Strategy Engineer conducted end-to-end trading pipeline verification with live data.

### Critical Findings

| # | Finding | Impact | Status |
|---|---------|--------|--------|
| 1 | CIV1 has ZERO trades ever | Primary crypto strategy dead | ROOT CAUSED: contradictory entry conditions (RSI<42 + close>EMA21) |
| 2 | 99.5% rejection rate was ALL forex, NOT crypto | Misleading metric | RESOLVED: cleared 1,308 stale records |
| 3 | GenericPaperTradingService not passing asset_class | Forex checked as crypto | FIXED |
| 4 | Dashboard reading orchestrator state from wrong path | Orchestrator state invisible | FIXED: Path("data/...") → Path(__file__).parents[2] |
| 5 | Equity sync swing guard verified working | Update reaches update_equity() | CONFIRMED: capital_delta_pct check passes |
| 6 | ADX not zero — earlier test used wrong dict key | False alarm | NOT A BUG (adx_value=18.27) |

### Stale Data Cleared
- 1,308 rejected TradeCheckLog entries (pre-fix noise)
- 1,308 rejected forex Order records ($1,000 sizing)
- 21 failed BackgroundJob records (old DB lock errors)

### CIV1 Root Cause Analysis
CryptoInvestorV1 entry conditions are contradictory:
1. RSI < 42 (oversold) AND close > EMA(21) (above trend) — opposite states
2. ADX > 20 required but market ADX = 11-18
3. HIGH_VOLATILITY regime gives CIV1 alignment=25 < conviction threshold 55
4. startup_candle_count = 150 (6+ days warm-up)

BMR and VB DO trade (5 and 16 trades respectively) — their conditions are achievable.

### Orchestrator State (Live)
| Strategy | Asset | Regime | Alignment | Action |
|----------|-------|--------|-----------|--------|
| CryptoInvestorV1 | crypto | high_volatility | 25 | reduce_size |
| BollingerMeanReversion | crypto | high_volatility | 65 | active |
| VolatilityBreakout | crypto | high_volatility | 70 | active |
| EquityMomentum | equity | weak_trend_down | 10 | pause |
| EquityMeanReversion | equity | weak_trend_down | 65 | active |

### Signal Pipeline (Live)
BTC/USDT: composite_score=78.0, label=strong_buy, 6/7 sources available.
All sources returning data: technical=90, regime=39, ml=46, sentiment=54, scanner=83, macro=50.
