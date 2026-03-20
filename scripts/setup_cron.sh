#!/usr/bin/env bash
# setup_cron.sh — Install crontab entries for platform automation.
#
# Installs:
#   @reboot     — Full platform startup
#   */5 * * * * — Watchdog (check all subsystems, auto-fix)
#   0 0 * * *   — Daily risk P&L reset (backup to scheduler)
#
# Idempotent: removes old entries before adding new ones.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PYTHON="$BACKEND_DIR/.venv/bin/python"
MARKER="# A1SI-AITP"

echo "Setting up cron jobs for A1SI-AITP platform..."

# Verify prerequisites
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: Python venv not found at $PYTHON"
    echo "Run 'make setup' first."
    exit 1
fi

# Remove old entries and add new ones
(
    # Keep existing non-A1SI entries
    crontab -l 2>/dev/null | grep -v "$MARKER" || true

    # Add our entries
    cat <<EOF
@reboot cd $ROOT_DIR && bash scripts/start.sh >> $BACKEND_DIR/data/logs/startup.log 2>&1 $MARKER
*/5 * * * * cd $ROOT_DIR && bash scripts/watchdog.sh --fix --quiet >> $BACKEND_DIR/data/logs/watchdog-cron.log 2>&1 $MARKER
0 0 * * * cd $BACKEND_DIR && SCHEDULER_DISABLED=1 $PYTHON manage.py watchdog --reset-daily --json >> $BACKEND_DIR/data/logs/daily-reset.log 2>&1 $MARKER
EOF
) | crontab -

echo ""
echo "Cron jobs installed:"
crontab -l | grep "$MARKER" | while read -r line; do
    echo "  $line"
done

echo ""
echo "Log locations:"
echo "  Startup:     $BACKEND_DIR/data/logs/startup.log"
echo "  Watchdog:    $BACKEND_DIR/data/logs/watchdog.log"
echo "  Daily reset: $BACKEND_DIR/data/logs/daily-reset.log"
