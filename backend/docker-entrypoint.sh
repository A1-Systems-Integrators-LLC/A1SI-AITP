#!/bin/bash
set -e

echo "→ Checking database directory permissions..."
touch /project/backend/data/.write-test && rm /project/backend/data/.write-test || {
    echo "FATAL: Cannot write to /project/backend/data/" >&2; exit 1
}

# Remove any stale WAL/SHM files from previous WAL-mode runs.
# We now use DELETE journal mode which doesn't create these files.
rm -f /project/backend/data/a1si_aitp.db-wal /project/backend/data/a1si_aitp.db-shm 2>/dev/null || true

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

echo "→ Closing startup DB connections..."
python manage.py shell -c "
from django.db import connections
for conn in connections.all():
    conn.close()
print('  Startup connections closed')
" || true

echo "→ Starting Daphne..."
exec "$@"
