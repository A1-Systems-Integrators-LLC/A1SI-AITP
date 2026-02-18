#!/bin/bash
# Phase 0: Environment Setup for E2E Pipeline
# Run this script with: sudo bash scripts/phase0_setup.sh
set -e

echo "=== Phase 0: Environment Setup ==="

# 0.1 Create NVMe swap (8GB)
echo ""
echo "--- Step 1: Creating 8GB NVMe swap file ---"
if [ -f /swapfile ]; then
    echo "Swapfile already exists, skipping"
else
    fallocate -l 8G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo "Swap created and enabled"
fi
swapon --show
free -h

# 0.3 Install Python 3.11
echo ""
echo "--- Step 2: Installing Python 3.11 ---"
if command -v python3.11 &>/dev/null; then
    echo "Python 3.11 already installed: $(python3.11 --version)"
else
    echo "Adding deadsnakes PPA..."
    add-apt-repository -y ppa:deadsnakes/ppa
    apt update
    apt install -y python3.11 python3.11-venv python3.11-dev
    echo "Python 3.11 installed: $(python3.11 --version)"
fi

# 0.4 Install TA-Lib C library
echo ""
echo "--- Step 3: Installing TA-Lib C library ---"
if ldconfig -p | grep -q libta_lib; then
    echo "TA-Lib already installed"
else
    echo "Building TA-Lib from source..."
    cd /tmp
    wget -q https://github.com/ta-lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz
    tar xzf ta-lib-0.6.4-src.tar.gz
    cd ta-lib-0.6.4
    ./configure --prefix=/usr/local
    make -j4
    make install
    ldconfig
    echo "TA-Lib installed successfully"
fi

echo ""
echo "=== Phase 0 sudo steps complete ==="
echo "Now return to Claude Code to continue with venv setup."
