#!/bin/bash
set -e

echo "→ Checking database directory permissions..."
touch /project/backend/data/.write-test && rm /project/backend/data/.write-test || {
    echo "FATAL: Cannot write to /project/backend/data/" >&2; exit 1
}

echo "→ Running migrations..."
python manage.py migrate --run-syncdb

if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "→ Creating superuser from env (if needed)..."
    python manage.py createsuperuser --noinput \
        --username "${DJANGO_SUPERUSER_USERNAME:-admin}" \
        --email "${DJANGO_SUPERUSER_EMAIL:-admin@localhost}" 2>/dev/null || true
else
    echo "→ Skipping superuser creation (set DJANGO_SUPERUSER_PASSWORD to enable)"
fi

echo "→ Validating environment..."
python manage.py validate_env || true

echo "→ Collecting static files..."
python manage.py collectstatic --noinput --clear 2>/dev/null

echo "→ Running pre-flight checks..."
python manage.py pilot_preflight || echo "WARNING: Pre-flight returned NO-GO (check logs)"

echo "→ Checkpointing WAL (clean start)..."
python -c "
import sqlite3, os
db = os.path.join('/project/backend/data', 'a1si_aitp.db')
if os.path.exists(db):
    conn = sqlite3.connect(db)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()
    print('  WAL checkpoint OK')
" || echo "  WARNING: WAL checkpoint failed (non-fatal)"

echo "→ Starting Daphne..."
exec "$@"
