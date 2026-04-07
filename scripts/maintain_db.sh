#!/usr/bin/env bash
set -euo pipefail
# PostgreSQL maintenance: health check and VACUUM/ANALYZE
# Usage: bash scripts/maintain_db.sh
#        make maintain-db

echo "=== PostgreSQL Maintenance ==="
docker compose exec -T postgres psql -U "${POSTGRES_USER:-a1si}" -d "${POSTGRES_DB:-a1si_aitp}" -c "
SELECT version();
SELECT pg_database_size(current_database()) AS db_size_bytes;
VACUUM ANALYZE;
"
echo "=== Maintenance complete ==="
