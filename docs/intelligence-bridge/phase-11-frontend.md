# IEB Phase 11: Frontend Conviction Dashboard

## Overview
Build the frontend UI layer to visualize and interact with the conviction scoring system (IEB phases 1-10).

## New Files
1. `frontend/src/api/signals.ts` — API wrappers for all signal endpoints
2. `frontend/src/pages/ConvictionDashboard.tsx` — New dedicated dashboard page
3. `frontend/tests/ConvictionDashboard.test.tsx` — Tests for new page

## Modified Files
1. `frontend/src/types/index.ts` — Add signal/conviction types
2. `frontend/src/App.tsx` — Add lazy route for /conviction
3. `frontend/src/components/Layout.tsx` — Add nav item
4. `frontend/src/pages/Trading.tsx` — Add conviction score widget near order form
5. `frontend/src/pages/MarketOpportunities.tsx` — Add signal quality indicator
6. `frontend/src/pages/MLModels.tsx` — Add accuracy/performance widget
7. `frontend/src/api/ml.ts` — Add model performance API

## ConvictionDashboard Sections
1. **Conviction Heatmap** — Batch signals for watchlist, color-coded by score
2. **Signal Component Breakdown** — Per-symbol radar display (6 sources)
3. **Strategy Orchestrator Status** — Active/paused/reduce_size per strategy
4. **Performance Attribution** — Win/loss per signal source
5. **Weight Recommendations** — Current vs recommended weights

## API Endpoints Used
- `GET /api/analysis/signals/<symbol>/` — Single composite signal
- `POST /api/analysis/signals/batch/` — Batch signals
- `GET /api/analysis/signals/strategy-status/` — Strategy status
- `GET /api/analysis/signals/attribution/` — Attribution list
- `GET /api/analysis/signals/accuracy/` — Source accuracy
- `GET /api/analysis/signals/weights/` — Weight recommendations
- `GET /api/analysis/ml/predictions/<symbol>/` — ML predictions
- `GET /api/analysis/ml/models/<model_id>/performance/` — Model performance

## Estimated Tests: ~50 new vitest tests
