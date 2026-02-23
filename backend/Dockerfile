FROM python:3.10-slim

# Build context is project root (A1SI-AITP/), not backend/
WORKDIR /project

# System deps for cryptography and argon2
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Copy platform modules needed by backend (common, configs)
COPY common/ ./common/
COPY configs/ ./configs/

# Copy trading framework files needed by backtest/screening services
COPY research/scripts/ ./research/scripts/
COPY nautilus/ ./nautilus/
COPY freqtrade/user_data/strategies/ ./freqtrade/user_data/strategies/
COPY freqtrade/config.json.example ./freqtrade/config.json

# Copy backend and install deps
COPY backend/ ./backend/
WORKDIR /project/backend
RUN pip install --no-cache-dir -e .

RUN mkdir -p /project/backend/data/logs /project/data/processed

COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create non-root user and set ownership
RUN groupadd -r appuser && useradd -r -g appuser -d /project appuser && \
    chown -R appuser:appuser /project
USER appuser

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
