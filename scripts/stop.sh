#!/usr/bin/env bash
# stop.sh — Graceful shutdown of all A1SI-AITP platform services.
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Stopping A1SI-AITP platform..."

# Stop Freqtrade instances
if pgrep -f "freqtrade trade" > /dev/null 2>&1; then
    echo "  Stopping Freqtrade instances..."
    pkill -f "freqtrade trade" 2>/dev/null || true
    # Wait up to 15s for graceful shutdown
    for i in $(seq 1 15); do
        pgrep -f "freqtrade trade" > /dev/null 2>&1 || break
        sleep 1
    done
    # Force kill if still running
    pkill -9 -f "freqtrade trade" 2>/dev/null || true
    echo "  Freqtrade stopped"
else
    echo "  Freqtrade: not running"
fi

# Stop frontend (Vite)
if pgrep -f "node.*vite" > /dev/null 2>&1; then
    pkill -f "node.*vite" 2>/dev/null || true
    echo "  Frontend stopped"
else
    echo "  Frontend: not running"
fi

# Stop backend (Daphne)
if pgrep -f "daphne.*config.asgi" > /dev/null 2>&1; then
    pkill -f "daphne.*config.asgi" 2>/dev/null || true
    echo "  Backend stopped"
else
    echo "  Backend: not running"
fi

# Stop Docker containers if running
if docker compose ps -q 2>/dev/null | grep -q .; then
    echo "  Stopping Docker containers..."
    cd "$ROOT_DIR" && docker compose down
    echo "  Docker containers stopped"
fi

echo "All services stopped."
