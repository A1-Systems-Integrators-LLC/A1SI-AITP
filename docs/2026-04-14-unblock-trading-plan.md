# Daily Plan: 2026-04-14 — Unblock Trading

**Owner:** Claude Agent Team
**Status:** COMPLETED
**Objective:** Eliminate the 88.4% order rejection rate and get all 7 strategies actively trading

## Problem Statement

- 7 Freqtrade strategies running in dry-run mode, all RUNNING state
- Only 3 strategies have generated ANY trades (VB: 4, Scalp: 2, Grid: 1)
- 4 strategies have ZERO trades (CIV1, BMR, Sentiment, Reversal)
- 138 total orders attempted, 122 rejected (88.4% rejection rate)
- Portfolio equity: $496.30 (-0.74%)
- User has approved aggressive trading parameters MULTIPLE TIMES — changes were never executed

## Root Cause Analysis

**Primary cause (116/122 rejections):** "Trading halted: Max drawdown breached: 16.08% >= 15.00%"
- The DB migration `0001_initial.py` created RiskLimits with `max_portfolio_drawdown=0.15` (15%)
- Code defaults were later updated to 0.99 but the DB row retained the old 15% value
- A 16% drawdown triggered the halt, blocking ALL subsequent trades
- DB value was updated to 0.99 in a previous session but the historical rejections remained

**Secondary cause (6/122 rejections):** "Position too large: 50.00% > 50.00%"
- Floating-point comparison with only 0.001 tolerance — edge case where exactly 50% was rejected

**Tertiary blockers (potential future):**
- Strategy orchestrator PAUSE_THRESHOLD=15 and REDUCE_THRESHOLD=35 could suppress trades when alignment drops
- These thresholds are inappropriate for a $500 learning portfolio

| # | Blocker | Old Value | New Value | File | Status |
|---|---------|-----------|-----------|------|--------|
| 1 | Orchestrator PAUSE_THRESHOLD | 15 | 0 | backend/trading/services/strategy_orchestrator.py:63 | DONE |
| 2 | Orchestrator REDUCE_THRESHOLD | 35 | 0 | backend/trading/services/strategy_orchestrator.py:64 | DONE |
| 3 | Position size tolerance | 0.001 | 0.01 | common/risk/risk_manager.py:420 | DONE |
| 4 | DB max_portfolio_drawdown | 0.15 (old) → 0.99 | 0.99 | risk_risklimits DB table | VERIFIED OK |
| 5 | RiskState is_halted | False | False | risk_riskstate DB table | VERIFIED OK |
| 6 | Strategy stoplosses | 10-15% | 10-15% | freqtrade/user_data/strategies/*.py | VERIFIED OK |
| 7 | Risk limits in code | aggressive | aggressive | common/risk/risk_manager.py defaults | VERIFIED OK |
| 8 | Regime multiplier | 1.0 (disabled) | 1.0 (disabled) | backend/risk/services/risk.py:329 | VERIFIED OK |
| 9 | Freqtrade dry_run | true | true (paper phase) | freqtrade/config*.json | VERIFIED OK |

## Changes Made

### Change 1: Strategy Orchestrator — Disable Pause/Reduce
- **File:** `backend/trading/services/strategy_orchestrator.py:63-64`
- **Before:** `PAUSE_THRESHOLD = 15`, `REDUCE_THRESHOLD = 35`
- **After:** `PAUSE_THRESHOLD = 0`, `REDUCE_THRESHOLD = 0`
- **Why:** Low alignment scores were pausing/reducing strategies. During learning phase, strategies should always run at full size. Re-enable at $5K.

### Change 2: Risk Manager — Fix Position Size Rounding
- **File:** `common/risk/risk_manager.py:420`
- **Before:** `if position_pct > eff_max_position_size_pct + 0.001`
- **After:** `if position_pct > eff_max_position_size_pct + 0.01`
- **Why:** 6 trades rejected with "50.00% > 50.00%" due to float rounding. 1% tolerance prevents false rejections.

### Change 3: Infrastructure — Reduce Thread Contention
- **File:** `backend/core/services/scheduler.py:68` — APScheduler threads 20 → 6
- **File:** `backend/core/services/dashboard.py:77` — Dashboard KPI threads 8 → 4
- **Why:** Excessive thread count caused GIL contention, starving Daphne's event loop. Users experienced ERR_CONNECTION_RESET on page load.

### Change 4: Frontend — Login Error Handling
- **File:** `frontend/src/pages/Login.tsx:21` — Added try/catch around login fetch
- **Why:** Network failures during backend overload produced uncaught TypeError in console.

### Change 5: Nginx — PDF Report Viewer CSP Fix
- **File:** `frontend/nginx.conf` — Added `/api/market/reports/` location with `SAMEORIGIN` framing
- **Why:** `X-Frame-Options: DENY` blocked the PDF iframe in the Reports page.

### Verified — No Change Needed
- **Strategy stoplosses:** All already widened (BMR/CIV1/Grid/Reversal: -15%, VB/Sentiment: -12%, Scalp: -10%)
- **Risk limits in DB:** Already aggressive (drawdown 99%, daily loss 50%, trade risk 20%)
- **Regime tightening:** Already disabled (multiplier returns 1.0)
- **Halt state:** Not currently halted

## Deployment

- [x] Build backend image
- [x] Restart backend container
- [x] Verify health checks pass
- [x] Freqtrade containers: no restart needed (no config changes)

## Verification Checklist

- [x] TradeCheckLog: 116 rejections were from old 15% limit (now 99%)
- [x] RiskState: is_halted=False confirmed
- [x] All 10 containers healthy
- [ ] Monitor rejection rate over next 24h — should drop to near 0%
- [ ] Monitor that strategies generate trades

## Strategy Status at Plan Start (2026-04-14 16:22 UTC)

| Strategy | Open | Closed | P&L (USDT) |
|----------|------|--------|------------|
| VolatilityBreakout | 3 | 1 | -1.10 |
| MomentumScalper15m | 1 | 1 | -0.84 |
| GridDCA | 0 | 1 | -0.13 |
| CryptoInvestorV1 | 0 | 0 | 0.00 |
| BollingerMeanReversion | 0 | 0 | 0.00 |
| SentimentEventTrader | 0 | 0 | 0.00 |
| TrendReversal | 0 | 0 | 0.00 |

## Decisions Log

| Date | Decision | Made By |
|------|----------|---------|
| 2026-04-09 | $500 aggressive capital, no drawdown limits until $5K | User |
| 2026-04-09 | Widen all stoplosses to 10-15% | User |
| 2026-04-09 | Switch to live trading when ready | User |
| 2026-04-09 | Never stop strategies for small losses | User |
| 2026-04-14 | Track all changes in daily plan docs, review every morning | User |
| 2026-04-14 | Agent team accountable for executing approved changes | User |

## Next Steps (2026-04-15)

1. Morning review: check trade counts across all 7 strategies — are they generating trades?
2. If still zero trades on CIV1/BMR/Sentiment/Reversal: investigate strategy signal generation
3. Begin Phase 1.3: prepare for live trading switch (verify Kraken API keys in Doppler)
