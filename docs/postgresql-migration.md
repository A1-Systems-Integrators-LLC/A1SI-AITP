# PostgreSQL Migration Guide

## Overview

A1SI-AITP uses SQLite by default (single-user desktop deployment). PostgreSQL is available as an optional backend for scaling to multi-user or multi-process deployments.

**SQLite remains the default.** PostgreSQL is opt-in via environment variables.

## Prerequisites

```bash
pip install 'a1si-aitp[postgres]'
# or
pip install 'psycopg[binary]>=3.1,<4'
```

## Configuration

Set these environment variables to switch to PostgreSQL:

```bash
USE_POSTGRES=true
POSTGRES_DB=a1si_aitp
POSTGRES_USER=a1si
POSTGRES_PASSWORD=<secure-password>
POSTGRES_HOST=localhost  # or 'postgres' in Docker
POSTGRES_PORT=5432
```

## Docker Deployment

Start with the postgres profile:

```bash
# Add POSTGRES_PASSWORD to .env first
echo "POSTGRES_PASSWORD=your-secure-password" >> .env

# Start with PostgreSQL
docker compose --profile postgres up -d

# Backend needs USE_POSTGRES=true in its environment
# Add to docker-compose.yml backend.environment:
#   USE_POSTGRES: "true"
#   POSTGRES_HOST: postgres
#   POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
```

## Data Migration

To migrate existing SQLite data to PostgreSQL:

1. Export from SQLite:
   ```bash
   python manage.py dumpdata --natural-foreign --natural-primary -o backup.json
   ```

2. Switch to PostgreSQL config (set env vars above)

3. Run migrations:
   ```bash
   python manage.py migrate
   ```

4. Import data:
   ```bash
   python manage.py loaddata backup.json
   ```

## Notes

- **WAL mode concerns do not apply** to PostgreSQL. The DELETE journal mode safeguards in `core/apps.py` only activate for SQLite.
- **Connection pooling**: PostgreSQL uses `CONN_MAX_AGE=600` (10 minutes) vs SQLite's `None` (indefinite). For high-traffic deployments, consider using `django-db-connection-pool` or PgBouncer.
- **Full-text search**: PostgreSQL enables Django's `SearchVector` / `SearchRank` for advanced text queries (not available in SQLite).
- **Concurrent writes**: PostgreSQL handles concurrent writes natively (no file locking needed).
