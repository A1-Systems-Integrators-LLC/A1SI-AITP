#!/usr/bin/env bash
# start.sh — Boot the LIVE PROD platform via Docker containers.
#
# Invoked by the @reboot cron entry (see scripts/setup_cron.sh). The prod group
# (aitp-prod, ports 4100-4199) is the live trading stack — that's what must come
# back after a host/WSL/Docker Desktop restart. Dev is started manually when
# developing; it is intentionally NOT auto-started here.
#
# `restart: unless-stopped` on every prod service means Docker Desktop alone will
# resume containers once it starts — this script is the belt-and-suspenders that
# also covers the case where the stack was `down`ed or containers were removed.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_PROD="docker compose -f docker-compose.prod.yml"

echo "╔══════════════════════════════════════════════════════╗"
echo "║         A1SI-AITP PROD START (container mode)        ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── Wait for the Docker daemon (Docker Desktop may still be coming up) ──────
echo "→ Waiting for Docker daemon..."
for i in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then
        echo "  ✓ Docker daemon ready"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "  ✗ Docker daemon not ready after 5min — aborting (will retry next @reboot/watchdog)"
        exit 1
    fi
    sleep 5
done

# ── Detect Doppler ──────────────────────────────────────────
DOPPLER_PREFIX=""
if command -v doppler >/dev/null 2>&1 && doppler configs get --plain --project aitp 2>/dev/null | grep -q dev; then
    DOPPLER_PREFIX="doppler run --"
    echo "→ Doppler detected — secrets will be injected"
else
    echo "→ Using .env file for secrets"
fi

# ── Start PROD group (aitp-prod) with the trading profile ──────────────────
echo "→ Starting prod stack (--profile trading)..."
$DOPPLER_PREFIX $COMPOSE_PROD --profile trading up -d

echo "→ Waiting for prod backend health..."
for i in $(seq 1 40); do
    s=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{end}}' aitp-prod-backend 2>/dev/null || echo "")
    if [ "$s" = "healthy" ]; then echo "  ✓ Prod backend healthy"; break; fi
    if [ "$i" -eq 40 ]; then echo "  ⚠ Health check timeout"; fi
    sleep 3
done

# ── Summary ────────────────────────────────────────────────
echo ""
echo "→ Prod containers:"
docker ps --filter "name=aitp-prod-" --format "  {{.Names}}\t{{.Status}}" 2>/dev/null
echo ""
echo "════════════════════════════════════════════════════════"
echo "  aitp-prod (ports 4100-4199):"
echo "    Frontend:        http://localhost:4101"
echo "    Backend API:     http://localhost:4100/api/"
echo "    Freqtrade scalp: http://localhost:4187"
echo "    Freqtrade sent:  http://localhost:4188"
echo "    Freqtrade rev:   http://localhost:4189"
echo ""
echo "  Logs:   make docker-prod-logs"
echo "  Status: make docker-status"
echo "════════════════════════════════════════════════════════"
