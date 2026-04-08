---
name: Backend deadlock fix (April 2026)
description: Root cause analysis and fix for Daphne/APScheduler thread pool starvation that caused prod backend to deadlock for 18+ hours
type: project
---

On 2026-04-08, the prod backend (aitp-prod-backend) was found deadlocked — 2,202 consecutive health check timeouts, 110 zombie curl processes, Daphne completely unresponsive.

**Root cause:** Thread pool starvation in a single-process Daphne server.
- APScheduler ran with default 10-thread pool, but 38+ tasks were scheduled including multi-hour ML training (7200s), backtests (7200s), and VBT screens (7200s).
- JobRunner had only 2 worker threads (MAX_JOB_WORKERS=2).
- Health endpoint was sync with DB queries, blocking on the starved event loop.
- Daphne ran as single process with no HTTP timeout.

**Fixes applied:**
1. Health endpoint refactored: basic check (`/api/health/`) is pure in-memory (no DB, no thread pool). Detailed check runs sub-checks concurrently with 5s per-check timeouts via asyncio.
2. APScheduler executor explicitly set to 20 threads (was default 10).
3. MAX_JOB_WORKERS raised from 2 to 4.
4. Critical executor minimum raised to 4 threads (was `max(2, max_workers)`).
5. Daphne given `-t 30` HTTP timeout and `--proxy-headers`.

**Why:** Daphne is single-process (no `--workers` flag). Multi-process ASGI servers like uvicorn `--workers` would cause duplicate schedulers. The scheduler must run in exactly one process.

**How to apply:** If adding more scheduled tasks, verify the APScheduler pool (20 threads) and JobRunner pool (4 batch + 4 critical) can handle the load. Monitor for health check timeouts as an early warning sign. The basic health check should NEVER be made to depend on DB or thread pools.

**Files changed:**
- backend/core/views.py (HealthView — async sub-checks with timeouts)
- backend/core/services/scheduler.py (APScheduler executor: 20 threads)
- backend/config/settings.py (MAX_JOB_WORKERS: 2 -> 4)
- backend/analysis/services/job_runner.py (critical executor min: 4)
- backend/Dockerfile (Daphne -t 30 --proxy-headers)
