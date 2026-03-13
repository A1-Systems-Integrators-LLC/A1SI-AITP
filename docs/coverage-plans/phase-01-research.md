# Phase 1: research/ — 46% → 100% Coverage

**Created**: 2026-03-09
**Files**: 7 source files, 390 uncovered lines
**Est. New Tests**: ~80

## Files & Test Strategy

### 1. pipeline_report.py (0% → 100%, 112 lines)

| Lines | Function | Test Approach |
|-------|----------|---------------|
| 21-28 | `collect_data_summary()` | Mock DATA_DIR.glob to return fake parquet Path objects with stat() |
| 31-39 | `collect_vbt_screening()` | Create temp summary.json files, verify parsed structure |
| 42-72 | `collect_gate_validation()` | Create temp validation JSON files with gate2/gate3 fields |
| 75-124 | `collect_freqtrade_backtests()` | Create temp zip with JSON inside, test strategy extraction + error path |
| 127-171 | `build_report()` | Mock all collect_* functions, verify report structure + summary stats |
| 174-239 | `main()` | Mock build_report, verify file save + print output |

**Test file**: `backend/tests/test_pipeline_report.py`

### 2. run_risk_validation.py (0% → 100%, 63 lines)

| Lines | Code | Test Approach |
|-------|------|---------------|
| 3-84 | Module-level script | Run via subprocess with mocked data pipeline, or mock all imports and exec |

**Test file**: `backend/tests/test_run_risk_validation.py`

### 3. validation_engine.py (63% → 100%, 81 lines)

| Lines | Function | Test Approach |
|-------|----------|---------------|
| 238-298 | `walk_forward_validate()` | Test with sufficient data, verify fold results structure |
| 318-359 | `perturbation_test()` | Test int + float param perturbation, exception handling |
| 411-443 | `run_validation()` gate2 pass branch | Use signal_fn that reliably generates passing gate2 results |
| 454-506 | `run_validation()` gate3 logic | Verify gate3_walkforward + gate3_perturbation report sections |

**Test file**: Expand `backend/tests/test_validation.py`

### 4. validate_bollinger_mean_reversion.py (43% → 100%, 35 lines)

| Lines | Function | Test Approach |
|-------|----------|---------------|
| 103-176 | `main()` | Mock argparse args, test synthetic + real data paths, verify report output |

### 5. validate_crypto_investor_v1.py (45% → 100%, 35 lines)

| Lines | Function | Test Approach |
|-------|----------|---------------|
| 107-180 | `main()` | Mock argparse args, test synthetic + real data paths |

### 6. validate_volatility_breakout.py (49% → 100%, 35 lines)

| Lines | Function | Test Approach |
|-------|----------|---------------|
| 129-202 | `main()` | Mock argparse args, test synthetic + real data paths |

**Test file**: Expand `backend/tests/test_validation.py`

### 7. vbt_screener.py (81% → 100%, 64 lines)

| Lines | Function | Test Approach |
|-------|----------|---------------|
| 503-532 | `walk_forward_validate()` internals | Test with data producing valid IS results, verify OOS extraction |
| 625-668 | `run_full_screen()` save + WF section | Mock load_ohlcv, test all 6 screens + result saving + equity branch |
| 705-757 | CLI `__main__` block | Test via subprocess with mocked data |

**Test file**: Expand `backend/tests/test_vbt_screener.py`

## Verification

```bash
python -m pytest backend/tests/test_pipeline_report.py backend/tests/test_run_risk_validation.py backend/tests/test_validation.py backend/tests/test_vbt_screener.py --cov=research --cov-report=term-missing -v
```

Target: 100% line coverage on all 7 research/ source files.
