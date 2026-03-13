# Phase 7: hftbacktest/ — 100% Coverage Plan

**Created**: 2026-03-09
**Current Coverage**: 89% (43 uncovered lines / 401 total)
**Target**: 100%

---

## Uncovered Files & Lines

### 1. `hftbacktest/hft_runner.py` (63% → 100%) — 40 uncovered lines

| Lines | Code | Test Strategy |
|-------|------|---------------|
| 43-45 | `except ImportError` in `_load_platform_config()` | Mock `builtins.__import__` to raise ImportError for yaml |
| 46-48 | `except Exception` in `_load_platform_config()` | Mock yaml.safe_load to raise RuntimeError |
| 113-116 | `convert_ohlcv_to_hft_ticks` returns None fallback | Mock `convert_ohlcv_to_hft_ticks` to return None + tick_path not existing |
| 170-215 | `__main__` CLI (argparse + all 4 subcommands + help) | `runpy.run_module` or mock `sys.argv` + exec; test convert, backtest, list-strategies, test, no-command |

### 2. `hftbacktest/strategies/base.py` (98% → 100%) — 2 uncovered lines

| Line | Code | Test Strategy |
|------|------|---------------|
| 72 | `raise NotImplementedError` in `on_tick()` | Instantiate `HFTBaseStrategy` directly and call `on_tick()` |
| 212 | `return pd.DataFrame()` when trades list empty after FIFO | Create fills that are all same-side (no round-trips) → empty trades list after FIFO |

### 3. `hftbacktest/strategies/market_maker.py` (96% → 100%) — 1 uncovered line

| Line | Code | Test Strategy |
|------|------|---------------|
| 43 | `return` after `check_drawdown_halt()` returns True | Set balance way below peak so drawdown > halt%, call `on_tick()` |

---

## Test File

`backend/tests/test_hft_phase7.py`

## Estimated New Tests: ~15-20

## Pragma Notes

- `__main__` block (line 170): Could pragma, but prefer testing CLI paths since they contain real logic (argparse + dispatching to real functions)
