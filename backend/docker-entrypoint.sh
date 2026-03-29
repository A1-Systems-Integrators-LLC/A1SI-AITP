#!/bin/bash
set -e

echo "→ Waiting for PostgreSQL..."
python -c "
import time, os, socket
host = os.environ.get('POSTGRES_HOST', 'postgres')
port = int(os.environ.get('POSTGRES_PORT', '5432'))
for i in range(30):
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        print(f'  PostgreSQL at {host}:{port} is ready')
        break
    except OSError:
        if i < 29:
            time.sleep(2)
        else:
            raise SystemExit(f'FATAL: PostgreSQL at {host}:{port} not reachable after 60s')
"

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

echo "→ Starting Daphne..."
exec "$@"
