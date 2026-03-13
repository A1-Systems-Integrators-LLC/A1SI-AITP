FROM python:3.12-slim

# Build context is project root (A1SI-AITP/), not backend/
WORKDIR /project

# System deps for cryptography and argon2
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev libffi-dev curl make && \
    rm -rf /var/lib/apt/lists/*

# Build TA-Lib C library from vendored source
COPY backend/ta-lib-0.4.0-src.tar.gz /tmp/
RUN tar -xzf /tmp/ta-lib-0.4.0-src.tar.gz -C /tmp && \
    cd /tmp/ta-lib && ./configure --prefix=/usr && make && make install && \
    rm -rf /tmp/ta-lib /tmp/ta-lib-0.4.0-src.tar.gz

# Copy platform modules needed by backend (common, configs)
COPY common/ ./common/
COPY configs/ ./configs/

# Copy trading framework files needed by backtest/screening services
COPY research/scripts/ ./research/scripts/
COPY nautilus/ ./nautilus/
COPY freqtrade/user_data/strategies/ ./freqtrade/user_data/strategies/
COPY freqtrade/config.json.example ./freqtrade/config.json
COPY hftbacktest/ ./hftbacktest/

# Copy backend and install deps (analysis extras add pandas/numpy/scipy/pyarrow)
COPY backend/ ./backend/
WORKDIR /project/backend
RUN pip install --no-cache-dir -e ".[analysis,ml]" ta-lib vectorbt

RUN mkdir -p /project/backend/data/logs /project/data/processed /project/models

# Ensure common/, research/, nautilus/, etc. are importable from backend
ENV PYTHONPATH="/project:${PYTHONPATH}"

COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create non-root user and set ownership
RUN groupadd -r appuser && useradd -r -g appuser -d /project appuser && \
    chown -R appuser:appuser /project
USER appuser

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
