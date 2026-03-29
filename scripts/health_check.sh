#!/usr/bin/env bash
set -euo pipefail
# Health check: returns exit 0 if healthy, exit 1 if degraded/unhealthy
# Usage: bash scripts/health_check.sh
#        make health-check

RESP=$(curl -sf http://localhost:4001/api/health/?detailed=true) || {
    echo "UNREACHABLE: could not connect to health endpoint" >&2
    exit 1
}

STATUS=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")

if [ "$STATUS" = "ok" ]; then
    echo "HEALTHY"
    exit 0
else
    echo "DEGRADED: $RESP" >&2
    exit 1
fi
