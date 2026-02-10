#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV="$BACKEND_DIR/.venv"

echo "=== crypto-investor setup ==="
echo ""

# Backend
echo "→ Setting up Python backend..."
if [ ! -d "$VENV" ]; then
    python3 -m venv --without-pip "$VENV"
    curl -sS https://bootstrap.pypa.io/get-pip.py | "$VENV/bin/python"
fi
"$VENV/bin/pip" install -e "$BACKEND_DIR[dev]" --quiet
mkdir -p "$BACKEND_DIR/data"
echo "  ✓ Backend ready"

# Frontend
echo "→ Setting up Node frontend..."
cd "$FRONTEND_DIR" && npm install --silent
echo "  ✓ Frontend ready"

# Env file
if [ ! -f "$ROOT_DIR/.env" ]; then
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    echo "  ✓ Created .env from .env.example"
fi

echo ""
echo "=== Setup complete ==="
echo "Run 'make dev' to start developing."
