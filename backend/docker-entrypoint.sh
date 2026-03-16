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

echo "→ Verifying SQLite journal mode..."
python manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
    c.execute('PRAGMA journal_mode')
    mode = c.fetchone()[0]
    if mode == 'wal':
        raise SystemExit('FATAL: SQLite is in WAL mode. WAL is incompatible with Docker virtiofs. Set PRAGMA journal_mode=DELETE in core/apps.py.')
    print(f'  Journal mode: {mode} (ok)')
    # Verify no WAL/SHM files exist
import os
for ext in ('-wal', '-shm'):
    path = '/project/backend/data/a1si_aitp.db' + ext
    if os.path.exists(path):
        raise SystemExit(f'FATAL: Stale {ext} file found at {path}. Delete it and ensure WAL mode is not enabled.')
print('  No WAL/SHM files (ok)')
" || { echo "FATAL: Journal mode check failed" >&2; exit 1; }

echo "→ Closing startup DB connections..."
python manage.py shell -c "
from django.db import connections
for conn in connections.all():
    conn.close()
print('  Startup connections closed')
" || true

echo "→ Starting Daphne..."
exec "$@"
