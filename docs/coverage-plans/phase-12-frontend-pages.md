# Phase 12: Frontend Pages — 100% Test Coverage

## Scope
All 16 page components in `frontend/src/pages/`. Target: 100% line coverage.

## Current Coverage (pre-phase)

| Page | Stmts % | Lines % | Test File Exists |
|------|---------|---------|------------------|
| Settings.tsx | 46.78 | 48.75 | Yes (40 tests) |
| RiskManagement.tsx | 51.74 | 53.28 | Yes (47 tests) |
| Scheduler.tsx | 57.89 | 54.28 | Yes |
| MLModels.tsx | 55.88 | 55.88 | Yes |
| Portfolio.tsx | 59.78 | 57.95 | Yes |
| Backtesting.tsx | 67.21 | 68.42 | Yes |
| DataManagement.tsx | 68.62 | 68.08 | Yes |
| Trading.tsx | 67.39 | 69.76 | Yes (24 tests) |
| PaperTrading.tsx | 78.57 | 73.68 | Yes (23 tests) |
| Workflows.tsx | 78.18 | 77.35 | Yes |
| Dashboard.tsx | 89.09 | 88.67 | Yes |
| RegimeDashboard.tsx | 89.28 | 92.10 | Yes |
| MarketAnalysis.tsx | 94.59 | 94.28 | Yes |
| Screening.tsx | 96.66 | 96.66 | Yes |
| Login.tsx | 100 | 100 | Yes |
| MarketOpportunities.tsx | — | — | **NO** |

## Strategy
- Work bottom-up from lowest coverage
- Create MarketOpportunities.test.tsx from scratch
- Add tests for uncovered mutation paths, conditional rendering, error states
- Use existing `renderWithProviders` + `mockFetch` helpers

## Key Gaps Per Page

### Settings.tsx (46% → 100%)
- Form submission handlers (create/update/delete exchange configs)
- Notification toggle save mutations
- Audit log filter interactions
- Data source form submission + delete
- Test connection result display/dismiss

### RiskManagement.tsx (51% → 100%)
- Halt/resume kill switch mutations
- Limits edit/save/cancel form
- Position sizer calculation
- Trade checker mutation + result display
- VaR method/hours switching
- Alert severity/event filter changes
- Metric recording, reset daily

### Scheduler.tsx (57% → 100%)
- Pause/resume/trigger mutation execution
- formatInterval edge cases

### MLModels.tsx (55% → 100%)
- Train mutation execution + job progress
- Predict mutation + result display
- Model count display

### Portfolio.tsx (59% → 100%)
- Create/update/delete portfolio mutations
- Edit form interactions
- Allocation table rendering
- No-live-prices message

### Trading.tsx (67% → 100%)
- Performance summary cards
- WS disconnected banner
- Error message on orders
- Orders error banner

### Backtesting.tsx (67% → 100%)
- Comparison table rendering
- Job progress/metrics/equity curve display
- Framework switching
- Strategies error banner

### DataManagement.tsx (68% → 100%)
- Download/sample mutations
- Quality check results table
- Job progress rendering

### PaperTrading.tsx (78% → 100%)
- Forex signals info card
- Open trades with data
- Duration formatting (days/hours/minutes)
- Event log entry coloring
- Start mutation error display

### Workflows.tsx (78% → 100%)
- Enable/disable mutation calls
- Step types panel content display

### Dashboard.tsx (89% → 100%)
- Remaining uncovered conditional branches

### RegimeDashboard.tsx (89% → 100%)
- Remaining uncovered conditional branches

### MarketAnalysis.tsx (94% → 100%)
- 2 uncovered lines (172-173)

### Screening.tsx (96% → 100%)
- 1 uncovered line (31)

### MarketOpportunities.tsx (0% → 100%)
- Complete test file: summary cards, system status, scanner status, type distribution, filters, opportunities table, daily report sections
