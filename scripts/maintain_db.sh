#!/usr/bin/env bash
set -euo pipefail
# SQLite maintenance: integrity check
# Usage: bash scripts/maintain_db.sh
#        make maintain-db

echo "=== SQLite Maintenance ==="
docker compose exec -T backend python manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
    c.execute('PRAGMA journal_mode')
    print('Journal mode:', c.fetchone())
    c.execute('PRAGMA integrity_check')
    result = c.fetchone()
    print('Integrity check:', result)
    if result[0] != 'ok':
        raise SystemExit('INTEGRITY CHECK FAILED')
"
echo "=== Maintenance complete ==="
