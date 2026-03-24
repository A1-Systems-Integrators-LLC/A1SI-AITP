#!/usr/bin/env bash
# watchdog.sh — Platform watchdog: monitor all subsystems, auto-restart failed components.
#
# Usage:
#   bash scripts/watchdog.sh              # Report only
#   bash scripts/watchdog.sh --fix        # Auto-remediate issues
#   bash scripts/watchdog.sh --fix --quiet  # For cron (suppress non-error output)
#
# Designed to run every 5 minutes via cron.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV="$BACKEND_DIR/.venv"
PYTHON="$VENV/bin/python"
FT_DIR="$ROOT_DIR/freqtrade"
FT_STRATEGY_PATH="$FT_DIR/user_data/strategies"
LOG_DIR="$BACKEND_DIR/data/logs"
LOG_FILE="$LOG_DIR/watchdog.log"

# Parse arguments
FIX=false
QUIET=false
for arg in "$@"; do
    case "$arg" in
        --fix) FIX=true ;;
        --quiet) QUIET=true ;;
    esac
done

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Logging helper
log() {
    local level="$1"; shift
    local msg="$*"
    local ts
    ts="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "[$ts] [$level] $msg" >> "$LOG_FILE"
    if [ "$QUIET" = false ] || [ "$level" = "ERROR" ] || [ "$level" = "CRITICAL" ]; then
        echo "[$level] $msg"
    fi
}

# Telegram alert (best-effort, uses .env if available)
send_alert() {
    local msg="$1"
    local token="" chat_id=""
    if [ -f "$ROOT_DIR/.env" ]; then
        token=$(grep '^TELEGRAM_BOT_TOKEN=' "$ROOT_DIR/.env" 2>/dev/null | cut -d= -f2- || true)
        chat_id=$(grep '^TELEGRAM_CHAT_ID=' "$ROOT_DIR/.env" 2>/dev/null | cut -d= -f2- || true)
    fi
    if [ -n "$token" ] && [ -n "$chat_id" ]; then
        curl -sf "https://api.telegram.org/bot${token}/sendMessage" \
            -d "chat_id=${chat_id}" \
            -d "text=[WATCHDOG] ${msg}" \
            -d "parse_mode=HTML" > /dev/null 2>&1 || true
    fi
}

ISSUES=0
FIXES=0

log "INFO" "Watchdog run started (fix=$FIX)"

# ─── 1. Check Backend (Django/Daphne) ──────────────────────────
check_backend() {
    # Try Docker first, then bare-metal
    if docker compose ps --format json 2>/dev/null | grep -q '"backend"'; then
        # Docker mode
        local health
        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' \
            "$(docker compose ps -q backend 2>/dev/null)" 2>/dev/null || echo "unknown")
        if [ "$health" = "healthy" ]; then
            log "INFO" "Backend (Docker): healthy"
            return 0
        fi
        log "ERROR" "Backend (Docker): $health"
        ISSUES=$((ISSUES + 1))
        if [ "$FIX" = true ]; then
            log "INFO" "Restarting Docker backend..."
            (cd "$ROOT_DIR" && docker compose up -d backend) >> "$LOG_FILE" 2>&1
            FIXES=$((FIXES + 1))
            send_alert "Backend container restarted"
        fi
        return 1
    fi

    # Bare-metal mode: check health endpoint
    if curl -sf http://localhost:8000/api/health/ > /dev/null 2>&1; then
        log "INFO" "Backend (bare-metal): healthy"
        return 0
    fi

    log "ERROR" "Backend: not responding on :8000"
    ISSUES=$((ISSUES + 1))
    if [ "$FIX" = true ]; then
        log "INFO" "Starting backend (Daphne)..."
        cd "$BACKEND_DIR" && DJANGO_DEBUG=true nohup "$PYTHON" -m daphne -b 0.0.0.0 -p 8000 \
            config.asgi:application >> "$LOG_DIR/backend.log" 2>&1 &
        sleep 5
        if curl -sf http://localhost:8000/api/health/ > /dev/null 2>&1; then
            log "INFO" "Backend started successfully"
            FIXES=$((FIXES + 1))
            send_alert "Backend auto-started by watchdog"
        else
            log "CRITICAL" "Backend failed to start"
            send_alert "CRITICAL: Backend failed to start"
        fi
    fi
    return 1
}

