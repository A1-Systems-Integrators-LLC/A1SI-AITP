# Phase 4: backend/core/ (61% → 100%)

**Created**: 2026-03-09
**Risk**: HIGH — Scheduler manages all automated tasks, platform bridge connects subsystems, views serve the dashboard. Auth system protects all endpoints.

## Current Coverage

| File | Coverage | Uncovered Lines | Gap Category |
|------|----------|-----------------|--------------|
| `views.py` | 21% | 628 lines | Views, framework detail functions |
| `services/dashboard.py` | 0% | 260 lines | KPI aggregation |
| `schema.py` | 0% | 49 lines | OpenAPI tag preprocessor |
| `management/commands/validate_env.py` | 0% | 61 lines | Env validation command |
| `auth.py` | 37% | 100+ lines | Login/logout/lockout |
| `services/notification.py` | 34% | ~130 lines | Telegram/webhook delivery |
| `apps.py` | 43% | Lines 22-56, 61-69, 90 | App ready, scheduler start |
| `services/metrics.py` | 52% | Lines 31-33, 47-65, 70, 82-91 | Prometheus metrics |
| `platform_bridge.py` | 59% | Lines 19, 24-26, 31-33, 38, 56-67 | Config loading, paths |
| `encryption.py` | 63% | Lines 18, 34-39 | Decrypt error path |
| `exception_handler.py` | 65% | Lines 27-32, 41-42, 50-52 | Error normalization |
| `error_response.py` | 67% | Line 8 | Error response helper |
| `services/scheduler.py` | 77% | Lines 243-279, 295-298, etc. | Task execution, workflow |
| `management/commands/validate_deps.py` | 77% | Lines 59-61, 65-69 | Missing dep paths |
| `models.py` | 81% | Lines 33-41, 58, 77 | clean(), __str__ |
| `management/commands/pilot_status.py` | 84% | Lines 67-68, 96-109, etc. | Report formatting |
| `services/ws_broadcast.py` | 87% | Lines 51, 87, 103 | Broadcast calls |
| `middleware.py` | 90% | Lines 111-129, 143, 159-161 | Rate limit paths |
| `logging.py` | 91% | Lines 41, 50 | Exception info, time format |
| `services/task_registry.py` | 92% | Lines 135-139, 186-188, etc. | Edge case branches |
| `management/commands/pilot_preflight.py` | 94% | Lines 59-60, 77, 106, etc. | Error/edge cases |
| `utils.py` | 14% | Lines 6-11 | safe_int function |

**Total uncovered: ~837 lines → 0 lines**

## Test Strategy

One comprehensive test file: `backend/tests/test_core_phase4.py` covering:

### 1. Views (views.py) — ~180 tests
- `csrf_failure()`: JSON 403 response
- `MetricsTokenOrSessionAuth`: Bearer token, session auth, unauthenticated
- `AuditLogListView`: All filters (user, action, status_code, dates), pagination
- `HealthView`: Simple + detailed mode, all 7 checks (db, disk, memory, scheduler, breakers, channel, jobs, WAL)
- `DashboardKPIView`: With/without asset_class
- `PlatformStatusView`: Framework list, data files, active jobs
- `PlatformConfigView`: Config exists, missing, no yaml
- `NotificationPreferencesView`: GET + PUT
- `MetricsView`: All metric sections (orders, risk, jobs, breakers, scheduler)
- `SchedulerStatusView`, `ScheduledTaskListView`, `ScheduledTaskDetailView`: CRUD
- `ScheduledTaskPauseView`, `ScheduledTaskResumeView`, `ScheduledTaskTriggerView`: Actions
- `_get_freqtrade_details()`, `_get_vectorbt_details()`, `_get_nautilus_details()`, `_get_hft_details()`, `_get_ccxt_details()`, `_get_framework_status()`: All branches

### 2. Dashboard Service (services/dashboard.py) — ~25 tests
- `get_kpis()`: Full aggregation
- `_get_portfolio_kpis()`: With/without portfolio, with/without asset_class, exception
- `_get_trading_kpis()`: With/without portfolio, exception
- `_get_risk_kpis()`: With/without portfolio, exception
- `_get_paper_trading_kpis()`: Running/stopped instances, exception per instance, total exception
- `_get_platform_kpis()`: Happy path, exception

### 3. Auth (auth.py) — ~15 tests
- `_get_client_ip()`: Direct, X-Forwarded-For with trusted/untrusted proxy
- `_is_locked_out()`: Under limit, at limit, lockout expired
- `_record_failure()`: First failure, repeated failures, pruning
- `_clear_failures()`: Clear existing, clear non-existent
- `LoginView`: Success, invalid creds, lockout
- `LogoutView`: Success
- `AuthStatusView`: Authenticated, anonymous

### 4. Notification Service (services/notification.py) — ~15 tests
- `TelegramFormatter`: All 5 formatters
- `NotificationService.should_notify()`: Channel/event toggles
- `send_telegram()`: Success, failure, not configured
- `send_webhook()`: Success, failure, not configured
- `send_telegram_sync()`: Success, failure, not configured

### 5. Metrics (services/metrics.py) — ~10 tests
- `MetricsCollector`: gauge, counter_inc, histogram_observe, collect, _key
- `timed()`: Context manager timing

### 6. Platform Bridge (platform_bridge.py) — ~8 tests
- `ensure_platform_imports()`: Adds to sys.path
- `get_processed_dir()`, `get_research_results_dir()`, `get_freqtrade_dir()`: Path creation
- `get_platform_config()`: File exists, missing, empty, parse error

### 7. Encryption (encryption.py) — ~5 tests
- `_get_fernet()`: No key configured
- `encrypt_value()` + `decrypt_value()`: Roundtrip
- `decrypt_value()`: Invalid token

### 8. Exception Handler (exception_handler.py) — ~6 tests
- DRF-handled exception normalization
- Unhandled exception (500)
- Field validation errors
- Already-normalized errors

### 9. Middleware (middleware.py) — ~10 tests
- `RateLimitMiddleware`: Login bucket, general bucket, rate exceeded, XFF handling
- `AuditMiddleware`: POST creates log, GET skipped

### 10. Other Files — ~20 tests
- `schema.py`: auto_tag_endpoints() with matching/non-matching paths
- `validate_env.py`: All required present, missing required, missing recommended
- `validate_deps.py`: Missing dep, strict mode exit
- `models.py`: clean() validation, __str__ methods
- `apps.py`: _maybe_start_order_sync(), _start_scheduler()
- `logging.py`: JSONFormatter with exception, formatTime
- `utils.py`: safe_int() all branches
- `error_response.py`: Helper function
- `ws_broadcast.py`: All broadcast functions

## Estimated New Tests: ~300

## Deliverable
- `backend/tests/test_core_phase4.py` — comprehensive test file
- 100% coverage on all backend/core/ files
