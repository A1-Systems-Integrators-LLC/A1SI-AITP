# 100% Test Coverage Plan — A1SI-AITP

**Created**: 2026-03-09
**Current State**: Backend 95% (1,654 uncovered lines / 33,129 total), Frontend 73.5% stmts / 75.3% lines
**Target**: 100% line coverage backend, 100% line coverage frontend
**Tests**: 2,960 backend (pytest) + 688 frontend (vitest) + 8 E2E = 3,656 total

---

## Approach

Bottom-up, subsystem-by-subsystem. Each phase has its own detailed plan document in `docs/coverage-plans/` that will be created before execution begins. Phases are ordered by **risk priority** — subsystems with the worst coverage and highest operational risk go first.

Each phase is a standalone task with full context. No assumptions. No shortcuts. Every uncovered line is accounted for.

---

## Phase Summary

| Phase | Subsystem | Current | Uncovered Lines | Priority | Est. Tests |
|-------|-----------|---------|-----------------|----------|------------|
| 1 | research/ | **100%** | 0 | **COMPLETE** — 172 tests, +77 new | ~80 |
| 2 | backend/analysis/ | **100%** | 0 | **COMPLETE** — 571 tests, +132 new | ~70 |
| 3 | backend/market/ | **100%** | 0 | **COMPLETE** — 350 tests, +240 new (was 60%, 732 uncovered) | ~50 |
| 4 | backend/core/ | **100%** | 0 | **COMPLETE** — 872 tests, +280 new (was 61%, 2149 stmts) | ~55 |
| 5 | nautilus/ | **100%** | 0 | **COMPLETE** — 237 tests, +33 new (was 85%, 110 uncovered) | ~35 |
| 6 | backend/trading/ | **100%** | 0 | **COMPLETE** — 293 tests, +97 new (was 83%, 190 uncovered) | ~30 |
| 7 | hftbacktest/ | **100%** | 0 | **COMPLETE** — 193 tests, +11 new | ~20 |
| 8 | backend/portfolio/ | **100%** | 0 | **COMPLETE** — 99 tests, +19 new (was 83%, 51 uncovered) | ~15 |
| 9 | common/ | **100%** | 0 | **COMPLETE** — 1682 stmts, +39 new tests | ~25 |
| 10 | backend/risk/ | **100%** | 0 | **COMPLETE** — 319 tests, +27 new (was 92%, 45 uncovered) | ~8 |
| 11 | backend/config/ + manage.py | **100%** | 0 | **COMPLETE** — 124 stmts, +11 new tests | ~5 |
| 12 | Frontend pages | **100%** | 0 | **COMPLETE** — 991→1039 vitest, +303 new tests | ~120 |
| 13 | Frontend components | **100%** | 0 | **COMPLETE** — 1039 vitest tests, +48 new | ~50 |
| 14 | Frontend hooks + api + utils | **100%** | 0 | **COMPLETE** — 1082 vitest tests, +43 new | ~40 |

**Total estimated new tests: ~600 backend + ~210 frontend = ~810 new tests**

**ALL 14 PHASES COMPLETE** — 100% line coverage across entire codebase (backend + frontend).

---

## Phase 1: research/ (46% → 100%)

**Risk**: Research scripts validate strategy correctness. Untested validation = undetected strategy bugs = bad trades.

### Files & Gaps

| File | Coverage | Uncovered | Missing Lines |
|------|----------|-----------|---------------|
| `research/scripts/pipeline_report.py` | 0% | 112 | 6-243 (entire file) |
| `research/scripts/run_risk_validation.py` | 0% | 63 | 3-84 (entire file) |
| `research/scripts/validation_engine.py` | 63% | 81 | 238-298, 318-359, 411-443, 454-506 |
| `research/scripts/validate_bollinger_mean_reversion.py` | 43% | 35 | 103-176 (main block) |
| `research/scripts/validate_crypto_investor_v1.py` | 45% | 35 | 107-180 (main block) |
| `research/scripts/validate_volatility_breakout.py` | 49% | 35 | 129-202 (main block) |
| `research/scripts/vbt_screener.py` | 81% | 64 | 503-532, 625-668, 705-757 |

