# Monitoring Guide

## Health Check Endpoint

```
GET /api/health/?detailed=true
```

Returns JSON with component status:

```json
{
  "status": "ok",
  "database": "ok",
  "disk": {"status": "ok", "free_gb": 120.5},
  "memory": {"status": "ok", "used_pct": 45.2},
  "scheduler": {"status": "running", "job_count": 9},
  "circuit_breaker": {"binance": "closed"},
  "channel_layer": "ok",
  "job_queue_staleness": 0
}
```

**Automated check**: `make health-check` (returns exit 0/1).

## Prometheus Metrics

```
GET /metrics/
```

Requires authentication (session or `METRICS_AUTH_TOKEN`). Restricted to localhost and Docker networks in nginx.

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `job_queue_pending` | Gauge | Pending background jobs |
| `job_queue_running` | Gauge | Running background jobs |
| `circuit_breaker_state` | Gauge | Per-exchange: 0=closed, 1=open |
| `scheduler_running` | Gauge | 1 if scheduler is active |
| `scheduler_job_count` | Gauge | Total scheduled tasks |
| `orders_created_total` | Counter | Total orders created |
| `dashboard_kpi_duration_seconds` | Histogram | KPI calculation time |
| `risk_check_duration_seconds` | Histogram | Risk check time |
| `workflow_execution_duration_seconds` | Histogram | Workflow execution time |

## Alert Thresholds

| Condition | Severity | Action |
|-----------|----------|--------|
| Health check returns non-"ok" | Warning | Investigate degraded component |
| `circuit_breaker_state` = 1 | Warning | Exchange connectivity issue |
| `job_queue_pending` > 10 | Warning | Job queue backing up |
| Drawdown >= 80% of limit | Warning | Auto-notification sent |
| Drawdown >= limit | Critical | Auto-halt triggered |
| Daily loss >= limit | Critical | Auto-halt triggered |

## Log Locations

### Backend Logs

- **Console**: `docker compose logs backend`
- **App log**: `backend/data/logs/app.log` (10MB rotating, 10 backups)
- **Security log**: `backend/data/logs/security.log` (auth events, 10MB rotating)

Log format is JSON in production, text in debug mode.

### Nginx Logs

- **Access log**: nginx-logs volume (`/var/log/nginx/access.log`)
- Format: JSON with request ID, upstream response time, status

### Viewing Logs

```bash
# All service logs
make docker-logs

# Backend only
make docker-logs-backend

# Frontend/nginx only
make docker-logs-frontend
```

## Scheduled Tasks

View and manage via API or UI (`/scheduler` page):

```
GET /api/scheduler/status/    # Scheduler running state
GET /api/scheduler/tasks/     # All task states + run counts
POST /api/scheduler/tasks/{id}/trigger/  # Manual trigger
POST /api/scheduler/tasks/{id}/pause/
POST /api/scheduler/tasks/{id}/resume/
```

### Default Schedule

| Task | Interval | Description |
|------|----------|-------------|
| data_refresh_crypto | 30m | Refresh crypto OHLCV |
| data_refresh_equity | 24h | Refresh equity OHLCV |
| data_refresh_forex | 1h | Refresh forex OHLCV |
| regime_detection | 30m | Detect market regimes |
| order_sync | 5m | Sync live orders with exchange |
| data_quality_check | 1h | Validate data files |
| news_fetch | 30m | Fetch news articles |
| risk_monitoring | 5m | Periodic risk check |
| db_maintenance | 24h | SQLite integrity check |

## Audit Trail

```
GET /api/audit-log/?action=POST&status_code=201&date_from=2026-02-01
```

Records all API requests with user, action, path, status code, and IP address.

## Risk Monitoring

The risk monitoring task runs every 5 minutes and:

1. Records metrics (VaR, CVaR, drawdown, equity)
2. Checks drawdown against limits
3. Checks daily loss against limits
4. Sends warning at 80% of limits
5. Auto-halts trading if limits are breached

View risk status: `GET /api/risk/{portfolio_id}/status/`

View risk metrics history: `GET /api/risk/{portfolio_id}/metrics/`
