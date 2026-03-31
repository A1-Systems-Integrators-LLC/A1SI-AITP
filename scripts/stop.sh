#!/usr/bin/env bash
# stop.sh — Graceful shutdown of all A1SI-AITP Docker containers.
# Stops both aitp-dev and aitp-prod groups.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_DEV="docker compose"
COMPOSE_PROD="docker compose -f docker-compose.prod.yml"

echo "Stopping A1SI-AITP platform (all container groups)..."

# Detect Doppler
DOPPLER_PREFIX=""
if command -v doppler >/dev/null 2>&1 && doppler configs get --plain --project aitp 2>/dev/null | grep -q dev; then
    DOPPLER_PREFIX="doppler run --"
fi

# Stop dev group
echo ""
echo "→ Stopping aitp-dev group..."
$DOPPLER_PREFIX $COMPOSE_DEV \
    --profile trading \
    --profile postgres \
    down 2>/dev/null || true

# Stop prod group
echo ""
echo "→ Stopping aitp-prod group..."
$DOPPLER_PREFIX $COMPOSE_PROD \
    --profile trading \
    --profile postgres \
    down 2>/dev/null || true

echo ""
echo "Verifying no AITP containers remain..."
remaining=$(docker ps --filter "name=aitp-" --format "{{.Names}}" 2>/dev/null)
if [ -n "$remaining" ]; then
    echo "  Stopping remaining containers:"
    echo "$remaining" | while read -r name; do
        echo "    $name"
        docker stop "$name" 2>/dev/null || true
    done
else
    echo "  ✓ All AITP containers stopped"
fi

echo ""
echo "All services stopped."
