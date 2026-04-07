# A1SI-AITP

Full-stack crypto investment platform with portfolio tracking, market analysis, automated trading, and a web dashboard.

Built for local desktop deployment (HP Intel Core i7) — async-first, Docker-ready.

## Tech Stack

- **Backend**: Python 3.12, Django 5.x, Django REST Framework, Django Channels (ASGI/Daphne), PostgreSQL 16, ccxt
- **Frontend**: TypeScript, React 19, Vite 6, TanStack React Query, Tailwind CSS v4, lightweight-charts
- **Trading**: Freqtrade (crypto), NautilusTrader (multi-asset), VectorBT (research), hftbacktest (HFT)
- **Tooling**: Makefile-driven, ruff + mypy (Python), eslint (TS), pytest + vitest

## Architecture

Multi-tier trading pipeline: VectorBT (screening) → Freqtrade (crypto trading) → NautilusTrader (multi-asset) → hftbacktest (HFT). Shared Parquet data pipeline across all tiers.

## Quick Start

```bash
make setup   # Create venv, install deps, migrate DB, create superuser, npm install
make dev     # Start backend (:8000 Daphne) + frontend (:5173 Vite)
```

## Commands

| Command                | Description                              |
|------------------------|------------------------------------------|
| `make setup`           | Install all dependencies                 |
| `make dev`             | Run backend + frontend in dev mode       |
| `make test`            | Run pytest + vitest                      |
| `make lint`            | Run ruff + eslint                        |
| `make build`           | Production build (frontend + static)     |
| `make docker-up`       | Start Docker containers                  |
| `make docker-down`     | Stop Docker containers                   |
| `make migrate`         | Run Django migrations                    |
| `make test-security`   | Run auth + security tests                |
| `make pilot-preflight` | Pre-flight checks for live trading       |
| `make pilot-status`    | Daily pilot trading status report        |
| `make backup`          | PostgreSQL backup (keeps 7 daily)        |
| `make clean`           | Remove build artifacts and caches        |

## Project Structure

```
backend/    Python Django REST backend
frontend/   React TypeScript frontend
freqtrade/  Freqtrade strategies and config
nautilus/   NautilusTrader multi-asset engine
research/   VectorBT screening scripts
common/     Shared data pipeline, indicators, risk management
configs/    Platform and Docker configuration
scripts/    Dev, ops, and setup scripts
docs/       Runbook, troubleshooting, monitoring guides
```
