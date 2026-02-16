FROM python:3.10-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Copy backend package and install
COPY backend/pyproject.toml backend/
COPY backend/config/ backend/config/
COPY backend/core/ backend/core/
COPY backend/portfolio/ backend/portfolio/
COPY backend/trading/ backend/trading/
COPY backend/market/ backend/market/
COPY backend/risk/ backend/risk/
COPY backend/analysis/ backend/analysis/
COPY backend/manage.py backend/
RUN pip install --no-cache-dir "./backend[analysis]" scipy

# Copy platform modules (common.*, research.*, etc.)
COPY common/ common/
COPY configs/ configs/
COPY freqtrade/ freqtrade/
COPY run.py ./

# Ensure common modules are importable
ENV PYTHONPATH=/app

# Create data directory and set ownership
RUN mkdir -p backend/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/')" || exit 1

CMD ["python", "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "--application-close-timeout", "60", "--root-path", "/app/backend", "config.asgi:application"]