### Test Strategy
- `pipeline_report.py`: Mock data sources, test each report section generator
- `run_risk_validation.py`: Mock validation engine, test CLI entry point
- `validation_engine.py`: Test report generation, metric calculation, threshold evaluation (lines 238-506)
- `validate_*.py`: Test main() blocks with mocked engine — these are CLI wrappers
- `vbt_screener.py`: Test walk-forward validation (503-532), CLI arg parsing (625-668), main orchestrator (705-757)

### Deliverable
- `docs/coverage-plans/phase-01-research.md` — detailed plan with exact test cases per uncovered line range
- New test files: `test_pipeline_report.py`, `test_run_risk_validation.py`, expanded `test_vbt_screener.py` and `test_validation.py`

---

## Phase 2: backend/analysis/ (72% → 100%)

**Risk**: ML service at 15% coverage, screening at 31%. These drive trading decisions. Silent failures here = lost money.

### Files & Gaps

| File | Coverage | Uncovered | Missing Lines |
|------|----------|-----------|---------------|
| `services/ml.py` | **15%** | 74 | 22-66 (train), 84-126 (predict), 131-146 (utils) |
| `services/screening.py` | **31%** | 77 | 61-248 (all screen execution paths) |
| `services/backtest.py` | **59%** | 53 | 60-106, 138-191 (framework invocation) |
| `views.py` | 83% | 64 | 50-106, 131-154, 312-488 (API endpoints) |
| `services/step_registry.py` | 79% | 24 | 115-205 (step executor functions) |
| `services/workflow_engine.py` | 94% | 10 | 51-59, 121-123, 294-296 |
| `services/job_runner.py` | 90% | 10 | 124-125, 166-183, 227-228 |
| `services/data_pipeline.py` | 97% | 3 | 62-64 |
| `models.py` | 97% | 5 | 46, 88, 152, 229, 257 |

### Test Strategy
- `ml.py`: Mock LightGBM/sklearn, test train flow end-to-end, predict with model registry, error paths
- `screening.py`: Mock VBT screener, test each screen type dispatch, error handling, result persistence
- `backtest.py`: Mock Freqtrade/Nautilus/HFT runners, test each framework dispatch path, result parsing
- `views.py`: HTTP-level tests for every uncovered endpoint (ML, screening, backtest, data quality, workflow)
- `step_registry.py`: Test each step executor with mocked dependencies
- `workflow_engine.py`: Test condition evaluation edge cases, step timeout, error propagation

### Deliverable
- `docs/coverage-plans/phase-02-analysis.md`
- Expanded test files covering all 320 uncovered lines

---

## Phase 3: backend/market/ (86% → 100%)

**Risk**: Market scanner, exchange service, and daily report drive signal generation and monitoring.

### Files & Gaps

| File | Coverage | Uncovered | Missing Lines |
|------|----------|-----------|---------------|
| `services/market_scanner.py` | 75% | 48 | 121-199 (detector internals), 270-494 (cleanup, alerts) |
| `services/daily_report.py` | 77% | 37 | 60-81, 104-139, 196-247, 275-333 |
| `services/exchange.py` | 82% | 21 | 57-78 (init/config), 117-187 (error paths) |
| `views.py` | 89% | 53 | 112-114, 294-505, 551-629, 680-749 |
| `services/data_router.py` | 70% | 10 | 35-62 (routing fallback) |
| `services/news.py` | 91% | 6 | 57-63, 84, 167 |
| `models.py` | 97% | 4 | 54, 83, 175, 211 |
| `consumers.py` | 99% | 1 | 24 |
| `services/regime.py` | 97% | 3 | 13, 178-179 |
| `routing.py` | 0% | 3 | 3-7 (WebSocket URL routing — covered indirectly) |

### Deliverable
- `docs/coverage-plans/phase-03-market.md`

---

## Phase 4: backend/core/ (88% → 100%)

**Risk**: Scheduler manages all automated tasks. Platform bridge connects subsystems. Views serve the dashboard.

### Files & Gaps

