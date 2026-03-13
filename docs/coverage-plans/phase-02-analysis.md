# Phase 2: backend/analysis/ — 73% → 100% Coverage

**Created**: 2026-03-09
**Subsystem**: `backend/analysis/`
**Current coverage**: 73% (414 uncovered lines of 1518)
**Target**: 100%

---

## Uncovered Files & Line Ranges

### 1. `services/ml.py` — 0% (87/87 lines uncovered)
All 4 methods completely untested at the service level.

| Method | Lines | Test Cases |
|--------|-------|------------|
| `train()` | 22-71 | Happy path (mock load_ohlcv, build_feature_matrix, train_model, ModelRegistry); empty data error; insufficient data (<100 rows); ImportError on data_pipeline; ImportError on ML modules |
| `predict()` | 84-126 | Happy path; missing model_id; model not found (FileNotFoundError); empty data; no valid feature rows; ImportError |
| `list_models()` | 131-136 | Happy path; ImportError returns [] |
| `get_model_detail()` | 141-146 | Happy path; ImportError returns None |

### 2. `services/screening.py` — 31% (77/112 lines uncovered)
Lines 61-248: All 4 screen helper functions + strategy dispatch logic.

| Function | Lines | Test Cases |
|----------|-------|------------|
| `run_full_screen()` dispatch | 61-90 | Each strategy type called; empty data; VBT ImportError per-strategy; generic Exception per-strategy; None/empty result_df |
| `_screen_sma()` | 102-131 | Mock vbt.MA.run_combs + Portfolio.from_signals; verify sort order |
| `_screen_rsi()` | 135-172 | Mock RSI + Portfolio; verify parameter combinations; os_lvl >= ob_lvl skip; empty results |
| `_screen_bollinger()` | 176-211 | Mock SMA + rolling + Portfolio; verify results |
| `_screen_ema_rsi()` | 215-248 | Mock EMA + RSI + Portfolio; verify results |

### 3. `services/backtest.py` — 59% (53/128 lines uncovered)
Lines 53-191: Framework-specific runners and result parsing.

| Method | Lines | Test Cases |
|--------|-------|------------|
| `_run_freqtrade()` full path | 53, 60-106 | Success with JSON results; non-zero return code; timeout; FileNotFoundError; missing config; results dir parsing with strategy data |
| `_run_nautilus()` | 115, 138-141, 147, 154-191 | Happy path; ImportError; no strategy specified (default); no strategy registered; error in result |
| `_run_hft()` | 202, 224-225, 239-240 | Happy path; ImportError; no strategy specified; error in result |
| `list_strategies()` | All lines | Freqtrade file discovery; Nautilus registry import; HFT registry import; ImportError fallbacks |

### 4. `views.py` — 69% (113/366 lines uncovered)
Major uncovered endpoints.

| View | Lines | Test Cases |
|------|-------|------------|
| `JobListView.get` | 50 | Filter by job_type |
| `JobDetailView.get` | 63-71 | Live progress overlay on running job |
| `JobCancelView.post` | 77-85 | Cancel success; job not found |
| `BacktestRunView.post` | 95-106 | Submit backtest job |
| `BacktestResultListView.get` | 131 | Filter by asset_class |
| `BacktestResultDetailView.get` | 139-146 | Not found case |
| `BacktestStrategyListView.get` | 152-154 | Returns strategy list |
| `ScreeningRunView.post` | 312-323 | Submit screening job |
| `ScreeningResultDetailView.get` | 336, 344-348 | Not found case |
| `DataDetailView.get` | 371-378 | Not found case |
| `DataDownloadView.post` | 388-398 | Submit download job |
| `DataGenerateSampleView.post` | 411-421 | Submit generate job |
| `MLTrainView.post` | 439-449 | Submit ML train job |
| `MLModelListView.get` | 458-460 | List models |
| `MLModelDetailView.get` | 466-471 | Get detail; not found |
| `MLPredictView.post` | 481-488 | Predict success; error response |
| `DataQualityListView.get` | 497-520 | Success; ImportError; OSError |
| `DataQualityDetailView.get` | 529-550 | Success; FileNotFoundError; ImportError; OSError |
| `WorkflowDetailView.delete` | 636-637 | Template protection; not found |
| `WorkflowEnableView.post` | 674-675 | Not found |
| `WorkflowDisableView.post` | 686-687 | Not found |
| `WorkflowRunDetailView.get` | 729 | Success |

