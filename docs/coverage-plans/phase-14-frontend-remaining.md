# Phase 14: Frontend Hooks + API + Utils (→ 100%)

**Created**: 2026-03-10
**Subsystem**: `frontend/src/hooks/`, `frontend/src/api/`, `frontend/src/utils/`, `frontend/tests/helpers.tsx`

---

## Summary

Cover all remaining uncovered lines in frontend hooks, API modules, utilities, and test helpers to achieve 100% line coverage across the entire frontend.

## Files & Gaps

| File | Current Lines % | Uncovered Lines | Test Needed |
|------|----------------|-----------------|-------------|
| `hooks/useSystemEvents.ts` | 50% | 54-91 | 5 event handler cases (news_update, sentiment_update, scheduler_event, regime_change, opportunity_alert) |
| `hooks/useWebSocket.ts` | 84% | 46-47, 103-110 | Unmount during connection, manual reconnect function |
| `api/news.ts` | 100% stmts, lines 8,15,17-24 | 8, 15, 17-24 | symbol-only param, sentiment/signal with individual params |
| `api/trading.ts` | 100% stmts, lines 23,26-27 | 23, 26-27 | perfQuery with portfolio_id, asset_class, date_from |
| `api/opportunities.ts` | 91% | 20 | dailyReportHistory endpoint |
| `api/data.ts` | lines 29,31-34 | 29, 31-34 | quality() and qualityDetail() endpoints |
| `api/portfolios.ts` | 91% | 20-21 | summary() and allocation() endpoints |
| `api/risk.ts` | lines 70-71 | 70-71 | getAlerts filter params (created_after, created_before) |
| `api/scheduler.ts` | 85% | 7 | task(id) endpoint |
| `api/screening.ts` | 80% | 16 | result(id) endpoint |
| `api/workflows.ts` | 84% | 19, 36 | delete() and cancelRun() endpoints |
| `utils/formatters.ts` | 71% | 12-13 | formatVolume thousands and raw ranges |
| `tests/helpers.tsx` | 92% | 64 | Unhandled fetch URL rejection |

## Test Plan

### 1. useSystemEvents — 5 new tests in `useSystemEvents.test.tsx`

- `processes news_update event` → invalidates news-articles, toasts article count
- `processes news_update with zero articles` → invalidates cache, no toast
- `processes sentiment_update event` → invalidates news-sentiment + sentiment-signal
- `processes scheduler_event completed` → sets state, toasts success
- `processes scheduler_event failed` → sets state, toasts error
- `processes regime_change event` → sets lastRegimeChange, toasts regime transition
- `processes opportunity_alert event` → invalidates opportunities + summary, toasts details

### 2. useWebSocket — 2 new tests in `useWebSocket.test.tsx`

- `closes socket if unmounted during onopen` → set unmountedRef, trigger onopen, verify close()
- `manual reconnect resets state and reconnects` → call reconnect(), verify new WebSocket created

### 3. formatters — 2 new tests in `formatters.test.ts`

- `formats thousands` → formatVolume(1500) === "1.5K"
- `formats raw numbers` → formatVolume(500) === "500"

### 4. API modules — ~15 new tests in `api-modules.test.ts`

- newsApi: list with symbol only, sentiment without params, signal with hours only
- tradingApi: performanceSummary with all params (portfolio_id, asset_class, date_from, date_to)
- opportunitiesApi: dailyReportHistory, list, summary
- dataApi: quality(), qualityDetail() with and without exchange
- portfoliosApi: summary(), allocation()
- riskApi: getAlerts with date filters
- schedulerApi: task(id)
- screeningApi: result(id)
- workflowsApi: delete(), cancelRun()

### 5. helpers.tsx — 1 new test

- `rejects unhandled non-API URLs` → verify mockFetch rejects for non-/api/ URL

## Deliverable

All files at 100% line coverage. Total new tests: ~25.
