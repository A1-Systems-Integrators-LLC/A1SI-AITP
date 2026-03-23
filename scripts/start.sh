#!/usr/bin/env bash
# start.sh — Full platform startup: backend + frontend + Freqtrade instances
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV="$BACKEND_DIR/.venv"
FT_DIR="$ROOT_DIR/freqtrade"
FT_STRATEGY_PATH="$FT_DIR/user_data/strategies"
PYTHON="$VENV/bin/python"

# ── Configurable: which Freqtrade instances to start ──────────
# Set FREQTRADE_INSTANCES env var to override (comma-separated)
# Default: the 3 pilot strategies
DEFAULT_FT_INSTANCES="CryptoInvestorV1,BollingerMeanReversion,VolatilityBreakout"
FT_INSTANCES="${FREQTRADE_INSTANCES:-$DEFAULT_FT_INSTANCES}"

# Strategy → config file mapping
declare -A FT_CONFIGS=(
    [CryptoInvestorV1]="config.json"
    [BollingerMeanReversion]="config_bmr.json"
    [VolatilityBreakout]="config_vb.json"
)

declare -A FT_PORTS=(
    [CryptoInvestorV1]=8080
    [BollingerMeanReversion]=8083
    [VolatilityBreakout]=8084
)

# ── Pre-flight checks ────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════╗"
echo "║            A1SI-AITP PLATFORM START                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Clear Python bytecode caches to prevent stale .pyc issues after code updates
echo "→ Clearing Python bytecode caches..."
find "$ROOT_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Check core ports
for port in 8000 5173; do
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo "ERROR: Port $port is already in use."
        echo "  Check with: ss -tlnp | grep $port"
        exit 1
    fi
done

# Check Freqtrade ports
IFS=',' read -ra FT_LIST <<< "$FT_INSTANCES"
for strategy in "${FT_LIST[@]}"; do
    port="${FT_PORTS[$strategy]}"
    if [ -n "$port" ] && ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo "WARNING: Port $port ($strategy) already in use — skipping"
    fi
done

# Collect PIDs for cleanup
PIDS=()

cleanup() {
    echo ""
    echo "Shutting down all services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    # Wait for graceful shutdown
    for pid in "${PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    echo "All services stopped."
}
trap cleanup EXIT INT TERM

# ── 1. Start Backend (Daphne) ────────────────────────────────
echo "→ Starting backend (Daphne) on :8000..."
cd "$BACKEND_DIR" && DJANGO_DEBUG=true "$PYTHON" -m daphne -b 0.0.0.0 -p 8000 config.asgi:application &
PIDS+=($!)
BACKEND_PID=$!

# ── 2. Start Frontend (Vite) ─────────────────────────────────
echo "→ Starting frontend (Vite) on :5173..."
cd "$FRONTEND_DIR" && npm run dev &
PIDS+=($!)

# Wait for backend to be ready
echo "→ Waiting for backend..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health/ > /dev/null 2>&1; then
        echo "  Backend ready."
        break
    fi
    sleep 1
done

# ── 3. Start Freqtrade Instances ─────────────────────────────
echo ""
echo "→ Starting Freqtrade instances: $FT_INSTANCES"
for strategy in "${FT_LIST[@]}"; do
    strategy=$(echo "$strategy" | xargs)  # trim whitespace
    config="${FT_CONFIGS[$strategy]}"
    port="${FT_PORTS[$strategy]}"

    if [ -z "$config" ]; then
        echo "  WARNING: Unknown strategy '$strategy' — skipping"
        continue
    fi

    config_path="$FT_DIR/$config"
    if [ ! -f "$config_path" ]; then
        echo "  WARNING: Config $config not found — skipping $strategy"
        continue
    fi

    # Skip if port already in use
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo "  ✓ $strategy (:$port) — already running"
        continue
    fi

    echo "  Starting $strategy (:$port)..."
    cd "$ROOT_DIR" && "$PYTHON" -m freqtrade trade \
        --config "$config_path" \
        --strategy "$strategy" \
        --strategy-path "$FT_STRATEGY_PATH" \
        > "/tmp/freqtrade-${strategy}.log" 2>&1 &
    PIDS+=($!)

    # Brief pause to avoid startup race conditions
    sleep 2
done

# ── 4. Verify Freqtrade instances ────────────────────────────
echo ""
echo "→ Verifying Freqtrade instances..."
sleep 5
for strategy in "${FT_LIST[@]}"; do
    strategy=$(echo "$strategy" | xargs)
    port="${FT_PORTS[$strategy]}"
    if curl -sf "http://localhost:${port}/api/v1/ping" --user freqtrader:freqtrader > /dev/null 2>&1; then
        echo "  ✓ $strategy (:$port) — running"
    else
        echo "  ✗ $strategy (:$port) — not responding (check /tmp/freqtrade-${strategy}.log)"
    fi
done

# ── 5. Summary ───────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Platform running:"
echo "    Backend:   http://localhost:8000"
echo "    Frontend:  http://localhost:5173"
echo "    Admin:     http://localhost:8000/admin/"
echo ""
echo "  Freqtrade instances:"
for strategy in "${FT_LIST[@]}"; do
    strategy=$(echo "$strategy" | xargs)
    port="${FT_PORTS[$strategy]}"
    echo "    $strategy: http://localhost:${port}"
done
echo ""
echo "  Logs: /tmp/freqtrade-<strategy>.log"
echo "  Press Ctrl+C to stop all services."
echo "════════════════════════════════════════════════════════"

wait