### 5. `services/step_registry.py` — 79% (24/113 lines uncovered)
Lines 20-41: Re-export wrappers. Lines 115-205: Workflow step executors.

| Function | Lines | Test Cases |
|----------|-------|------------|
| `_step_data_refresh` | 20-21 | Delegates to task_registry |
| `_step_regime_detection` | 25-26 | Delegates to task_registry |
| `_step_news_fetch` | 30-31 | Delegates to task_registry |
| `_step_data_quality` | 35-36 | Delegates to task_registry |
| `_step_order_sync` | 40-41 | Delegates to task_registry |
| `_step_vbt_screen` | 115 | Success; exception |
| `_step_sentiment_aggregate` | 129-131 | Success; exception |
| `_step_composite_score` | 169-170 | Success; regimes with up/down/unknown; exception |
| `_step_alert_evaluate` | 179-181 | Alerts triggered; no alerts; notification failure |
| `_step_strategy_recommend` | 197-199 | Success; exception |
| `_step_ml_training` | 204-205 | Delegates to task_registry |

### 6. `services/job_runner.py` — 78% (22/101 lines uncovered)
Lines 23-55: Recovery functions. Lines 124-125, 166-167, 180-183, 227-228: Error/broadcast paths.

| Function | Lines | Test Cases |
|----------|-------|------------|
| `recover_stale_jobs()` | 23-35 | With stale jobs; no stale jobs |
| `recover_stale_workflow_runs()` | 43-55 | With stale runs; no stale runs |
| `_run_job` WS broadcast fail | 124-125 | Broadcast exception swallowed |
| `_run_job` completion broadcast fail | 166-167 | Broadcast exception swallowed |
| `_run_job` multi-strategy persist | 180-183 | Multi-strategy backtest result |
| `_run_job` failure broadcast | 227-228 | Failure broadcast exception swallowed |

### 7. `services/workflow_engine.py` — 94% (10/164 lines uncovered)
Lines 51, 56-59: Condition evaluation edge cases. Lines 121-123, 294-296: Minor paths.

| Function | Lines | Test Cases |
|----------|-------|------------|
| `_evaluate_condition` | 51 | >= operator |
| `_evaluate_condition` | 56-59 | <= operator; string != comparison |
| `execute_workflow` StepRun DoesNotExist | 121-123 | Missing step run record |
| `WorkflowEngine.cancel` with job | 294-296 | Cancel propagation to job |

### 8. `models.py` — 83% (25/146 lines uncovered)
Lines 34-46, 88, 117-123, 143-149, 152, 229, 257: clean() and __str__.

| Model | Lines | Test Cases |
|-------|-------|------------|
| `BackgroundJob.clean()` | 34-43 | Invalid progress; invalid status; valid |
| `BackgroundJob.__str__` | 46 | String representation |
| `BacktestResult.__str__` | 88 | String representation |
| `Workflow.clean()` | 117-123 | Invalid schedule interval |
| `WorkflowStep.clean()` | 143-149 | Invalid order; invalid timeout |
| `WorkflowStep.__str__` | 152 | String representation |
| `WorkflowStepRun.__str__` | 229 | String representation |
| `ScreenResult.__str__` | 257 | String representation |

### 9. `services/data_pipeline.py` — 97% (3/88 lines uncovered)
Lines 62-64: Error path in get_data_info.

| Method | Lines | Test Cases |
|--------|-------|------------|
| `get_data_info` error | 62-64 | Corrupt parquet file raises exception |

---

## Test File Organization

- `backend/tests/test_analysis_phase2.py` — Main test file for all Phase 2 coverage gaps

## Execution Order

1. Write all tests in a single file
2. Run coverage to verify 100%
3. Fix any remaining gaps
4. Update memory

## Estimated Tests: ~85