# ─── 2. Check Frontend ─────────────────────────────────────────
check_frontend() {
    # Docker mode
    if docker compose ps --format json 2>/dev/null | grep -q '"frontend"'; then
        local status
        status=$(docker compose ps frontend --format '{{.Status}}' 2>/dev/null || echo "unknown")
        if echo "$status" | grep -qi "up"; then
            log "INFO" "Frontend (Docker): running"
            return 0
        fi
        log "ERROR" "Frontend (Docker): $status"
        ISSUES=$((ISSUES + 1))
        if [ "$FIX" = true ]; then
            (cd "$ROOT_DIR" && docker compose up -d frontend) >> "$LOG_FILE" 2>&1
            FIXES=$((FIXES + 1))
        fi
        return 1
    fi

    # Bare-metal: check Vite on :5173
    if curl -sf http://localhost:5173/ > /dev/null 2>&1; then
        log "INFO" "Frontend (Vite): running on :5173"
        return 0
    fi

    log "WARN" "Frontend: not responding on :5173"
    ISSUES=$((ISSUES + 1))
    if [ "$FIX" = true ]; then
        log "INFO" "Starting frontend (Vite)..."
        cd "$ROOT_DIR/frontend" && nohup npm run dev >> "$LOG_DIR/frontend.log" 2>&1 &
        FIXES=$((FIXES + 1))
    fi
    return 1
}

# ─── 3. Check Freqtrade Instances ──────────────────────────────
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

# Full 3-strategy operation (restored 2026-03-24 operational overhaul)
DEFAULT_WATCHDOG_FT="CryptoInvestorV1,BollingerMeanReversion,VolatilityBreakout"
WATCHDOG_FT_INSTANCES="${WATCHDOG_FT_INSTANCES:-$DEFAULT_WATCHDOG_FT}"

check_freqtrade() {
    local ft_user="freqtrader"
    local ft_pass="freqtrader"
    local all_ok=true

    IFS=',' read -ra FT_LIST <<< "$WATCHDOG_FT_INSTANCES"
    for strategy in "${FT_LIST[@]}"; do
        strategy=$(echo "$strategy" | xargs)  # trim whitespace
        local port="${FT_PORTS[$strategy]}"
        local config="${FT_CONFIGS[$strategy]}"

        if curl -sf "http://localhost:${port}/api/v1/ping" --user "${ft_user}:${ft_pass}" > /dev/null 2>&1; then
            log "INFO" "Freqtrade $strategy (:$port): running"
        else
            log "ERROR" "Freqtrade $strategy (:$port): not responding"
            ISSUES=$((ISSUES + 1))
            all_ok=false

            if [ "$FIX" = true ]; then
                local config_path="$FT_DIR/$config"
                if [ -f "$config_path" ]; then
                    # Check if port is in use by something else
                    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
                        log "WARN" "Port $port in use but Freqtrade not responding — skipping restart"
                        continue
                    fi
                    log "INFO" "Starting Freqtrade $strategy on :$port..."
                    cd "$ROOT_DIR" && nohup "$PYTHON" -m freqtrade trade \
                        --config "$config_path" \
                        --strategy "$strategy" \
                        --strategy-path "$FT_STRATEGY_PATH" \
                        >> "/tmp/freqtrade-${strategy}.log" 2>&1 &
                    sleep 5
                    if curl -sf "http://localhost:${port}/api/v1/ping" --user "${ft_user}:${ft_pass}" > /dev/null 2>&1; then
                        log "INFO" "Freqtrade $strategy started successfully"
                        FIXES=$((FIXES + 1))
                        send_alert "Freqtrade $strategy auto-started by watchdog"
                    else
                        log "ERROR" "Freqtrade $strategy failed to start — check /tmp/freqtrade-${strategy}.log"
                        send_alert "Freqtrade $strategy failed to start"
                    fi
                else
                    log "ERROR" "Config $config_path not found — cannot restart $strategy"
                fi
            fi
        fi
    done

    $all_ok && return 0 || return 1
}

