#!/usr/bin/env bash
# start.sh — Full platform startup via Docker containers.
# Dev group (aitp-dev) runs on ports 4000-4099.
# Prod group (aitp-prod) runs on ports 4100-4199.
# Groups are fully isolated — no cross-references.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_DEV="docker compose"
COMPOSE_PROD="docker compose -f docker-compose.prod.yml"

echo "╔══════════════════════════════════════════════════════╗"
echo "║            A1SI-AITP PLATFORM START                  ║"
echo "║            (Container-Only Mode)                     ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Detect Doppler ──────────────────────────────────────────
DOPPLER_PREFIX=""
if command -v doppler >/dev/null 2>&1 && doppler configs get --plain --project aitp 2>/dev/null | grep -q dev; then
    DOPPLER_PREFIX="doppler run --"
    echo "→ Doppler detected — secrets will be injected"
else
    echo "→ Using .env file for secrets"
fi

# ── Start DEV group (aitp-dev) ─────────────────────────────
echo ""
echo "═══ DEV GROUP (aitp-dev, ports 4000-4099) ═══"
echo ""

echo "→ Starting core (backend + frontend)..."
$DOPPLER_PREFIX $COMPOSE_DEV up -d

echo "→ Waiting for dev backend health..."
for i in $(seq 1 40); do
    s=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{end}}' aitp-dev-backend 2>/dev/null || echo "")
    if [ "$s" = "healthy" ]; then echo "  ✓ Dev backend healthy"; break; fi
    if [ "$i" -eq 40 ]; then echo "  ⚠ Health check timeout"; fi
    sleep 3
done
$DOPPLER_PREFIX $COMPOSE_DEV start frontend 2>/dev/null || true

echo "→ Starting trading containers..."
$DOPPLER_PREFIX $COMPOSE_DEV --profile trading up -d

echo "→ Starting research containers..."
$DOPPLER_PREFIX $COMPOSE_DEV --profile research up -d

echo "→ Starting monitoring..."
$DOPPLER_PREFIX $COMPOSE_DEV --profile monitoring up -d

# ── Verify DEV ─────────────────────────────────────────────
echo ""
echo "→ Dev containers:"
docker ps --filter "name=aitp-dev-" --format "  {{.Names}}\t{{.Status}}" 2>/dev/null

# ── Summary ────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  aitp-dev (ports 4000-4099):"
echo "    Frontend:       http://localhost:4001"
echo "    Backend API:    http://localhost:4000/api/"
echo "    Freqtrade CIV1: http://localhost:4080"
echo "    Freqtrade BMR:  http://localhost:4083"
echo "    Freqtrade VB:   http://localhost:4084"
echo "    NautilusTrader: http://localhost:4090/health"
echo "    VectorBT:       http://localhost:4092/health"
echo "    Prometheus:     http://localhost:4010"
echo "    Grafana:        http://localhost:4011"
echo ""
echo "  Logs:   make docker-logs"
echo "  Status: make docker-status"
echo "════════════════════════════════════════════════════════"
