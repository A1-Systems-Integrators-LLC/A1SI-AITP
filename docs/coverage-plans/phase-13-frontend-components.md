# Phase 13: Frontend Components — 100% Line Coverage

**Created**: 2026-03-10
**Target**: 100% line coverage on all 24 component files in `frontend/src/components/`

## Current State

| File | Lines % | Uncovered Lines | Status |
|------|---------|----------------|--------|
| AssetClassBadge.tsx | 100% | — | Done |
| AssetClassSelector.tsx | 100% | — | Done |
| ConfirmDialog.tsx | 100% | — | Done |
| ConnectionStatus.tsx | 100% | — | Done |
| EmergencyStopButton.tsx | 38% | 23-29, 33-41, 47-48 | **NEEDS TESTS** |
| EquityCurve.tsx | 90% | 49-50, 96-97 | **NEEDS TESTS** |
| ErrorBoundary.tsx | 100% | — | Done |
| ExchangeHealthBadge.tsx | 92% | 25 | **NEEDS TESTS** |
| FieldError.tsx | 100% | — | Done |
| HoldingsTable.tsx | 66% | 59-63, 220, 234, 268, 329 | **NEEDS TESTS** |
| Layout.tsx | 81% | 70-72, 79-80 | **NEEDS TESTS** |
| MarketStatusBadge.tsx | 90% | 22, 25 | **NEEDS TESTS** |
| NewsFeed.tsx | 79% | 31-32, 110-113 | **NEEDS TESTS** |
| OrderForm.tsx | 70% | 71, 81, 98, 150 | **NEEDS TESTS** |
| Pagination.tsx | 100% | — | Done |
| PriceChart.tsx | 72% | 67, 92-105, 130-140 | **NEEDS TESTS** |
| ProgressBar.tsx | 100% | — | Done |
| QueryError.tsx | 100% | — | Done |
| QueryResult.tsx | 85% | 48, 55 | **NEEDS TESTS** |
| SkeletonCard.tsx | 100% | — | Done |
| SkeletonTable.tsx | 100% | — | Done |
| ThemeToggle.tsx | 100% | — | Done |
| Toast.tsx | 100% | — | Done |
| WidgetErrorFallback.tsx | 100% | — | Done |

**10 files need new tests**, 14 files already at 100%.

---

## Test Plan by Component

### 1. EmergencyStopButton.tsx (38% → 100%)

**Uncovered**:
- Lines 23-29: haltMutation onSuccess/onError callbacks
- Lines 33-41: startHold interval logic (progress increment, trigger mutate at 100%)
- Lines 47-48: cancelHold (clearInterval, reset progress)

**Tests**:
- Hold button via mouseDown, advance timers to trigger mutation
- Verify onSuccess invalidates queries and shows toast
- Verify onError shows error toast
- mouseUp cancels hold before completion
- mouseLeave cancels hold

### 2. HoldingsTable.tsx (66% → 100%)

**Uncovered**:
- Lines 59-63: startEdit function (sets editingId, editAmount, editPrice)
- Line 220: setEditAmount onChange in edit mode
- Line 234: setEditPrice onChange in edit mode
- Line 268: saveEdit (calls updateMutation.mutate)
- Line 329: onConfirm in delete dialog (calls deleteMutation.mutate)

**Tests**:
- Click Edit → verify inputs populated with holding values
- Change edit amount/price inputs
- Click Save → verify mutation called with correct data
- Click Delete → Confirm in dialog → verify delete mutation called
- Add holding form: type symbol/amount/price, click Add

### 3. OrderForm.tsx (70% → 100%)

**Uncovered**:
- Line 71: confirmLiveOrder function body
- Line 81: portfolio select onChange
- Line 98: symbol input onChange
- Line 150: price input onChange

**Tests**:
- Change portfolio select value
- Type in symbol input
- Type in price input
- Live mode: submit → confirm dialog → click Confirm → verify mutation

### 4. PriceChart.tsx (72% → 100%)

**Uncovered**:
- Line 67: priceFormatter callback
- Lines 92-105: overlay indicators loop
- Lines 130-140: MACD histogram series in pane

**Tests**:
- Render with overlayIndicators + indicatorData → verify addSeries called for each
- Render with paneIndicators including "macd_hist" → verify HistogramSeries used
- Render with forex assetClass → verify priceFormatter uses 5 decimals

### 5. NewsFeed.tsx (79% → 100%)

**Uncovered**:
- Lines 31-32: timeAgo "days" branch (hrs >= 24)
- Lines 110-113: handleRefresh async function

**Tests**:
- Article published >24h ago → shows "Xd ago"
- Click Refresh button → verify fetch called and queries invalidated

### 6. Layout.tsx (81% → 100%)

**Uncovered**:
- Lines 70-72: order update toast (symbol/status extraction from lastOrderUpdate)
- Lines 79-80: risk alert toast (message extraction from lastRiskAlert)

**Tests**:
- Set lastOrderUpdate in mock → verify toast called with order info
- Set lastRiskAlert in mock → verify toast called with alert message

### 7. QueryResult.tsx (85% → 100%)

**Uncovered**:
- Line 48: inline error rendering (span with error message)
- Line 55: retry button click handler

**Tests**:
- Render inline error → verify span with error text
- Click Retry button → verify refetch called

### 8. EquityCurve.tsx (90% → 100%)

**Uncovered**:
- Lines 49-50: early return when sorted trades is empty (trades with no close_date/profit_abs)
- Lines 96-97: ResizeObserver callback (chart.applyOptions with width)

**Tests**:
- Trades with no close_date → chart created then removed (early return)
- Trigger ResizeObserver callback → verify applyOptions called

### 9. MarketStatusBadge.tsx (90% → 100%)

**Uncovered**:
- Line 22: isForexOpen returns false on Saturday (day === 6)
- Line 25: isForexOpen returns false for Friday after 22:00 UTC

**Tests**:
- Set time to Saturday → forex shows "Weekend"
- Set time to Friday 23:00 UTC → forex shows "Weekend"
- Set time to Sunday before 22:00 UTC → forex shows "Weekend"
- Set time to Sunday after 22:00 UTC → forex shows "Session Active"

### 10. ExchangeHealthBadge.tsx (92% → 100%)

**Uncovered**:
- Line 25: isError condition (query fails entirely)

**Tests**:
- Mock fetch to reject → verify "Disconnected" shown via isError path

---

## Estimated New Tests: ~45-55
