# ══════════════════════════════════════════════════════════════
# A1SI-AITP Backend — Multi-stage Docker build
# Build context: project root (A1SI-AITP/), not backend/
# ══════════════════════════════════════════════════════════════

# ── Stage 1: Build (compile TA-Lib C library + install Python packages) ──
FROM python:3.12-slim AS builder

WORKDIR /project

# System deps for cryptography, argon2, and TA-Lib build
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libc6-dev libffi-dev curl make && \
    rm -rf /var/lib/apt/lists/*

# Build TA-Lib C library from vendored source
# The vendored 0.4.0 config.guess doesn't know aarch64 (ARM64).
# Download fresh config.guess/config.sub from GNU to support Apple Silicon.
COPY backend/ta-lib-0.4.0-src.tar.gz /tmp/
RUN tar -xzf /tmp/ta-lib-0.4.0-src.tar.gz -C /tmp && \
    cd /tmp/ta-lib && \
    curl -sL -o config.guess 'https://git.savannah.gnu.org/cgit/config.git/plain/config.guess' && \
    curl -sL -o config.sub 'https://git.savannah.gnu.org/cgit/config.git/plain/config.sub' && \
    chmod +x config.guess config.sub && \
    ./configure --prefix=/usr && make && make install && \
    rm -rf /tmp/ta-lib /tmp/ta-lib-0.4.0-src.tar.gz

# Copy platform modules needed by backend (common, configs)
COPY common/ ./common/
COPY configs/ ./configs/

# Copy trading framework files needed by backtest/screening services
COPY research/scripts/ ./research/scripts/
COPY nautilus/ ./nautilus/
COPY freqtrade/user_data/strategies/ ./freqtrade/user_data/strategies/
COPY freqtrade/config.json.example ./freqtrade/config.json
COPY freqtrade/config_*.json ./freqtrade/
COPY hftbacktest/ ./hftbacktest/

# Copy platform orchestrator (needed by tests and CLI)
COPY run.py ./run.py

# Copy backend and install all deps
# - analysis: pandas, numpy, scipy, pyarrow, yfinance
# - ml: lightgbm, scikit-learn, xgboost, optuna
# - trading: freqtrade, ta-lib
# - sentiment: vaderSentiment
COPY backend/ ./backend/
WORKDIR /project/backend
RUN pip install --no-cache-dir -e ".[dev,analysis,ml,trading,sentiment,postgres]" vectorbt


# ── Stage 2: Runtime (minimal image without build tools) ──
FROM python:3.12-slim

WORKDIR /project

# Runtime-only system deps: libffi for cryptography, libgomp for lightgbm, TA-Lib shared library
RUN apt-get update && \
    apt-get install -y --no-install-recommends libffi8 libgomp1 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy TA-Lib shared library from builder
COPY --from=builder /usr/lib/libta_lib* /usr/lib/
COPY --from=builder /usr/include/ta-lib/ /usr/include/ta-lib/
RUN ldconfig

# Copy installed Python packages (entire site-packages + bin scripts)
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy project files from builder
COPY --from=builder /project/ /project/

WORKDIR /project/backend

RUN mkdir -p /project/backend/data/logs /project/data/processed /project/models

# Ensure common/, research/, nautilus/, freqtrade strategies are importable
ENV PYTHONPATH="/project:/project/freqtrade/user_data/strategies:${PYTHONPATH}"

COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create non-root user and set ownership
RUN groupadd -r appuser && useradd -r -g appuser -d /project appuser && \
    chown -R appuser:appuser /project
USER appuser

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
