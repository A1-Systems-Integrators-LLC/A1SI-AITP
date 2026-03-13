# IEB Phase 8: Strategy Orchestrator

## Summary

Implements a centralized strategy orchestrator that evaluates regime-strategy alignment and manages strategy pause/resume state. Bridges the gap between the existing `_run_strategy_orchestration` task executor (which computed alignment but discarded results) and the trading strategies (which had no way to know they were misaligned).

## Components

### 1. `backend/trading/services/strategy_orchestrator.py` (NEW)

**`StrategyOrchestrator`** — Thread-safe singleton service:
- `evaluate(asset_classes)` — Detects regime per asset class, checks alignment tables, updates state store
- `get_state(strategy, asset_class)` → `StrategyState` or None
- `get_all_states()` → list of all states
- `is_paused(strategy, asset_class)` → bool
- `get_size_modifier(strategy, asset_class)` → 1.0 (active), 0.5 (reduce_size), 0.0 (pause)

**State transitions** trigger:
- `AlertLog` entry (severity: warning for pause, info for resume)
- WebSocket `strategy_status` broadcast
- Telegram notification (rate-limited, 15min cooldown) for pause/resume

**Alignment thresholds**: ≤10 = pause, ≤30 = reduce_size, >30 = active

### 2. `backend/core/services/ws_broadcast.py` (MODIFIED)

Added `broadcast_strategy_status(strategy, asset_class, regime, alignment, action)` — new WS event type `strategy_status`.

### 3. `backend/core/services/task_registry.py` (MODIFIED)

`_run_strategy_orchestration` now delegates to `StrategyOrchestrator.get_instance().evaluate()` instead of computing alignment inline. Returns `transitioned` count in addition to existing fields.

### 4. `backend/config/settings.py` (MODIFIED)

Added `strategy_orchestration` scheduled task: every 15 minutes, all asset classes.

### 5. `backend/analysis/views.py` (MODIFIED)

`StrategyStatusView.get()` now prefers orchestrator persisted state when available, falling back to fresh computation before the first orchestrator run.

### 6. `freqtrade/user_data/strategies/_conviction_helpers.py` (MODIFIED)

Added `check_strategy_paused(strategy)`:
- Queries `/api/analysis/signals/strategy-status/` for pause status
- 60-second cache to avoid API spam
- Skipped in BACKTEST/HYPEROPT mode
- Fail-open: returns False (not paused) if API unreachable

`check_conviction()` now calls `check_strategy_paused()` first — if paused, rejects entry without checking conviction signal.

### 7. `backend/tests/test_freqtrade_conviction.py` (MODIFIED)

Added `_skip_pause_check` autouse fixture to `TestCheckConviction` class so existing tests aren't affected by the new pause check in `check_conviction()`.

## Tests

**38 new tests** in `backend/tests/test_strategy_orchestrator.py`:
- StrategyState dataclass (1)
- Singleton management (2)
- State management (7)
- Evaluate with mocked regime (3)
- State persistence after evaluate (4)
- Transition handling — AlertLog, WS broadcast, Telegram (7)
- WS broadcast helper (1)
- Task registry executor (2)
- StrategyStatusView API integration (2)
- Scheduled task config (2)
- Freqtrade pause check — backtest, API pause, fail-open, cache, conviction integration (5)
- Error handling — alert/broadcast/telegram failure isolation (3)

## Verification

```bash
# All 38 new tests pass
python -m pytest backend/tests/test_strategy_orchestrator.py -v

# Existing tests unaffected
python -m pytest backend/tests/test_signal_service.py backend/tests/test_freqtrade_conviction.py -v

# Lint clean
python -m ruff check backend/trading/services/strategy_orchestrator.py backend/tests/test_strategy_orchestrator.py
```