| File | Coverage | Uncovered | Missing Lines |
|------|----------|-----------|---------------|
| `services/scheduler.py` | 77% | 51 | 243-279 (APScheduler lifecycle), 330-447 (sync, auto-schedule) |
| `views.py` | 85% | 63 | 83-239 (framework status, metrics), 295-403 (various endpoints), 503-775 |
| `management/commands/pilot_status.py` | 84% | 24 | 67-109, 116-256 |
| `core/apps.py` | 78% | 10 | 44-69, 90 (ready() signal handlers) |
| `encryption.py` | 79% | 4 | 18, 37-39 |
| `platform_bridge.py` | 70% | 11 | 19-67 (config loading) |
| `management/commands/validate_deps.py` | 77% | 6 | 59-69 |
| `management/commands/pilot_preflight.py` | 94% | 10 | 59-60, 77, 106, 127-128, 150, 176, 246-247 |
| `services/task_registry.py` | 95% | 16 | 186-188, 256-258, 447-545 |
| `exception_handler.py` | 81% | 5 | 27-32 |
| `services/notification.py` | 97% | 3 | 200-202 |
| `auth.py` | 97% | 2 | 29, 47 |
| `models.py` | 97% | 2 | 58, 77 |
| `middleware.py` | 99% | 1 | 143 |
| `logging.py` | 96% | 1 | 50 |
| `schema.py` | 91% | 1 | 45 |

### Deliverable
- `docs/coverage-plans/phase-04-core.md`

---

## Phase 5: nautilus/ (85% → 100%) — COMPLETE

**Completed**: 2026-03-09
**Result**: 237 tests, +33 new, 100% coverage on all 13 files

### Approach
- Direct NT Strategy instantiation for adapter init coverage (NativeMeanReversion through NativeForexRange)
- Real BacktestEngine with mocked signal engine for on_bar/entry/exit/stoploss tests
- `patch("nautilus.engine.HAS_NAUTILUS_TRADER", False)` for ImportError guard tests
- `pragma: no cover` on module-level import fallbacks and `__main__` block (7 locations)
- Edge case tests for volume/BB width guards in individual strategies

### Deliverable
- `docs/coverage-plans/phase-05-nautilus.md`
- `backend/tests/test_nautilus_phase5.py` (33 new tests)

---

## Phase 6: backend/trading/ (83% → 100%) — COMPLETE

**Completed**: 2026-03-09
**Result**: 293 tests, +97 new, 100% coverage on all 19 files

### Approach
- Model validation: `Order.clean()` (amount/price/side/limit), `OrderFillEvent.clean()`, `__str__` methods
- Serializer validation: `OrderCreateSerializer.validate_exchange_id` with invalid exchange
- Paper trading service: Config errors (JSON/missing), env URL override, API alive, start errors (FileNotFoundError, generic), stop (external process, kill timeout), status (external API, exited process), async methods (_ft_get success/errors, trades/profit/perf/balance), log events (OSError, invalid JSON, missing file)
- Order sync: Sync loop body, per-order exceptions, top-level exception
- Live trading: Partial fill detection (SUBMITTED→PARTIAL_FILL invalid transition → ValueError caught), cancel_all per-order exception
- Generic paper trading: Market hours ImportError, risk rejection, zero price, limit buy/sell unfilled, get_status
- Forex paper trading: Max positions, sell-side entry fallback, no entry order, exit submit failure, price exception/success
- Views: All filter branches (mode/asset_class/symbol/status/date_from/date_to), cancel (404/terminal/live/paper), live trading status, cached exchange status (TTL hit/refresh/exchange failure), CSV export (all branches), paper trading views (status forex exception, trades forex, history, profit, performance, balance, log), multi-instance factory, exchange health (connected/disconnected)
- `pragma: no cover` on views.py line 226 (race-condition double-check after lock)

### Deliverable
- `docs/coverage-plans/phase-06-trading.md`
- `backend/tests/test_trading_phase6.py` (97 new tests)

---

## Phase 7: hftbacktest/ (87% → 100%) — COMPLETE

**Completed**: 2026-03-09
**Result**: 193 tests, +11 new, 100% coverage on all 8 files

### Approach
- Extracted `cli_main(argv)` function from `__main__` block for testability; `__main__` line is `pragma: no cover`
- Mocked `builtins.__import__` to raise ImportError for yaml (config loading fallback)
- Mocked `yaml.safe_load` to raise RuntimeError (generic exception path)
- Mocked `convert_ohlcv_to_hft_ticks` returning None for tick fallback path
- Direct `cli_main()` calls with argv for all 5 CLI paths (convert, backtest, list-strategies, test, no-command)
- Direct `HFTBaseStrategy.on_tick()` for NotImplementedError
- All-same-side fills to trigger empty trades DataFrame after FIFO processing
- Drawdown halt on MarketMaker to trigger early return

### Deliverable
- `docs/coverage-plans/phase-07-hftbacktest.md`
- `backend/tests/test_hft_phase7.py` (11 new tests)

