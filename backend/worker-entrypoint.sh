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

echo "→ Starting scheduler worker..."
exec python manage.py run_scheduler
