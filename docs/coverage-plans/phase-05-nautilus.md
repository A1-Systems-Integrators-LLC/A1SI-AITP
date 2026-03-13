# Phase 5: nautilus/ — 100% Coverage Plan

**Target**: nautilus/ subsystem from 85% → 100% line coverage
**Uncovered**: 110 statements across 8 files
**Approach**: pragma for module-level import guards + __main__ block; tests for all functional gaps

---

## Pragma: no cover (untestable module-level code)

| File | Lines | Reason |
|------|-------|--------|
| `engine.py` | 38-39 | `except ImportError: HAS_NAUTILUS_TRADER = False` (module-level) |
| `nt_native.py` | 39-40 | `except ImportError: HAS_NAUTILUS_TRADER = False` (module-level) |
| `nt_native.py` | 232-234 | `else: NATIVE_STRATEGY_REGISTRY = {}` (module-level) |
| `nautilus_runner.py` | 47-48 | `except ImportError: HAS_NAUTILUS_TRADER = False` (module-level) |
| `nautilus_runner.py` | 367-420 | `if __name__ == "__main__":` CLI block (dispatches to tested functions) |

**Estimated pragma stmts**: ~37

---

## Test Coverage Map

### nt_native.py (40 stmts to cover)

| Lines | What | Test |
|-------|------|------|
| 105 | `_enter_long(bar)` on entry signal | `test_on_bar_enter_long` |
| 107-108 | `_exit_position(bar)` on exit signal | `test_on_bar_exit_position` |
| 110-115 | Stop loss check + exit | `test_on_bar_stop_loss` |
| 118-133 | `_enter_long()` — order creation, position tracking | Covered by on_bar_enter_long |
| 136-147 | `_exit_position()` — order creation, position clear | Covered by on_bar_exit + _exit_no_position |
| 152-153 | `on_stop()` flatten | `test_on_stop_flatten` |
| 170-173 | `NativeMeanReversion.__init__` | `test_native_mean_reversion_init` |
| 179-184 | `NativeVolatilityBreakout.__init__` | `test_native_volatility_breakout_init` |
| 190-193 | `NativeEquityMomentum.__init__` | `test_native_equity_momentum_init` |
| 199-202 | `NativeEquityMeanReversion.__init__` | `test_native_equity_mean_reversion_init` |
| 208-211 | `NativeForexTrend.__init__` | `test_native_forex_trend_init` |
| 217-220 | `NativeForexRange.__init__` | `test_native_forex_range_init` |

### engine.py (9 stmts to cover)

| Lines | What | Test |
|-------|------|------|
| 55-56 | Config load exception handler | `test_load_nautilus_config_exception` |
| 90 | `raise ImportError` in create_backtest_engine | `test_create_backtest_engine_no_nt` |
| 110 | `raise ImportError` in add_venue | `test_add_venue_no_nt` |
| 137 | `raise ImportError` in create_crypto_instrument | `test_create_crypto_instrument_no_nt` |
| 176 | `raise ImportError` in create_equity_instrument | `test_create_equity_instrument_no_nt` |
| 214 | `raise ImportError` in create_forex_instrument | `test_create_forex_instrument_no_nt` |
| 288 | `raise ImportError` in build_bar_type | `test_build_bar_type_no_nt` |
| 312 | `raise ImportError` in convert_df_to_bars | `test_convert_df_to_bars_no_nt` |

### nautilus_runner.py (13 stmts to cover)

| Lines | What | Test |
|-------|------|------|
| 63-65 | `_load_platform_config` generic exception | `test_load_platform_config_exception` |
| 263-265 | `_run_native_backtest` exception fallback | `test_run_native_backtest_exception` |
| 358-360 | `run_nautilus_engine_test` exception | `test_engine_test_exception` |
| 361-364 | `run_nautilus_engine_test` NT not installed | `test_engine_test_not_installed` |

### base.py (6 stmts to cover)

| Lines | What | Test |
|-------|------|------|
| 129 | `should_enter` NotImplementedError | `test_should_enter_not_implemented` |
| 133 | `should_exit` NotImplementedError | `test_should_exit_not_implemented` |
| 195 | Position sizing zero risk_per_unit | `test_position_sizing_zero_risk` |
| 230-232 | Risk gate API exception | `test_risk_gate_exception` |

### Strategy edge cases (4 stmts)

| File | Line | Test |
|------|------|------|
| equity_mean_reversion.py | 33 | `test_equity_mean_reversion_low_volume` |
| equity_momentum.py | 55 | `test_equity_momentum_exit_no_conditions` |
| forex_range.py | 33 | `test_forex_range_invalid_bb` |
| volatility_breakout.py | 43 | `test_volatility_breakout_zero_bb_width` |

---

## Estimated: ~32 new tests
## Test file: `backend/tests/test_nautilus_phase5.py`
