# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A1SI-AITP — Full-stack crypto investment platform with portfolio tracking, market analysis, automated trading, and a web dashboard. Integrates multiple trading frameworks in a multi-tier architecture.

## Tech Stack

- **Backend**: Python 3.10, Django 5.x, Django REST Framework, Django Channels (ASGI/Daphne), SQLite, ccxt
- **Frontend**: TypeScript, React 19, Vite 6, TanStack React Query, Tailwind CSS v4, lightweight-charts
- **Tooling**: Makefile-driven, ruff + mypy (Python), eslint (TS), pytest + vitest
- **Trading Frameworks**: Freqtrade (crypto engine), NautilusTrader (multi-asset), VectorBT (research), hftbacktest (HFT)

## Architecture

- **Monorepo**: `backend/` + `frontend/` (web app) alongside platform modules (`common/`, `research/`, `nautilus/`, `freqtrade/`)
- **Database**: SQLite with WAL mode — single-user, low-memory target (Jetson 8GB RAM)
- **Auth**: Django session-based authentication, CSRF protection, DRF SessionAuthentication + IsAuthenticated defaults
- **ASGI**: Django Channels + Daphne server, async views for ccxt exchange calls
- **Django apps**: core (auth, health, platform), portfolio, trading, market, risk, analysis
- **Service layer**: Exchange service wraps ccxt; risk/analysis services in app `services/` dirs
- **Frontend served by nginx in prod** (Docker), Vite dev proxy in development
- **Multi-tier trading**: VectorBT (screening) → Freqtrade (crypto trading) → NautilusTrader (multi-asset) → hftbacktest (HFT)
- **Shared data pipeline**: Parquet format for OHLCV data shared across all framework tiers

## Commands

```bash
make setup          # Create venv, install deps, migrate DB, create superuser, npm install
make dev            # Backend :8000 (Daphne) + frontend :5173 (Vite proxies API)
make test           # pytest + vitest
make lint           # ruff check + eslint
make build          # Production build
make migrate        # makemigrations + migrate
make test-security  # Run auth + security tests only
make harden         # Set file permissions (600 .env, 700 data dirs)
make audit          # pip-audit + npm audit
make certs          # Generate self-signed TLS certs
make backup         # SQLite backup (keeps 7 daily)

# Platform orchestrator
python run.py status                  # Show platform status
python run.py validate                # Validate framework installs
python run.py data generate-sample    # Generate synthetic test data
python run.py data download           # Download real market data
python run.py research screen         # Run VectorBT strategy screens
python run.py freqtrade backtest      # Run Freqtrade backtests
python run.py nautilus test           # Test NautilusTrader engine
```

## Key Paths

- Backend Django apps: `backend/core/`, `backend/portfolio/`, `backend/trading/`, `backend/market/`, `backend/risk/`, `backend/analysis/`
- Django settings: `backend/config/settings.py`
- Django URLs: `backend/config/urls.py`
- Backend tests: `backend/tests/`
- Frontend source: `frontend/src/`
- Database files: `backend/data/` (gitignored)
- Django migrations: `backend/<app>/migrations/`
- Shared data pipeline: `common/data_pipeline/pipeline.py`
- Technical indicators: `common/indicators/technical.py`
- Risk management: `common/risk/risk_manager.py`
- VectorBT screener: `research/scripts/vbt_screener.py`
- NautilusTrader runner: `nautilus/nautilus_runner.py`
- Freqtrade strategies: `freqtrade/user_data/strategies/`
- Freqtrade config: `freqtrade/config.json`
- Platform config: `configs/platform_config.yaml`
- Market data: `data/processed/` (Parquet, gitignored)
- Platform orchestrator: `run.py`

## Memory

After completing any task that changes code, tests, dependencies, or architecture, **always update the memory file** at `~/.claude/projects/-home-rredmer-Dev-Portfolio-A1SI-AITP/memory/MEMORY.md` (and `next-steps.md` if roadmap items changed). Keep test counts, implementation status, and dependency notes current.

## Conventions

- Python: ruff formatting, type hints everywhere, async def for IO
- TypeScript: strict mode, named exports, functional components
- API routes: `/api/` prefix, RESTful, all require authentication (except health/login)
- Models: Django ORM with `models.Field` style
- Serializers: DRF ModelSerializer / Serializer
- Views: DRF APIView classes
- Platform imports use `common.`, `research.`, `nautilus.` prefixes (PROJECT_ROOT on sys.path)
- Default credentials (dev only): admin/admin
