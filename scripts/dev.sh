#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV="$BACKEND_DIR/.venv"

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "Starting backend (Daphne) on :8000..."
cd "$BACKEND_DIR" && DJANGO_DEBUG=true "$VENV/bin/python" -m daphne -b 0.0.0.0 -p 8000 config.asgi:application &
BACKEND_PID=$!

echo "Starting frontend on :5173..."
cd "$FRONTEND_DIR" && npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Admin:    http://localhost:8000/admin/"
echo ""
echo "Press Ctrl+C to stop."

wait
