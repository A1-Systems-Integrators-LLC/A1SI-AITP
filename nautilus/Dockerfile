# ════════════════════════════════════���═════════════════════════
# NautilusTrader Worker — Backtesting engine container
# Runs as a standalone worker that the Django backend calls via HTTP.
# Build context: project root (A1SI-AITP/)
# ═══════════════════════════���══════════════════════════════════

FROM python:3.12-slim AS builder

WORKDIR /project

# System deps for nautilus_trader (Cython/C++ compilation) and TA-Lib
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc g++ libc6-dev libffi-dev curl make cmake && \
    rm -rf /var/lib/apt/lists/*

# Build TA-Lib C library from vendored source
COPY backend/ta-lib-0.4.0-src.tar.gz /tmp/
RUN tar -xzf /tmp/ta-lib-0.4.0-src.tar.gz -C /tmp && \
    cd /tmp/ta-lib && \
    curl -sL -o config.guess 'https://git.savannah.gnu.org/cgit/config.git/plain/config.guess' && \
    curl -sL -o config.sub 'https://git.savannah.gnu.org/cgit/config.git/plain/config.sub' && \
    chmod +x config.guess config.sub && \
    ./configure --prefix=/usr && make && make install && \
    rm -rf /tmp/ta-lib /tmp/ta-lib-0.4.0-src.tar.gz

# Install NautilusTrader and shared dependencies
RUN pip install --no-cache-dir \
    "nautilus_trader>=1.200.0" \
    "ccxt>=4.0.0" \
    "pandas>=2.0.0" \
    "numpy>=1.24.0" \
    "pyarrow>=14.0.0" \
    "ta-lib>=0.4.28" \
    "pyyaml>=6.0" \
    "uvicorn>=0.30.0" \
    "starlette>=0.38.0" \
    "httpx>=0.27.0"


# ── Stage 2: Runtime ──
FROM python:3.12-slim

WORKDIR /project

RUN apt-get update && \
    apt-get install -y --no-install-recommends libffi8 libgomp1 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy TA-Lib shared library
COPY --from=builder /usr/lib/libta_lib* /usr/lib/
COPY --from=builder /usr/include/ta-lib/ /usr/include/ta-lib/
RUN ldconfig

# Copy installed Python packages
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy project code needed by NautilusTrader
# NOTE: data/ is mounted as a volume at runtime, not baked into the image
COPY common/ ./common/
COPY configs/ ./configs/
COPY nautilus/ ./nautilus/

RUN mkdir -p /project/nautilus/results /project/data/processed

ENV PYTHONPATH="/project:${PYTHONPATH}"

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /project appuser && \
    chown -R appuser:appuser /project
USER appuser

EXPOSE 4090

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:4090/health || exit 1

CMD ["python", "-m", "uvicorn", "nautilus.worker:app", "--host", "0.0.0.0", "--port", "4090"]
