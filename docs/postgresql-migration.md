# PostgreSQL Database

## Overview

A1SI-AITP uses PostgreSQL 16 as its sole database backend. PostgreSQL runs in a Docker volume, handles concurrent writes from Daphne/scheduler/job runner, and survives container restarts.

> **CRITICAL:** SQLite was removed from this project in March 2026 after repeated database corruption caused by Docker virtiofs bind mount incompatibility. **Never revert to SQLite.**

## Configuration

PostgreSQL is configured via environment variables (managed by Doppler):

```bash
POSTGRES_DB=a1si_aitp
POSTGRES_USER=a1si
POSTGRES_PASSWORD=<secure-password>
POSTGRES_HOST=postgres    # Docker service name
POSTGRES_PORT=5432
```

## Docker Deployment

The `postgres` service is a default (non-profile) dependency of `backend` in both compose files:

```bash
# Dev
doppler run -- docker compose up -d

# Prod
doppler run -c prod -- docker compose -f docker-compose.prod.yml up -d
```

## Connection Settings

- `CONN_MAX_AGE=600` — 10-minute persistent connections
- `CONN_HEALTH_CHECKS=True` — verify connections before use
- `connect_timeout=10` — fail fast on unreachable host

For high-traffic deployments, consider PgBouncer for connection pooling.

## Backup & Recovery

Daily automated backups run at 2 AM Eastern via the `db_backup_daily` scheduled task. Manual backup:

```bash
# Inside the backend container
pg_dump -U a1si a1si_aitp | gzip > backup_$(date +%Y%m%d).sql.gz
```

## Notes

- **Full-text search**: PostgreSQL enables Django's `SearchVector` / `SearchRank` for advanced text queries.
- **Concurrent writes**: PostgreSQL handles concurrent writes natively via MVCC — no file locking concerns.
- **Data lives in Docker volume** — not a bind mount. This avoids the virtiofs I/O issues that corrupted the previous SQLite database.
