#!/usr/bin/env bash
# setup_cron.sh — Install crontab entries for Docker-based platform automation.
#
# All services run in Docker containers. Cron jobs manage container lifecycle
# and run management commands via docker compose exec.
#
# Installs:
#   @reboot     — Start all AITP containers
#   */5 * * * * — Watchdog (check container health, restart if needed)
#   0 0 * * *   — Daily risk P&L reset
#
# Idempotent: removes old entries before adding new ones.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MARKER="# A1SI-AITP"
LOG_DIR="$ROOT_DIR/backend/data/logs"

echo "Setting up cron jobs for A1SI-AITP platform (Docker mode)..."

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Build Doppler prefix if available
DOPPLER_CMD=""
if command -v doppler >/dev/null 2>&1; then
    DOPPLER_CMD="doppler run --project aitp --config dev --"
fi

# Remove old entries and add new ones
(
    # Keep existing non-A1SI entries
    crontab -l 2>/dev/null | grep -v "$MARKER" || true

    # Add container-based entries
    cat <<EOF
@reboot cd $ROOT_DIR && bash scripts/start.sh >> $LOG_DIR/startup.log 2>&1 $MARKER
*/5 * * * * cd $ROOT_DIR && $DOPPLER_CMD docker compose exec -T backend python manage.py watchdog --fix --json >> $LOG_DIR/watchdog-cron.log 2>&1 $MARKER
0 0 * * * cd $ROOT_DIR && $DOPPLER_CMD docker compose exec -T backend python manage.py watchdog --reset-daily --json >> $LOG_DIR/daily-reset.log 2>&1 $MARKER
EOF
) | crontab -

echo ""
echo "Cron jobs installed:"
crontab -l | grep "$MARKER" | while read -r line; do
    echo "  $line"
done

echo ""
echo "Log locations:"
echo "  Startup:     $LOG_DIR/startup.log"
echo "  Watchdog:    $LOG_DIR/watchdog-cron.log"
echo "  Daily reset: $LOG_DIR/daily-reset.log"
echo ""
echo "All cron jobs run via Docker containers — no native processes."