---

## Phase 8: backend/portfolio/ (83% → 100%) — COMPLETE

**Completed**: 2026-03-09
**Result**: 99 tests, +19 new, 100% coverage on all 14 files

### Approach
- Model `__str__` methods: Portfolio and Holding
- Model `clean()` validation: negative amount, negative avg_buy_price, both negative, valid
- Views: PUT/PATCH portfolio (success + 404), PUT/DELETE holding (success + 404), IntegrityError on duplicate holding
- Analytics `_fetch_prices`: ImportError (sys.modules sentinel + reload), ConnectionError/TimeoutError/OSError on ExchangeService init

### Deliverable
- `docs/coverage-plans/phase-08-portfolio.md`
- `backend/tests/test_portfolio_phase8.py` (19 new tests)

---

## Phase 9: common/ (94% → 100%) — COMPLETE

**Completed**: 2026-03-09
**Result**: 1682 stmts, 0 missed, 100% coverage on all 23 files, +39 new tests

### Approach
- `pragma: no cover` on pipeline.py `__main__` CLI block, ml/registry.py + ml/trainer.py ImportError guards, sessions.py dead-code safety fallbacks (2 lines)
- Tested: pipeline crypto timeframes default, validate_data NaN/outlier/OHLC issues, model registry list/save/load edge cases, Atom feed parsing, news dedup, market hours edge cases, yfinance tz_localize, supertrend direction changes, negative/neutral sentiment, risk manager market-hours ImportError + correlation check + heat check issues, regime transition probabilities, strategy router unknown-regime fallback + weight-based switch logic

### Deliverable
- `docs/coverage-plans/phase-09-common.md`
- `backend/tests/test_common_phase9.py` (39 new tests)

---

## Phase 10: backend/risk/ (92% → 100%) — COMPLETE

**Completed**: 2026-03-10
**Result**: 319 tests, +27 new, 100% coverage on all 13 files

### Approach
- Model `__str__` methods: RiskState, RiskLimits, RiskMetricHistory, TradeCheckLog (approved/rejected), AlertLog
- Model `clean()` validation: negative min_risk_reward, negative max_leverage, both negative
- `periodic_risk_check` notification failures: daily loss auto-halt exception handler, risk warning exception handler
- Views: All 11 uncovered endpoints (equity update, position size, reset daily, VaR, heat check, metric history, record metrics, halt, resume, alert list with filters, trade log)

### Deliverable
- `docs/coverage-plans/phase-10-risk.md`
- `backend/tests/test_risk_phase10.py` (27 new tests)

---

## Phase 11: backend/config/ + manage.py (75% → 100%)

### Files & Gaps

| File | Coverage | Uncovered | Missing Lines |
|------|----------|-----------|---------------|
| `config/asgi.py` | 0% | 8 | 3-16 (ASGI app setup) |
| `config/wsgi.py` | 0% | 4 | 3-9 (WSGI app setup) |
| `manage.py` | 0% | 11 | 4-22 (CLI entry point) |
| `config/settings.py` | 92% | 8 | 29, 31, 167-170, 264-266 |

### Notes
- `asgi.py`, `wsgi.py`, `manage.py` are Django boilerplate entry points — test with subprocess or pragma: no cover
- `settings.py` uncovered lines are conditional imports / environment-specific branches

### Deliverable
- `docs/coverage-plans/phase-11-config.md`

---

## Phase 12: Frontend Pages (67% → 100% lines)

**Risk**: 14 of 15 pages below 100%. Settings (49%), RiskManagement (53%), MLModels (56%), Scheduler (58%).

### Files & Gaps

| File | Lines Coverage | Key Gaps |
|------|---------------|----------|
| `pages/Settings.tsx` | 49% | Most handlers untested |
| `pages/RiskManagement.tsx` | 53% | Modal/action paths (58-790) |
| `pages/Scheduler.tsx` | 54% | Task interaction handlers |
| `pages/MLModels.tsx` | 56% | Train/predict flows |
| `pages/Portfolio.tsx` | 58% | CRUD handlers |
| `pages/Backtesting.tsx` | 68% | Metrics display, selection |
| `pages/Trading.tsx` | 70% | Mode switching, filters |
| `pages/PaperTrading.tsx` | 74% | Instance management |
| `pages/Workflows.tsx` | 77% | Enable/disable, detail expand |
| `pages/Dashboard.tsx` | 89% | Edge cases |
| `pages/RegimeDashboard.tsx` | 92% | Minor gaps |
| `pages/MarketAnalysis.tsx` | 94% | 2 lines |
| `pages/Screening.tsx` | 97% | 1 line |
| `App.tsx` | 100% lines | (stmts 43% due to lazy — lines OK) |

