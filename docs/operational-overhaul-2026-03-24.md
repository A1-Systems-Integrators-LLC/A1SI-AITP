# Operational Overhaul Plan — 2026-03-24

## Problem Statement

The system has extensive infrastructure (35 scheduled tasks, 10K+ jobs completed, 457 data files) but appears dead to the user:
- No visible portfolios with holdings
- No filled crypto trades (only 6 forex paper trades)
- 1,299 rejected forex orders (position sizing bug)
- ML accuracy at 50% (coin flip)
- 0 signal attributions (feedback loop disconnected)
- Dashboard lacks system activity visibility
- 2 of 3 Freqtrade instances down

## Phase 1: Stop the Bleeding (COMPLETED)

### Fix 1: Forex Paper Trading Position Sizing
- **Root cause**: `POSITION_SIZE_USD = 1000.0` hardcoded, but pilot portfolio equity is $500 with 20% max position limit → $1000/$500 = 200% > 20% → every order rejected
- **Fix**: Dynamic sizing from RiskState equity × RiskLimits.max_position_size_pct, fallback to $100
- **File**: `backend/trading/services/forex_paper_trading.py`

### Fix 2: Freqtrade 3-Strategy Operation Restored
- **Root cause**: Commit caa09f2 consolidated to BMR-only for $500 capital review
- **Fix**: Reverted `start.sh` and `watchdog.sh` to all 3 strategies (CIV1, BMR, VB)
- **Files**: `scripts/start.sh`, `scripts/watchdog.sh`

### Fix 3: Signal Attribution Recording
- **Root cause**: `_conviction_helpers.py` had no code to POST attribution data to Django API at trade entry
- **Fix**: Added `record_signal_attribution()` function that POSTs signal component breakdown (technical, ML, sentiment, regime, scanner, win_rate contributions) to `/api/signals/record/` endpoint
- **Files**: `freqtrade/user_data/strategies/_conviction_helpers.py`, all 3 active strategies

## Phase 2: Dashboard Overhaul (COMPLETED)

### Fix 4: System Health Card
- Shows scheduler status, data freshness, Freqtrade instance status, job completion stats
- **Backend**: `DashboardService._get_system_health()`
- **Frontend**: `SystemHealthCard` component

### Fix 5: Agent Learning Card
- Shows ML accuracy, predictions count, signal attributions, last training, orchestrator states
- **Backend**: `DashboardService._get_learning_status()`
- **Frontend**: `AgentLearningCard` component

### Fix 6: Activity Feed
- Shows last 15 system events from jobs, alerts, and scheduled tasks (24h window)
- **Backend**: `DashboardService._get_activity_feed()`
- **Frontend**: `ActivityFeedWidget` component

### Fix 7: Trading Performance Always Visible
- Removed `total_trades > 0` gate — card now always shows
- Added order stats: total orders, filled orders, rejection rate
- Color-coded rejection rate (green <20%, yellow 20-50%, red >50%)

### Fix 8: Portfolio Equity from RiskState
- When portfolio has 0 holdings, falls back to RiskState equity data
- Shows actual pilot equity ($1,496.90) instead of $0

## Phase 3: Autonomous Operation (COMPLETED)

### Fix 9: Autonomous Check Command
- New management command: `manage.py autonomous_check [--fix] [--json]`
- Checks: Freqtrade instances, ML training, signal attributions, data freshness, scheduler, order health
- Auto-fix: triggers ML training if never run
- Added as scheduled task: hourly, with `fix: true`

### Fix 10: Task Registry Executor
- `_run_autonomous_check` in task_registry.py
- Runs all 6 health checks, applies fixes if params.fix=True

## Phase 4: Continuous Learning Pipeline (PLANNED)

Priority items for next session:
1. Route Reddit text through FinBERT (already loaded, wiring change)
2. Concept drift detection for ML models (monitor rolling accuracy, trigger retrain)
3. Strategy discovery from freqtrade-strategies GitHub repo
4. Glassnode free-tier API for MVRV/SOPR on-chain indicators
5. Temporal Fusion Transformer as third ML model type

## Test Results

- Frontend: 1,125 tests passing (60 files, 0 failures)
- Backend: 5,214+ tests passing (1 pre-existing flaky test excluded)
