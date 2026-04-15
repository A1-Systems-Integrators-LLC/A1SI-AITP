# Daily Plan: 2026-04-15 — Backend Stability Fix (Worker Separation)

**Owner:** Claude Agent Team
**Status:** COMPLETED
**Objective:** Permanently fix daily backend instability (504s, ERR_CONNECTION_RESET)

## Root Cause Analysis

**Why the backend fails daily:**

The backend ran Daphne (HTTP/WebSocket server) AND APScheduler (38 background tasks) in the **same Python process**. Python's GIL means all threads compete for CPU time.

- **58 task executions per hour** across 38 scheduled tasks
- Every 30 minutes, **11 tasks fire simultaneously** (data pipeline, ML, regime detection, market scans)
- Data pipeline loads 428 parquet files (5,000-6,000 rows each) — CPU-bound
- When tasks saturate the GIL, Daphne cannot accept TCP connections
- Result: health checks timeout (2,500 consecutive failures), all HTTP requests fail with ERR_CONNECTION_RESET
- Yesterday's fix (20→6 threads) was insufficient — the tasks themselves hold the GIL, not the thread count

## Solution: Process Separation

Moved the scheduler into a dedicated `worker` container. Same Docker image, different entrypoint.

| Component | Before | After |
|-----------|--------|-------|
| Backend (Daphne) | HTTP + WebSocket + Scheduler + 38 tasks | HTTP + WebSocket only |
| Worker | N/A | Scheduler + 38 tasks (new container) |
| Scheduler threads | 6 (shared GIL) | 10 (own process, no competition) |

## Changes Made

### 1. New worker container
- **File:** `docker-compose.prod.yml` — added `worker` service using `backend-base` with `worker-entrypoint.sh`
- **File:** `backend/worker-entrypoint.sh` — waits for PostgreSQL, runs `manage.py run_scheduler`
- **File:** `backend/core/management/commands/run_scheduler.py` — standalone scheduler process with signal handling

### 2. Backend scheduler disabled
- **File:** `docker-compose.prod.yml` — set `SCHEDULER_ENABLED=false` on backend service
- Reads from `SCHEDULER_ENABLED` env var (already in `config/settings.py:346`)

### 3. Scheduler health monitoring
- Heartbeat file `/tmp/scheduler_alive` touched every 15s by scheduler
- Docker health check validates the file exists

### 4. Dockerfile updated
- **File:** `backend/Dockerfile` — added `COPY backend/worker-entrypoint.sh`

## Verification

- Backend: 0 TaskScheduler instances, HTTP 200 in 63ms
- Worker: 1 TaskScheduler instance, 38 tasks scheduled, heartbeat active
- All 11 containers healthy (backend, worker, frontend, 7 Freqtrade, postgres)

## Morning Review: Trading Performance

| Strategy | Open | Closed | W/L | P&L (USDT) | vs Yesterday |
|----------|------|--------|-----|------------|-------------|
| CIV1 | 0 | 3 | 0/3 | -4.20 | +3 trades (was 0) |
| BMR | 0 | 1 | 0/1 | -0.35 | +1 trade (was 0) |
| VB | 1 | 4 | 1/3 | -4.81 | +3 closed |
| Grid | 1 | 6 | 0/6 | -1.64 | +5 trades |
| Scalp | 3 | 1 | 1/0 | -1.85 | +2 open |
| **Sentiment** | **0** | **0** | - | **0.00** | **no trades** |
| Reversal | 1 | 0 | 0/0 | +0.23 | +1 open |

**Key findings:**
- 6 of 7 strategies now generating trades (up from 3 yesterday)
- Sentiment is the only zero-trade strategy — it scans pairs but never generates entry signals
- Sentiment strategy likely requires external sentiment data that isn't reaching it
- Total closed trades: 15 (up from 7 yesterday)
- Win rate across all: 3/13 (23%) — learning phase, expected to be low

## Decisions Log

| Date | Decision | Made By |
|------|----------|---------|
| 2026-04-15 | Separate scheduler into dedicated worker container | Agent (approved pattern) |
| 2026-04-15 | Investigate Sentiment strategy signal generation next | Agent |

## Next Steps (2026-04-16)

1. Verify backend stays healthy for 24h (no ERR_CONNECTION_RESET)
2. Investigate SentimentEventTrader: why no entry signals despite 7 pairs in whitelist
3. Begin Phase 1.3: prepare live trading switch (Kraken API key verification)