### Deliverable
- `docs/coverage-plans/phase-12-frontend-pages.md`

---

## Phase 13: Frontend Components (79% → 100% lines) — COMPLETE

**Completed**: 2026-03-10
**Result**: 1039 vitest tests, +48 new, 100% line coverage on all 24 component files

### Approach
- EmergencyStopButton: real timers + mouseDown/mouseUp to test hold-to-halt interval logic, mutation callbacks
- HoldingsTable: Edit mode inputs (onChange handlers), Save/Delete mutations (success + error), Add holding form submission
- OrderForm: portfolio/symbol/price input onChange, live order confirmation flow (confirmLiveOrder), mutation error handler
- PriceChart: Spy on createChart/addSeries to verify overlay indicators, MACD histogram, forex priceFormatter
- NewsFeed: 2-day-old article for "days ago" branch, Refresh button triggers newsApi.fetch
- Layout: useState force-update pattern with mockReturnValueOnce to simulate WebSocket order/alert changes between renders
- QueryResult: Inline error rendering, Retry button click
- EquityCurve: Trades without close_date (empty sort → early return), ResizeObserver callback trigger
- MarketStatusBadge: Saturday, Friday after 22:00 UTC, Sunday before/after 22:00 UTC forex session checks
- ExchangeHealthBadge: fetch rejection for isError path

### Deliverable
- `docs/coverage-plans/phase-13-frontend-components.md`
- Updated 10 test files with +48 new tests

---

## Phase 14: Frontend Hooks + API + Utils (80-91% → 100%)

### Files & Gaps

| File | Lines Coverage | Key Gaps |
|------|---------------|----------|
| `hooks/useSystemEvents.ts` | 50% | WS message dispatch (54-91) |
| `hooks/useWebSocket.ts` | 84% | Reconnection logic |
| `api/opportunities.ts` | 33% | Most functions untested |
| `api/data.ts` | 64% | Download/quality functions |
| `api/portfolios.ts` | 83% | 2 functions |
| `api/exchangeConfigs.ts` | 85% | 2 functions |
| `api/workflows.ts` | 85% | 2 functions |
| `api/scheduler.ts` | 86% | 1 function |
| `api/screening.ts` | 80% | 1 function |
| `api/trading.ts` | 100% lines | (stmts 85%) |
| `utils/formatters.ts` | 71% | Volume formatting |

### Deliverable
- `docs/coverage-plans/phase-14-frontend-remaining.md`

---

## Execution Rules

1. **Each phase gets its own detailed plan** in `docs/coverage-plans/phase-NN-<name>.md` before any code is written
2. **Each detailed plan lists every uncovered line** with the exact test case that will cover it
3. **No test is written without reading the source code first** — understand what the code does before testing it
4. **Tests must verify behavior, not just exercise code paths** — assertions on return values, side effects, error messages
5. **Run coverage after each phase** to verify 100% for that subsystem before moving to the next
6. **Update memory after each phase** with new test counts and coverage numbers
7. **Save all plans to docs/** — never rely on conversation context for plan persistence

## Verification

After all 14 phases:
- `python -m pytest backend/tests/ --cov=backend --cov=common --cov=research --cov=nautilus --cov=hftbacktest --cov-report=term-missing` → 100%
- `cd frontend && npx vitest run --coverage` → 100% lines on all files
- CI thresholds raised to 100/100/100/100

---

## Files Excluded from Coverage (pragma: no cover)

These Django boilerplate files may be excluded with `# pragma: no cover` if testing them adds no value:
- `backend/config/asgi.py` (8 lines — ASGI application setup)
- `backend/config/wsgi.py` (4 lines — WSGI application setup)
- `backend/manage.py` (11 lines — Django CLI entry point)
- `backend/market/routing.py` (3 lines — WebSocket URL config, tested indirectly)
- `backend/*/apps.py` (4 lines each — Django AppConfig boilerplate, 5 files)

**Decision**: Will be determined in Phase 11. If excluded, they will be explicitly marked with `# pragma: no cover` and documented.
