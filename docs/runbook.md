# Operations Runbook

## Start / Stop / Restart

```bash
# Start all containers (detached)
make docker-up

# Stop all containers
make docker-down

# Restart (stop + start)
make docker-restart

# Full deploy: build images + restart
make docker-deploy

# Full clean deploy: rebuild without cache + restart
make docker-deploy-clean
```

## Check Status

```bash
# Container status + health
make docker-status

# Health check (exit 0 = healthy, exit 1 = degraded)
make health-check

# View logs (follow)
make docker-logs
make docker-logs-backend
make docker-logs-frontend
```

## Database Operations

### Backup

```bash
make backup
```

Creates an encrypted, compressed backup in `backend/data/backups/`. Keeps 7 daily copies.

Requires `BACKUP_ENCRYPTION_KEY` in `.env`.

### Restore

```bash
make restore
```

Prompts for the backup file to restore. Performs decrypt, decompress, integrity check, and safety backup of current DB before overwriting.

### Maintenance

```bash
make maintain-db
```

Runs SQLite journal mode verification + integrity check inside the backend container.

### Data Cleanup

```bash
make clean-data        # Clean records older than 30 days
make clean-data 60     # Custom: 60 days
```

Removes old completed/failed background jobs, audit logs, and news articles.

## Exchange Configuration

1. Log into Django admin: `http://localhost:4000/admin/`
2. Navigate to Market > Exchange Configs
3. Add a new config with exchange ID, API key, and secret
4. Keys are encrypted at rest using `DJANGO_ENCRYPTION_KEY`
5. Test connectivity: `GET /api/trading/exchange-health/`

### Key Rotation

```bash
# Via API (tests new key before applying)
POST /api/exchange-configs/<pk>/rotate/
Content-Type: application/json
{"api_key": "new-key", "api_secret": "new-secret"}
```

## Common Admin Operations

### Create Superuser

```bash
make createsuperuser
```

### Run Migrations

```bash
make migrate
```

### Generate API Schema

```bash
make generate-types
```

### Security Hardening

```bash
make harden   # Set file permissions (600 .env, 700 data dirs)
make audit     # pip-audit + npm audit
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | Yes (prod) | Django secret key |
| `DJANGO_ENCRYPTION_KEY` | Yes (prod) | Key for encrypting exchange API secrets |
| `DJANGO_DEBUG` | No | `true` for dev mode (default: `false`) |
| `EXCHANGE_ID` | No | Default exchange (default: `binance`) |
| `BACKUP_ENCRYPTION_KEY` | Recommended | GPG key for backup encryption |
| `NEWSAPI_KEY` | No | NewsAPI.org key for news fetching |
| `TELEGRAM_BOT_TOKEN` | No | Telegram notifications |
| `TELEGRAM_CHAT_ID` | No | Telegram chat for alerts |
| `ORDER_SYNC_TIMEOUT_HOURS` | No | Hours before SUBMITTED orders are timed out (default: 24) |
