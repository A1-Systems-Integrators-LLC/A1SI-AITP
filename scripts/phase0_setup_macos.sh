#!/usr/bin/env bash
# phase0_setup_macos.sh — macOS Apple Silicon prerequisites for A1SI-AITP
#
# Run once on a fresh MacBook Pro M2 before `make setup`.
# Requires: Homebrew (https://brew.sh)
set -euo pipefail

echo "╔══════════════════════════════════════════════════════╗"
echo "║   A1SI-AITP — macOS Apple Silicon Setup              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Check for Homebrew ─────────────────────────────────
if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add to PATH for this session
    eval "$(/opt/homebrew/bin/brew shellenv)"
else
    echo "✓ Homebrew found: $(brew --prefix)"
fi

# ── 2. Install system dependencies ────────────────────────
echo ""
echo "→ Installing system dependencies..."
brew install python@3.12 ta-lib node@20 2>/dev/null || true

# Ensure python3.12 and node@20 are linked
brew link --overwrite python@3.12 2>/dev/null || true
brew link --overwrite node@20 2>/dev/null || true

# ── 3. Verify installations ───────────────────────────────
echo ""
echo "→ Verifying installations..."

echo -n "  Python: "
python3.12 --version 2>/dev/null || python3 --version

echo -n "  Node:   "
node --version

echo -n "  npm:    "
npm --version

echo -n "  TA-Lib: "
if [ -f "$(brew --prefix)/lib/libta_lib.dylib" ]; then
    echo "installed ($(brew --prefix)/lib/libta_lib.dylib)"
else
    echo "NOT FOUND — pip install ta-lib will fail"
    exit 1
fi

# ── 4. Optional: Docker Desktop ───────────────────────────
echo ""
if command -v docker >/dev/null 2>&1; then
    echo "✓ Docker found: $(docker --version)"
    echo "  Note: Docker Desktop for Mac uses ARM64 images automatically."
else
    echo "⚠ Docker not found."
    echo "  Install Docker Desktop for Mac from: https://www.docker.com/products/docker-desktop/"
    echo "  Docker is required for production builds and monitoring stack."
fi

# ── 5. Summary ────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Prerequisites installed. Next steps:"
echo ""
echo "    cd $(dirname "$0")/.."
echo "    make setup          # Create venv, install deps, init DB"
echo "    make dev            # Start backend + frontend"
echo ""
echo "  Note: TA-Lib C library is installed via Homebrew."
echo "  The Python ta-lib wrapper will be installed by pip"
echo "  during 'make setup'."
echo "════════════════════════════════════════════════════════"