# ─── 4. Check Risk State (via Django management command) ───────
check_risk_state() {
    # Only run if backend is up
    if ! curl -sf http://localhost:8000/api/health/ > /dev/null 2>&1; then
        log "WARN" "Skipping risk state check — backend not responding"
        return 1
    fi

    local fix_flag=""
    if [ "$FIX" = true ]; then
        fix_flag="--fix"
    fi

    local result
    result=$(cd "$BACKEND_DIR" && SCHEDULER_DISABLED=1 "$PYTHON" manage.py watchdog --json $fix_flag --portfolio-id 1 2>/dev/null || echo '{"summary":{"healthy":false}}')

    local healthy
    healthy=$(echo "$result" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(d.get('summary',{}).get('healthy',False))" 2>/dev/null || echo "False")

    if [ "$healthy" = "True" ]; then
        log "INFO" "Risk state: healthy"
        return 0
    fi

    log "ERROR" "Risk state: unhealthy"
    ISSUES=$((ISSUES + 1))

    # Log fix details if any were applied
    local fix_count
    fix_count=$(echo "$result" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('fixes',[])))" 2>/dev/null || echo "0")
    if [ "$fix_count" -gt 0 ]; then
        log "INFO" "Applied $fix_count risk state fixes"
        FIXES=$((FIXES + fix_count))
        send_alert "Risk state auto-fixed ($fix_count fixes applied)"
    fi
    return 1
}

# ─── 5. Check Scheduler Health (via detailed health endpoint) ──
check_scheduler() {
    local health_json
    health_json=$(curl -sf "http://localhost:8000/api/health/?detailed=true" 2>/dev/null || echo '{}')

    local scheduler_status
    scheduler_status=$(echo "$health_json" | "$PYTHON" -c "
import sys, json
try:
    d = json.load(sys.stdin)
    checks = d.get('checks', {})
    sched = checks.get('scheduler', {})
    print(sched.get('running', False))
except: print('unknown')
" 2>/dev/null || echo "unknown")

    if [ "$scheduler_status" = "True" ]; then
        log "INFO" "Scheduler: running"
        return 0
    fi

    log "ERROR" "Scheduler: not running (requires backend restart)"
    ISSUES=$((ISSUES + 1))
    if [ "$FIX" = true ]; then
        send_alert "Scheduler not running — backend restart may be needed"
    fi
    return 1
}

# ─── Run all checks ────────────────────────────────────────────
check_backend || true
check_frontend || true
check_freqtrade || true
check_scheduler || true
check_risk_state || true

# ─── Summary ───────────────────────────────────────────────────
if [ "$ISSUES" -eq 0 ]; then
    log "INFO" "Watchdog complete: ALL SYSTEMS OK"
else
    log "WARN" "Watchdog complete: $ISSUES issues found, $FIXES fixes applied"
    if [ "$ISSUES" -gt "$FIXES" ] && [ "$FIX" = true ]; then
        send_alert "Watchdog: $ISSUES issues, $FIXES fixed, $((ISSUES - FIXES)) remaining"
    fi
fi

# Rotate log if >10MB
if [ -f "$LOG_FILE" ] && [ "$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt 10485760 ]; then
    mv "$LOG_FILE" "${LOG_FILE}.old"
    log "INFO" "Rotated watchdog log"
fi
