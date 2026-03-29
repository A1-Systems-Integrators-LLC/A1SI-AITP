# Troubleshooting Guide

## Common Error Codes

| HTTP Code | Meaning | Typical Cause |
|-----------|---------|---------------|
| 401 | Unauthorized | Session expired; re-login |
| 403 | Forbidden | CSRF token missing or invalid |
| 408 | Request Timeout | Exchange API call timed out |
| 409 | Conflict | Duplicate holding (symbol+portfolio) |
| 429 | Too Many Requests | Rate limit exceeded (nginx or Django) |
| 503 | Service Unavailable | Exchange unreachable or circuit breaker open |

## SQLite Issues

### "database table is locked" (SQLITE_LOCKED, error 6)

This is an intra-connection conflict during savepoints/FK checks, not inter-connection.

**Cause**: Concurrent operations within Django test transactions, or FK constraint checks conflicting with savepoints.

**Fix**: The `pytest-rerunfailures` plugin retries these automatically (configured in `pyproject.toml`). In production, SQLite DELETE journal mode + 30s timeout handles most cases.

### "database is locked" (SQLITE_BUSY, error 5)

Inter-connection conflict — another process holds a write lock.

**Cause**: Long-running write transaction blocking others.

**Fix**:
1. Check for stuck processes: `docker compose exec backend python manage.py shell -c "from django.db import connection; c=connection.cursor(); c.execute('PRAGMA busy_timeout'); print(c.fetchone())"`
2. Run integrity check: `make maintain-db`
3. If persistent, restart the backend container

### WAL Mode Warning

> **NEVER enable SQLite WAL mode.** WAL mode is incompatible with Docker virtiofs bind mounts — the SHM file uses mmap which virtiofs cannot handle, causing stale file descriptors, "disk I/O error", and database corruption. The platform uses DELETE journal mode exclusively.

## Exchange Connectivity

### Circuit Breaker Open

The exchange service uses a circuit breaker that opens after 3 consecutive failures.

**Check**: `GET /api/health/?detailed=true` — look at `circuit_breaker` section.

**Fix**: Wait for the 10-second fail timeout to expire. The circuit breaker resets automatically.

### Exchange Timeout (408)

**Cause**: Network latency or exchange API degradation.

**Fix**:
1. Check exchange status page
2. Monitor with: `GET /api/trading/exchange-health/` (shows latency in ms)
3. If persistent, check Docker DNS resolution: `docker compose exec backend python -c "import socket; print(socket.getaddrinfo('api.binance.com', 443))"`

### Exchange Unavailable (503)

**Cause**: Exchange is down, maintenance, or geo-blocked (Binance in some CI environments).

**Fix**: Wait for exchange to recover. Check `/api/trading/exchange-health/` for status.

## Docker Issues

### Container Won't Start

```bash
# Check logs
docker compose logs backend --tail=100
docker compose logs frontend --tail=100

# Rebuild images
make docker-build-clean

# Reset everything (WARNING: destroys volumes)
make docker-clean
```

### Health Check Failing

```bash
# Check detailed health
curl -sf http://localhost:4000/api/health/?detailed=true | python3 -m json.tool

# Common issues:
# - database: SQLite file permissions
# - disk: Low disk space
# - memory: Backend using too much RAM
# - scheduler: Scheduler not started
```

### Out of Memory

Backend is limited to 8GB, frontend to 512MB.

```bash
# Check current memory usage
docker stats --no-stream
```

If backend OOM: check for large data downloads or backtests. Consider reducing `MAX_JOB_WORKERS`.

### PID Limit Reached

Backend: 512 PIDs, Frontend: 256 PIDs.

**Symptom**: "cannot allocate memory" or "resource temporarily unavailable"

**Fix**: Check for runaway processes:
```bash
docker compose exec backend ps aux | wc -l
```

## Frontend Issues

### Blank Page After Deploy

1. Check nginx logs: `docker compose logs frontend --tail=50`
2. Verify build succeeded: `docker compose exec frontend ls /usr/share/nginx/html/index.html`
3. Clear browser cache (Vite uses content-hashed filenames)

### WebSocket Connection Failing

1. Check backend is running on port 8000
2. Verify nginx WebSocket proxy: `/ws/` location in nginx.conf
3. Check browser console for connection errors
4. ConnectionLimiterMixin allows max 5 connections per user (close code 4029 = limit reached)

### Rate Limiting (429)

**Nginx rate limits**: 10 req/s for API, 2 req/s for login.

Burst settings allow:
- API: burst of 20 requests
- Login: burst of 5 requests

**Django rate limits**: 120 req/min general, 20 req/min login.
